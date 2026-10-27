# -*- coding: utf-8 -*-
"""
bot7.py - نظام إدارة وحماية موحّد لـ Discord (discord.py 2.x)

التشغيل:
    pip install -U discord.py
    export BOT_TOKEN="..."        (Windows: set BOT_TOKEN=...)
    python bot7.py

يحتاج تفعيل Server Members Intent و Message Content Intent من Developer Portal.
"""

import asyncio
import copy
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Awaitable, Callable, Optional

import discord
from discord.ext import commands

# ============================================================
# الإعدادات العامة
# ============================================================

PREFIX = "!"
DATA_FILE = Path("bot7_data.json")
TOKEN = os.getenv("BOT_TOKEN")
NO_MENTIONS = discord.AllowedMentions.none()
MAX_TIMEOUT = 28 * 24 * 60 * 60
MASS_KICK_REASON = "طرد جماعي بأمر مالك السيرفر"
DANGEROUS_PERMS = (
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "manage_webhooks", "ban_members", "kick_members",
)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"}
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
REPEAT_RE = re.compile(r"(.)\1{24,}", re.DOTALL)

DEFAULTS = {
    "protection": False,
    "trusted_bot_ids": [],
    "admin_role_id": None,
    "ban_role_id": None,
    "kick_role_id": None,
    "log_channel_id": None,
    "spam": {"limit": 6, "window": 8, "timeout_min": 10},
    "mentions": {"max": 5, "timeout_min": 5},
    "media": {"limit": 4, "window": 10, "timeout_min": 5},
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
SHORTCUT_LEVEL = {
    "ban": "ban", "kick": "kick", "clear": "manage",
    "warn": "manage", "timeout": "manage",
}
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
# قاعدة البيانات
# ============================================================

DATABASE: dict = {}
DB_LOCK = asyncio.Lock()


def load_db() -> None:
    global DATABASE
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        DATABASE = data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        DATABASE = {}


def save_db() -> None:
    tmp = DATA_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(DATABASE, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
    except OSError as exc:
        print(f"[DB ERROR] {exc}")


async def persist() -> None:
    async with DB_LOCK:
        await asyncio.to_thread(save_db)


def cfg_of(guild_id: int) -> dict:
    cfg = DATABASE.setdefault(str(guild_id), {})
    for key, default in DEFAULTS.items():
        cfg.setdefault(key, copy.deepcopy(default))
    for key in ("spam", "mentions", "media", "shortcuts"):
        for sub, value in DEFAULTS[key].items():
            cfg[key].setdefault(sub, copy.deepcopy(value))
    return cfg


# ============================================================
# أدوات مساعدة
# ============================================================

BACKGROUND: set[asyncio.Task] = set()
MSG_HISTORY: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=40))
JOIN_HISTORY: dict[int, deque] = defaultdict(lambda: deque(maxlen=200))
RAID_UNTIL: dict[int, float] = {}
DESTRUCTIVE: dict[tuple[int, int, str], deque] = defaultdict(lambda: deque(maxlen=20))
MASS_KICK_RUNNING: set[int] = set()


def spawn(coro) -> None:
    task = asyncio.create_task(coro)
    BACKGROUND.add(task)
    task.add_done_callback(BACKGROUND.discard)


def norm(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def clean_reason(text: str) -> str:
    text = text.strip()
    return text[:450] if text else "بدون سبب"


def has_role(member: discord.Member, role_id) -> bool:
    return bool(role_id) and any(role.id == int(role_id) for role in member.roles)


def has_level(member: discord.Member, guild: discord.Guild, level: str) -> bool:
    if member.id == guild.owner_id:
        return True
    if level == "owner":
        return False
    if member.guild_permissions.administrator:
        return True
    if level == "config":
        return False
    return has_role(member, cfg_of(guild.id).get(LEVEL_ROLE[level]))


def is_privileged(member: discord.Member, guild: discord.Guild) -> bool:
    return has_level(member, guild, "manage")


def requires(level: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("هذا الأمر داخل السيرفر فقط.")
        if not has_level(ctx.author, ctx.guild, level):
            raise commands.CheckFailure(LEVEL_MSG[level])
        return True
    return commands.check(predicate)


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


async def delete_quietly(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.HTTPException:
        pass


async def edit_quietly(message: Optional[discord.Message], content: str) -> None:
    if message is None:
        return
    try:
        await message.edit(content=content)
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
    return next(
        (m for m in guild.members if name in {norm(m.display_name), norm(m.name)}),
        None,
    )


def resolve_role(guild: discord.Guild, token: str) -> Optional[discord.Role]:
    mention = re.fullmatch(r"<@&(\d+)>", token.strip())
    if mention:
        return guild.get_role(int(mention.group(1)))
    if token.strip().isdigit():
        return guild.get_role(int(token.strip()))
    name = norm(token)
    return next((r for r in guild.roles if norm(r.name) == name), None)


async def log(
    guild: discord.Guild,
    title: str,
    target: Optional[discord.abc.User],
    moderator: Optional[discord.abc.User],
    reason: str,
    extra: Optional[str] = None,
) -> None:
    channel_id = cfg_of(guild.id).get("log_channel_id")
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


async def apply_timeout(member: discord.Member, seconds: int, reason: str) -> tuple[bool, str]:
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


async def find_audit_actor(
    guild: discord.Guild,
    action: discord.AuditLogAction,
    target_id: Optional[int] = None,
) -> Optional[discord.abc.User]:
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


# ============================================================
# العمليات المشتركة (تُستخدم من الأوامر ومن الاختصارات)
# ============================================================

async def op_ban(guild, moderator, target, reason) -> tuple[bool, str]:
    if not bot_has(guild, "ban_members"):
        return False, "البوت يحتاج صلاحية Ban Members."
    ok, error = can_moderate(guild, target)
    if not ok:
        return False, error
    try:
        await target.ban(reason=reason, delete_message_seconds=0)
    except discord.HTTPException as exc:
        return False, f"فشل الحظر: {exc}"
    await log(guild, "Ban", target, moderator, reason)
    return True, f"تم حظر {target.mention}."


async def op_kick(guild, moderator, target, reason) -> tuple[bool, str]:
    if not bot_has(guild, "kick_members"):
        return False, "البوت يحتاج صلاحية Kick Members."
    ok, error = can_moderate(guild, target)
    if not ok:
        return False, error
    try:
        await target.kick(reason=reason)
    except discord.HTTPException as exc:
        return False, f"فشل الطرد: {exc}"
    await log(guild, "Kick", target, moderator, reason)
    return True, f"تم طرد {target.mention}."


async def op_timeout(guild, moderator, target, seconds, reason) -> tuple[bool, str]:
    ok, error = await apply_timeout(target, seconds, reason)
    if not ok:
        return False, error
    await log(guild, "Timeout", target, moderator, reason, f"المدة: {duration_text(seconds)}")
    return True, f"تم إعطاء {target.mention} تايم اوت لمدة **{duration_text(seconds)}**."


async def op_untimeout(guild, moderator, target) -> tuple[bool, str]:
    if not bot_has(guild, "moderate_members"):
        return False, "البوت يحتاج صلاحية Moderate Members."
    ok, error = can_moderate(guild, target)
    if not ok:
        return False, error
    try:
        await target.timeout(None, reason=f"إلغاء التايم اوت بواسطة {moderator}")
    except discord.HTTPException as exc:
        return False, f"فشل الإلغاء: {exc}"
    await log(guild, "Remove Timeout", target, moderator, "إلغاء التايم اوت")
    return True, f"تم إلغاء التايم اوت عن {target.mention}."


async def op_warn(guild, moderator, target, reason) -> tuple[bool, str]:
    items = cfg_of(guild.id)["warnings"].setdefault(str(target.id), [])
    items.append({
        "reason": reason,
        "moderator_id": moderator.id,
        "timestamp": discord.utils.utcnow().isoformat(),
    })
    await persist()
    await log(guild, "Warning", target, moderator, reason, f"إجمالي التحذيرات: {len(items)}")
    return True, f"⚠️ تم تحذير {target.mention}. عدد تحذيراته: **{len(items)}**."


async def op_clear(guild, channel, moderator, amount, trigger) -> tuple[bool, str]:
    if not bot_has(guild, "manage_messages"):
        return False, "البوت يحتاج صلاحية Manage Messages."
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return False, "لا يمكن المسح في هذا النوع من الرومات."
    try:
        deleted = await channel.purge(limit=amount, before=trigger)
    except discord.HTTPException as exc:
        return False, f"تعذر المسح: {exc}"
    await log(guild, "Clear Messages", None, moderator, f"مسح {len(deleted)} رسالة من {channel.mention}")
    return True, f"تم مسح **{len(deleted)}** رسالة."


# ============================================================
# الحماية التلقائية (قابلة للتشغيل والإيقاف من أمر واحد)
# ============================================================

async def punish(message, minutes, reason, title) -> bool:
    guild, author = message.guild, message.author
    MSG_HISTORY[(guild.id, author.id)].clear()
    await delete_quietly(message)
    ok, error = await apply_timeout(author, minutes * 60, f"حماية تلقائية: {reason}")
    await log(guild, title, author, bot.user, reason, None if ok else f"تعذر التايم اوت: {error}")
    return True


async def protect_message(message: discord.Message) -> bool:
    guild = message.guild
    author = message.author
    if not isinstance(author, discord.Member) or author.bot:
        return False
    cfg = cfg_of(guild.id)
    if not cfg["protection"] or is_privileged(author, guild):
        return False

    content = message.content or ""
    mentions = mention_count(message)
    if mentions >= max(1, cfg["mentions"]["max"]):
        return await punish(
            message, cfg["mentions"]["timeout_min"],
            f"سبام منشنات: {mentions} منشن في رسالة واحدة", "Mention Spam",
        )
    if REPEAT_RE.search(content) or len(URL_RE.findall(content)) >= 4:
        return await punish(message, 3, "إغراق أحرف أو روابط", "Flood Protection")

    now = time.monotonic()
    key = (guild.id, author.id)
    history = MSG_HISTORY[key]
    text = norm(content)
    media = has_media(message)
    history.append((now, text, media))

    spam = cfg["spam"]
    recent = [h for h in history if now - h[0] <= spam["window"]]
    if len(recent) >= spam["limit"]:
        return await punish(
            message, spam["timeout_min"],
            f"سبام رسائل: {len(recent)} رسائل خلال {spam['window']} ثوانٍ", "Message Spam",
        )
    if text and sum(1 for h in recent if h[1] == text) >= spam["limit"]:
        return await punish(
            message, spam["timeout_min"],
            "تكرار نفس الرسالة بشكل سبامي", "Duplicate Spam",
        )

    media_cfg = cfg["media"]
    media_recent = [h for h in history if h[2] and now - h[0] <= media_cfg["window"]]
    if len(media_recent) >= media_cfg["limit"]:
        return await punish(
            message, media_cfg["timeout_min"],
            f"سبام صور ومرفقات: {len(media_recent)} خلال {media_cfg['window']} ثوانٍ", "Media Spam",
        )
    return False


async def check_bot_join(bot_member: discord.Member) -> None:
    guild = bot_member.guild
    await asyncio.sleep(2)  # ننتظر Discord يطبق صلاحيات الرتبة المُدارة
    member = guild.get_member(bot_member.id) or bot_member
    cfg = cfg_of(guild.id)
    if member.id in cfg["trusted_bot_ids"]:
        return
    dangerous = [p for p in DANGEROUS_PERMS if getattr(member.guild_permissions, p, False)]
    if not dangerous:
        return

    actor = await find_audit_actor(guild, discord.AuditLogAction.bot_add, member.id)
    actor_member = guild.get_member(actor.id) if actor else None
    if actor_member is not None and has_level(actor_member, guild, "manage"):
        await log(
            guild, "Privileged Bot Joined", member, actor,
            "انضم بوت بصلاحيات عالية بواسطة إدارة موثوقة، ولم يُطرد.",
            "الصلاحيات: " + ", ".join(dangerous),
        )
        return

    me = guild.me
    if me and me.guild_permissions.kick_members and member.top_role < me.top_role:
        try:
            await member.kick(reason="بوت بصلاحيات عالية أُضيف دون إذن من الإدارة")
            await log(
                guild, "High-Risk Bot Removed", member, actor,
                "تم طرد بوت بصلاحيات عالية أُضيف دون إذن.",
                "الصلاحيات: " + ", ".join(dangerous),
            )
            return
        except discord.HTTPException as exc:
            error = str(exc)
    else:
        error = "رتبة البوت لا تسمح بطرد هذا البوت."

    await log(
        guild, "High-Risk Bot Alert", member, actor,
        f"رُصد بوت بصلاحيات عالية ولم يُطرد. {error}",
        "الصلاحيات: " + ", ".join(dangerous),
    )


async def protect_join(member: discord.Member) -> None:
    guild = member.guild
    if not cfg_of(guild.id)["protection"]:
        return
    if member.bot:
        spawn(check_bot_join(member))
        return

    now = time.monotonic()
    joins = JOIN_HISTORY[guild.id]
    joins.append(now)
    if sum(1 for t in joins if now - t <= 20) >= 8 and RAID_UNTIL.get(guild.id, 0) < now:
        RAID_UNTIL[guild.id] = now + 120
        await log(
            guild, "Join Raid Alert", None, bot.user,
            "رُصدت موجة انضمام سريعة. تم تفعيل تقييد الحسابات الجديدة لمدة دقيقتين.",
        )

    if RAID_UNTIL.get(guild.id, 0) > now and discord.utils.utcnow() - member.created_at < timedelta(days=3):
        ok, _ = await apply_timeout(member, 600, "حماية موجة انضمام: حساب حديث")
        if ok:
            await log(guild, "Raid Account Restricted", member, bot.user, "تم تقييد حساب حديث مؤقتًا.")


async def watch_destructive(guild, target_id, action, label) -> None:
    if not cfg_of(guild.id)["protection"]:
        return
    await asyncio.sleep(1)
    actor = await find_audit_actor(guild, action, target_id)
    if actor is None or actor.id in (guild.owner_id, bot.user.id):
        return

    now = time.monotonic()
    history = DESTRUCTIVE[(guild.id, actor.id, label)]
    history.append(now)
    while history and now - history[0] > 15:
        history.popleft()
    if len(history) < 3:
        return
    history.clear()

    reason = f"مؤشر تخريب: {label} 3 مرات خلال 15 ثانية."
    member = guild.get_member(actor.id)
    if member is None:
        await log(guild, "Anti-Nuke Alert", actor, bot.user, reason)
        return
    ok, error = await apply_timeout(member, 3600, reason)
    await log(guild, "Anti-Nuke Alert", member, bot.user, reason, None if ok else f"تعذر التايم اوت: {error}")


# ============================================================
# الطرد الجماعي (مالك السيرفر فقط)
# ============================================================

def plan_mass_kick(guild: discord.Guild) -> tuple[list[discord.Member], int, int]:
    me = guild.me
    if me is None:
        return [], 0, 0
    targets: list[discord.Member] = []
    bots = 0
    locked = 0
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


async def run_mass_kick(guild: discord.Guild, requester: discord.Member, status: Optional[discord.Message]) -> None:
    MASS_KICK_RUNNING.add(guild.id)
    try:
        targets, bots, locked = plan_mass_kick(guild)
        total = len(targets)
        kicked = 0
        failed = 0
        for index, member in enumerate(targets, 1):
            try:
                await member.kick(reason=MASS_KICK_REASON)
                kicked += 1
            except discord.NotFound:
                pass  # غادر قبل أن نطرده
            except discord.HTTPException:
                failed += 1
            if index % 20 == 0:
                await edit_quietly(status, f"⏳ جاري الطرد: {index}/{total}")
            await asyncio.sleep(0.35)

        summary = f"✅ اكتمل الطرد الجماعي. تم طرد **{kicked}** عضو."
        await edit_quietly(status, summary)
        await log(
            guild, "Mass Kick", None, requester,
            f"تم طرد {kicked} عضو بأمر من مالك السيرفر.",
            f"فشل: {failed} | بوتات مستثناة: {bots} | رتب أعلى من البوت: {locked}",
        )
    finally:
        MASS_KICK_RUNNING.discard(guild.id)


# ============================================================
# زر التأكيد (زران: تأكيد / إلغاء)
# ============================================================

class ConfirmView(discord.ui.View):
    def __init__(
        self,
        author: discord.Member,
        owner_only: bool,
        label: str,
        style: discord.ButtonStyle,
        handler: Callable[[discord.Interaction], Awaitable[None]],
    ):
        super().__init__(timeout=60)
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
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            return False
        if member.id != self.author_id:
            await interaction.response.send_message("هذا التأكيد لصاحب الأمر فقط.", ephemeral=True)
            return False
        level = "owner" if self.owner_only else "config"
        if not has_level(member, guild, level):
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
        try:
            await self.message.edit(content="انتهت مهلة التأكيد، لم يحدث شيء.", embed=None, view=None)
        except discord.HTTPException:
            pass


# ============================================================
# البوت
# ============================================================

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
)


def config_text(guild: discord.Guild, cfg: dict) -> str:
    def role_mention(key: str) -> str:
        rid = cfg.get(key)
        role = guild.get_role(int(rid)) if rid else None
        return role.mention if role else "غير محددة"

    channel_id = cfg.get("log_channel_id")
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    trusted = ", ".join(str(x) for x in cfg["trusted_bot_ids"]) or "لا يوجد"

    shortcut_lines = []
    for label, action in SHORTCUT_TYPES.items():
        names = cfg["shortcuts"].get(action, [])
        shortcut_lines.append(f"• `{label}`: " + (", ".join(f"`{n}`" for n in names) or "معطّل"))

    return (
        "**🛡️ إعدادات النظام**\n"
        f"الحماية التلقائية: {'✅ تعمل' if cfg['protection'] else '⏸️ متوقفة'}\n"
        f"رتبة الإدارة: {role_mention('admin_role_id')}\n"
        f"رتبة الحظر: {role_mention('ban_role_id')}\n"
        f"رتبة الطرد: {role_mention('kick_role_id')}\n"
        f"روم اللوق: {channel.mention if isinstance(channel, discord.TextChannel) else 'غير محدد'}\n"
        f"بوتات موثوقة: {trusted}\n\n"
        "**الاختصارات (بدون !):**\n" + "\n".join(shortcut_lines) + "\n\n"
        "**التعديل:**\n"
        "`!اعداد رتبة ادارة @رتبة` | `!اعداد رتبة حظر @رتبة` | `!اعداد رتبة طرد @رتبة`\n"
        "`!اعداد لوق #روم` (بدون روم = تعطيل)\n"
        "`!اعداد اختصار حظر كلمة1 كلمة2` (`-` للتعطيل)\n"
        "`!اعداد بوت_موثوق ID` (إضافة/إزالة)"
    )


async def handle_shortcut(message: discord.Message) -> bool:
    guild = message.guild
    member = message.author
    if not isinstance(member, discord.Member):
        return False

    cfg = cfg_of(guild.id)
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
    if not has_level(member, guild, level):
        await message.channel.send(LEVEL_MSG[level], delete_after=6)
        return True

    if action == "clear":
        if len(parts) < 2 or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 100:
            await message.channel.send("استخدمه كذا: `مسح 20` (من 1 إلى 100).", delete_after=6)
            return True
        _, text = await op_clear(guild, message.channel, member, int(parts[1]), message)
        await delete_quietly(message)
        await message.channel.send(text, delete_after=6, allowed_mentions=NO_MENTIONS)
        return True

    target = await resolve_member(guild, parts[1]) if len(parts) > 1 else None
    if target is None:
        await message.channel.send("حدد العضو بمنشن أو ID.", delete_after=6)
        return True

    if action == "timeout":
        if len(parts) < 3:
            await message.channel.send("استخدمه كذا: `تايم_اوت @العضو 10m السبب`", delete_after=6)
            return True
        seconds = parse_duration(parts[2])
        if seconds is None:
            await message.channel.send("المدة غير صحيحة. مثال: `10m` أو `2h` أو `1d`.", delete_after=6)
            return True
        _, text = await op_timeout(guild, member, target, seconds, clean_reason(" ".join(parts[3:])))
    elif action == "warn":
        _, text = await op_warn(guild, member, target, clean_reason(" ".join(parts[2:])))
    elif action == "ban":
        _, text = await op_ban(guild, member, target, clean_reason(" ".join(parts[2:])))
    else:  # kick
        _, text = await op_kick(guild, member, target, clean_reason(" ".join(parts[2:])))

    await delete_quietly(message)
    await message.channel.send(text, delete_after=8, allowed_mentions=NO_MENTIONS)
    return True


# ============================================================
# الأحداث
# ============================================================

@bot.event
async def on_ready():
    print("=" * 60)
    print(f"تم تشغيل البوت: {bot.user} | ID: {bot.user.id}")
    print(f"السيرفرات: {len(bot.guilds)} | discord.py {discord.__version__}")
    print("=" * 60)
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}مساعدة"))


@bot.event
async def on_message(message: discord.Message):
    if message.guild is not None and not message.author.bot:
        try:
            if await protect_message(message):
                return
            if not message.content.startswith(PREFIX) and await handle_shortcut(message):
                return
        except discord.HTTPException as exc:
            print(f"[MESSAGE] {exc}")
    await bot.process_commands(message)


@bot.event
async def on_member_join(member: discord.Member):
    await protect_join(member)


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    spawn(watch_destructive(channel.guild, channel.id, discord.AuditLogAction.channel_delete, "حذف القنوات"))


@bot.event
async def on_guild_role_delete(role: discord.Role):
    spawn(watch_destructive(role.guild, role.id, discord.AuditLogAction.role_delete, "حذف الرتب"))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.CheckFailure):
        text = str(error) or "ما عندك صلاحية."
    elif isinstance(error, commands.MissingRequiredArgument):
        text = f"ناقصك `{error.param.name}`. استخدم `!مساعدة`."
    elif isinstance(error, commands.BadArgument):
        text = "ما قدرت أفهم المدخلات أو ما لقيت العضو/الرتبة/الروم."
    else:
        original = getattr(error, "original", error)
        print(f"[COMMAND ERROR] {type(original).__name__}: {original}")
        text = "حدث خطأ غير متوقع أثناء تنفيذ الأمر."
    try:
        await ctx.send(text, delete_after=8)
    except discord.HTTPException:
        pass


# ============================================================
# الأوامر
# ============================================================

@bot.command(name="مساعدة", aliases=["مساعده"])
async def cmd_help(ctx: commands.Context):
    await ctx.send(
        "**🛡️ bot7 - الأوامر**\n"
        "**الإدارة:** `!حظر @عضو السبب` | `!طرد @عضو السبب` | `!تايم_اوت @عضو 10m السبب` | `!فك_التايم @عضو`\n"
        "**التحذيرات:** `!تحذير @عضو السبب` | `!تحذيرات @عضو` | `!حذف_تحذيرات @عضو`\n"
        "**أخرى:** `!فك_الحظر ID` | `!مسح 20`\n"
        "**الإعداد:** `!اعداد` (عرض وتعديل الرتب واللوق والاختصارات)\n"
        "**الحماية:** `!مراقبة_تلقائية` (تشغيل/إيقاف مع تأكيد)\n"
        "**مالك السيرفر فقط:** `!طرد_الكل` (طرد كل الأعضاء ما عدا البوتات، مع تأكيد)\n"
        "الاختصارات تعمل بدون `!` بعد ضبطها من `!اعداد`.",
        allowed_mentions=NO_MENTIONS,
    )


@bot.command(name="اعداد", aliases=["إعداد", "config"])
@requires("config")
async def cmd_config(ctx: commands.Context, *args: str):
    guild = ctx.guild
    cfg = cfg_of(guild.id)
    if not args:
        await ctx.send(config_text(guild, cfg), allowed_mentions=NO_MENTIONS)
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
        await persist()
        await ctx.send(f"تم تحديد {role.mention}.", allowed_mentions=NO_MENTIONS)
        return

    if sub == "لوق":
        if not ctx.message.channel_mentions:
            cfg["log_channel_id"] = None
            await persist()
            await ctx.send("تم تعطيل اللوق.")
            return
        channel = ctx.message.channel_mentions[0]
        cfg["log_channel_id"] = channel.id
        await persist()
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
            cleaned = []
            for alias in raw:
                if alias.startswith(PREFIX) or " " in alias or alias in cleaned:
                    continue
                cleaned.append(alias)
            if not cleaned:
                await ctx.send("حدد اختصارًا واحدًا على الأقل بدون مسافات.")
                return
            cfg["shortcuts"][action] = cleaned
        await persist()
        names = cfg["shortcuts"][action]
        await ctx.send(f"تم تحديث اختصارات **{norm(args[1])}**: " + (", ".join(f"`{n}`" for n in names) or "معطّل"))
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
        await persist()
        await ctx.send(text)
        return

    await ctx.send("صيغة غير معروفة. استخدم `!مساعدة` أو `!اعداد` لعرض الإعدادات.")


@bot.command(name="مراقبة_تلقائية", aliases=["مراقبة", "الحماية"])
@requires("config")
async def cmd_protection(ctx: commands.Context):
    guild = ctx.guild
    turning_on = not cfg_of(guild.id)["protection"]

    async def apply(interaction: discord.Interaction) -> None:
        cfg_of(guild.id)["protection"] = turning_on
        await persist()
        state = "✅ تم تشغيل الحماية التلقائية." if turning_on else "⏸️ تم إيقاف الحماية التلقائية."
        await interaction.response.edit_message(content=state, embed=None, view=None)

    embed = discord.Embed(
        title="🛡️ تأكيد الحماية التلقائية" if turning_on else "⏸️ تأكيد إيقاف الحماية",
        color=discord.Color.orange(),
        description=(
            "الحماية تشمل: سبام الرسائل والتكرار، المنشنات الزائدة، سبام الصور والمرفقات، "
            "إغراق الأحرف والروابط، موجات الانضمام، البوتات عالية الصلاحيات، وتخريب القنوات والرتب."
            if turning_on else
            "سيتم إيقاف كل الحمايات التلقائية حتى تقوم بتشغيلها مرة أخرى."
        ),
    )
    view = ConfirmView(
        ctx.author, owner_only=False,
        label="تأكيد التشغيل" if turning_on else "تأكيد الإيقاف",
        style=discord.ButtonStyle.success if turning_on else discord.ButtonStyle.danger,
        handler=apply,
    )
    view.message = await ctx.send(embed=embed, view=view)


@bot.command(name="طرد_الكل", aliases=["kickall"])
@requires("owner")
async def cmd_kick_all(ctx: commands.Context):
    guild = ctx.guild
    if not bot_has(guild, "kick_members"):
        await ctx.send("البوت يحتاج صلاحية Kick Members.")
        return
    if guild.id in MASS_KICK_RUNNING:
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
            "لن يرسل البوت أي رسالة للأعضاء المطرودين. العملية لا يمكن التراجع عنها."
        ),
    )
    embed.add_field(name="سيتم طرد", value=f"**{len(targets)}** عضو", inline=True)
    embed.add_field(name="بوتات مستثناة", value=f"{bots_count}", inline=True)
    embed.add_field(name="رتب أعلى من البوت", value=f"{locked}", inline=True)

    async def start(interaction: discord.Interaction) -> None:
        if guild.id in MASS_KICK_RUNNING:
            await interaction.response.edit_message(content="⚠️ هناك عملية طرد جارية بالفعل.", embed=None, view=None)
            return
        await interaction.response.edit_message(content="⏳ جاري الطرد...", embed=None, view=None)
        spawn(run_mass_kick(guild, ctx.author, interaction.message))

    view = ConfirmView(
        ctx.author, owner_only=True,
        label="تأكيد طرد الكل",
        style=discord.ButtonStyle.danger,
        handler=start,
    )
    view.message = await ctx.send(embed=embed, view=view)


@bot.command(name="حظر", aliases=["ban"])
@requires("ban")
async def cmd_ban(ctx: commands.Context, member: discord.Member, *, reason: str = ""):
    _, text = await op_ban(ctx.guild, ctx.author, member, clean_reason(reason))
    await ctx.send(text, allowed_mentions=NO_MENTIONS)


@bot.command(name="فك_الحظر", aliases=["unban"])
@requires("ban")
async def cmd_unban(ctx: commands.Context, user_id: int):
    if not bot_has(ctx.guild, "ban_members"):
        await ctx.send("البوت يحتاج صلاحية Ban Members.")
        return
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=f"فك حظر بواسطة {ctx.author}")
    except discord.NotFound:
        await ctx.send("المستخدم غير محظور أو الـID غير صحيح.")
        return
    except discord.HTTPException as exc:
        await ctx.send(f"فشل فك الحظر: {exc}")
        return
    await log(ctx.guild, "Unban", user, ctx.author, "فك حظر")
    await ctx.send(f"تم فك الحظر عن `{user}`.")


@bot.command(name="طرد", aliases=["kick"])
@requires("kick")
async def cmd_kick(ctx: commands.Context, member: discord.Member, *, reason: str = ""):
    _, text = await op_kick(ctx.guild, ctx.author, member, clean_reason(reason))
    await ctx.send(text, allowed_mentions=NO_MENTIONS)


@bot.command(name="تايم_اوت", aliases=["timeout", "تايم"])
@requires("manage")
async def cmd_timeout(ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = ""):
    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send("صيغة المدة: `10m` أو `2h` أو `1d` أو رقم فقط كدقائق. الحد الأعلى 28 يوم.")
        return
    _, text = await op_timeout(ctx.guild, ctx.author, member, seconds, clean_reason(reason))
    await ctx.send(text, allowed_mentions=NO_MENTIONS)


@bot.command(name="فك_التايم", aliases=["untimeout"])
@requires("manage")
async def cmd_untimeout(ctx: commands.Context, member: discord.Member):
    _, text = await op_untimeout(ctx.guild, ctx.author, member)
    await ctx.send(text, allowed_mentions=NO_MENTIONS)


@bot.command(name="تحذير", aliases=["warn"])
@requires("manage")
async def cmd_warn(ctx: commands.Context, member: discord.Member, *, reason: str = ""):
    _, text = await op_warn(ctx.guild, ctx.author, member, clean_reason(reason))
    await ctx.send(text, allowed_mentions=NO_MENTIONS)


@bot.command(name="تحذيرات", aliases=["warnings"])
@requires("manage")
async def cmd_warnings(ctx: commands.Context, member: discord.Member):
    items = cfg_of(ctx.guild.id)["warnings"].get(str(member.id), [])
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


@bot.command(name="حذف_تحذيرات", aliases=["مسح_تحذيرات"])
@requires("manage")
async def cmd_clear_warnings(ctx: commands.Context, member: discord.Member):
    removed = len(cfg_of(ctx.guild.id)["warnings"].pop(str(member.id), []))
    await persist()
    await log(ctx.guild, "Clear Warnings", member, ctx.author, f"حذف {removed} تحذير")
    await ctx.send(f"تم حذف **{removed}** تحذير عن {member.mention}.", allowed_mentions=NO_MENTIONS)


@bot.command(name="مسح", aliases=["clear"])
@requires("manage")
async def cmd_clear(ctx: commands.Context, amount: int):
    if not 1 <= amount <= 100:
        await ctx.send("حدد رقمًا من 1 إلى 100.")
        return
    _, text = await op_clear(ctx.guild, ctx.channel, ctx.author, amount, ctx.message)
    await delete_quietly(ctx.message)
    await ctx.send(text, delete_after=6)


# ============================================================
# التشغيل
# ============================================================

if __name__ == "__main__":
    load_db()
    if not TOKEN:
        raise SystemExit("ضع التوكن في متغير البيئة BOT_TOKEN.")
    bot.run(TOKEN)