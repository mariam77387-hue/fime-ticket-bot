# =========================================================
# Team Fime — bot3.py
# Advanced Invite System + SQLite Database
#
# يعتمد على bot2.py الموجود عندك، ويحافظ على أنظمته الحالية:
# Logs + Moderation + Protection + Levels + Buttons
# + Roles + Ping + AI + Permanent Invite
#
# الإضافات:
# - SQLite Database
# - Invite Tracking
# - معرفة صاحب الدعوة
# - Invite Statistics
# - Invite Top
# - Invite Info
# - حفظ الدعوات
# - اكتشاف حذف Permanent Invite
# - إنشاء رابط بديل تلقائي
# - فحص دوري للرابط الدائم
# - حماية Discord Invites
# - السماح برابط Team Fime تلقائيًا
# =========================================================

import asyncio
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import bot2


# =========================================================
# Database
# =========================================================

DB_FILE = "team_fime.db"


class FimeDatabase:
    def __init__(self, path=DB_FILE):
        self.path = path
        self.conn = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                display_name TEXT,
                joined_at TEXT,
                last_seen TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                guild_id INTEGER NOT NULL,
                code TEXT NOT NULL,
                inviter_id INTEGER,
                channel_id INTEGER,
                uses INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 0,
                max_age INTEGER DEFAULT 0,
                is_permanent INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                last_seen TEXT,
                PRIMARY KEY (guild_id, code)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                invite_code TEXT,
                member_id INTEGER NOT NULL,
                inviter_id INTEGER,
                joined_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_invite_uses_guild_inviter
            ON invite_uses(guild_id, inviter_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_invite_uses_member
            ON invite_uses(guild_id, member_id)
        """)

        self.conn.commit()

    def upsert_user(self, guild_id, user_id, username, display_name, joined_at=None):
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT INTO users (
                guild_id,
                user_id,
                username,
                display_name,
                joined_at,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET
                username=excluded.username,
                display_name=excluded.display_name,
                last_seen=excluded.last_seen
        """, (
            guild_id,
            user_id,
            username,
            display_name,
            joined_at or now,
            now,
        ))

        self.conn.commit()

    def save_invite(
        self,
        guild_id,
        code,
        inviter_id,
        channel_id,
        uses,
        max_uses=0,
        max_age=0,
        is_permanent=False,
        active=True,
    ):
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT INTO invites (
                guild_id,
                code,
                inviter_id,
                channel_id,
                uses,
                max_uses,
                max_age,
                is_permanent,
                active,
                created_at,
                last_seen
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, code)
            DO UPDATE SET
                inviter_id=excluded.inviter_id,
                channel_id=excluded.channel_id,
                uses=excluded.uses,
                max_uses=excluded.max_uses,
                max_age=excluded.max_age,
                is_permanent=excluded.is_permanent,
                active=excluded.active,
                last_seen=excluded.last_seen
        """, (
            guild_id,
            code,
            inviter_id,
            channel_id,
            uses,
            max_uses,
            max_age,
            1 if is_permanent else 0,
            1 if active else 0,
            now,
            now,
        ))

        self.conn.commit()

    def mark_invite_deleted(self, guild_id, code):
        self.conn.execute("""
            UPDATE invites
            SET active = 0,
                last_seen = ?
            WHERE guild_id = ?
              AND code = ?
        """, (
            datetime.now(timezone.utc).isoformat(),
            guild_id,
            code,
        ))

        self.conn.commit()

    def record_invite_use(
        self,
        guild_id,
        code,
        member_id,
        inviter_id,
    ):
        now = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT INTO invite_uses (
                guild_id,
                invite_code,
                member_id,
                inviter_id,
                joined_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            guild_id,
            code,
            member_id,
            inviter_id,
            now,
        ))

        self.conn.commit()

    def get_invite_count(self, guild_id, inviter_id):
        row = self.conn.execute("""
            SELECT COUNT(*) AS total
            FROM invite_uses
            WHERE guild_id = ?
              AND inviter_id = ?
        """, (
            guild_id,
            inviter_id,
        )).fetchone()

        return int(row["total"] if row else 0)

    def get_invite_top(self, guild_id, limit=10):
        return self.conn.execute("""
            SELECT
                inviter_id,
                COUNT(*) AS total
            FROM invite_uses
            WHERE guild_id = ?
              AND inviter_id IS NOT NULL
            GROUP BY inviter_id
            ORDER BY total DESC
            LIMIT ?
        """, (
            guild_id,
            limit,
        )).fetchall()

    def get_member_invites(self, guild_id, member_id, limit=15):
        return self.conn.execute("""
            SELECT
                invite_code,
                member_id,
                joined_at
            FROM invite_uses
            WHERE guild_id = ?
              AND inviter_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (
            guild_id,
            member_id,
            limit,
        )).fetchall()

    def get_invite_info(self, guild_id, code):
        return self.conn.execute("""
            SELECT *
            FROM invites
            WHERE guild_id = ?
              AND code = ?
        """, (
            guild_id,
            code,
        )).fetchone()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


# =========================================================
# Advanced Invite Cog
# =========================================================

class AdvancedFimeBot(bot2.ServerLogger):

    DISCORD_INVITE_REGEX = re.compile(
        r"(?:https?://)?(?:www\.)?"
        r"(?:discord\.gg|discord\.com/invite|discordapp\.com/invite)"
        r"/([A-Za-z0-9-]+)",
        re.IGNORECASE,
    )

    def __init__(self, bot):
        super().__init__(bot)

        self.db = FimeDatabase()

        # آخر snapshot للدعوات لكل سيرفر.
        self._invite_cache = {}

        # يمنع أكثر من عملية فحص لنفس السيرفر في نفس الوقت.
        self._invite_locks = {}

        # منع تشغيل الفحص أكثر من مرة.
        self._invite_checker_started = False

    async def cog_load(self):
        await super().cog_load()

        if not self.permanent_invite_checker.is_running():
            self.permanent_invite_checker.start()

        print("✅ Team Fime bot3 Advanced Invite System loaded.")

    async def cog_unload(self):
        if self.permanent_invite_checker.is_running():
            self.permanent_invite_checker.cancel()

        self.db.close()

        await super().cog_unload()

    # =====================================================
    # Database helpers
    # =====================================================

    async def db_call(self, function, *args):
        """
        SQLite عملياتها سريعة، لكن نشغلها خارج event loop
        حتى لا نوقف Discord أثناء الكتابة.
        """
        return await asyncio.to_thread(function, *args)

    # =====================================================
    # Invite configuration
    # =====================================================

    def get_invite_protection(self, guild):
        cfg = bot2.guild_config(guild)
        protection = cfg.setdefault("protection", {})

        protection.setdefault("invite_protection_enabled", True)
        protection.setdefault("allow_server_invites", True)
        protection.setdefault("allowed_invite_codes", [])

        return protection

    def save_invite_config(self, guild, protection):
        def writer(cfg):
            cfg.setdefault("protection", {}).update({
                "invite_protection_enabled":
                    protection.get("invite_protection_enabled", True),

                "allow_server_invites":
                    protection.get("allow_server_invites", True),

                "allowed_invite_codes":
                    protection.get("allowed_invite_codes", []),
            })

        bot2.update_guild_config(guild, writer)

    # =====================================================
    # Discord Invite Detection
    # =====================================================

    def extract_discord_invites(self, content):
        if not content:
            return []

        return [
            match.group(1)
            for match in self.DISCORD_INVITE_REGEX.finditer(content)
        ]

    def contains_discord_invite(self, content):
        return bool(self.extract_discord_invites(content))

    def get_saved_permanent_code(self, guild):
        cfg = bot2.guild_config(guild)
        return cfg.get("permanent_invite_code")

    def is_allowed_discord_invite(self, guild, code):
        protection = self.get_invite_protection(guild)

        if not protection.get("invite_protection_enabled", True):
            return True

        if protection.get("allow_server_invites", True):
            permanent_code = self.get_saved_permanent_code(guild)

            if permanent_code and permanent_code.lower() == code.lower():
                return True

        allowed_codes = protection.get("allowed_invite_codes", [])

        return any(
            str(saved).lower() == code.lower()
            for saved in allowed_codes
        )

    # =====================================================
    # Invite snapshots
    # =====================================================

    async def fetch_invite_snapshot(self, guild):
        """
        يجلب جميع الدعوات ويحولها إلى dictionary
        حتى نستطيع معرفة أي دعوة زادت استخدامها.
        """

        try:
            invites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            return None

        snapshot = {}

        for invite in invites:
            inviter_id = None

            try:
                if invite.inviter:
                    inviter_id = invite.inviter.id
            except Exception:
                inviter_id = None

            channel_id = None

            try:
                if invite.channel:
                    channel_id = invite.channel.id
            except Exception:
                pass

            uses = invite.uses or 0

            max_uses = invite.max_uses or 0
            max_age = invite.max_age or 0

            is_permanent = (
                max_age == 0 and
                max_uses == 0
            )

            snapshot[invite.code] = {
                "code": invite.code,
                "inviter_id": inviter_id,
                "channel_id": channel_id,
                "uses": uses,
                "max_uses": max_uses,
                "max_age": max_age,
                "is_permanent": is_permanent,
                "invite": invite,
            }

            await self.db_call(
                self.db.save_invite,
                guild.id,
                invite.code,
                inviter_id,
                channel_id,
                uses,
                max_uses,
                max_age,
                is_permanent,
                True,
            )

        return snapshot

    async def initialize_invite_cache(self, guild):
        snapshot = await self.fetch_invite_snapshot(guild)

        if snapshot is not None:
            self._invite_cache[guild.id] = snapshot

        return snapshot

    # =====================================================
    # Find used invite
    # =====================================================

    async def detect_used_invite(self, guild):
        """
        يقارن snapshot قديم بالجديد.
        الدعوة التي ارتفع عدد استخدامها هي الدعوة المستخدمة غالبًا.
        """

        old_snapshot = self._invite_cache.get(guild.id)

        new_snapshot = await self.fetch_invite_snapshot(guild)

        if new_snapshot is None:
            return None

        self._invite_cache[guild.id] = new_snapshot

        if not old_snapshot:
            return None

        candidates = []

        for code, current in new_snapshot.items():
            old = old_snapshot.get(code)

            if old is None:
                continue

            old_uses = int(old.get("uses", 0) or 0)
            new_uses = int(current.get("uses", 0) or 0)

            if new_uses > old_uses:
                candidates.append((
                    new_uses - old_uses,
                    current,
                ))

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return candidates[0][1]

    # =====================================================
    # Permanent Invite
    # =====================================================

    async def ensure_permanent_invite_advanced(
        self,
        guild,
        preferred=None,
        force_new=False,
        announce_recovery=False,
    ):
        """
        نسخة محسنة من permanent invite.

        تحافظ على الرابط الحالي إذا كان صالحًا.
        إذا انحذف أو أصبح غير صالح:
        يتم إنشاء رابط دائم جديد تلقائيًا.
        """

        lock = self._invite_locks.setdefault(
            guild.id,
            asyncio.Lock(),
        )

        async with lock:
            cfg = bot2.guild_config(guild)
            saved_code = cfg.get("permanent_invite_code")

            if saved_code and not force_new:
                try:
                    invite = await self.bot.fetch_invite(
                        saved_code,
                        with_counts=False,
                    )

                    if (
                        invite
                        and invite.guild
                        and invite.guild.id == guild.id
                    ):
                        return invite, False

                except (
                    discord.NotFound,
                    discord.HTTPException,
                    discord.Forbidden,
                ):
                    pass

            invite, created = await super().ensure_permanent_invite(
                guild,
                preferred,
                force_new=True,
            )

            if invite is None:
                return None, False

            # السماح بالرابط الدائم الجديد داخل حماية الروابط.
            protection = self.get_invite_protection(guild)

            allowed_codes = protection.setdefault(
                "allowed_invite_codes",
                [],
            )

            # لا نحتاج إضافته للقائمة لأن permanent invite
            # مسموح تلقائيًا، لكن نضمن إعدادات الحماية.
            self.save_invite_config(guild, protection)

            # حفظ الدعوة الجديدة في قاعدة البيانات.
            inviter_id = None

            try:
                if invite.inviter:
                    inviter_id = invite.inviter.id
            except Exception:
                pass

            channel_id = None

            try:
                if invite.channel:
                    channel_id = invite.channel.id
            except Exception:
                pass

            await self.db_call(
                self.db.save_invite,
                guild.id,
                invite.code,
                inviter_id,
                channel_id,
                invite.uses or 0,
                invite.max_uses or 0,
                invite.max_age or 0,
                True,
                True,
            )

            # تحديث cache.
            await self.initialize_invite_cache(guild)

            if announce_recovery:
                await self.send_log(
                    guild,
                    "invite_create",
                    "♻️ تم إنشاء رابط Permanent Invite بديل تلقائيًا.",
                    fields=[
                        (
                            "🔗 الرابط الجديد",
                            f"https://discord.gg/{invite.code}",
                            False,
                        ),
                        (
                            "♾️ الحالة",
                            "دائم — بدون انتهاء وبدون حد استخدام",
                            False,
                        ),
                    ],
                )

            return invite, True

    # =====================================================
    # Invite Commands
    # =====================================================

    @app_commands.command(
        name="invites",
        description="عرض عدد الدعوات التي جلبها عضو"
    )
    @app_commands.describe(
        member="العضو — اختياري"
    )
    async def invites(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ):
        member = member or interaction.user

        total = await self.db_call(
            self.db.get_invite_count,
            interaction.guild.id,
            member.id,
        )

        embed = discord.Embed(
            title="🔗 Invite Statistics",
            description=(
                f"{member.mention} لديه **{total}** "
                f"دعوة ناجحة مسجلة."
            ),
            color=discord.Color.blurple(),
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="invitetop",
        description="عرض أفضل الأشخاص في الدعوات"
    )
    async def invitetop(
        self,
        interaction: discord.Interaction,
    ):
        rows = await self.db_call(
            self.db.get_invite_top,
            interaction.guild.id,
            10,
        )

        if not rows:
            await interaction.response.send_message(
                "📊 لا توجد دعوات مسجلة حتى الآن.",
                ephemeral=True,
            )
            return

        lines = []

        for index, row in enumerate(rows, start=1):
            inviter_id = int(row["inviter_id"])
            total = int(row["total"])

            member = interaction.guild.get_member(
                inviter_id
            )

            if member:
                name = member.mention
            else:
                name = f"`{inviter_id}`"

            medal = {
                1: "🥇",
                2: "🥈",
                3: "🥉",
            }.get(index, f"`#{index}`")

            lines.append(
                f"{medal} {name} — **{total} دعوة**"
            )

        embed = discord.Embed(
            title="🏆 Invite Top",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )

        embed.set_footer(
            text="Team Fime • Invite Statistics"
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="inviteinfo",
        description="عرض معلومات دعوة معينة"
    )
    @app_commands.describe(
        code="كود الدعوة مثل abc123"
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def inviteinfo(
        self,
        interaction: discord.Interaction,
        code: str,
    ):
        code = code.strip()

        row = await self.db_call(
            self.db.get_invite_info,
            interaction.guild.id,
            code,
        )

        if row is None:
            await interaction.response.send_message(
                "❌ ما عندي معلومات عن هذه الدعوة.",
                ephemeral=True,
            )
            return

        inviter_id = row["inviter_id"]
        inviter = (
            interaction.guild.get_member(
                int(inviter_id)
            )
            if inviter_id
            else None
        )

        channel_id = row["channel_id"]
        channel = (
            interaction.guild.get_channel(
                int(channel_id)
            )
            if channel_id
            else None
        )

        embed = discord.Embed(
            title="🔗 Invite Information",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="🔑 Code",
            value=f"`{row['code']}`",
            inline=True,
        )

        embed.add_field(
            name="📊 Uses",
            value=f"`{row['uses']}`",
            inline=True,
        )

        embed.add_field(
            name="♾️ Permanent",
            value=(
                "🟢 نعم"
                if row["is_permanent"]
                else "🔴 لا"
            ),
            inline=True,
        )

        embed.add_field(
            name="👤 المنشئ",
            value=(
                inviter.mention
                if inviter
                else (
                    f"`{inviter_id}`"
                    if inviter_id
                    else "غير معروف"
                )
            ),
            inline=True,
        )

        embed.add_field(
            name="💬 الروم",
            value=(
                channel.mention
                if channel
                else (
                    f"`{channel_id}`"
                    if channel_id
                    else "غير معروف"
                )
            ),
            inline=True,
        )

        embed.add_field(
            name="📌 الحالة",
            value=(
                "🟢 Active"
                if row["active"]
                else "🔴 Deleted"
            ),
            inline=True,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # =====================================================
    # Invite Protection Settings
    # =====================================================

    @app_commands.command(
        name="inviteprotection",
        description="تشغيل أو إيقاف حماية Discord Invites"
    )
    @app_commands.describe(
        enabled="True للتشغيل، False للإيقاف"
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def inviteprotection(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ):
        if not bot2.is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ للإداريين فقط.",
                ephemeral=True,
            )
            return

        protection = self.get_invite_protection(
            interaction.guild
        )

        protection["invite_protection_enabled"] = enabled

        self.save_invite_config(
            interaction.guild,
            protection,
        )

        await interaction.response.send_message(
            "🛡️ Discord Invite Protection: "
            f"{'🟢 ON' if enabled else '🔴 OFF'}",
            ephemeral=True,
        )

    @app_commands.command(
        name="inviteallow",
        description="السماح بدعوة Discord معينة"
    )
    @app_commands.describe(
        code="كود الدعوة"
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def inviteallow(
        self,
        interaction: discord.Interaction,
        code: str,
    ):
        if not bot2.is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ للإداريين فقط.",
                ephemeral=True,
            )
            return

        code = code.strip()

        # لو المستخدم حط الرابط كاملًا.
        match = self.DISCORD_INVITE_REGEX.search(code)

        if match:
            code = match.group(1)

        if not re.fullmatch(
            r"[A-Za-z0-9-]+",
            code,
        ):
            await interaction.response.send_message(
                "❌ كود الدعوة غير صحيح.",
                ephemeral=True,
            )
            return

        protection = self.get_invite_protection(
            interaction.guild
        )

        allowed = protection.setdefault(
            "allowed_invite_codes",
            [],
        )

        if code.lower() not in {
            str(x).lower()
            for x in allowed
        }:
            allowed.append(code)

        self.save_invite_config(
            interaction.guild,
            protection,
        )

        await interaction.response.send_message(
            f"✅ تم السماح بدعوة Discord:\n"
            f"`https://discord.gg/{code}`",
            ephemeral=True,
        )

    @app_commands.command(
        name="inviteunallow",
        description="إزالة السماح عن دعوة Discord"
    )
    @app_commands.describe(
        code="كود الدعوة"
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def inviteunallow(
        self,
        interaction: discord.Interaction,
        code: str,
    ):
        if not bot2.is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ للإداريين فقط.",
                ephemeral=True,
            )
            return

        match = self.DISCORD_INVITE_REGEX.search(code)

        if match:
            code = match.group(1)

        protection = self.get_invite_protection(
            interaction.guild
        )

        protection["allowed_invite_codes"] = [
            x
            for x in protection.get(
                "allowed_invite_codes",
                [],
            )
            if str(x).lower() != code.lower()
        ]

        self.save_invite_config(
            interaction.guild,
            protection,
        )

        await interaction.response.send_message(
            f"♻️ تم إلغاء السماح بالدعوة `{code}`.",
            ephemeral=True,
        )

    @app_commands.command(
        name="invitestatus",
        description="عرض حالة نظام الدعوات والحماية"
    )
    @app_commands.default_permissions(
        administrator=True
    )
    async def invitestatus(
        self,
        interaction: discord.Interaction,
    ):
        if not bot2.is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ للإداريين فقط.",
                ephemeral=True,
            )
            return

        protection = self.get_invite_protection(
            interaction.guild
        )

        permanent = self.get_saved_permanent_code(
            interaction.guild
        )

        cache = self._invite_cache.get(
            interaction.guild.id,
            {},
        )

        embed = discord.Embed(
            title="🔗 Invite System",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="♾️ Permanent Invite",
            value=(
                f"`https://discord.gg/{permanent}`"
                if permanent
                else "❌ غير موجود"
            ),
            inline=False,
        )

        embed.add_field(
            name="🛡️ Invite Protection",
            value=(
                "🟢 ON"
                if protection.get(
                    "invite_protection_enabled",
                    True,
                )
                else "🔴 OFF"
            ),
            inline=True,
        )

        embed.add_field(
            name="🏠 Server Invites",
            value=(
                "🟢 مسموحة"
                if protection.get(
                    "allow_server_invites",
                    True,
                )
                else "🔴 ممنوعة"
            ),
            inline=True,
        )

        embed.add_field(
            name="🔗 Known Invites",
            value=f"`{len(cache)}`",
            inline=True,
        )

        allowed = protection.get(
            "allowed_invite_codes",
            [],
        )

        embed.add_field(
            name="✅ Allowed Codes",
            value=(
                ", ".join(
                    f"`{x}`"
                    for x in allowed[:15]
                )
                if allowed
                else "لا يوجد"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # =====================================================
    # Member Join — Invite Tracking
    # =====================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # أولًا نحافظ على Anti-Raid + Join Log الموجود في bot2.
        await super().on_member_join(member)

        # حفظ المستخدم في قاعدة البيانات.
        try:
            await self.db_call(
                self.db.upsert_user,
                member.guild.id,
                member.id,
                member.name,
                member.display_name,
                datetime.now(timezone.utc).isoformat(),
            )
        except Exception as error:
            print(
                f"⚠️ User DB error: {error}"
            )

        # البوتات لا نحسب دخولها كدعوة عضو.
        if member.bot:
            return

        try:
            used_invite = await self.detect_used_invite(
                member.guild
            )

            inviter = None
            invite_code = None

            if used_invite:
                invite_code = used_invite["code"]

                inviter_id = used_invite.get(
                    "inviter_id"
                )

                if inviter_id:
                    inviter = member.guild.get_member(
                        int(inviter_id)
                    )

                await self.db_call(
                    self.db.record_invite_use,
                    member.guild.id,
                    invite_code,
                    member.id,
                    inviter_id,
                )

            # إذا لم نستطع تحديد الدعوة.
            if invite_code is None:
                invite_code = "unknown"

            if inviter:
                inviter_text = inviter.mention

                await self.send_log(
                    member.guild,
                    "member_join",
                    (
                        f"دخل {member.mention} إلى السيرفر "
                        f"عن طريق دعوة {inviter.mention}."
                    ),
                    fields=[
                        (
                            "🔗 الدعوة",
                            f"`{invite_code}`",
                            True,
                        ),
                        (
                            "👤 الداعي",
                            inviter.mention,
                            True,
                        ),
                    ],
                )

            else:
                await self.send_log(
                    member.guild,
                    "member_join",
                    (
                        f"دخل {member.mention} إلى السيرفر، "
                        "ولم أتمكن من تحديد مصدر الدعوة."
                    ),
                    fields=[
                        (
                            "🔗 المصدر",
                            "Unknown",
                            True,
                        ),
                    ],
                )

        except Exception as error:
            print(
                f"⚠️ Invite tracking error "
                f"in {member.guild.name}: {error}"
            )

    # =====================================================
    # Invite Create
    # =====================================================

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        # الحفاظ على اللوق القديم.
        await super().on_invite_create(invite)

        if not invite.guild:
            return

        inviter_id = None

        try:
            if invite.inviter:
                inviter_id = invite.inviter.id
        except Exception:
            pass

        channel_id = None

        try:
            if invite.channel:
                channel_id = invite.channel.id
        except Exception:
            pass

        await self.db_call(
            self.db.save_invite,
            invite.guild.id,
            invite.code,
            inviter_id,
            channel_id,
            invite.uses or 0,
            invite.max_uses or 0,
            invite.max_age or 0,
            (
                (invite.max_age or 0) == 0
                and (invite.max_uses or 0) == 0
            ),
            True,
        )

        await self.initialize_invite_cache(
            invite.guild
        )

    # =====================================================
    # Invite Delete — Permanent Recovery
    # =====================================================

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if not invite.guild:
            return

        code = invite.code

        await self.db_call(
            self.db.mark_invite_deleted,
            invite.guild.id,
            code,
        )

        # نرسل اللوق القديم أولًا.
        await super().on_invite_delete(invite)

        permanent_code = self.get_saved_permanent_code(
            invite.guild
        )

        # إذا الرابط المحذوف هو الرابط الدائم.
        if (
            permanent_code
            and permanent_code.lower() == code.lower()
        ):
            print(
                f"♻️ Permanent Invite deleted "
                f"in {invite.guild.name}. "
                f"Creating replacement..."
            )

            try:
                new_invite, created = (
                    await self.ensure_permanent_invite_advanced(
                        invite.guild,
                        force_new=True,
                        announce_recovery=True,
                    )
                )

                if new_invite:
                    print(
                        f"✅ New permanent invite created: "
                        f"{new_invite.code}"
                    )
                else:
                    print(
                        f"⚠️ Could not recreate "
                        f"permanent invite in "
                        f"{invite.guild.name}"
                    )

            except Exception as error:
                print(
                    f"❌ Permanent invite recovery error: "
                    f"{error}"
                )

        else:
            try:
                await self.initialize_invite_cache(
                    invite.guild
                )
            except Exception:
                pass

    # =====================================================
    # Message Protection — Discord Invites
    # =====================================================

    async def process_discord_invite_protection(
        self,
        message,
    ):
        if (
            not message.guild
            or not message.content
            or message.author.bot
        ):
            return False

        protection = self.get_invite_protection(
            message.guild
        )

        if not protection.get(
            "invite_protection_enabled",
            True,
        ):
            return False

        codes = self.extract_discord_invites(
            message.content
        )

        if not codes:
            return False

        for code in codes:
            if self.is_allowed_discord_invite(
                message.guild,
                code,
            ):
                continue

            # دعوة خارجية غير مسموحة.
            try:
                await message.delete()
            except discord.HTTPException:
                pass

            timeout_seconds = int(
                protection.get(
                    "spam_timeout_seconds",
                    600,
                )
            )

            try:
                await message.author.timeout(
                    discord.utils.utcnow()
                    + bot2.timedelta(
                        seconds=timeout_seconds
                    ),
                    reason=(
                        "Team Fime Invite Protection: "
                        "External Discord Invite"
                    ),
                )
            except Exception:
                pass

            await self.send_log(
                message.guild,
                "protection",
                (
                    f"🛡️ تم منع Discord Invite غير مسموح "
                    f"به من {message.author.mention}."
                ),
                fields=[
                    (
                        "🔗 الدعوة",
                        f"`https://discord.gg/{code}`",
                        False,
                    ),
                    (
                        "👤 العضو",
                        message.author.mention,
                        True,
                    ),
                    (
                        "💬 الروم",
                        bot2.channel_text(
                            message.channel
                        ),
                        True,
                    ),
                    (
                        "⚖️ العقوبة",
                        f"Timeout `{timeout_seconds}` ثانية",
                        True,
                    ),
                ],
            )

            return True

        return False

    async def process_protection(self, message):
        """
        Discord Invite Protection قبل الحماية القديمة.

        إذا كان الرابط مسموحًا:
        نسمح له ونترك بقية أنظمة الحماية تعمل.

        إذا كان ممنوعًا:
        يتم حذفه وتطبيق العقوبة.
        """

        blocked = await self.process_discord_invite_protection(
            message
        )

        if blocked:
            return

        # الحماية الأصلية تبقى كما هي.
        await super().process_protection(message)

    # =====================================================
    # Permanent Invite Checker
    # =====================================================

    @tasks.loop(minutes=5)
    async def permanent_invite_checker(self):
        """
        كل 5 دقائق:
        - يفحص الرابط الدائم.
        - إذا انحذف أو أصبح غير صالح:
          ينشئ رابطًا جديدًا.
        - يحدث Invite cache.
        """

        for guild in list(self.bot.guilds):
            try:
                await self.ensure_permanent_invite_advanced(
                    guild,
                    force_new=False,
                    announce_recovery=True,
                )

                await self.initialize_invite_cache(
                    guild
                )

            except Exception as error:
                print(
                    f"⚠️ Invite checker error "
                    f"in {guild.name}: {error}"
                )

    @permanent_invite_checker.before_loop
    async def before_permanent_invite_checker(self):
        await self.bot.wait_until_ready()

    # =====================================================
    # Ready
    # =====================================================

    @commands.Cog.listener()
    async def on_ready(self):
        # تشغيل أنظمة bot2 الأصلية.
        await super().on_ready()

        # تجهيز Invite cache لكل السيرفرات.
        for guild in list(self.bot.guilds):
            try:
                await self.ensure_permanent_invite_advanced(
                    guild,
                    force_new=False,
                    announce_recovery=False,
                )

                await self.initialize_invite_cache(
                    guild
                )

            except Exception as error:
                print(
                    f"⚠️ Invite startup error "
                    f"in {guild.name}: {error}"
                )

        print(
            "✅ Team Fime bot3 is fully ready."
        )


# =========================================================
# Setup
# =========================================================

async def setup(bot):
    await bot.add_cog(
        AdvancedFimeBot(bot)
    )

    print(
        "✅ تم تشغيل Team Fime bot3 بالكامل."
    )