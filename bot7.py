# -*- coding: utf-8 -*-
"""
bot7.py - نظام إدارة ومراقبة متكامل لـ Discord باستخدام discord.py 2.x

الميزات:
- تحديد رتبة الإدارة التي يسمح لها بالتحذير والتايم اوت ومسح الرسائل.
- تحديد رتبة الحظر ورتبة الطرد.
- اختصارات بدون prefix للحظر والطرد والتحذير والتايم اوت والمسح.
- مكافحة سبام الرسائل.
- مكافحة سبام المنشنات.
- مكافحة سبام الصور/المرفقات والستيكرات.
- نظام تحذيرات محفوظ في bot7_data.json.
- لوق للإجراءات الإدارية.
- أوامر فك الحظر وإلغاء التايم اوت وعرض التحذيرات.

تحتاج discord.py 2.x:
    pip install -U discord.py

وتحتاج تفعيل Message Content Intent و Server Members Intent
من Discord Developer Portal > Bot > Privileged Gateway Intents.
"""

import asyncio
import json
import os
import re
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

# ============================================================
# إعدادات عامة
# ============================================================

PREFIX = "!"
DATA_FILE = Path("bot7_data.json")

# في الاستضافة ضع متغير البيئة BOT_TOKEN.
# ويمكن وضع التوكن مكان PUT_BOT_TOKEN_HERE عند الحاجة.

DEFAULT_GUILD_CONFIG = {
    "admin_role_id": None,
    "ban_role_id": None,
    "kick_role_id": None,
    "log_channel_id": None,

    "anti_spam_enabled": True,
    "spam_message_limit": 6,
    "spam_window_seconds": 8,
    "spam_timeout_minutes": 10,

    "anti_mentions_enabled": True,
    "max_mentions": 5,
    "mention_timeout_minutes": 5,

    "anti_media_enabled": True,
    "media_limit": 4,
    "media_window_seconds": 10,
    "media_timeout_minutes": 5,

    # اختصارات تعمل بدون prefix.
    "shortcuts": {
        "ban": ["حظر"],
        "kick": ["طرد"],
        "clear": ["مسح"],
        "warn": ["تحذير"],
        "timeout": ["تايم_اوت"],
    },

    # الأشخاص الذين تم تحذيرهم:
    # {"user_id": [{"reason": "...", "moderator_id": 123, "timestamp": "..."}]}
    "warnings": {},
}


def copy_default_config() -> dict:
    return json.loads(json.dumps(DEFAULT_GUILD_CONFIG, ensure_ascii=False))


try:
    with DATA_FILE.open("r", encoding="utf-8") as f:
        DATABASE = json.load(f)
        if not isinstance(DATABASE, dict):
            DATABASE = {}
except (FileNotFoundError, json.JSONDecodeError, OSError):
    DATABASE = {}


def get_config(guild_id: int) -> dict:
    key = str(guild_id)
    if key not in DATABASE or not isinstance(DATABASE[key], dict):
        DATABASE[key] = copy_default_config()
        return DATABASE[key]

    # إضافة أي مفاتيح ناقصة بعد تحديث الكود.
    changed = False
    for k, v in DEFAULT_GUILD_CONFIG.items():
        if k not in DATABASE[key]:
            DATABASE[key][k] = json.loads(json.dumps(v, ensure_ascii=False))
            changed = True

    if not isinstance(DATABASE[key].get("shortcuts"), dict):
        DATABASE[key]["shortcuts"] = json.loads(json.dumps(DEFAULT_GUILD_CONFIG["shortcuts"], ensure_ascii=False))
        changed = True

    for action, aliases in DEFAULT_GUILD_CONFIG["shortcuts"].items():
        if action not in DATABASE[key]["shortcuts"] or not isinstance(DATABASE[key]["shortcuts"][action], list):
            DATABASE[key]["shortcuts"][action] = list(aliases)
            changed = True

    if not isinstance(DATABASE[key].get("warnings"), dict):
        DATABASE[key]["warnings"] = {}
        changed = True

    if changed:
        save_database()

    return DATABASE[key]


def save_database() -> None:
    temp_file = DATA_FILE.with_suffix(".tmp")
    try:
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(DATABASE, f, ensure_ascii=False, indent=2)
        temp_file.replace(DATA_FILE)
    except OSError as exc:
        print(f"[DATABASE ERROR] {exc}")


# قفل بسيط لمنع تداخل عمليات حفظ البيانات.
DB_LOCK = asyncio.Lock()


async def save_database_async() -> None:
    async with DB_LOCK:
        await asyncio.to_thread(save_database)


# ============================================================
# أدوات مساعدة
# ============================================================


def normalize_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def role_is_set(member: discord.Member, role_id: Optional[int]) -> bool:
    if not role_id:
        return False
    return any(role.id == int(role_id) for role in member.roles)


def is_server_admin(member: discord.Member) -> bool:
    return member.guild.owner_id == member.id or member.guild_permissions.administrator


def has_management_role(member: discord.Member, cfg: dict) -> bool:
    if is_server_admin(member):
        return True
    return role_is_set(member, cfg.get("admin_role_id"))


def has_ban_role(member: discord.Member, cfg: dict) -> bool:
    if is_server_admin(member):
        return True
    return role_is_set(member, cfg.get("ban_role_id"))


def has_kick_role(member: discord.Member, cfg: dict) -> bool:
    if is_server_admin(member):
        return True
    return role_is_set(member, cfg.get("kick_role_id"))


def bot_member(guild: discord.Guild) -> Optional[discord.Member]:
    return guild.me or (bot.user and guild.get_member(bot.user.id))


def can_bot_moderate_target(guild: discord.Guild, target: discord.Member) -> tuple[bool, str]:
    me = bot_member(guild)
    if me is None:
        return False, "ما قدرت أحدد رتبة البوت داخل السيرفر."

    if target.id == guild.owner_id:
        return False, "ما أقدر أطبق عقوبة على مالك السيرفر."

    if target.id == me.id:
        return False, "ما ينفع أعاقب نفسي، خلونا نترك البوت يعيش."

    if target.top_role >= me.top_role:
        return False, "رتبة العضو مساوية أو أعلى من أعلى رتبة عند البوت. ارفع رتبة البوت."

    return True, ""


def has_bot_permission(guild: discord.Guild, permission: str) -> bool:
    me = bot_member(guild)
    if me is None:
        return False
    return getattr(me.guild_permissions, permission, False)


def parse_duration(value: str) -> Optional[int]:
    """ترجع المدة بالثواني. رقم مجرد = دقائق."""
    value = value.strip().lower()
    if value.isdigit():
        minutes = int(value)
        return minutes * 60 if minutes > 0 else None

    match = re.fullmatch(r"(\d+)\s*([smhd]|ث|د|س|ي|ثانية|دقيقة|ساعة|يوم)", value)
    if not match:
        return None

    number = int(match.group(1))
    unit = match.group(2)
    if number <= 0:
        return None

    if unit in ("s", "ث", "ثانية"):
        return number
    if unit in ("m", "د", "دقيقة"):
        return number * 60
    if unit in ("h", "س", "ساعة"):
        return number * 60 * 60
    if unit in ("d", "ي", "يوم"):
        return number * 24 * 60 * 60

    return None


def duration_text(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400} يوم"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} ساعة"
    if seconds % 60 == 0:
        return f"{seconds // 60} دقيقة"
    return f"{seconds} ثانية"


def is_image_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").lower()
    if content_type.startswith("image/"):
        return True
    suffix = Path(attachment.filename).suffix.lower()
    return suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"}


def message_is_media(message: discord.Message) -> bool:
    has_image = any(is_image_attachment(a) for a in message.attachments)
    has_sticker = bool(message.stickers)
    return has_image or has_sticker


def mention_count(message: discord.Message) -> int:
    count = len(message.mentions) + len(message.role_mentions)
    if message.mention_everyone:
        count += 1
    return count


def format_reason(reason: str, fallback: str) -> str:
    reason = reason.strip()
    return reason[:450] if reason else fallback


async def delete_message_safely(message: discord.Message) -> None:
    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def send_log(
    guild: discord.Guild,
    action: str,
    target: Optional[discord.abc.User],
    moderator: Optional[discord.abc.User],
    reason: str,
    extra: Optional[str] = None,
) -> None:
    cfg = get_config(guild.id)
    channel_id = cfg.get("log_channel_id")
    if not channel_id:
        return

    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return

    embed = discord.Embed(title=f"🛡️ {action}", description=reason[:4000])
    if target is not None:
        embed.add_field(name="العضو", value=f"{target.mention} (`{target.id}`)", inline=False)
    if moderator is not None:
        embed.add_field(name="بواسطة", value=f"{moderator.mention} (`{moderator.id}`)", inline=False)
    if extra:
        embed.add_field(name="تفاصيل", value=extra[:1024], inline=False)

    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except (discord.Forbidden, discord.HTTPException):
        pass


async def apply_timeout(
    target: discord.Member,
    seconds: int,
    reason: str,
    moderator: Optional[discord.abc.User],
) -> tuple[bool, str]:
    guild = target.guild
    if seconds > 28 * 24 * 60 * 60:
        return False, "الـ timeout في Discord حده الأقصى 28 يومًا."

    if not has_bot_permission(guild, "moderate_members"):
        return False, "البوت يحتاج صلاحية Moderate Members."

    ok, error = can_bot_moderate_target(guild, target)
    if not ok:
        return False, error

    try:
        await target.timeout(timedelta(seconds=seconds), reason=reason[:512])
        return True, ""
    except discord.Forbidden:
        return False, "Discord رفض العملية. تأكد من صلاحية Moderate Members وارتفاع رتبة البوت."
    except discord.HTTPException as exc:
        return False, f"حدث خطأ من Discord: {exc}"


async def add_warning(
    guild: discord.Guild,
    target: discord.Member,
    moderator: discord.Member,
    reason: str,
) -> int:
    cfg = get_config(guild.id)
    warnings = cfg.setdefault("warnings", {})
    key = str(target.id)
    warnings.setdefault(key, []).append({
        "reason": reason,
        "moderator_id": moderator.id,
        "timestamp": discord.utils.utcnow().isoformat(),
    })
    await save_database_async()
    return len(warnings[key])


async def resolve_member(guild: discord.Guild, token: str) -> Optional[discord.Member]:
    token = token.strip()
    mention_match = re.fullmatch(r"<@!?(\d+)>", token)
    if mention_match:
        user_id = int(mention_match.group(1))
    elif token.isdigit():
        user_id = int(token)
    else:
        user_id = None

    if user_id is not None:
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    normalized = normalize_text(token.lstrip("@"))
    for member in guild.members:
        candidates = {
            normalize_text(member.display_name),
            normalize_text(member.name),
            normalize_text(f"{member.name}#{member.discriminator}"),
        }
        if normalized in candidates:
            return member

    return None


async def parse_shortcut_target(guild: discord.Guild, parts: list[str], index: int = 1) -> tuple[Optional[discord.Member], str]:
    if len(parts) <= index:
        return None, "حدد العضو بمنشن أو ID."
    target = await resolve_member(guild, parts[index])
    if target is None:
        return None, "ما قدرت ألقى العضو. استخدم منشن أو ID."
    return target, ""


# ============================================================
# هياكل مراقبة السبام في الذاكرة
# ============================================================

MESSAGE_HISTORY: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
MEDIA_HISTORY: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
DUPLICATE_HISTORY: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=20))
LAST_AUTO_ACTION: dict[tuple[int, int], float] = {}


async def auto_moderate(message: discord.Message) -> bool:
    """ترجع True إذا تم تنفيذ عقوبة تلقائية."""
    if message.guild is None or message.author.bot:
        return False
    if not isinstance(message.author, discord.Member):
        return False

    guild = message.guild
    cfg = get_config(guild.id)
    author = message.author

    # الإدارة ومالك السيرفر مستثنون من مكافحة السبام.
    if is_server_admin(author) or has_management_role(author, cfg):
        return False

    now = discord.utils.utcnow().timestamp()
    key = (guild.id, author.id)

    # ---------------------- سبام المنشن ----------------------
    if cfg.get("anti_mentions_enabled", True):
        m_count = mention_count(message)
        max_mentions = int(cfg.get("max_mentions", 5))
        if m_count >= max_mentions and max_mentions > 0:
            timeout_minutes = max(1, int(cfg.get("mention_timeout_minutes", 5)))
            reason = f"سبام منشنات: {m_count} منشن في رسالة واحدة."
            await delete_message_safely(message)
            ok, error = await apply_timeout(author, timeout_minutes * 60, reason, bot.user)
            if ok:
                await send_log(guild, "Auto-Mention Anti-Spam", author, bot.user, reason)
                LAST_AUTO_ACTION[key] = now
                return True
            print(f"[AUTO MODERATION] {error}")

    # ---------------------- سبام الرسائل ----------------------
    spam_window = max(1, int(cfg.get("spam_window_seconds", 8)))
    spam_limit = max(1, int(cfg.get("spam_message_limit", 6)))
    history = MESSAGE_HISTORY[key]
    history.append(now)
    while history and history[0] < now - spam_window:
        history.popleft()

    if cfg.get("anti_spam_enabled", True) and len(history) >= spam_limit:
        # منع تكرار العقوبة عدة مرات خلال نافذة قصيرة.
        last_action = LAST_AUTO_ACTION.get(key, 0)
        if now - last_action >= spam_window:
            timeout_minutes = max(1, int(cfg.get("spam_timeout_minutes", 10)))
            reason = f"سبام رسائل: {len(history)} رسائل خلال {spam_window} ثوانٍ."
            await delete_message_safely(message)
            ok, error = await apply_timeout(author, timeout_minutes * 60, reason, bot.user)
            if ok:
                await send_log(guild, "Auto Message Anti-Spam", author, bot.user, reason)
                LAST_AUTO_ACTION[key] = now
                history.clear()
                return True
            print(f"[AUTO MODERATION] {error}")

    # ---------------------- سبام الصور/الستيكرات ----------------------
    if cfg.get("anti_media_enabled", True) and message_is_media(message):
        media_window = max(1, int(cfg.get("media_window_seconds", 10)))
        media_limit = max(1, int(cfg.get("media_limit", 4)))
        media_history = MEDIA_HISTORY[key]
        media_history.append(now)
        while media_history and media_history[0] < now - media_window:
            media_history.popleft()

        if len(media_history) >= media_limit:
            last_action = LAST_AUTO_ACTION.get(key, 0)
            if now - last_action >= media_window:
                timeout_minutes = max(1, int(cfg.get("media_timeout_minutes", 5)))
                reason = f"سبام صور/مرفقات/ستيكرات: {len(media_history)} خلال {media_window} ثوانٍ."
                await delete_message_safely(message)
                ok, error = await apply_timeout(author, timeout_minutes * 60, reason, bot.user)
                if ok:
                    await send_log(guild, "Auto Media Anti-Spam", author, bot.user, reason)
                    LAST_AUTO_ACTION[key] = now
                    media_history.clear()
                    return True
                print(f"[AUTO MODERATION] {error}")

    # ---------------------- تكرار نفس الرسالة ----------------------
    text = normalize_text(message.content)
    if text:
        dup_history = DUPLICATE_HISTORY[key]
        dup_history.append((now, text))
        duplicate_window = spam_window
        same_count = sum(1 for ts, old_text in dup_history if ts >= now - duplicate_window and old_text == text)
        if cfg.get("anti_spam_enabled", True) and same_count >= spam_limit:
            last_action = LAST_AUTO_ACTION.get(key, 0)
            if now - last_action >= spam_window:
                timeout_minutes = max(1, int(cfg.get("spam_timeout_minutes", 10)))
                reason = f"تكرار رسالة بشكل سبامي: نفس الرسالة {same_count} مرات خلال {duplicate_window} ثوانٍ."
                await delete_message_safely(message)
                ok, error = await apply_timeout(author, timeout_minutes * 60, reason, bot.user)
                if ok:
                    await send_log(guild, "Auto Duplicate Anti-Spam", author, bot.user, reason)
                    LAST_AUTO_ACTION[key] = now
                    dup_history.clear()
                    return True
                print(f"[AUTO MODERATION] {error}")

    return False


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
    strip_after_prefix=True,
)


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"تم تشغيل البوت: {bot.user} | ID: {bot.user.id}")
    print(f"السيرفرات: {len(bot.guilds)}")
    print(f"discord.py: {discord.__version__}")
    print("=" * 60)
    try:
        await bot.change_presence(activity=discord.Game(name=f"الإدارة | {PREFIX}مساعدة"))
    except discord.HTTPException:
        pass


@bot.event
async def on_guild_join(guild: discord.Guild):
    get_config(guild.id)
    await save_database_async()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild is not None:
        try:
            await auto_moderate(message)
        except Exception as exc:
            print(f"[AUTO MODERATION ERROR] {type(exc).__name__}: {exc}")

        # الاختصارات تعمل فقط على الرسائل بدون prefix.
        if not message.content.startswith(PREFIX):
            handled = await handle_prefixless_shortcut(message)
            if handled:
                return



# ============================================================
# تحقق من الصلاحيات
# ============================================================

async def require_config_permission(ctx: commands.Context) -> bool:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("هذا الأمر داخل السيرفر فقط.")
        return False
    if not is_server_admin(ctx.author):
        await ctx.send("هذا الأمر لمالك السيرفر أو لمن يملك Administrator فقط.")
        return False
    return True


async def require_management_permission(ctx: commands.Context) -> bool:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("هذا الأمر داخل السيرفر فقط.")
        return False
    cfg = get_config(ctx.guild.id)
    if not has_management_role(ctx.author, cfg):
        await ctx.send("ما عندك رتبة الإدارة المسموح لها بهذا الأمر.")
        return False
    return True


async def require_ban_permission(ctx: commands.Context) -> bool:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("هذا الأمر داخل السيرفر فقط.")
        return False
    cfg = get_config(ctx.guild.id)
    if not has_ban_role(ctx.author, cfg):
        await ctx.send("ما عندك رتبة الحظر المسموح لها بهذا الأمر.")
        return False
    return True


async def require_kick_permission(ctx: commands.Context) -> bool:
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        await ctx.send("هذا الأمر داخل السيرفر فقط.")
        return False
    cfg = get_config(ctx.guild.id)
    if not has_kick_role(ctx.author, cfg):
        await ctx.send("ما عندك رتبة الطرد المسموح لها بهذا الأمر.")
        return False
    return True


# ============================================================
# أوامر المالك / الإعداد
# ============================================================

@bot.command(name="مساعدة", aliases=["مساعده"])
async def help_command(ctx: commands.Context):
    embed = discord.Embed(title="🛡️ نظام الإدارة - bot7", description="كل أوامر الإدارة الأساسية موجودة هنا.")
    embed.add_field(
        name="⚙️ الإعداد",
        value=(
            "`!اختصارات` لعرض كل الإعدادات.\n"
            "`!اختصارات ادارة @رتبة`\n"
            "`!اختصارات حظر_رتبة @رتبة`\n"
            "`!اختصارات طرد_رتبة @رتبة`\n"
            "`!لوق #روم`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔨 الإدارة",
        value=(
            "`!حظر @عضو السبب`\n"
            "`!طرد @عضو السبب`\n"
            "`!تايم_اوت @عضو 10m السبب`\n"
            "`!تحذير @عضو السبب`\n"
            "`!مسح 20`\n"
            "`!فك_التايم @عضو`\n"
            "`!تحذيرات @عضو`\n"
            "`!حذف_تحذيرات @عضو`\n"
            "`!فك_الحظر ID`"
        ),
        inline=False,
    )
    embed.add_field(
        name="🤖 المراقبة التلقائية",
        value=(
            "`!مكافحة_السبام 6 8 10`\n"
            "`!مكافحة_المنشن 5 5`\n"
            "`!مكافحة_الوسائط 4 10 5`\n"
            "آخر رقم في كل أمر = مدة التايم اوت بالدقائق."
        ),
        inline=False,
    )
    embed.set_footer(text="الاختصارات تعمل بدون ! بعد ضبطها، لأن البشر قرروا أن prefix هو عمل إضافي ضروري.")
    await ctx.send(embed=embed)


@bot.command(name="اختصارات")
async def shortcuts(ctx: commands.Context, action: Optional[str] = None, *values: str):
    if not await require_config_permission(ctx):
        return

    cfg = get_config(ctx.guild.id)

    if action is None:
        admin_role = ctx.guild.get_role(int(cfg["admin_role_id"])) if cfg.get("admin_role_id") else None
        ban_role = ctx.guild.get_role(int(cfg["ban_role_id"])) if cfg.get("ban_role_id") else None
        kick_role = ctx.guild.get_role(int(cfg["kick_role_id"])) if cfg.get("kick_role_id") else None
        lines = [
            "**الرتب:**",
            f"الإدارة: {admin_role.mention if admin_role else 'غير محددة'}",
            f"الحظر: {ban_role.mention if ban_role else 'غير محددة'}",
            f"الطرد: {kick_role.mention if kick_role else 'غير محددة'}",
            "",
            "**الاختصارات الحالية:**",
        ]
        for name, aliases in cfg["shortcuts"].items():
            lines.append(f"`{name}`: " + (", ".join(f"`{a}`" for a in aliases) if aliases else "لا يوجد"))
        lines += [
            "",
            "**طريقة الإعداد:**",
            "`!اختصارات ادارة @رتبة`",
            "`!اختصارات حظر_رتبة @رتبة`",
            "`!اختصارات طرد_رتبة @رتبة`",
            "`!اختصارات حظر كلمة1 كلمة2`",
            "`!اختصارات طرد كلمة1 كلمة2`",
            "`!اختصارات تحذير كلمة1 كلمة2`",
            "`!اختصارات تايم_اوت كلمة1 كلمة2`",
            "`!اختصارات مسح كلمة1 كلمة2`",
            "لحذف كل الاختصارات لنوع معين: `!اختصارات حظر -`",
        ]
        await ctx.send("\n".join(lines))
        return

    action_n = normalize_text(action)

    # ---------------- الرتب داخل نفس الأمر ----------------
    role_actions = {
        "ادارة": "admin_role_id",
        "الادارة": "admin_role_id",
        "رتبة_الادارة": "admin_role_id",
        "حظر_رتبة": "ban_role_id",
        "رتبة_الحظر": "ban_role_id",
        "الطرد_رتبة": "kick_role_id",
        "رتبة_الطرد": "kick_role_id",
    }

    if action_n in role_actions:
        if not values:
            await ctx.send("منشن الرتبة. مثال: `!اختصارات ادارة @رتبة`")
            return
        role = await discord.RoleConverter().convert(ctx, values[0])
        if role.is_default():
            await ctx.send("لا يمكن استخدام @everyone كرتبة إدارة.")
            return
        cfg[role_actions[action_n]] = role.id
        await save_database_async()
        await ctx.send(f"تم تحديد {role.mention} لهذا النوع.", allowed_mentions=discord.AllowedMentions.none())
        return

    # ---------------- ضبط الاختصارات ----------------
    shortcut_map = {
        "حظر": "ban",
        "ban": "ban",
        "طرد": "kick",
        "kick": "kick",
        "مسح": "clear",
        "clear": "clear",
        "تحذير": "warn",
        "warn": "warn",
        "تايم_اوت": "timeout",
        "timeout": "timeout",
        "تايم": "timeout",
    }

    target_action = shortcut_map.get(action_n)
    if target_action is None:
        await ctx.send("نوع غير معروف. استخدم `!اختصارات` لعرض الخيارات.")
        return

    aliases = [normalize_text(v) for v in values if normalize_text(v)]
    if aliases == ["-"]:
        cfg["shortcuts"][target_action] = []
    else:
        cleaned = []
        for alias in aliases:
            if alias != PREFIX and not alias.startswith(PREFIX) and " " not in alias:
                if alias not in cleaned:
                    cleaned.append(alias)
        if not cleaned:
            await ctx.send("حدد اختصارًا واحدًا على الأقل. مثال: `!اختصارات حظر حظر بان`")
            return
        cfg["shortcuts"][target_action] = cleaned

    await save_database_async()
    await ctx.send(
        f"تم تحديث اختصارات **{target_action}**: "
        + (", ".join(f"`{x}`" for x in cfg["shortcuts"][target_action]) or "لا يوجد")
    )


@bot.command(name="لوق", aliases=["سجل", "روم_لوق"])
async def set_log(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    if not await require_config_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    if channel is None:
        cfg["log_channel_id"] = None
        await save_database_async()
        await ctx.send("تم تعطيل اللوق.")
        return
    cfg["log_channel_id"] = channel.id
    await save_database_async()
    await ctx.send(f"تم تحديد روم اللوق: {channel.mention}", allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="مكافحة_السبام")
async def anti_spam(ctx: commands.Context, message_limit: int, window_seconds: int, timeout_minutes: int):
    if not await require_config_permission(ctx):
        return
    if not (1 <= message_limit <= 50 and 1 <= window_seconds <= 120 and 1 <= timeout_minutes <= 40320):
        await ctx.send("القيم: الرسائل 1-50، الثواني 1-120، التايم اوت 1-40320 دقيقة.")
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_spam_enabled"] = True
    cfg["spam_message_limit"] = message_limit
    cfg["spam_window_seconds"] = window_seconds
    cfg["spam_timeout_minutes"] = timeout_minutes
    await save_database_async()
    await ctx.send(f"تم تفعيل سبام الرسائل: **{message_limit}** رسائل / **{window_seconds}** ثوانٍ -> تايم اوت **{timeout_minutes}** دقيقة.")


@bot.command(name="ايقاف_السبام")
async def disable_spam(ctx: commands.Context):
    if not await require_config_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_spam_enabled"] = False
    await save_database_async()
    await ctx.send("تم إيقاف مراقبة سبام الرسائل والتكرار.")


@bot.command(name="مكافحة_المنشن")
async def anti_mentions(ctx: commands.Context, max_mentions: int, timeout_minutes: int):
    if not await require_config_permission(ctx):
        return
    if not (1 <= max_mentions <= 50 and 1 <= timeout_minutes <= 40320):
        await ctx.send("القيم غير صحيحة.")
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_mentions_enabled"] = True
    cfg["max_mentions"] = max_mentions
    cfg["mention_timeout_minutes"] = timeout_minutes
    await save_database_async()
    await ctx.send(f"تم تفعيل مكافحة المنشن: **{max_mentions}** منشن أو أكثر -> تايم اوت **{timeout_minutes}** دقيقة.")


@bot.command(name="ايقاف_المنشن")
async def disable_mentions(ctx: commands.Context):
    if not await require_config_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_mentions_enabled"] = False
    await save_database_async()
    await ctx.send("تم إيقاف مكافحة سبام المنشنات.")


@bot.command(name="مكافحة_الوسائط")
async def anti_media(ctx: commands.Context, media_limit: int, window_seconds: int, timeout_minutes: int):
    if not await require_config_permission(ctx):
        return
    if not (1 <= media_limit <= 50 and 1 <= window_seconds <= 120 and 1 <= timeout_minutes <= 40320):
        await ctx.send("القيم غير صحيحة.")
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_media_enabled"] = True
    cfg["media_limit"] = media_limit
    cfg["media_window_seconds"] = window_seconds
    cfg["media_timeout_minutes"] = timeout_minutes
    await save_database_async()
    await ctx.send(f"تم تفعيل مكافحة الصور/المرفقات/الستيكرات: **{media_limit}** خلال **{window_seconds}** ثوانٍ -> تايم اوت **{timeout_minutes}** دقيقة.")


@bot.command(name="ايقاف_الوسائط")
async def disable_media(ctx: commands.Context):
    if not await require_config_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    cfg["anti_media_enabled"] = False
    await save_database_async()
    await ctx.send("تم إيقاف مكافحة سبام الصور/المرفقات/الستيكرات.")


# ============================================================
# أوامر الإدارة المباشرة
# ============================================================

@bot.command(name="حظر", aliases=["ban"])
async def ban(ctx: commands.Context, member: discord.Member, *, reason: str = "بدون سبب"):
    if not await require_ban_permission(ctx):
        return
    if not has_bot_permission(ctx.guild, "ban_members"):
        await ctx.send("البوت يحتاج صلاحية Ban Members.")
        return
    ok, error = can_bot_moderate_target(ctx.guild, member)
    if not ok:
        await ctx.send(error)
        return
    reason = format_reason(reason, "بدون سبب")
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
        await ctx.send(f"تم حظر {member.mention}.", allowed_mentions=discord.AllowedMentions.none())
        await send_log(ctx.guild, "Ban", member, ctx.author, reason)
    except discord.Forbidden:
        await ctx.send("Discord رفض الحظر. تأكد من رتبة البوت وصلاحية Ban Members.")
    except discord.HTTPException as exc:
        await ctx.send(f"خطأ من Discord: {exc}")


@bot.command(name="فك_الحظر", aliases=["unban"])
async def unban(ctx: commands.Context, user_id: str):
    if not await require_ban_permission(ctx):
        return
    if not user_id.isdigit():
        await ctx.send("اكتب ID المستخدم فقط.")
        return
    try:
        user = await bot.fetch_user(int(user_id))
        await ctx.guild.unban(user, reason=f"فك حظر بواسطة {ctx.author}")
        await ctx.send(f"تم فك الحظر عن `{user}`.")
        await send_log(ctx.guild, "Unban", user, ctx.author, "فك حظر")
    except discord.NotFound:
        await ctx.send("المستخدم غير محظور أو الـID غير صحيح.")
    except discord.Forbidden:
        await ctx.send("البوت يحتاج صلاحية Ban Members.")
    except discord.HTTPException as exc:
        await ctx.send(f"خطأ من Discord: {exc}")


@bot.command(name="طرد", aliases=["kick"])
async def kick(ctx: commands.Context, member: discord.Member, *, reason: str = "بدون سبب"):
    if not await require_kick_permission(ctx):
        return
    if not has_bot_permission(ctx.guild, "kick_members"):
        await ctx.send("البوت يحتاج صلاحية Kick Members.")
        return
    ok, error = can_bot_moderate_target(ctx.guild, member)
    if not ok:
        await ctx.send(error)
        return
    reason = format_reason(reason, "بدون سبب")
    try:
        await member.kick(reason=reason)
        await ctx.send(f"تم طرد {member.mention}.", allowed_mentions=discord.AllowedMentions.none())
        await send_log(ctx.guild, "Kick", member, ctx.author, reason)
    except discord.Forbidden:
        await ctx.send("Discord رفض الطرد. تأكد من رتبة البوت وصلاحية Kick Members.")
    except discord.HTTPException as exc:
        await ctx.send(f"خطأ من Discord: {exc}")


@bot.command(name="تايم_اوت", aliases=["timeout", "تايم"])
async def timeout_member(ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "بدون سبب"):
    if not await require_management_permission(ctx):
        return
    seconds = parse_duration(duration)
    if seconds is None:
        await ctx.send("صيغة المدة: `10m` أو `2h` أو `1d` أو رقم فقط كدقائق. الحد الأعلى 28 يوم.")
        return
    reason = format_reason(reason, "بدون سبب")
    ok, error = await apply_timeout(member, seconds, reason, ctx.author)
    if not ok:
        await ctx.send(error)
        return
    await ctx.send(
        f"تم إعطاء {member.mention} تايم اوت لمدة **{duration_text(seconds)}**.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@bot.command(name="فك_التايم", aliases=["untimeout"])
async def remove_timeout(ctx: commands.Context, member: discord.Member):
    if not await require_management_permission(ctx):
        return
    if not has_bot_permission(ctx.guild, "moderate_members"):
        await ctx.send("البوت يحتاج صلاحية Moderate Members.")
        return
    ok, error = can_bot_moderate_target(ctx.guild, member)
    if not ok:
        await ctx.send(error)
        return
    try:
        await member.timeout(None, reason=f"إلغاء تايم اوت بواسطة {ctx.author}")
        await ctx.send(f"تم إلغاء التايم اوت عن {member.mention}.", allowed_mentions=discord.AllowedMentions.none())
        await send_log(ctx.guild, "Remove Timeout", member, ctx.author, "إلغاء التايم اوت")
    except discord.Forbidden:
        await ctx.send("Discord رفض العملية. تأكد من صلاحية Moderate Members.")
    except discord.HTTPException as exc:
        await ctx.send(f"خطأ من Discord: {exc}")


@bot.command(name="تحذير", aliases=["warn"])
async def warn(ctx: commands.Context, member: discord.Member, *, reason: str = "بدون سبب"):
    if not await require_management_permission(ctx):
        return
    reason = format_reason(reason, "بدون سبب")
    count = await add_warning(ctx.guild, member, ctx.author, reason)
    await ctx.send(f"⚠️ تم تحذير {member.mention}. عدد تحذيراته الآن: **{count}**.", allowed_mentions=discord.AllowedMentions.none())
    await send_log(ctx.guild, "Warning", member, ctx.author, reason, f"إجمالي التحذيرات: {count}")


@bot.command(name="تحذيرات", aliases=["warnings"])
async def warnings(ctx: commands.Context, member: discord.Member):
    if not await require_management_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    items = cfg.get("warnings", {}).get(str(member.id), [])
    if not items:
        await ctx.send(f"{member.mention} ما عليه تحذيرات.", allowed_mentions=discord.AllowedMentions.none())
        return

    lines = [f"**تحذيرات {member}:**"]
    for i, item in enumerate(items[-20:], start=max(1, len(items) - 19)):
        moderator_id = item.get("moderator_id")
        mod = ctx.guild.get_member(int(moderator_id)) if moderator_id else None
        mod_text = mod.mention if mod else str(moderator_id or "غير معروف")
        reason = str(item.get("reason", "بدون سبب"))[:250]
        lines.append(f"`#{i}` بواسطة {mod_text}: {reason}")
    await ctx.send("\n".join(lines), allowed_mentions=discord.AllowedMentions.none())


@bot.command(name="حذف_تحذيرات", aliases=["مسح_تحذيرات"])
async def clear_warnings(ctx: commands.Context, member: discord.Member):
    if not await require_management_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    removed = len(cfg.setdefault("warnings", {}).pop(str(member.id), []))
    await save_database_async()
    await ctx.send(f"تم حذف **{removed}** تحذيرات عن {member.mention}.", allowed_mentions=discord.AllowedMentions.none())
    await send_log(ctx.guild, "Clear Warnings", member, ctx.author, "حذف جميع التحذيرات")


@bot.command(name="مسح", aliases=["clear"])
async def clear_messages(ctx: commands.Context, amount: int):
    if not await require_management_permission(ctx):
        return
    if not has_bot_permission(ctx.guild, "manage_messages"):
        await ctx.send("البوت يحتاج صلاحية Manage Messages.")
        return
    if not 1 <= amount <= 100:
        await ctx.send("حدد رقمًا من 1 إلى 100.")
        return
    if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
        await ctx.send("لا يمكن استخدام المسح هنا.")
        return

    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"تم مسح **{max(0, len(deleted) - 1)}** رسالة.", delete_after=3)
        await send_log(ctx.guild, "Clear Messages", None, ctx.author, f"مسح {amount} رسالة من #{ctx.channel}")
    except discord.Forbidden:
        await ctx.send("لا أملك صلاحية قراءة سجل الرسائل أو حذف الرسائل.")
    except discord.HTTPException as exc:
        await ctx.send(f"تعذر المسح: {exc}")


# ============================================================
# اختصارات بدون prefix
# ============================================================

async def handle_prefixless_shortcut(message: discord.Message) -> bool:
    if message.guild is None or not isinstance(message.author, discord.Member):
        return False

    cfg = get_config(message.guild.id)
    content = message.content.strip()
    if not content:
        return False

    parts = content.split()
    first = normalize_text(parts[0])

    action = None
    for action_name, aliases in cfg.get("shortcuts", {}).items():
        if any(first == normalize_text(alias) for alias in aliases):
            action = action_name
            break

    if action is None:
        return False

    # ---------------- المسح ----------------
    if action == "clear":
        if not has_management_role(message.author, cfg):
            await message.channel.send("ما عندك رتبة الإدارة المسموح لها بالمسح.", delete_after=4)
            return True
        if len(parts) < 2 or not parts[1].isdigit():
            await message.channel.send("استخدم الاختصار كذا: `مسح 20`", delete_after=5)
            return True

        amount = int(parts[1])
        if not 1 <= amount <= 100:
            await message.channel.send("المسح من 1 إلى 100 رسالة.", delete_after=4)
            return True
        if not has_bot_permission(message.guild, "manage_messages"):
            await message.channel.send("البوت يحتاج Manage Messages.", delete_after=4)
            return True
        try:
            deleted = await message.channel.purge(limit=amount + 1)
            await message.channel.send(f"تم مسح **{max(0, len(deleted) - 1)}** رسالة.", delete_after=3)
            await send_log(message.guild, "Clear Messages Shortcut", None, message.author, f"مسح {amount} رسالة")
        except discord.Forbidden:
            await message.channel.send("ما عندي صلاحية مسح الرسائل.", delete_after=4)
        except discord.HTTPException as exc:
            await message.channel.send(f"تعذر المسح: {exc}", delete_after=4)
        return True

    # ---------------- بقية العقوبات تحتاج عضو ----------------
    target, error = await parse_shortcut_target(message.guild, parts, 1)
    if target is None:
        await message.channel.send(error, delete_after=5)
        return True

    if action == "ban":
        if not has_ban_role(message.author, cfg):
            await message.channel.send("ما عندك رتبة الحظر المسموح لها.", delete_after=4)
            return True
        if not has_bot_permission(message.guild, "ban_members"):
            await message.channel.send("البوت يحتاج Ban Members.", delete_after=4)
            return True
        ok, error = can_bot_moderate_target(message.guild, target)
        if not ok:
            await message.channel.send(error, delete_after=5)
            return True
        reason = format_reason(" ".join(parts[2:]), "بدون سبب")
        try:
            await target.ban(reason=reason, delete_message_seconds=0)
            await delete_message_safely(message)
            await message.channel.send(f"تم حظر {target.mention}.", delete_after=5, allowed_mentions=discord.AllowedMentions.none())
            await send_log(message.guild, "Ban Shortcut", target, message.author, reason)
        except discord.Forbidden:
            await message.channel.send("Discord رفض الحظر بسبب الصلاحيات/ترتيب الرتب.", delete_after=5)
        except discord.HTTPException as exc:
            await message.channel.send(f"تعذر الحظر: {exc}", delete_after=5)
        return True

    if action == "kick":
        if not has_kick_role(message.author, cfg):
            await message.channel.send("ما عندك رتبة الطرد المسموح لها.", delete_after=4)
            return True
        if not has_bot_permission(message.guild, "kick_members"):
            await message.channel.send("البوت يحتاج Kick Members.", delete_after=4)
            return True
        ok, error = can_bot_moderate_target(message.guild, target)
        if not ok:
            await message.channel.send(error, delete_after=5)
            return True
        reason = format_reason(" ".join(parts[2:]), "بدون سبب")
        try:
            await target.kick(reason=reason)
            await delete_message_safely(message)
            await message.channel.send(f"تم طرد {target.mention}.", delete_after=5, allowed_mentions=discord.AllowedMentions.none())
            await send_log(message.guild, "Kick Shortcut", target, message.author, reason)
        except discord.Forbidden:
            await message.channel.send("Discord رفض الطرد بسبب الصلاحيات/ترتيب الرتب.", delete_after=5)
        except discord.HTTPException as exc:
            await message.channel.send(f"تعذر الطرد: {exc}", delete_after=5)
        return True

    if action == "warn":
        if not has_management_role(message.author, cfg):
            await message.channel.send("ما عندك رتبة الإدارة للتحذير.", delete_after=4)
            return True
        reason = format_reason(" ".join(parts[2:]), "بدون سبب")
        count = await add_warning(message.guild, target, message.author, reason)
        await delete_message_safely(message)
        await message.channel.send(f"⚠️ تم تحذير {target.mention}. التحذيرات: **{count}**.", delete_after=5, allowed_mentions=discord.AllowedMentions.none())
        await send_log(message.guild, "Warning Shortcut", target, message.author, reason, f"إجمالي التحذيرات: {count}")
        return True

    if action == "timeout":
        if not has_management_role(message.author, cfg):
            await message.channel.send("ما عندك رتبة الإدارة للتايم اوت.", delete_after=4)
            return True
        if len(parts) < 3:
            await message.channel.send("استخدمه كذا: `تايم_اوت @العضو 10m السبب`", delete_after=5)
            return True
        seconds = parse_duration(parts[2])
        if seconds is None:
            await message.channel.send("المدة غير صحيحة. استخدم `10m` أو `2h` أو `1d`.", delete_after=5)
            return True
        reason = format_reason(" ".join(parts[3:]), "بدون سبب")
        ok, error = await apply_timeout(target, seconds, reason, message.author)
        if not ok:
            await message.channel.send(error, delete_after=5)
            return True
        await delete_message_safely(message)
        await message.channel.send(
            f"تم تايم اوت {target.mention} لمدة **{duration_text(seconds)}**.",
            delete_after=5,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True

    return False


# ============================================================
# معلومات الإعدادات
# ============================================================

@bot.command(name="حالة_الإدارة", aliases=["حالة", "config"])
async def config_status(ctx: commands.Context):
    if not await require_config_permission(ctx):
        return
    cfg = get_config(ctx.guild.id)
    admin_role = ctx.guild.get_role(int(cfg["admin_role_id"])) if cfg.get("admin_role_id") else None
    ban_role = ctx.guild.get_role(int(cfg["ban_role_id"])) if cfg.get("ban_role_id") else None
    kick_role = ctx.guild.get_role(int(cfg["kick_role_id"])) if cfg.get("kick_role_id") else None
    log_channel = ctx.guild.get_channel(int(cfg["log_channel_id"])) if cfg.get("log_channel_id") else None

    text = (
        "**🛡️ حالة bot7**\n"
        f"رتبة الإدارة: {admin_role.mention if admin_role else 'غير محددة'}\n"
        f"رتبة الحظر: {ban_role.mention if ban_role else 'غير محددة'}\n"
        f"رتبة الطرد: {kick_role.mention if kick_role else 'غير محددة'}\n"
        f"روم اللوق: {log_channel.mention if isinstance(log_channel, discord.TextChannel) else 'غير محدد'}\n\n"
        f"سبام الرسائل: {'✅' if cfg.get('anti_spam_enabled') else '❌'} | {cfg.get('spam_message_limit')} / {cfg.get('spam_window_seconds')}ث | Timeout {cfg.get('spam_timeout_minutes')}د\n"
        f"سبام المنشن: {'✅' if cfg.get('anti_mentions_enabled') else '❌'} | {cfg.get('max_mentions')} / رسالة | Timeout {cfg.get('mention_timeout_minutes')}د\n"
        f"سبام الوسائط: {'✅' if cfg.get('anti_media_enabled') else '❌'} | {cfg.get('media_limit')} / {cfg.get('media_window_seconds')}ث | Timeout {cfg.get('media_timeout_minutes')}د"
    )
    await ctx.send(text, allowed_mentions=discord.AllowedMentions.none())


# ============================================================
# معالجة أخطاء الأوامر
# ============================================================

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"ناقصك `{error.param.name}`. استخدم `!مساعدة`.")
        return
    if isinstance(error, commands.MemberNotFound):
        await ctx.send("ما لقيت العضو. استخدم منشن أو ID صحيح.")
        return
    if isinstance(error, commands.RoleNotFound):
        await ctx.send("ما لقيت الرتبة. منشنها بالشكل الصحيح.")
        return
    if isinstance(error, commands.ChannelNotFound):
        await ctx.send("ما لقيت الروم.")
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("المدخلات غير صحيحة. استخدم `!مساعدة` لمعرفة الصيغة.")
        return
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("ما عندك صلاحية Discord المطلوبة.")
        return

    original = getattr(error, "original", error)
    print(f"[COMMAND ERROR] {type(original).__name__}: {original}")
    try:
        await ctx.send("حدث خطأ غير متوقع أثناء تنفيذ الأمر.")
    except discord.HTTPException:
        pass


# ============================================================
# تحميل bot7 كـ Extension داخل bot.py
# ============================================================

async def setup(bot_instance: commands.Bot):
    """تحميل نظام الإدارة داخل الـBot الرئيسي في bot.py."""
    global bot
    bot = bot_instance

    # نقل الأوامر إلى البوت الرئيسي مع منع أي تعارض في الاسم أو aliases.
    loaded_commands = []
    skipped_commands = []

    for command in list(_DECORATOR_BOT.commands):
        if bot.get_command(command.name) is not None:
            skipped_commands.append(f"{command.name} (name)")
            continue

        safe_aliases = []
        for alias in getattr(command, "aliases", ()):
            if bot.get_command(alias) is None:
                safe_aliases.append(alias)
            else:
                skipped_commands.append(f"{command.name} -> {alias} (alias)")

        command.aliases = safe_aliases

        try:
            bot.add_command(command)
            loaded_commands.append(command.name)
        except commands.CommandRegistrationError as exc:
            skipped_commands.append(f"{command.name} ({exc})")
        except Exception as exc:
            print(f"[BOT7 COMMAND LOAD ERROR] {command.name}: {exc}")
            skipped_commands.append(f"{command.name} ({type(exc).__name__})")

    if skipped_commands:
        print("⚠️ تم تجاهل أوامر/اختصارات متعارضة في bot7.py: " + ", ".join(skipped_commands))

    # أحداث bot7 التي يجب أن تعمل مع الـBot الرئيسي.
    bot.add_listener(on_ready, "on_ready")
    bot.add_listener(on_guild_join, "on_guild_join")
    bot.add_listener(on_message, "on_message")
    bot.add_listener(on_command_error, "on_command_error")

    print(
        "✅ تم تحميل نظام الإدارة والمراقبة من bot7.py "
        f"({len(loaded_commands)} أمر)"
    )


# نحتفظ بالـBot المؤقت الذي سجّلت عليه decorators أثناء import.
_DECORATOR_BOT = bot
