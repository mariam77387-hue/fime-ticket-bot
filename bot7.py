# -*- coding: utf-8 -*-
"""
bot7.py - نظام إدارة وحماية موحّد على هيئة Cog.
يُحمَّل من bot.py عبر:  await bot.load_extension("bot7")
"""

import asyncio
import copy
import json
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional

import discord
from discord.ext import commands

DATA_FILE = Path("bot7_data.json")
PREFIX = "!"  # لازم يكون نفس البريفكس في bot.py
COG_NAME = "Moderation"
NO_MENTIONS = discord.AllowedMentions.none()
MAX_TIMEOUT = 28 * 24 * 3600
MASS_KICK_REASON = "طرد جماعي بأمر مالك السيرفر"
DANGEROUS_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "ban_members", "kick_members",
)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"}
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
REPEAT_RE = re.compile(r"(.)\1{24,}", re.DOTALL)

DEFAULTS = {
    "protection": False,
    "trusted_bot_ids": [],
    "admin_role_id": None,
    "ban_role_id": None,
    "kick_role_id": None,
    "log_channel_id": None,
    "invite_filter": True,
    "banned_words": [],
    "spam": {"limit": 6, "window": 8, "timeout_min": 10},
    "mentions": {"max": 5, "timeout_min": 5},
    "media": {"limit": 4, "window": 10, "timeout_min": 5},
    "escalation": {"warnings": 3, "timeout_min": 60},
    "shortcuts": {
        "ban": ["حظر"], "kick": ["طرد"], "clear": ["مسح"],
        "warn": ["تحذير"], "timeout": ["تايم_اوت"],
    },
    "warnings": {},
}

SHORTCUT_TYPES = {
    "حظر": "ban", "طرد": "kick", "مسح": "clear",
    "تحذير": "warn", "تايم_اوت": "timeout",
}
SHORTCUT_LEVEL = {"ban": "ban", "kick": "kick", "clear": "manage", "warn": "manage", "timeout": "manage"}
ROLE_SLOTS = {"ادارة": "admin_role_id", "حظر": "ban_role_id", "طرد": "kick_role_id"}
LEVEL_ROLE = {"manage": "admin_role_id", "ban": "ban_role_id", "kick": "kick_role_id"}
LEVEL_MSG = {
    "owner": "هذا الأمر لمالك السيرفر فقط.",
    "config": "هذا الأمر لمالك السيرفر أو من يملك Administrator.",
    "manage": "ما عندك رتبة الإدارة المسموح لها بهذا الأمر.",
    "ban": "ما عندك رتبة الحظر المسموح لها بهذا الأمر.",
    "kick": "ما عندك رتبة الطرد المسموح لها بهذا الأمر.",
}
UNITS = {
    "s": 1, "ث": 1, "ثانية": 1,
    "m": 60, "د": 60, "دقيقة": 60,
    "h": 3600, "س": 3600, "ساعة": 3600,
    "d": 86400, "ي": 86400, "يوم": 86400,
}


# ============================================================
# أدوات مساعدة عامة
# ============================================================

def norm(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def clean_reason(text: str) -> str:
    text = text.strip()
    return text[:450] if text else "بدون سبب"


def has_role(member: discord.Member, role_id) -> bool:
    return bool(role_id) and any(role.id == int(role_id) for role in member.roles)


def bot_has(guild: discord.Guild, perm: str) -> bool:
    me = guild.me
    return bool(me and getattr(me.guild_permissions, perm, False))


def can_moderate(guild: discord.Guild, target: discord.Member) -> tuple[bool, str]:
    me = guild.me
    if me is None:
        return False, "ما قدرت أحدد رتبة البوت."
    if target.id == guild.owner_id:
        return False, "ما أقدر أعاقب مالك السيرفر."
    if target.id == me.id:
        return False, "ما أقدر أعاقب نفسي."
    if target.top_role >= me.top_role:
        return False, "رتبة العضو أعلى أو مساوية لرتبة البوت. ارفع رتبة البوت."
    return True, ""


def parse_duration(token: str) -> Optional[int]:
    token = token.strip().lower()
    if token.isdigit():
        minutes = int(token)
        return minutes * 60 if minutes > 0 else None
    match = re.fullmatch(r"(\d+)\s*(\S+)", token)
    if not match:
        return None
    unit = UNITS.get(match.group(2))
    number = int(match.group(1))
    if unit is None or number <= 0:
        return None
    seconds = number * unit
    return seconds if seconds <= MAX_TIMEOUT else None


def duration_text(seconds: int) -> str:
    for size, name in ((86400, "يوم"), (3600, "ساعة"), (60, "دقيقة")):
        if seconds % size == 0:
            return f"{seconds // size} {name}"
    return f"{seconds} ثانية"


def mention_count(message: discord.Message) -> int:
    count = len(message.mentions) + len(message.role_mentions)
    return count + (1 if message.mention_everyone else 0)


def has_media(message: discord.Message) -> bool:
    if message.stickers:
        return True
    for attachment in message.attachments:
        if (attachment.content_type or "").startswith("image/"):
            return True
        if Path(attachment.filename).suffix.lower() in IMAGE_EXT:
            return True
    return False


async def delete_quietly(message: Optional[discord.Message]) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except discord.HTTPException:
        pass


async def edit_quietly(message: Optional[discord.Message], content: str) -> None:
    if message is None:
        return
    try:
        await message.edit(content=content, embed=None, view=None)
    except discord.HTTPException:
        pass


async def resolve_member(guild: discord.Guild, token: str) -> Optional[discord.Member]:
    token = token.strip()
    mention = re.fullmatch(r"<@!?(\d+)>", token)
    if mention:
        user_id = int(mention.group(1))
    elif token.isdigit():
        user_id = int(token)
    else:
        user_id = None

    if user_id is not None:
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.HTTPException:
                return None
        return member

    name = norm(token.lstrip("@"))
    return next((m for m in guild.members if name in {norm(m.display_name), norm(m.name)}), None)


def resolve_role(guild: discord.Guild, token: str) -> Optional[discord.Role]:
    mention = re.fullmatch(r"<@&(\d+)>", token.strip())
    if mention:
        return guild.get_role(int(mention.group(1)))
    if token.strip().isdigit():
        return guild.get_role(int(token.strip()))
    name = norm(token)
    return next((r for r in guild.roles if norm(r.name) == name), None)


def plan_mass_kick(guild: discord.Guild) -> tuple[list[discord.Member], int, int]:
    """يرجع (الأهداف، عدد البوتات المستثناة، عدد الأعضاء الأعلى من البوت)."""
    me = guild.me
    if me is None:
        return [], 0, 0
    targets, bots, locked = [], 0, 0
    for member in guild.members:
        if member.bot:
            bots += 1
            continue
        if member.id in (guild.owner_id, me.id):
            continue
        if member.top_role >= me.top_role:
            locked += 1
            continue
        targets.append(member)
    return targets, bots, locked


# ============================================================
# ConfirmView: زرين (تأكيد / إلغاء)
# ============================================================

class ConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "Moderation",
        author: discord.Member,
        owner_only: bool,
        label: str,
        style: discord.ButtonStyle,
        handler: Callable[[discord.Interaction], Awaitable[None]],
    ):
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author.id
        self.owner_only = owner_only
        self.handler = handler
        self.finished = False
        self.message: Optional[discord.Message] = None

        yes = discord.ui.Button(label=label, style=style, emoji="✅")
        no = discord.ui.Button(label="إلغاء", style=discord.ButtonStyle.secondary, emoji="✖️")
        yes.callback = self._yes
        no.callback = self._no
        self.add_item(yes)
        self.add_item(no)

    async def _allowed(self, interaction: discord.Interaction) -> bool:
        member, guild = interaction.user, interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            return False
        if member.id != self.author_id:
            await interaction.response.send_message("هذا التأكيد لصاحب الأمر فقط.", ephemeral=True)
            return False
        level = "owner" if self.owner_only else "config"
        if not self.cog.has_level(member, guild, level):
            await interaction.response.send_message("ما عندك صلاحية لهذا التأكيد.", ephemeral=True)
            return False
        return True

    async def _yes(self, interaction: discord.Interaction) -> None:
        if self.finished or not await self._allowed(interaction):
            return
        self.finished = True
        self.stop()
        await self.handler(interaction)

    async def _no(self, interaction: discord.Interaction) -> None:
        if self.finished or not await self._allowed(interaction):
            return
        self.finished = True
        self.stop()
        await interaction.response.edit_message(content="تم الإلغاء. لم يتغير شيء.", embed=None, view=None)

    async def on_timeout(self) -> None:
        if self.finished or self.message is None:
            return
        await edit_quietly(self.message, "انتهت مهلة التأكيد، لم يحدث شيء.")


# ============================================================
# Cog الرئيسي
# ============================================================

def requires(level: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("هذا الأمر داخل السيرفر فقط.")
        cog = ctx.bot.get_cog(COG_NAME)
        if cog is None or not cog.has_level(ctx.author, ctx.guild, level):
            raise commands.CheckFailure(LEVEL_MSG[level])
        return True
    return commands.check(predicate)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: dict = self._load()
        self.db_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.msg_history: dict = defaultdict(lambda: deque(maxlen=40))
        self.join_history: dict = defaultdict(lambda: deque(maxlen=200))
        self.raid_until: dict[int, float] = {}
        self.destructive: dict = defaultdict(lambda: deque(maxlen=20))
        self.mass_kick_running: set[int] = set()

    # ---------------- قاعدة البيانات ----------------

    @staticmethod
    def _load() -> dict:
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self) -> None:
        tmp = DATA_FILE.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.db, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(DATA_FILE)
        except OSError as exc:
            print(f"[BOT7 DB ERROR] {exc}")

    async def persist(self) -> None:
        async with self.db_lock:
            await asyncio.to_thread(self._write)

    def cfg(self, guild_id: int) -> dict:
        cfg = self.db.setdefault(str(guild_id), {})
        for key, default in DEFAULTS.items():
            if isinstance(default, dict):
                section = cfg.get(key)
                if not isinstance(section, dict):
                    section = cfg[key] = {}
                for sub, value in default.items():
                    section.setdefault(sub, copy.deepcopy(value))
            else:
                cfg.setdefault(key, copy.deepcopy(default))
        return cfg

    def spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # ---------------- الصلاحيات ----------------

    def has_level(self, member: discord.Member, guild: discord.Guild, level: str) -> bool:
        if member.id == guild.owner_id:
            return True
        if level == "owner":
            return False
        if member.guild_permissions.administrator:
            return True
        if level == "config":
            return False
        return has_role(member, self.cfg(guild.id).get(LEVEL_ROLE[level]))

    def is_privileged(self, member: discord.Member, guild: discord.Guild) -> bool:
        return any(self.has_level(member, guild, lvl) for lvl in ("manage", "ban", "kick"))

    # ---------------- اللوق ----------------

    async def log(self, guild, title, target, moderator, reason, extra=None) -> None:
        channel_id = self.cfg(guild.id).get("log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title=f"🛡️ {title}",
            description=reason[:3500],
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        if target is not None:
            embed.add_field(name="العضو", value=f"{target.mention} (`{target.id}`)", inline=False)
        if moderator is not None:
            embed.add_field(name="بواسطة", value=f"{moderator.mention} (`{moderator.id}`)", inline=False)
        if extra:
            embed.add_field(name="تفاصيل", value=str(extra)[:1000], inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    # ---------------- العمليات المشتركة ----------------

    async def apply_timeout(self, member: discord.Member, seconds: int, reason: str) -> tuple[bool, str]:
        guild = member.guild
        if not 1 <= seconds <= MAX_TIMEOUT:
            return False, "المدة لازم تكون بين ثانية و28 يوم."
        if not bot_has(guild, "moderate_members"):
            return False, "البوت يحتاج صلاحية Moderate Members."
        ok, error = can_moderate(guild, member)
        if not ok:
            return False, error
        try:
            await member.timeout(timedelta(seconds=seconds), reason=reason[:500])
        except discord.HTTPException as exc:
            return False, f"رفض Discord العملية: {exc}"
        return True, ""

    async def op_ban(self, guild, moderator, target, reason) -> tuple[bool, str]:
        if not bot_has(guild, "ban_members"):
            return False, "البوت يحتاج صلاحية Ban Members."
        ok, error = can_moderate(guild, target)
        if not ok:
            return False, error
        try:
            await target.ban(reason=reason, delete_message_seconds=0)
        except discord.HTTPException as exc:
            return False, f"فشل الحظر: {exc}"
        await self.log(guild, "Ban", target, moderator, reason)
        return True, f"تم حظر {target.mention}."

    async def op_kick(self, guild, moderator, target, reason) -> tuple[bool, str]:
        if not bot_has(guild, "kick_members"):
            return False, "البوت يحتاج صلاحية Kick Members."
        ok, error = can_moderate(guild, target)
        if not ok:
            return False, error
        try:
            await target.kick(reason=reason)
        except discord.HTTPException as exc:
            return False, f"فشل الطرد: {exc}"
        await self.log(guild, "Kick", target, moderator, reason)
        return True, f"تم طرد {target.mention}."

    async def op_timeout(self, guild, moderator, target, seconds, reason) -> tuple[bool, str]:
        ok, error = await self.apply_timeout(target, seconds, reason)
        if not ok:
            return False, error
        await self.log(guild, "Timeout", target, moderator, reason, f"المدة: {duration_text(seconds)}")
        return True, f"تم إعطاء {target.mention} تايم اوت لمدة **{duration_text(seconds)}**."

    async def op_untimeout(self, guild, moderator, target) -> tuple[bool, str]:
        if not bot_has(guild, "moderate_members"):
            return False, "البوت يحتاج صلاحية Moderate Members."
        ok, error = can_moderate(guild, target)
        if not ok:
            return False, error
        try:
            await target.timeout(None, reason=f"إلغاء التايم اوت بواسطة {moderator}")
        except discord.HTTPException as exc:
            return False, f"فشل الإلغاء: {exc}"
        await self.log(guild, "Remove Timeout", target, moderator, "إلغاء التايم اوت")
        return True, f"تم إلغاء التايم اوت عن {target.mention}."

    async def op_warn(self, guild, moderator, target, reason) -> tuple[bool, str]:
        cfg = self.cfg(guild.id)
        items = cfg["warnings"].setdefault(str(target.id), [])
        items.append({
            "reason": reason,
            "moderator_id": moderator.id,
            "timestamp": discord.utils.utcnow().isoformat(),
        })
        await self.persist()
        count = len(items)
        extra = f"إجمالي التحذيرات: {count}"
        text = f"⚠️ تم تحذير {target.mention}. عدد تحذيراته: **{count}**."

        esc = cfg["escalation"]
        if count >= esc["warnings"]:
            minutes = max(1, int(esc["timeout_min"]))
            ok, _ = await self.apply_timeout(target, minutes * 60, f"تصعيد تلقائي: {count} تحذيرات")
            if ok:
                extra += f" | تايم اوت تلقائي {duration_text(minutes * 60)}"
                text += f" تم إعطاؤه تايم اوت **{duration_text(minutes * 60)}** بسبب التصعيد."

        await self.log(guild, "Warning", target, moderator, reason, extra)
        return True, text

    async def op_clear(self, guild, channel, moderator, amount, before) -> tuple[bool, str]:
        if not bot_has(guild, "manage_messages"):
            return False, "البوت يحتاج صلاحية Manage Messages."
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False, "لا يمكن المسح في هذا النوع من الرومات."
        try:
            deleted = await channel.purge(limit=amount, before=before)
        except discord.HTTPException as exc:
            return False, f"تعذر المسح: {exc}"
        await self.log(guild, "Clear Messages", None, moderator, f"مسح {len(deleted)} رسالة من {channel.mention}")
        return True, f"تم مسح **{len(deleted)}** رسالة."

    async def op_lock(self, guild, channel: discord.TextChannel, moderator, locked: bool) -> tuple[bool, str]:
        if not bot_has(guild, "manage_channels"):
            return False, "البوت يحتاج صلاحية Manage Channels."
        overwrite = channel.overwrites_for(guild.default_role)
        overwrite.send_messages = False if locked else None
        try:
            await channel.set_permissions(
                guild.default_role, overwrite=overwrite,
                reason=f"{'قفل' if locked else 'فتح'} الروم بواسطة {moderator}",
            )
        except discord.HTTPException as exc:
            return False, f"فشل التعديل: {exc}"
        title = "Channel Locked" if locked else "Channel Unlocked"
        await self.log(guild, title, None, moderator, f"{channel.mention}")
        return True, ("🔒 تم قفل الروم." if locked else "🔓 تم فتح الروم.")

    async def op_slowmode(self, guild, channel, moderator, seconds: int) -> tuple[bool, str]:
        if not bot_has(guild, "manage_channels"):
            return False, "البوت يحتاج صلاحية Manage Channels."
        if not isinstance(channel, discord.TextChannel):
            return False, "البطء يشتغل على الرومات النصية فقط."
        try:
            await channel.edit(slowmode_delay=seconds, reason=f"بواسطة {moderator}")
        except discord.HTTPException as exc:
            return False, f"فشل التعديل: {exc}"
        await self.log(guild, "Slowmode", None, moderator, f"{channel.mention}: {seconds} ثانية")
        return True, ("تم إيقاف البطء." if seconds == 0 else f"تم ضبط البطء على **{seconds}** ثانية.")

    # ---------------- الحماية التلقائية ----------------

    async def punish(self, message: discord.Message, minutes: int, reason: str, title: str) -> bool:
        guild, author = message.guild, message.author
        self.msg_history[(guild.id, author.id)].clear()
        await delete_quietly(message)
        ok, error = await self.apply_timeout(author, minutes * 60, f"حماية تلقائية: {reason}")
        await self.log(guild, title, author, self.bot.user, reason, None if ok else f"تعذر التايم اوت: {error}")
        return True

    async def protect_message(self, message: discord.Message) -> bool:
        guild, author = message.guild, message.author
        if not isinstance(author, discord.Member) or author.bot:
            return False
        cfg = self.cfg(guild.id)
        if not cfg["protection"] or self.is_privileged(author, guild):
            return False

        content = message.content or ""
        text = norm(content)

        if cfg["invite_filter"] and INVITE_RE.search(content):
            return await self.punish(message, 10, "نشر رابط دعوة لسيرفر آخر", "Invite Filter")

        for word in cfg["banned_words"]:
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text):
                return await self.punish(message, 5, "استخدام كلمة ممنوعة", "Banned Word")

        mentions = mention_count(message)
        if mentions >= max(1, cfg["mentions"]["max"]):
            return await self.punish(
                message, cfg["mentions"]["timeout_min"],
                f"سبام منشنات: {mentions} منشن في رسالة واحدة", "Mention Spam",
            )

        if REPEAT_RE.search(content) or len(URL_RE.findall(content)) >= 4:
            return await self.punish(message, 3, "إغراق أحرف أو روابط", "Flood Protection")

        now = time.monotonic()
        key = (guild.id, author.id)
        history = self.msg_history[key]
        media = has_media(message)
        history.append((now, text, media))

        spam = cfg["spam"]
        recent = [h for h in history if now - h[0] <= spam["window"]]
        if len(recent) >= spam["limit"]:
            return await self.punish(
                message, spam["timeout_min"],
                f"سبام رسائل: {len(recent)} رسائل خلال {spam['window']} ثوانٍ", "Message Spam",
            )
        if text and sum(1 for h in recent if h[1] == text) >= spam["limit"]:
            return await self.punish(message, spam["timeout_min"], "تكرار نفس الرسالة", "Duplicate Spam")

        media_cfg = cfg["media"]
        media_recent = [h for h in history if h[2] and now - h[0] <= media_cfg["window"]]
        if len(media_recent) >= media_cfg["limit"]:
            return await self.punish(
                message, media_cfg["timeout_min"],
                f"سبام صور ومرفقات: {len(media_recent)} خلال {media_cfg['window']} ثوانٍ", "Media Spam",
            )
        return False

    async def check_bot_join(self, bot_member: discord.Member) -> None:
        guild = bot_member.guild
        await asyncio.sleep(2)
        member = guild.get_member(bot_member.id) or bot_member
        cfg = self.cfg(guild.id)
        if member.id in cfg["trusted_bot_ids"]:
            return
        dangerous = [p for p in DANGEROUS_PERMS if getattr(member.guild_permissions, p, False)]
        if not dangerous:
            return

        actor = await self.find_audit_actor(guild, discord.AuditLogAction.bot_add, member.id)
        actor_member = guild.get_member(actor.id) if actor else None
        perms_text = "الصلاحيات: " + ", ".join(dangerous)

        if actor_member is not None and self.has_level(actor_member, guild, "manage"):
            await self.log(guild, "Privileged Bot Joined", member, actor,
                           "انضم بوت بصلاحيات عالية بواسطة إدارة موثوقة، ولم يُطرد.", perms_text)
            return

        error = "رتبة البوت لا تسمح بطرد هذا البوت."
        me = guild.me
        if me and me.guild_permissions.kick_members and member.top_role < me.top_role:
            try:
                await member.kick(reason="بوت بصلاحيات عالية أُضيف دون إذن من الإدارة")
                await self.log(guild, "High-Risk Bot Removed", member, actor,
                               "تم طرد بوت بصلاحيات عالية أُضيف دون إذن.", perms_text)
                return
            except discord.HTTPException as exc:
                error = str(exc)
        await self.log(guild, "High-Risk Bot Alert", member, actor,
                       f"رُصد بوت بصلاحيات عالية ولم يُطرد. {error}", perms_text)

    async def protect_join(self, member: discord.Member) -> None:
        guild = member.guild
        if not self.cfg(guild.id)["protection"]:
            return
        if member.bot:
            self.spawn(self.check_bot_join(member))
            return

        now = time.monotonic()
        joins = self.join_history[guild.id]
        joins.append(now)
        if sum(1 for t in joins if now - t <= 20) >= 8 and self.raid_until.get(guild.id, 0) < now:
            self.raid_until[guild.id] = now + 120
            await self.log(guild, "Join Raid Alert", None, self.bot.user,
                           "رُصدت موجة انضمام سريعة. تم تقييد الحسابات الحديثة لمدة دقيقتين.")

        young = discord.utils.utcnow() - member.created_at < timedelta(days=3)
        if self.raid_until.get(guild.id, 0) > now and young:
            ok, _ = await self.apply_timeout(member, 600, "حماية موجة انضمام: حساب حديث")
            if ok:
                await self.log(guild, "Raid Account Restricted", member, self.bot.user,
                               "تم تقييد حساب حديث مؤقتًا.")

    async def find_audit_actor(self, guild, action, target_id=None):
        if not bot_has(guild, "view_audit_log"):
            return None
        try:
            async for entry in guild.audit_logs(limit=6, action=action):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 30:
                    break
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                return entry.user
        except discord.HTTPException:
            return None
        return None

    async def watch_destructive(self, guild, target_id, action, label) -> None:
        if not self.cfg(guild.id)["protection"]:
            return
        await asyncio.sleep(1)
        actor = await self.find_audit_actor(guild, action, target_id)
        if actor is None or actor.id in (guild.owner_id, self.bot.user.id):
            return

        now = time.monotonic()
        history = self.destructive[(guild.id, actor.id, label)]
        history.append(now)
        while history and now - history[0] > 15:
            history.popleft()
        if len(history) < 3:
            return
        history.clear()

        reason = f"مؤشر تخريب: {label} 3 مرات خلال 15 ثانية."
        member = guild.get_member(actor.id)
        if member is None:
            await self.log(guild, "Anti-Nuke Alert", actor, self.bot.user, reason)
            return
        ok, error = await self.apply_timeout(member, 3600, reason)
        await self.log(guild, "Anti-Nuke Alert", member, self.bot.user, reason,
                       None if ok else f"تعذر التايم اوت: {error}")

    # ---------------- الطرد الجماعي ----------------

    async def run_mass_kick(self, guild, requester, status_message) -> None:
        self.mass_kick_running.add(guild.id)
        try:
            targets, bots, locked = plan_mass_kick(guild)
            total = len(targets)
            kicked = failed = 0
            for index, member in enumerate(targets, 1):
                try:
                    await member.kick(reason=MASS_KICK_REASON)
                    kicked += 1
                except discord.NotFound:
                    pass
                except discord.HTTPException:
                    failed += 1
                if index % 25 == 0:
                    await edit_quietly(status_message, f"⏳ جاري الطرد: {index}/{total}")
                await asyncio.sleep(0.35)

            await edit_quietly(status_message, f"✅ اكتمل الطرد الجماعي. تم طرد **{kicked}** عضو.")
            await self.log(
                guild, "Mass Kick", None, requester,
                f"تم طرد {kicked} عضو بأمر من مالك السيرفر.",
                f"فشل: {failed} | بوتات مستثناة: {bots} | رتب أعلى من البوت: {locked}",
            )
        finally:
            self.mass_kick_running.discard(guild.id)

    # ---------------- الاختصارات بدون prefix ----------------

    async def handle_shortcut(self, message: discord.Message) -> bool:
        guild, member = message.guild, message.author
        if not isinstance(member, discord.Member):
            return False

        cfg = self.cfg(guild.id)
        parts = message.content.split()
        if not parts:
            return False
        first = norm(parts[0])
        action = next(
            (a for a, names in cfg["shortcuts"].items() if first in {norm(n) for n in names}),
            None,
        )
        if action is None:
            return False

        level = SHORTCUT_LEVEL[action]
        if not self.has_level(member, guild, level):
            await message.channel.send(LEVEL_MSG[level], delete_after=6)
            return True

        if action == "clear":
            if len(parts) < 2 or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 100:
                await message.channel.send("استخدمه كذا: `مسح 20` (من 1 إلى 100).", delete_after=6)
                return True
            _, text = await self.op_clear(guild, message.channel, member, int(parts[1]), message)
            await delete_quietly(message)
            await message.channel.send(text, delete_after=6, allowed_mentions=NO_MENTIONS)
            return True

        target = await resolve_member(guild, parts[1]) if len(parts) > 1 else None
        if target is None:
            await message.channel.send("حدد العضو بمنشن أو ID.", delete_after=6)
            return True

        if action == "timeout":
            seconds = parse_duration(parts[2]) if len(parts) > 2 else None
            if seconds is None:
                await message.channel.send("استخدمه كذا: `تايم_اوت @العضو 10m السبب`", delete_after=6)
                return True
            _, text = await self.op_timeout(guild, member, target, seconds, clean_reason(" ".join(parts[3:])))
        elif action == "warn":
            _, text = await self.op_warn(guild, member, target, clean_reason(" ".join(parts[2:])))
        elif action == "ban":
            _, text = await self.op_ban(guild, member, target, clean_reason(" ".join(parts[2:])))
        else:
            _, text = await self.op_kick(guild, member, target, clean_reason(" ".join(parts[2:])))

        await delete_quietly(message)
        await message.channel.send(text, delete_after=8, allowed_mentions=NO_MENTIONS)
        return True

    def config_text(self, guild: discord.Guild, cfg: dict) -> str:
        def role_mention(key: str) -> str:
            rid = cfg.get(key)
            role = guild.get_role(int(rid)) if rid else None
            return role.mention if role else "غير محددة"

        channel_id = cfg.get("log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        words = cfg["banned_words"]
        shortcut_lines = [
            f"• `{label}`: " + (", ".join(f"`{n}`" for n in cfg["shortcuts"].get(action, [])) or "معطّل")
            for label, action in SHORTCUT_TYPES.items()
        ]
        esc = cfg["escalation"]
        return (
            "**🛡️ إعدادات النظام**\n"
            f"الحماية التلقائية: {'✅ تعمل' if cfg['protection'] else '⏸️ متوقفة'}\n"
            f"رتبة الإدارة: {role_mention('admin_role_id')}\n"
            f"رتبة الحظر: {role_mention('ban_role_id')}\n"
            f"رتبة الطرد: {role_mention('kick_role_id')}\n"
            f"روم اللوق: {channel.mention if isinstance(channel, discord.TextChannel) else 'غير محدد'}\n"
            f"منع روابط الدعوات: {'✅' if cfg['invite_filter'] else '❌'}\n"
            f"الكلمات الممنوعة: {len(words)} كلمة\n"
            f"تصعيد التحذيرات: عند {esc['warnings']} تحذيرات ← تايم اوت {duration_text(esc['timeout_min'] * 60)}\n"
            f"بوتات موثوقة: {', '.join(map(str, cfg['trusted_bot_ids'])) or 'لا يوجد'}\n\n"
            "**الاختصارات (بدون !):**\n" + "\n".join(shortcut_lines) + "\n\n"
            "**التعديل بأمر `!اعداد`:**\n"
            "`!اعداد رتبة ادارة @رتبة` | `!اعداد رتبة حظر @رتبة` | `!اعداد رتبة طرد @رتبة`\n"
            "`!اعداد لوق #روم` (بدون روم = تعطيل)\n"
            "`!اعداد اختصار حظر كلمة1 كلمة2` (`-` للتعطيل)\n"
            "`!اعداد كلمة_ممنوعة كلمة` (إضافة/إزالة)\n"
            "`!اعداد منع_الدعوات` (تشغيل/إيقاف)\n"
            "`!اعداد تصعيد 3 60` (عدد التحذيرات، المدة بالدقائق)\n"
            "`!اعداد بوت_موثوق ID` (إضافة/إزالة)"
        )

    # ============================================================
    # المستمعون
    # ============================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        try:
            if await self.protect_message(message):
                return
            if not message.content.startswith(PREFIX):
                await self.handle_shortcut(message)
        except discord.HTTPException as exc:
            print(f"[BOT7 MESSAGE] {exc}")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.protect_join(member)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        self.spawn(self.watch_destructive(
            channel.guild, channel.id, discord.AuditLogAction.channel_delete, "حذف القنوات"))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        self.spawn(self.watch_destructive(
            role.guild, role.id, discord.AuditLogAction.role_delete, "حذف الرتب"))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            text = str(error) or "ما عندك صلاحية."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"ناقصك `{error.param.name}`. استخدم `!مساعدة`."
        elif isinstance(error, commands.BadArgument):
            text = "ما قدرت أفهم المدخلات أو ما لقيت العضو/الرتبة/الروم."
        else:
            original = getattr(error, "original", error)
            print(f"[BOT7 COMMAND] {type(original).__name__}: {original}")
            text = "حدث خطأ غير متوقع أثناء تنفيذ الأمر."
        try:
            await ctx.send(text, delete_after=8)
        except discord.HTTPException:
            pass

    # ============================================================
    # الأوامر
    # ============================================================

    @commands.command(name="مساعدة", aliases=["مساعده"])
    async def cmd_help(self, ctx: commands.Context):
        await ctx.send(
            "**🛡️ bot7 - الأوامر**\n"
            "**الإدارة:** `!حظر @عضو السبب` | `!طرد @عضو السبب` | `!تايم_اوت @عضو 10m السبب` | `!فك_التايم @عضو`\n"
            "**التحذيرات:** `!تحذير @عضو السبب` | `!تحذيرات @عضو` | `!حذف_تحذيرات @عضو`\n"
            "**الرومات:** `!قفل_الروم` | `!فتح_الروم` | `!بطء 10` (0 للإيقاف) | `!مسح 20`\n"
            "**أخرى:** `!فك_الحظر ID` | `!معلومات @عضو`\n"
            "**الإعداد:** `!اعداد` | **الحماية:** `!مراقبة_تلقائية` (تشغيل/إيقاف مع تأكيد)\n"
            "**مالك السيرفر فقط:** `!طرد_الكل` (طرد كل الأعضاء ما عدا البوتات، مع تأكيد بزرين)\n"
            "الاختصارات تعمل بدون `!` بعد ضبطها من `!اعداد`.",
            allowed_mentions=NO_MENTIONS,
        )

    @commands.command(name="اعداد", aliases=["إعداد", "config"])
    @requires("config")
    async def cmd_config(self, ctx: commands.Context, *args: str):
        guild = ctx.guild
        cfg = self.cfg(guild.id)
        if not args:
            await ctx.send(self.config_text(guild, cfg), allowed_mentions=NO_MENTIONS)
            return

        sub = norm(args[0])

        if sub == "رتبة" and len(args) >= 3:
            key = ROLE_SLOTS.get(norm(args[1]))
            if key is None:
                await ctx.send("النوع: `ادارة` أو `حظر` أو `طرد`.")
                return
            role = resolve_role(guild, args[2])
            if role is None or role.is_default():
                await ctx.send("ما لقيت الرتبة، أو لا يمكن استخدام @everyone.")
                return
            cfg[key] = role.id
            await self.persist()
            await ctx.send(f"تم تحديد {role.mention}.", allowed_mentions=NO_MENTIONS)
            return

        if sub == "لوق":
            if not ctx.message.channel_mentions:
                cfg["log_channel_id"] = None
                await self.persist()
                await ctx.send("تم تعطيل اللوق.")
                return
            channel = ctx.message.channel_mentions[0]
            cfg["log_channel_id"] = channel.id
            await self.persist()
            await ctx.send(f"تم تحديد روم اللوق: {channel.mention}", allowed_mentions=NO_MENTIONS)
            return

        if sub == "اختصار" and len(args) >= 3:
            action = SHORTCUT_TYPES.get(norm(args[1]))
            if action is None:
                await ctx.send("النوع: `حظر` `طرد` `مسح` `تحذير` `تايم_اوت`.")
                return
            raw = [norm(a) for a in args[2:]]
            if raw == ["-"]:
                cfg["shortcuts"][action] = []
            else:
                cleaned: list[str] = []
                for alias in raw:
                    if alias.startswith(PREFIX) or " " in alias or alias in cleaned:
                        continue
                    cleaned.append(alias)
                if not cleaned:
                    await ctx.send("حدد اختصارًا واحدًا على الأقل بدون مسافات.")
                    return
                cfg["shortcuts"][action] = cleaned
            await self.persist()
            names = cfg["shortcuts"][action]
            await ctx.send(f"تم تحديث اختصارات **{norm(args[1])}**: " + (", ".join(f"`{n}`" for n in names) or "معطّل"))
            return

        if sub == "كلمة_ممنوعة" and len(args) >= 2:
            word = norm(" ".join(args[1:]))
            if word in cfg["banned_words"]:
                cfg["banned_words"].remove(word)
                text = f"تمت إزالة `{word}` من الكلمات الممنوعة."
            else:
                cfg["banned_words"].append(word)
                text = f"تمت إضافة `{word}` إلى الكلمات الممنوعة."
            await self.persist()
            await ctx.send(text)
            return

        if sub == "منع_الدعوات":
            cfg["invite_filter"] = not cfg["invite_filter"]
            await self.persist()
            await ctx.send("✅ منع روابط الدعوات مفعّل." if cfg["invite_filter"] else "❌ منع روابط الدعوات معطّل.")
            return

        if sub == "تصعيد" and len(args) >= 3 and args[1].isdigit() and args[2].isdigit():
            count, minutes = int(args[1]), int(args[2])
            if not (1 <= count <= 50 and 1 <= minutes <= 40320):
                await ctx.send("عدد التحذيرات من 1 إلى 50، والمدة من 1 إلى 40320 دقيقة.")
                return
            cfg["escalation"] = {"warnings": count, "timeout_min": minutes}
            await self.persist()
            await ctx.send(f"تم ضبط التصعيد: عند **{count}** تحذيرات ← تايم اوت **{duration_text(minutes * 60)}**.")
            return

        if sub == "بوت_موثوق" and len(args) >= 2 and args[1].isdigit():
            bot_id = int(args[1])
            trusted = cfg["trusted_bot_ids"]
            if bot_id in trusted:
                trusted.remove(bot_id)
                text = "تمت إزالة البوت من القائمة الموثوقة."
            else:
                trusted.append(bot_id)
                text = "تمت إضافة البوت للقائمة الموثوقة."
            await self.persist()
            await ctx.send(text)
            return

        await ctx.send("صيغة غير معروفة. استخدم `!اعداد` لعرض الخيارات.")

    @commands.command(name="مراقبة_تلقائية", aliases=["مراقبة", "الحماية"])
    @requires("config")
    async def cmd_protection(self, ctx: commands.Context):
        guild = ctx.guild
        turning_on = not self.cfg(guild.id)["protection"]

        async def apply(interaction: discord.Interaction) -> None:
            self.cfg(guild.id)["protection"] = turning_on
            await self.persist()
            state = "✅ تم تشغيل الحماية التلقائية." if turning_on else "⏸️ تم إيقاف الحماية التلقائية."
            await interaction.response.edit_message(content=state, embed=None, view=None)

        embed = discord.Embed(
            title="🛡️ تأكيد الحماية التلقائية" if turning_on else "⏸️ تأكيد إيقاف الحماية",
            color=discord.Color.orange(),
            description=(
                "الحماية تشمل: سبام الرسائل والتكرار، المنشنات، الصور والمرفقات، "
                "إغراق الأحرف والروابط، روابط الدعوات، الكلمات الممنوعة، موجات الانضمام، "
                "البوتات عالية الصلاحيات، وتخريب القنوات والرتب."
                if turning_on else
                "سيتم إيقاف كل الحمايات التلقائية حتى تشغلها مرة أخرى."
            ),
        )
        view = ConfirmView(
            self, ctx.author, owner_only=False,
            label="تأكيد التشغيل" if turning_on else "تأكيد الإيقاف",
            style=discord.ButtonStyle.success if turning_on else discord.ButtonStyle.danger,
            handler=apply,
        )
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="طرد_الكل", aliases=["kickall"])
    @requires("owner")
    async def cmd_kick_all(self, ctx: commands.Context):
        guild = ctx.guild
        if not bot_has(guild, "kick_members"):
            await ctx.send("البوت يحتاج صلاحية Kick Members.")
            return
        if guild.id in self.mass_kick_running:
            await ctx.send("هناك عملية طرد جارية بالفعل.")
            return

        try:
            await guild.chunk()
        except (discord.HTTPException, discord.ClientException):
            pass

        targets, bots_count, locked = plan_mass_kick(guild)
        if not targets:
            await ctx.send("ما فيه أعضاء يمكن طردهم.")
            return

        embed = discord.Embed(
            title="⚠️ تأكيد الطرد الجماعي",
            color=discord.Color.red(),
            description=(
                "سيتم طرد كل الأعضاء البشريين، ما عدا: مالك السيرفر، والبوتات، "
                "والأعضاء الذين رتبهم أعلى من البوت.\n\n"
                "لن يرسل البوت أي رسالة للأعضاء. العملية لا يمكن التراجع عنها."
            ),
        )
        embed.add_field(name="سيتم طرد", value=f"**{len(targets)}** عضو", inline=True)
        embed.add_field(name="بوتات مستثناة", value=str(bots_count), inline=True)
        embed.add_field(name="رتب أعلى من البوت", value=str(locked), inline=True)

        async def start(interaction: discord.Interaction) -> None:
            if guild.id in self.mass_kick_running:
                await interaction.response.edit_message(content="⚠️ هناك عملية طرد جارية بالفعل.", embed=None, view=None)
                return
            await interaction.response.edit_message(content="⏳ جاري الطرد...", embed=None, view=None)
            self.spawn(self.run_mass_kick(guild, ctx.author, interaction.message))

        view = ConfirmView(
            self, ctx.author, owner_only=True,
            label="تأكيد طرد الكل", style=discord.ButtonStyle.danger, handler=start,
        )
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="حظر", aliases=["ban"])
    @requires("ban")
    async def cmd_ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = ""):
        _, text = await self.op_ban(ctx.guild, ctx.author, member, clean_reason(reason))
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @commands.command(name="فك_الحظر", aliases=["unban"])
    @requires("ban")
    async def cmd_unban(self, ctx: commands.Context, user_id: int):
        if not bot_has(ctx.guild, "ban_members"):
            await ctx.send("البوت يحتاج صلاحية Ban Members.")
            return
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"فك حظر بواسطة {ctx.author}")
        except discord.NotFound:
            await ctx.send("المستخدم غير محظور أو الـID غير صحيح.")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"فشل فك الحظر: {exc}")
            return
        await self.log(ctx.guild, "Unban", user, ctx.author, "فك حظر")
        await ctx.send(f"تم فك الحظر عن `{user}`.")

    @commands.command(name="طرد", aliases=["kick"])
    @requires("kick")
    async def cmd_kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = ""):
        _, text = await self.op_kick(ctx.guild, ctx.author, member, clean_reason(reason))
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @commands.command(name="تايم_اوت", aliases=["timeout", "تايم"])
    @requires("manage")
    async def cmd_timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = ""):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.send("صيغة المدة: `10m` أو `2h` أو `1d` أو رقم فقط كدقائق. الحد الأعلى 28 يوم.")
            return
        _, text = await self.op_timeout(ctx.guild, ctx.author, member, seconds, clean_reason(reason))
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @commands.command(name="فك_التايم", aliases=["untimeout"])
    @requires("manage")
    async def cmd_untimeout(self, ctx: commands.Context, member: discord.Member):
        _, text = await self.op_untimeout(ctx.guild, ctx.author, member)
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @commands.command(name="تحذير", aliases=["warn"])
    @requires("manage")
    async def cmd_warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = ""):
        _, text = await self.op_warn(ctx.guild, ctx.author, member, clean_reason(reason))
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @commands.command(name="تحذيرات", aliases=["warnings"])
    @requires("manage")
    async def cmd_warnings(self, ctx: commands.Context, member: discord.Member):
        items = self.cfg(ctx.guild.id)["warnings"].get(str(member.id), [])
        if not items:
            await ctx.send(f"{member.mention} ما عليه تحذيرات.", allowed_mentions=NO_MENTIONS)
            return
        shown = items[-15:]
        start = len(items) - len(shown) + 1
        lines = [f"**تحذيرات {member.display_name}** (المجموع: {len(items)})"]
        for index, item in enumerate(shown, start):
            mod = ctx.guild.get_member(int(item.get("moderator_id", 0)))
            mod_text = mod.mention if mod else "غير معروف"
            lines.append(f"`#{index}` بواسطة {mod_text}: {str(item.get('reason', ''))[:200]}")
        await ctx.send("\n".join(lines), allowed_mentions=NO_MENTIONS)

    @commands.command(name="حذف_تحذيرات", aliases=["مسح_تحذيرات"])
    @requires("manage")
    async def cmd_clear_warnings(self, ctx: commands.Context, member: discord.Member):
        removed = len(self.cfg(ctx.guild.id)["warnings"].pop(str(member.id), []))
        await self.persist()
        await self.log(ctx.guild, "Clear Warnings", member, ctx.author, f"حذف {removed} تحذير")
        await ctx.send(f"تم حذف **{removed}** تحذير عن {member.mention}.", allowed_mentions=NO_MENTIONS)

    @commands.command(name="مسح", aliases=["clear"])
    @requires("manage")
    async def cmd_clear(self, ctx: commands.Context, amount: int):
        if not 1 <= amount <= 100:
            await ctx.send("حدد رقمًا من 1 إلى 100.")
            return
        _, text = await self.op_clear(ctx.guild, ctx.channel, ctx.author, amount, ctx.message)
        await delete_quietly(ctx.message)
        await ctx.send(text, delete_after=6)

    @commands.command(name="قفل_الروم", aliases=["lock"])
    @requires("manage")
    async def cmd_lock(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("القفل يشتغل على الرومات النصية فقط.")
            return
        _, text = await self.op_lock(ctx.guild, ctx.channel, ctx.author, True)
        await ctx.send(text)

    @commands.command(name="فتح_الروم", aliases=["unlock"])
    @requires("manage")
    async def cmd_unlock(self, ctx: commands.Context):
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("الفتح يشتغل على الرومات النصية فقط.")
            return
        _, text = await self.op_lock(ctx.guild, ctx.channel, ctx.author, False)
        await ctx.send(text)

    @commands.command(name="بطء", aliases=["slowmode"])
    @requires("manage")
    async def cmd_slowmode(self, ctx: commands.Context, seconds: int):
        if not 0 <= seconds <= 21600:
            await ctx.send("البطء بين 0 و 21600 ثانية (0 للإيقاف).")
            return
        _, text = await self.op_slowmode(ctx.guild, ctx.channel, ctx.author, seconds)
        await ctx.send(text)

    @commands.command(name="معلومات", aliases=["info"])
    @requires("manage")
    async def cmd_info(self, ctx: commands.Context, member: discord.Member):
        items = self.cfg(ctx.guild.id)["warnings"].get(str(member.id), [])
        timed = member.timed_out_until
        timed_text = (
            f"حتى {discord.utils.format_dt(timed, 'R')}"
            if timed and timed > discord.utils.utcnow() else "لا"
        )
        embed = discord.Embed(title=f"معلومات {member.display_name}", color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="الحساب أُنشئ", value=discord.utils.format_dt(member.created_at, "D"), inline=True)
        embed.add_field(name="انضم للسيرفر", value=discord.utils.format_dt(member.joined_at, "D") if member.joined_at else "غير معروف", inline=True)
        embed.add_field(name="أعلى رتبة", value=member.top_role.mention, inline=True)
        embed.add_field(name="تحذيرات", value=str(len(items)), inline=True)
        embed.add_field(name="تايم اوت", value=timed_text, inline=True)
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @commands.command(name="طرد_الكل", aliases=["kickall"])
    @requires("owner")
    async def _placeholder_never_used(self, ctx: commands.Context):
        pass


# ============================================================
# نقطة التحميل - تستدعيها discord.py عند load_extension("bot7")
# ============================================================

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
    print("✅ تم تحميل نظام bot7 كـ Cog")