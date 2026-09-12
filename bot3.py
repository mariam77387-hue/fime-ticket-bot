# -*- coding: utf-8 -*-
"""
bot3.py
=======
نظام Self Roles / Role Selection مستقل بالكامل — Extension منفصل عن bot.py و bot2.py.

يُحمَّل داخل البوت الأساسي عبر:
    await bot.load_extension("bot3")

لا يعدّل أو يعتمد على أي كود موجود في bot.py أو bot2.py (الترحيب، التذاكر،
الحماية، اللوجز، الدعوات، إلخ). كل شيء هنا مستقل: قاعدة بيانات خاصة
(self_roles.db)، Views خاصة، أوامر خاصة، ونظام لوجز خاص.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import sqlite3
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("bot3.self_roles")

# ---------------------------------------------------------------------------
# إعدادات عامة
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "self_roles.db")
DEFAULT_ADMIN_ROLE_NAME = "skibidi admin"
MAX_SELECT_OPTIONS = 25
INVALID_EMOJI_FALLBACK = "🎭"


def utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# معالجة الإيموجيات
# ---------------------------------------------------------------------------

CUSTOM_EMOJI_PATTERN = re.compile(
    r"^<(?P<animated>a)?:(?P<name>[A-Za-z0-9_]+):(?P<id>\d+)>$"
)


def _looks_like_unicode_emoji(value: str) -> bool:
    """
    فحص خفيف للتأكد أن القيمة تحتوي على Unicode Emoji حقيقي
    بدل تمرير نص عشوائي إلى Discord.
    """

    for char in value:
        code = ord(char)

        # Miscellaneous Symbols
        if 0x1F300 <= code <= 0x1FAFF:
            return True

        # Miscellaneous Symbols / Dingbats
        if 0x2600 <= code <= 0x27BF:
            return True

        # Regional Indicator Symbols
        if 0x1F1E6 <= code <= 0x1F1FF:
            return True

        # © ® ™
        if code in (0x00A9, 0x00AE, 0x2122):
            return True

    return False


def safe_select_emoji(
    value: Optional[str],
    guild: Optional[discord.Guild] = None,
    fallback: str = INVALID_EMOJI_FALLBACK,
):
    """
    يحوّل الإيموجي إلى صيغة آمنة لـ Discord SelectOption.

    يدعم:
    - Unicode Emoji
    - Custom Emoji <:name:id>
    - Animated Custom Emoji <a:name:id>

    وإذا كانت القيمة غير صالحة يرجع fallback بدل التسبب
    بخطأ 50035 Invalid Form Body.
    """

    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    # -------------------------------------------------------
    # Custom Discord Emoji
    # -------------------------------------------------------
    match = CUSTOM_EMOJI_PATTERN.fullmatch(value)

    if match:
        try:
            emoji_id = int(match.group("id"))
            emoji_name = match.group("name")
            animated = bool(match.group("animated"))

            # إذا كان السيرفر معروفًا، نتأكد أن الإيموجي موجود فعلاً.
            if guild is not None:
                guild_emoji = guild.get_emoji(emoji_id)

                if guild_emoji is None:
                    logger.warning(
                        "Self Roles: Custom Emoji غير موجود، سيتم استخدام fallback: %s",
                        value,
                    )
                    return fallback

                return guild_emoji

            return discord.PartialEmoji(
                name=emoji_name,
                id=emoji_id,
                animated=animated,
            )

        except (ValueError, TypeError, OverflowError):
            logger.warning(
                "Self Roles: Custom Emoji غير صالح: %s",
                value,
            )
            return fallback

    # -------------------------------------------------------
    # رفض صيغ Discord Emoji النصية غير الصحيحة
    # مثل :emoji_name:
    # -------------------------------------------------------
    if value.startswith(":") and value.endswith(":"):
        logger.warning(
            "Self Roles: Emoji بصيغة غير صالحة: %s",
            value,
        )
        return fallback

    # -------------------------------------------------------
    # Unicode Emoji
    # -------------------------------------------------------
    if _looks_like_unicode_emoji(value):
        return value

    # -------------------------------------------------------
    # أي قيمة أخرى تعتبر غير صالحة
    # -------------------------------------------------------
    logger.warning(
        "Self Roles: Emoji غير صالح: %s — سيتم استخدام %s",
        value,
        fallback,
    )

    return fallback


# ---------------------------------------------------------------------------
# طبقة قاعدة البيانات (SQLite مستقل تمامًا: self_roles.db)
# ---------------------------------------------------------------------------

class SelfRolesDB:
    """طبقة وصول لقاعدة بيانات self_roles.db."""

    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS self_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    emoji TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    UNIQUE(guild_id, role_id)
                );

                CREATE TABLE IF NOT EXISTS self_role_panels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL UNIQUE,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER,
                    title TEXT,
                    description TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS self_role_settings (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_role_selection INTEGER NOT NULL DEFAULT 0,
                    role_selection_dm INTEGER NOT NULL DEFAULT 0,
                    restore_roles_on_rejoin INTEGER NOT NULL DEFAULT 0,
                    log_enabled INTEGER NOT NULL DEFAULT 0,
                    log_channel_id INTEGER,
                    admin_role_id INTEGER,
                    panel_color INTEGER,
                    panel_title TEXT,
                    panel_description TEXT
                );

                CREATE TABLE IF NOT EXISTS self_role_member_selections (
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    selected_at TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id, role_id)
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    # ---------------- self_roles ----------------

    def _add_role(self, guild_id, role_id, name, description, emoji):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO self_roles
                    (guild_id, role_id, name, description, emoji, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(guild_id, role_id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    emoji=excluded.emoji,
                    enabled=1
                """,
                (guild_id, role_id, name, description, emoji, utcnow_iso()),
            )
            conn.commit()
        finally:
            conn.close()

    async def add_role(self, guild_id, role_id, name, description, emoji):
        await self._run(
            self._add_role,
            guild_id,
            role_id,
            name,
            description,
            emoji,
        )

    def _remove_role(self, guild_id, role_id) -> bool:
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM self_roles WHERE guild_id=? AND role_id=?",
                (guild_id, role_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    async def remove_role(self, guild_id, role_id) -> bool:
        return await self._run(
            self._remove_role,
            guild_id,
            role_id,
        )

    def _list_roles(self, guild_id, only_enabled: bool = False):
        conn = self._connect()
        try:
            if only_enabled:
                cur = conn.execute(
                    """
                    SELECT * FROM self_roles
                    WHERE guild_id=? AND enabled=1
                    ORDER BY id
                    """,
                    (guild_id,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT * FROM self_roles
                    WHERE guild_id=?
                    ORDER BY id
                    """,
                    (guild_id,),
                )

            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    async def list_roles(self, guild_id, only_enabled: bool = False):
        return await self._run(
            self._list_roles,
            guild_id,
            only_enabled,
        )

    def _disable_role_by_role_id(self, guild_id, role_id):
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE self_roles
                SET enabled=0
                WHERE guild_id=? AND role_id=?
                """,
                (guild_id, role_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def disable_role_by_role_id(self, guild_id, role_id):
        await self._run(
            self._disable_role_by_role_id,
            guild_id,
            role_id,
        )

    # ---------------- panels ----------------

    def _upsert_panel(
        self,
        guild_id,
        channel_id,
        message_id,
        title,
        description,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO self_role_panels
                    (guild_id, channel_id, message_id, title, description, enabled)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    message_id=excluded.message_id,
                    title=excluded.title,
                    description=excluded.description,
                    enabled=1
                """,
                (
                    guild_id,
                    channel_id,
                    message_id,
                    title,
                    description,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def upsert_panel(
        self,
        guild_id,
        channel_id,
        message_id,
        title,
        description,
    ):
        await self._run(
            self._upsert_panel,
            guild_id,
            channel_id,
            message_id,
            title,
            description,
        )

    def _get_panel(self, guild_id):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT * FROM self_role_panels
                WHERE guild_id=?
                """,
                (guild_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    async def get_panel(self, guild_id):
        return await self._run(
            self._get_panel,
            guild_id,
        )

    def _get_all_panels(self):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT * FROM self_role_panels
                WHERE enabled=1
                """
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    async def get_all_panels(self):
        return await self._run(
            self._get_all_panels
        )

    # ---------------- settings ----------------

    def _ensure_settings_row(self, guild_id):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO self_role_settings (guild_id)
                VALUES (?)
                """,
                (guild_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_settings(self, guild_id):
        self._ensure_settings_row(guild_id)

        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT * FROM self_role_settings
                WHERE guild_id=?
                """,
                (guild_id,),
            )
            row = cur.fetchone()
            return dict(row)
        finally:
            conn.close()

    async def get_settings(self, guild_id):
        return await self._run(
            self._get_settings,
            guild_id,
        )

    def _update_settings(self, guild_id, **kwargs):
        if not kwargs:
            return

        self._ensure_settings_row(guild_id)

        conn = self._connect()
        try:
            cols = ", ".join(
                f"{k}=?"
                for k in kwargs
            )

            values = list(kwargs.values()) + [guild_id]

            conn.execute(
                f"""
                UPDATE self_role_settings
                SET {cols}
                WHERE guild_id=?
                """,
                values,
            )

            conn.commit()
        finally:
            conn.close()

    async def update_settings(self, guild_id, **kwargs):
        await self._run(
            self._update_settings,
            guild_id,
            **kwargs,
        )

    # ---------------- member selections ----------------

    def _save_member_selection(
        self,
        guild_id,
        user_id,
        role_id,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO self_role_member_selections
                    (guild_id, user_id, role_id, selected_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    guild_id,
                    user_id,
                    role_id,
                    utcnow_iso(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def save_member_selection(
        self,
        guild_id,
        user_id,
        role_id,
    ):
        await self._run(
            self._save_member_selection,
            guild_id,
            user_id,
            role_id,
        )

    def _remove_member_selection(
        self,
        guild_id,
        user_id,
        role_id,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """
                DELETE FROM self_role_member_selections
                WHERE guild_id=? AND user_id=? AND role_id=?
                """,
                (
                    guild_id,
                    user_id,
                    role_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    async def remove_member_selection(
        self,
        guild_id,
        user_id,
        role_id,
    ):
        await self._run(
            self._remove_member_selection,
            guild_id,
            user_id,
            role_id,
        )

    def _get_member_selections(
        self,
        guild_id,
        user_id,
    ):
        conn = self._connect()
        try:
            cur = conn.execute(
                """
                SELECT role_id
                FROM self_role_member_selections
                WHERE guild_id=? AND user_id=?
                """,
                (
                    guild_id,
                    user_id,
                ),
            )

            return [
                r["role_id"]
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    async def get_member_selections(
        self,
        guild_id,
        user_id,
    ):
        return await self._run(
            self._get_member_selections,
            guild_id,
            user_id,
        )


# ---------------------------------------------------------------------------
# دوال حماية الرتب
# ---------------------------------------------------------------------------

def validate_role_for_self_roles(
    guild: discord.Guild,
    role: discord.Role,
) -> tuple[bool, str]:

    bot_member = guild.me

    if role.is_default():
        return False, "لا يمكن استخدام رتبة @everyone"

    if role.managed:
        return (
            False,
            "هذه رتبة مُدارة (Managed Role / رتبة بوت أو تكامل) ولا يمكن التحكم بها",
        )

    if bot_member is None:
        return False, "تعذر التحقق من عضوية البوت في السيرفر"

    if not bot_member.guild_permissions.manage_roles:
        return False, "البوت لا يملك صلاحية Manage Roles"

    if bot_member.top_role <= role:
        return (
            False,
            f"رتبة البوت ({bot_member.top_role.name}) بنفس مستوى أو أدنى من الرتبة "
            f"المطلوبة ({role.name}) — ارفع رتبة البوت فوقها",
        )

    return True, ""


# ---------------------------------------------------------------------------
# Views (Persistent)
# ---------------------------------------------------------------------------

class SelfRoleSelectMenu(discord.ui.Select):
    """قائمة الاختيار المتعدد الخاصة بلوحة رتب سيرفر معيّن."""

    def __init__(
        self,
        cog: "SelfRolesCog",
        guild_id: int,
        roles: list[dict],
    ):
        self.cog = cog
        self.guild_id = guild_id

        self.role_map: dict[str, dict] = {
            str(r["role_id"]): r
            for r in roles
        }

        guild = cog.bot.get_guild(guild_id)

        options = []

        for r in roles[:MAX_SELECT_OPTIONS]:

            safe_emoji = safe_select_emoji(
                r.get("emoji"),
                guild=guild,
                fallback=INVALID_EMOJI_FALLBACK,
            )

            options.append(
                discord.SelectOption(
                    label=(r["name"] or "رتبة")[:100],
                    value=str(r["role_id"]),
                    description=(r["description"] or "")[:100] or None,
                    emoji=safe_emoji,
                )
            )

        super().__init__(
            placeholder="🔽 اختر الرتب التي تريدها",
            min_values=0,
            max_values=max(len(options), 1),
            options=(
                options
                if options
                else [
                    discord.SelectOption(
                        label="لا توجد رتب بعد",
                        value="none",
                    )
                ]
            ),
            custom_id=f"selfroles_select_{guild_id}",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        if not self.role_map:
            return await interaction.response.send_message(
                "❌ لا توجد رتب مضافة حاليًا في هذا النظام.",
                ephemeral=True,
            )

        await self.cog.handle_selection(
            interaction,
            self.guild_id,
            self.role_map,
            set(self.values),
        )


class SelfRolePanelView(discord.ui.View):
    """View دائم للوحة اختيار الرتب."""

    def __init__(
        self,
        guild_id: int,
        roles: list[dict],
        cog: "SelfRolesCog",
    ):
        super().__init__(timeout=None)

        self.add_item(
            SelfRoleSelectMenu(
                cog,
                guild_id,
                roles,
            )
        )


# ---------------------------------------------------------------------------
# قائمة مساعدة تفاعلية لأوامر Self Roles
# ---------------------------------------------------------------------------

COMMAND_HELP: dict[str, tuple[str, str]] = {
    "rolesetup": (
        "📋 /rolesetup",
        "يعرض حالة نظام Self Roles الحالية: عدد الرتب، حالة اللوحة، وكل الإعدادات المفعّلة.",
    ),
    "roleadd": (
        "➕ /roleadd",
        "يضيف رتبة جديدة لنظام Self Roles.\nالخيارات: `role`، `name`، `emoji` (اختياري)، `description` (اختياري).",
    ),
    "roleremove": (
        "➖ /roleremove",
        "يحذف رتبة من نظام Self Roles.\nالخيارات: `role`.",
    ),
    "rolelist": (
        "📃 /rolelist",
        "يعرض كل الرتب المضافة في النظام مع حالتها (مفعّلة / معطّلة).",
    ),
    "rolepanel": (
        "🎭 /rolepanel",
        "ينشئ لوحة اختيار الرتب في روم معيّن، أو يحدّث اللوحة الموجودة تلقائيًا بدل تكرارها.\nالخيارات: `channel`.",
    ),
    "roleconfig": (
        "⚙️ /roleconfig",
        (
            "يعرض أو يعدّل إعدادات النظام: توجيه الأعضاء الجدد، رسالة DM، "
            "استعادة الرتب عند العودة، اللوجز، رتبة الإدارة، ولون/عنوان/وصف اللوحة.\n"
            "استدعِه بدون خيارات لعرض الإعدادات الحالية."
        ),
    ),
    "rolehelp": (
        "❓ /rolehelp",
        "يعرض هذه القائمة نفسها في أي وقت.",
    ),
}


class RoleHelpSelect(discord.ui.Select):

    def __init__(self):
        options = [
            discord.SelectOption(
                label=title,
                value=key,
                description=desc.split("\n")[0][:100],
            )
            for key, (title, desc) in COMMAND_HELP.items()
        ]

        super().__init__(
            placeholder="📖 اختر أمرًا لعرض شرحه بالتفصيل",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):
        title, desc = COMMAND_HELP[self.values[0]]

        embed = discord.Embed(
            title=title,
            description=desc,
            color=0x5865F2,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class RoleHelpView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(RoleHelpSelect())


# ---------------------------------------------------------------------------
# الـ Cog الرئيسي
# ---------------------------------------------------------------------------

class SelfRolesCog(commands.Cog):
    """نظام Self Roles الكامل، مستقل تمامًا عن باقي أنظمة البوت."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = SelfRolesDB()
        self._active_views: dict[int, SelfRolePanelView] = {}

    # ---------------- تسجيل الـ Views عند الإقلاع ----------------

    async def cog_load(self) -> None:
        try:
            panels = await self.db.get_all_panels()
        except Exception:
            logger.exception(
                "Self Roles: تعذّر قراءة اللوحات عند الإقلاع"
            )
            return

        for panel in panels:
            try:
                roles = await self.db.list_roles(
                    panel["guild_id"],
                    only_enabled=True,
                )

                if not roles:
                    continue

                view = SelfRolePanelView(
                    panel["guild_id"],
                    roles,
                    self,
                )

                self.bot.add_view(view)

                self._active_views[
                    panel["guild_id"]
                ] = view

            except Exception:
                logger.exception(
                    "Self Roles: فشل تسجيل الـ View لسيرفر %s",
                    panel.get("guild_id"),
                )

    # ---------------- أدوات مساعدة داخلية ----------------

    async def _check_admin(
        self,
        interaction: discord.Interaction,
    ) -> bool:

        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
        ):
            return False

        member = interaction.user
        guild = interaction.guild

        if member.id == guild.owner_id:
            return True

        if member.guild_permissions.administrator:
            return True

        settings = await self.db.get_settings(guild.id)

        admin_role_id = settings.get("admin_role_id")

        member_role_ids = {
            r.id
            for r in member.roles
        }

        if admin_role_id and admin_role_id in member_role_ids:
            return True

        if not admin_role_id:
            default_role = discord.utils.get(
                guild.roles,
                name=DEFAULT_ADMIN_ROLE_NAME,
            )

            if (
                default_role
                and default_role.id in member_role_ids
            ):
                return True

        return False

    def _build_panel_embed(
        self,
        guild: discord.Guild,
        settings: dict,
    ) -> discord.Embed:

        color_val = (
            settings.get("panel_color")
            or 0x5865F2
        )

        title = (
            settings.get("panel_title")
            or "🎭 اختر رتبك"
        )

        desc = (
            settings.get("panel_description")
            or "اختر المنشنات التي تريد استقبالها، ويمكنك تغيير اختياراتك في أي وقت."
        )

        embed = discord.Embed(
            title=title,
            description=desc,
            color=color_val,
        )

        embed.set_footer(
            text=guild.name,
            icon_url=(
                guild.icon.url
                if guild.icon
                else None
            ),
        )

        return embed

    async def _log(
        self,
        guild: discord.Guild,
        title: str,
        member: Optional[discord.abc.User] = None,
        extra: Optional[str] = None,
    ) -> None:

        try:
            settings = await self.db.get_settings(
                guild.id
            )

            if (
                not settings.get("log_enabled")
                or not settings.get("log_channel_id")
            ):
                return

            channel = guild.get_channel(
                settings["log_channel_id"]
            )

            if channel is None:
                return

            embed = discord.Embed(
                title=title,
                color=discord.Color.blurple(),
                timestamp=utcnow(),
            )

            if member is not None:
                embed.add_field(
                    name="العضو",
                    value=f"{member.mention} (`{member.id}`)",
                    inline=False,
                )

            if extra:
                embed.add_field(
                    name="التفاصيل",
                    value=extra[:1024],
                    inline=False,
                )

            embed.set_footer(
                text="Self Roles System"
            )

            await channel.send(
                embed=embed
            )

        except discord.Forbidden:
            logger.warning(
                "Self Roles: لا صلاحية للإرسال في روم اللوجز (guild=%s)",
                guild.id,
            )

        except discord.HTTPException:
            logger.exception(
                "Self Roles: فشل إرسال لوج (guild=%s)",
                guild.id,
            )

        except Exception:
            logger.exception(
                "Self Roles: خطأ غير متوقع أثناء تسجيل اللوج"
            )

    async def _refresh_panel(
        self,
        guild_id: int,
    ) -> None:

        panel = await self.db.get_panel(
            guild_id
        )

        if (
            not panel
            or not panel.get("message_id")
        ):
            return

        guild = self.bot.get_guild(
            guild_id
        )

        if guild is None:
            return

        channel = guild.get_channel(
            panel["channel_id"]
        )

        if channel is None:
            return

        roles = await self.db.list_roles(
            guild_id,
            only_enabled=True,
        )

        settings = await self.db.get_settings(
            guild_id
        )

        embed = self._build_panel_embed(
            guild,
            settings,
        )

        try:
            message = await channel.fetch_message(
                panel["message_id"]
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return

        try:
            if roles:
                view = SelfRolePanelView(
                    guild_id,
                    roles,
                    self,
                )

                await message.edit(
                    embed=embed,
                    view=view,
                )

                self.bot.add_view(view)

                self._active_views[
                    guild_id
                ] = view

            else:
                await message.edit(
                    embed=embed,
                    view=None,
                )

                self._active_views.pop(
                    guild_id,
                    None,
                )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            logger.exception(
                "Self Roles: فشل تحديث لوحة الرتب (guild=%s)",
                guild_id,
            )

    # ---------------- معالجة اختيار العضو ----------------

    async def handle_selection(
        self,
        interaction: discord.Interaction,
        guild_id: int,
        role_map: dict[str, dict],
        selected_values: set[str],
    ) -> None:

        guild = interaction.guild
        member = interaction.user

        if (
            guild is None
            or not isinstance(member, discord.Member)
        ):
            return await interaction.response.send_message(
                "❌ حدث خطأ غير متوقع.",
                ephemeral=True,
            )

        await interaction.response.defer(
            ephemeral=True,
            thinking=False,
        )

        # فقط الرتب الموجودة داخل هذه القائمة تحديدًا يُسمح بلمسها
        all_menu_role_ids = {
            int(v)
            for v in role_map.keys()
            if v.isdigit()
        }

        selected_role_ids = {
            int(v)
            for v in selected_values
            if v.isdigit()
        }

        member_role_ids = {
            r.id
            for r in member.roles
        }

        to_add_ids = (
            selected_role_ids
            - member_role_ids
        )

        to_remove_ids = (
            all_menu_role_ids
            - selected_role_ids
        ) & member_role_ids

        added: list[str] = []
        removed: list[str] = []
        failed: list[tuple[str, str]] = []

        for rid in to_add_ids:

            role = guild.get_role(rid)

            if role is None:
                continue

            ok, reason = validate_role_for_self_roles(
                guild,
                role,
            )

            if not ok:
                failed.append(
                    (
                        role.name,
                        reason,
                    )
                )
                continue

            try:
                await member.add_roles(
                    role,
                    reason="Self Roles: اختيار العضو",
                )

                added.append(
                    role.name
                )

                await self.db.save_member_selection(
                    guild.id,
                    member.id,
                    role.id,
                )

            except discord.Forbidden:
                failed.append(
                    (
                        role.name,
                        "صلاحيات البوت غير كافية",
                    )
                )

            except discord.HTTPException as e:
                failed.append(
                    (
                        role.name,
                        f"خطأ Discord: {e}",
                    )
                )

        for rid in to_remove_ids:

            role = guild.get_role(rid)

            if role is None:
                await self.db.remove_member_selection(
                    guild.id,
                    member.id,
                    rid,
                )
                continue

            try:
                await member.remove_roles(
                    role,
                    reason="Self Roles: إلغاء اختيار العضو",
                )

                removed.append(
                    role.name
                )

                await self.db.remove_member_selection(
                    guild.id,
                    member.id,
                    role.id,
                )

            except discord.Forbidden:
                failed.append(
                    (
                        role.name,
                        "صلاحيات البوت غير كافية",
                    )
                )

            except discord.HTTPException as e:
                failed.append(
                    (
                        role.name,
                        f"خطأ Discord: {e}",
                    )
                )

        lines = []

        if added:
            lines.append(
                "✅ تمت إضافة: "
                + "، ".join(added)
            )

        if removed:
            lines.append(
                "➖ تمت إزالة: "
                + "، ".join(removed)
            )

        if failed:
            lines.append(
                "⚠️ تعذّر: "
                + "، ".join(
                    f"{n} ({r})"
                    for n, r in failed
                )
            )

        if not lines:
            lines.append(
                "ℹ️ لا يوجد تغيير في رتبك."
            )

        try:
            await interaction.followup.send(
                "\n".join(lines),
                ephemeral=True,
            )
        except discord.HTTPException:
            pass

        for name in added:
            await self._log(
                guild,
                "👤 Member selected role",
                member=member,
                extra=f"➕ {name}",
            )

        for name in removed:
            await self._log(
                guild,
                "👤 Member selected role",
                member=member,
                extra=f"➖ {name}",
            )

        for name, reason in failed:
            await self._log(
                guild,
                "⚠️ Role assignment failed",
                member=member,
                extra=f"{name} — {reason}",
            )

    # ---------------- أحداث (Listeners) ----------------

    @commands.Cog.listener()
    async def on_guild_role_delete(
        self,
        role: discord.Role,
    ) -> None:

        try:
            roles = await self.db.list_roles(
                role.guild.id
            )
        except Exception:
            logger.exception(
                "Self Roles: فشل قراءة الرتب عند on_guild_role_delete"
            )
            return

        if any(
            r["role_id"] == role.id
            and r["enabled"]
            for r in roles
        ):
            await self.db.disable_role_by_role_id(
                role.guild.id,
                role.id,
            )

            await self._refresh_panel(
                role.guild.id
            )

            await self._log(
                role.guild,
                "⚠️ Self role deleted & disabled",
                extra=(
                    f"الرتبة: {role.name} "
                    f"(ID: {role.id}) — تم تعطيلها تلقائيًا في النظام"
                ),
            )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member: discord.Member,
    ) -> None:

        if member.bot:
            return

        guild = member.guild

        try:
            settings = await self.db.get_settings(
                guild.id
            )
        except Exception:
            logger.exception(
                "Self Roles: فشل قراءة الإعدادات عند on_member_join"
            )
            return

        # استعادة الرتب السابقة إن كانت مفعّلة
        if settings.get(
            "restore_roles_on_rejoin"
        ):
            try:
                previous_ids = await self.db.get_member_selections(
                    guild.id,
                    member.id,
                )

                if previous_ids:

                    active_roles = await self.db.list_roles(
                        guild.id,
                        only_enabled=True,
                    )

                    active_ids = {
                        r["role_id"]
                        for r in active_roles
                    }

                    to_restore = []

                    for rid in previous_ids:

                        if rid not in active_ids:
                            continue

                        role = guild.get_role(rid)

                        if role is None:
                            continue

                        ok, _reason = validate_role_for_self_roles(
                            guild,
                            role,
                        )

                        if ok:
                            to_restore.append(role)

                    if to_restore:
                        await member.add_roles(
                            *to_restore,
                            reason="Self Roles: استعادة عند العودة",
                        )

                        await self._log(
                            guild,
                            "🔄 Restored self roles on rejoin",
                            member=member,
                            extra="، ".join(
                                r.name
                                for r in to_restore
                            ),
                        )

            except discord.Forbidden:
                await self._log(
                    guild,
                    "⚠️ Role assignment failed",
                    member=member,
                    extra="Forbidden أثناء استعادة الرتب",
                )

            except discord.HTTPException as e:
                await self._log(
                    guild,
                    "⚠️ Role assignment failed",
                    member=member,
                    extra=str(e),
                )

            except Exception:
                logger.exception(
                    "Self Roles: خطأ غير متوقع أثناء استعادة الرتب"
                )

        # توجيه العضو الجديد للوحة الرتب عبر خاص
        if (
            settings.get("welcome_role_selection")
            and settings.get("role_selection_dm")
        ):
            try:
                panel = await self.db.get_panel(
                    guild.id
                )

                if (
                    panel
                    and panel.get("enabled")
                    and panel.get("message_id")
                ):
                    channel = guild.get_channel(
                        panel["channel_id"]
                    )

                    if channel is not None:
                        link = (
                            f"https://discord.com/channels/"
                            f"{guild.id}/"
                            f"{channel.id}/"
                            f"{panel['message_id']}"
                        )

                        text = (
                            f"👋 أهلاً بك في **{guild.name}**!\n"
                            f"يمكنك اختيار رتبك من هنا:\n"
                            f"{link}"
                        )

                        await member.send(
                            text
                        )

            except discord.Forbidden:
                pass

            except discord.HTTPException:
                logger.exception(
                    "Self Roles: فشل إرسال رسالة خاصة لعضو جديد"
                )

    # ---------------- Slash Commands ----------------

    group_error_msg = (
        "❌ ما تملك الصلاحية الكافية لاستخدام هذا الأمر."
    )

    @app_commands.command(
        name="rolehelp",
        description="عرض قائمة تفاعلية بكل أوامر نظام Self Roles",
    )
    @app_commands.guild_only()
    async def rolehelp(
        self,
        interaction: discord.Interaction,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🎭 أوامر نظام Self Roles",
            description=(
                "اختر أمرًا من القائمة تحت لعرض شرحه بالتفصيل، "
                "أو استخدم الأوامر مباشرة من شريط الكتابة:"
            ),
            color=0x5865F2,
        )

        for title, desc in COMMAND_HELP.values():
            embed.add_field(
                name=title,
                value=desc.split("\n")[0],
                inline=False,
            )

        await interaction.response.send_message(
            embed=embed,
            view=RoleHelpView(),
            ephemeral=True,
        )

    @app_commands.command(
        name="rolesetup",
        description="عرض حالة نظام Self Roles وإرشادات الاستخدام",
    )
    @app_commands.guild_only()
    async def rolesetup(
        self,
        interaction: discord.Interaction,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        guild = interaction.guild

        roles = await self.db.list_roles(
            guild.id
        )

        enabled_roles = [
            r
            for r in roles
            if r["enabled"]
        ]

        panel = await self.db.get_panel(
            guild.id
        )

        settings = await self.db.get_settings(
            guild.id
        )

        embed = discord.Embed(
            title="🎭 حالة نظام Self Roles",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="عدد الرتب المضافة",
            value=str(len(roles)),
            inline=True,
        )

        embed.add_field(
            name="الرتب المفعّلة",
            value=str(len(enabled_roles)),
            inline=True,
        )

        embed.add_field(
            name="اللوحة",
            value=(
                f"<#{panel['channel_id']}>"
                if panel
                else "لم تُنشأ بعد"
            ),
            inline=True,
        )

        embed.add_field(
            name="اختيار العضو الجديد",
            value=(
                "✅ مفعّل"
                if settings.get(
                    "welcome_role_selection"
                )
                else "❌ متوقف"
            ),
            inline=True,
        )

        embed.add_field(
            name="رسالة خاصة للعضو الجديد",
            value=(
                "✅ مفعّل"
                if settings.get(
                    "role_selection_dm"
                )
                else "❌ متوقف"
            ),
            inline=True,
        )

        embed.add_field(
            name="استعادة الرتب عند العودة",
            value=(
                "✅ مفعّل"
                if settings.get(
                    "restore_roles_on_rejoin"
                )
                else "❌ متوقف"
            ),
            inline=True,
        )

        embed.add_field(
            name="اللوجز",
            value=(
                f"✅ مفعّل — <#{settings['log_channel_id']}>"
                if (
                    settings.get("log_enabled")
                    and settings.get("log_channel_id")
                )
                else "❌ متوقف"
            ),
            inline=False,
        )

        embed.add_field(
            name="📋 الأوامر المتاحة",
            value=(
                "`/roleadd` إضافة رتبة\n"
                "`/roleremove` حذف رتبة\n"
                "`/rolelist` عرض الرتب\n"
                "`/rolepanel` إنشاء/تحديث اللوحة\n"
                "`/roleconfig` إعدادات النظام"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="roleadd",
        description="إضافة رتبة إلى نظام Self Roles",
    )
    @app_commands.describe(
        role="الرتبة",
        name="الاسم الظاهر في القائمة",
        emoji="الإيموجي",
        description="وصف مختصر",
    )
    @app_commands.guild_only()
    async def roleadd(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        name: str,
        emoji: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        guild = interaction.guild

        ok, reason = validate_role_for_self_roles(
            guild,
            role,
        )

        if not ok:
            return await interaction.response.send_message(
                f"❌ لا يمكن إضافة هذه الرتبة: {reason}",
                ephemeral=True,
            )

        existing = await self.db.list_roles(
            guild.id
        )

        existing_ids = {
            r["role_id"]
            for r in existing
        }

        enabled_count = len(
            [
                r
                for r in existing
                if r["enabled"]
            ]
        )

        if (
            role.id not in existing_ids
            and enabled_count >= MAX_SELECT_OPTIONS
        ):
            return await interaction.response.send_message(
                f"❌ تم الوصول للحد الأقصى ({MAX_SELECT_OPTIONS}) من الرتب في نظام واحد.",
                ephemeral=True,
            )

        await self.db.add_role(
            guild.id,
            role.id,
            name,
            description,
            emoji,
        )

        await self._refresh_panel(
            guild.id
        )

        await interaction.response.send_message(
            f"✅ تمت إضافة الرتبة {role.mention} باسم **{name}**",
            ephemeral=True,
        )

        await self._log(
            guild,
            "➕ Role added",
            extra=(
                f"{name} → "
                f"{role.mention} "
                f"({role.id})"
            ),
        )

    @app_commands.command(
        name="roleremove",
        description="حذف رتبة من نظام Self Roles",
    )
    @app_commands.describe(
        role="الرتبة المراد حذفها من النظام"
    )
    @app_commands.guild_only()
    async def roleremove(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        guild = interaction.guild

        removed = await self.db.remove_role(
            guild.id,
            role.id,
        )

        if not removed:
            return await interaction.response.send_message(
                "❌ هذه الرتبة غير موجودة في نظام Self Roles.",
                ephemeral=True,
            )

        await self._refresh_panel(
            guild.id
        )

        await interaction.response.send_message(
            f"✅ تمت إزالة {role.mention} من نظام Self Roles.",
            ephemeral=True,
        )

        await self._log(
            guild,
            "➖ Role removed",
            extra=f"{role.name} ({role.id})",
        )

    @app_commands.command(
        name="rolelist",
        description="عرض جميع الرتب في نظام Self Roles",
    )
    @app_commands.guild_only()
    async def rolelist(
        self,
        interaction: discord.Interaction,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        roles = await self.db.list_roles(
            interaction.guild.id
        )

        if not roles:
            return await interaction.response.send_message(
                "ℹ️ لا توجد رتب مضافة بعد. استخدم `/roleadd`.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="📋 رتب Self Roles",
            color=discord.Color.blurple(),
        )

        lines = []

        for r in roles:

            status = (
                "✅"
                if r["enabled"]
                else "🚫 (معطّلة)"
            )

            emoji = r["emoji"] or ""

            lines.append(
                f"{status} {emoji} "
                f"**{r['name']}** — "
                f"<@&{r['role_id']}>"
            )

        embed.description = "\n".join(
            lines
        )[:4000]

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @app_commands.command(
        name="rolepanel",
        description="إنشاء أو تحديث لوحة اختيار الرتب في روم معيّن",
    )
    @app_commands.describe(
        channel="القناة التي ستُنشر فيها اللوحة"
    )
    @app_commands.guild_only()
    async def rolepanel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        guild = interaction.guild

        roles = await self.db.list_roles(
            guild.id,
            only_enabled=True,
        )

        if not roles:
            return await interaction.response.send_message(
                "❌ لا توجد رتب مفعّلة بعد. أضف رتبًا أولًا عبر `/roleadd`.",
                ephemeral=True,
            )

        perms = channel.permissions_for(
            guild.me
        )

        if not (
            perms.send_messages
            and perms.embed_links
        ):
            return await interaction.response.send_message(
                f"❌ ما أملك صلاحية الإرسال أو وضع Embeds في {channel.mention}.",
                ephemeral=True,
            )

        settings = await self.db.get_settings(
            guild.id
        )

        embed = self._build_panel_embed(
            guild,
            settings,
        )

        view = SelfRolePanelView(
            guild.id,
            roles,
            self,
        )

        existing_panel = await self.db.get_panel(
            guild.id
        )

        message = None

        if (
            existing_panel
            and existing_panel.get("message_id")
        ):
            old_channel = guild.get_channel(
                existing_panel["channel_id"]
            )

            if old_channel is not None:
                try:
                    message = await old_channel.fetch_message(
                        existing_panel["message_id"]
                    )

                    if old_channel.id == channel.id:
                        await message.edit(
                            embed=embed,
                            view=view,
                        )

                    else:
                        try:
                            await message.delete()
                        except (
                            discord.Forbidden,
                            discord.HTTPException,
                        ):
                            pass

                        message = None

                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    message = None

        if message is None:
            try:
                message = await channel.send(
                    embed=embed,
                    view=view,
                )

            except discord.Forbidden:
                return await interaction.response.send_message(
                    f"❌ تعذّر الإرسال في {channel.mention} (صلاحيات).",
                    ephemeral=True,
                )

            except discord.HTTPException as e:
                return await interaction.response.send_message(
                    f"❌ فشل إنشاء اللوحة: {e}",
                    ephemeral=True,
                )

        await self.db.upsert_panel(
            guild.id,
            channel.id,
            message.id,
            settings.get("panel_title"),
            settings.get("panel_description"),
        )

        self.bot.add_view(view)

        self._active_views[
            guild.id
        ] = view

        await interaction.response.send_message(
            f"✅ تم إنشاء/تحديث لوحة الرتب في {channel.mention}",
            ephemeral=True,
        )

        await self._log(
            guild,
            "🎭 Self roles panel updated",
            extra=f"القناة: {channel.mention}",
        )

    @app_commands.command(
        name="roleconfig",
        description="عرض أو تعديل إعدادات نظام Self Roles",
    )
    @app_commands.describe(
        welcome_role_selection="توجيه الأعضاء الجدد لاختيار الرتب",
        role_selection_dm="إرسال رابط اللوحة للعضو الجديد بالخاص",
        restore_roles_on_rejoin="استعادة رتب العضو عند عودته للسيرفر",
        log_enabled="تفعيل/إيقاف لوجز نظام Self Roles",
        log_channel="روم اللوجز الخاص بالنظام",
        admin_role="الرتبة المسموح لها بإدارة النظام",
        color="لون اللوحة (كود Hex مثل #5865F2)",
        title="عنوان اللوحة",
        description="وصف اللوحة",
    )
    @app_commands.guild_only()
    async def roleconfig(
        self,
        interaction: discord.Interaction,
        welcome_role_selection: Optional[bool] = None,
        role_selection_dm: Optional[bool] = None,
        restore_roles_on_rejoin: Optional[bool] = None,
        log_enabled: Optional[bool] = None,
        log_channel: Optional[discord.TextChannel] = None,
        admin_role: Optional[discord.Role] = None,
        color: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ):
        if not await self._check_admin(
            interaction
        ):
            return await interaction.response.send_message(
                self.group_error_msg,
                ephemeral=True,
            )

        guild = interaction.guild

        updates: dict = {}

        if welcome_role_selection is not None:
            updates["welcome_role_selection"] = int(
                welcome_role_selection
            )

        if role_selection_dm is not None:
            updates["role_selection_dm"] = int(
                role_selection_dm
            )

        if restore_roles_on_rejoin is not None:
            updates["restore_roles_on_rejoin"] = int(
                restore_roles_on_rejoin
            )

        if log_enabled is not None:
            updates["log_enabled"] = int(
                log_enabled
            )

        if log_channel is not None:
            updates["log_channel_id"] = (
                log_channel.id
            )

        if admin_role is not None:
            updates["admin_role_id"] = (
                admin_role.id
            )

        if title is not None:
            updates["panel_title"] = title[:256]

        if description is not None:
            updates["panel_description"] = description[:2000]

        if color is not None:
            try:
                updates["panel_color"] = int(
                    color.lstrip("#"),
                    16,
                )
            except ValueError:
                return await interaction.response.send_message(
                    "❌ صيغة اللون غير صحيحة. استخدم كود Hex مثل `#5865F2`.",
                    ephemeral=True,
                )

        if not updates:

            settings = await self.db.get_settings(
                guild.id
            )

            embed = discord.Embed(
                title="⚙️ إعدادات Self Roles الحالية",
                color=discord.Color.blurple(),
            )

            embed.add_field(
                name="اختيار العضو الجديد",
                value=(
                    "✅"
                    if settings.get(
                        "welcome_role_selection"
                    )
                    else "❌"
                ),
                inline=True,
            )

            embed.add_field(
                name="رسالة خاصة",
                value=(
                    "✅"
                    if settings.get(
                        "role_selection_dm"
                    )
                    else "❌"
                ),
                inline=True,
            )

            embed.add_field(
                name="استعادة عند العودة",
                value=(
                    "✅"
                    if settings.get(
                        "restore_roles_on_rejoin"
                    )
                    else "❌"
                ),
                inline=True,
            )

            embed.add_field(
                name="اللوجز",
                value=(
                    f"✅ <#{settings['log_channel_id']}>"
                    if (
                        settings.get("log_enabled")
                        and settings.get("log_channel_id")
                    )
                    else "❌"
                ),
                inline=True,
            )

            embed.add_field(
                name="رتبة الإدارة",
                value=(
                    f"<@&{settings['admin_role_id']}>"
                    if settings.get("admin_role_id")
                    else (
                        f"(افتراضي: "
                        f"{DEFAULT_ADMIN_ROLE_NAME})"
                    )
                ),
                inline=True,
            )

            embed.add_field(
                name="عنوان اللوحة",
                value=(
                    settings.get("panel_title")
                    or "(افتراضي)"
                ),
                inline=True,
            )

            embed.add_field(
                name="وصف اللوحة",
                value=(
                    settings.get("panel_description")
                    or "(افتراضي)"
                )[:1024],
                inline=False,
            )

            return await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

        await self.db.update_settings(
            guild.id,
            **updates,
        )

        if any(
            k in updates
            for k in (
                "panel_title",
                "panel_description",
                "panel_color",
            )
        ):
            await self._refresh_panel(
                guild.id
            )

        await interaction.response.send_message(
            "✅ تم تحديث إعدادات نظام Self Roles.",
            ephemeral=True,
        )

        await self._log(
            guild,
            "⚙️ Self roles settings updated",
            extra=str(updates),
        )


# ---------------------------------------------------------------------------
# Extension entrypoint
# ---------------------------------------------------------------------------

async def setup(
    bot: commands.Bot,
) -> None:
    await bot.add_cog(
        SelfRolesCog(bot)
    )