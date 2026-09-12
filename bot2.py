import asyncio
import json
import os
import re
import time
import urllib.request
import urllib.error
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks


# =========================================================
# Team Fime — bot2.py
# Server Logs + Moderation + Protection + Levels + Buttons
# + Roles + Ping + Optional AI
#
# ملاحظة:
# - لا يوجد on_member_remove عمدًا.
# - يتم تحميل هذا الملف من bot.py عبر:
#       import bot2
#       asyncio.run(bot2.setup(bot))
# =========================================================

CONFIG_FILE = "config.json"

LOG_COLORS = {
    "member_join": discord.Color.green(),
    "role_create": discord.Color.green(),
    "role_delete": discord.Color.red(),
    "role_update": discord.Color.orange(),
    "channel_create": discord.Color.green(),
    "channel_delete": discord.Color.red(),
    "channel_update": discord.Color.orange(),
    "voice_join": discord.Color.green(),
    "voice_leave": discord.Color.red(),
    "voice_move": discord.Color.blurple(),
    "thread_create": discord.Color.green(),
    "thread_delete": discord.Color.red(),
    "thread_update": discord.Color.orange(),
    "category_create": discord.Color.green(),
    "category_delete": discord.Color.red(),
    "category_update": discord.Color.orange(),
    "emoji_create": discord.Color.green(),
    "emoji_delete": discord.Color.red(),
    "emoji_update": discord.Color.orange(),
    "sticker_create": discord.Color.green(),
    "sticker_delete": discord.Color.red(),
    "sticker_update": discord.Color.orange(),
    "member_update": discord.Color.blurple(),
    "ban": discord.Color.red(),
    "unban": discord.Color.green(),
    "message_delete": discord.Color.red(),
    "message_bulk_delete": discord.Color.red(),
    "message_edit": discord.Color.orange(),
    "invite_create": discord.Color.green(),
    "invite_delete": discord.Color.red(),
    "guild_update": discord.Color.orange(),
    "warning": discord.Color.orange(),
    "protection": discord.Color.red(),
    "moderation": discord.Color.red(),
    "level": discord.Color.gold(),
    "ai": discord.Color.blurple(),
}

EVENT_LABELS = {
    "member_join": "👤 دخول عضو",
    "role_create": "🟢 إنشاء رتبة",
    "role_delete": "🔴 حذف رتبة",
    "role_update": "🟠 تعديل رتبة",
    "channel_create": "🟢 إنشاء روم",
    "channel_delete": "🔴 حذف روم",
    "channel_update": "🟠 تعديل روم",
    "voice_join": "🔊 دخول فويس",
    "voice_leave": "🔇 خروج من الفويس",
    "voice_move": "🔀 نقل في الفويس",
    "thread_create": "🧵 إنشاء Thread",
    "thread_delete": "🗑️ حذف Thread",
    "thread_update": "📝 تعديل Thread",
    "category_create": "📁 إنشاء Category",
    "category_delete": "🗑️ حذف Category",
    "category_update": "📝 تعديل Category",
    "emoji_create": "😀 إنشاء Emoji",
    "emoji_delete": "🗑️ حذف Emoji",
    "emoji_update": "😀 تعديل Emoji",
    "sticker_create": "🏷️ إنشاء Sticker",
    "sticker_delete": "🗑️ حذف Sticker",
    "sticker_update": "🏷️ تعديل Sticker",
    "member_update": "✏️ تعديل عضو",
    "ban": "🔨 حظر عضو",
    "unban": "🔓 فك حظر عضو",
    "message_delete": "🗑️ حذف رسالة",
    "message_bulk_delete": "🗑️ حذف رسائل",
    "message_edit": "✏️ تعديل رسالة",
    "invite_create": "🔗 إنشاء دعوة",
    "invite_delete": "🔗 حذف دعوة",
    "guild_update": "⚙️ تعديل السيرفر",
    "warning": "⚠️ تحذير",
    "protection": "🛡️ حماية",
    "moderation": "⚖️ عقوبة",
    "level": "⭐ Level",
    "ai": "🤖 AI",
}

ENABLED_DEFAULTS = {key: True for key in EVENT_LABELS}


# =========================================================
# Config helpers
# =========================================================

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(data):
    temp = CONFIG_FILE + ".bot2.tmp"
    try:
        with open(temp, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temp, CONFIG_FILE)
        return True
    except OSError as error:
        print(f"❌ bot2 config error: {error}")
        return False


def guild_config(guild):
    data = load_config()
    guilds = data.setdefault("guilds", {})
    cfg = guilds.setdefault(str(guild.id), {})

    cfg.setdefault("server_log_channel_id", None)
    cfg.setdefault("server_log_events", dict(ENABLED_DEFAULTS))

    # Levels
    cfg.setdefault("levels_enabled", True)
    cfg.setdefault("level_chat_xp_min", 8)
    cfg.setdefault("level_chat_xp_max", 15)
    cfg.setdefault("level_chat_cooldown", 45)
    cfg.setdefault("level_voice_xp_per_minute", 3)
    cfg.setdefault("level_rewards", {})
    cfg.setdefault("level_xp", {})
    cfg.setdefault("level_channel_id", None)

    # Protection
    protection = cfg.setdefault("protection", {})
    protection.setdefault("enabled", True)
    protection.setdefault("anti_spam", True)
    protection.setdefault("spam_limit", 5)
    protection.setdefault("spam_window", 5)
    protection.setdefault("spam_timeout_seconds", 600)
    protection.setdefault("anti_repeat", True)
    protection.setdefault("repeat_limit", 3)
    protection.setdefault("anti_links", True)
    protection.setdefault("allowed_domains", [])
    protection.setdefault("anti_mentions", True)
    protection.setdefault("mention_limit", 5)
    protection.setdefault("mention_timeout_minutes", 10)
    protection.setdefault("exempt_spam_role_ids", [])
    protection.setdefault("exempt_link_role_ids", [])
    protection.setdefault("security_enabled", True)
    protection.setdefault("raid_join_limit", 8)
    protection.setdefault("raid_window_seconds", 15)
    protection.setdefault("raid_timeout_minutes", 10)
    protection.setdefault("security_action", "timeout_new_joins")

    # Permanent invite
    cfg.setdefault("permanent_invite_code", None)
    cfg.setdefault("permanent_invite_channel_id", None)

    # AI
    ai = cfg.setdefault("ai", {})
    ai.setdefault("enabled", False)
    ai.setdefault("channel_id", None)
    ai.setdefault("system_prompt", "أنت مساعد مفيد وودود داخل سيرفر Discord. كن مختصرًا وواضحًا. إذا سأل المستخدم عن سكربتات أو إعدادات البوت، أعطه شرحًا آمنًا ومباشرًا.")

    # Warnings
    cfg.setdefault("warnings", {})

    save_config(data)
    return cfg


def update_guild_config(guild, callback):
    data = load_config()
    guilds = data.setdefault("guilds", {})
    cfg = guilds.setdefault(str(guild.id), {})
    callback(cfg)
    save_config(data)
    return cfg


def set_value(guild, path, value):
    def writer(cfg):
        target = cfg
        for key in path[:-1]:
            target = target.setdefault(key, {})
        target[path[-1]] = value
    update_guild_config(guild, writer)


def get_value(guild, path, default=None):
    cfg = guild_config(guild)
    target = cfg
    for key in path:
        if not isinstance(target, dict) or key not in target:
            return default
        target = target[key]
    return target


# =========================================================
# Generic helpers
# =========================================================

def truncate(value, limit=900):
    if value is None:
        return "غير متوفر"
    value = str(value)
    if not value:
        return "بدون قيمة"
    return value if len(value) <= limit else value[:limit - 3] + "..."


def mention_user(user):
    if user is None:
        return "غير معروف"
    return getattr(user, "mention", f"`{getattr(user, 'id', 'unknown')}`")


def channel_text(channel):
    if channel is None:
        return "غير معروف"
    mention = getattr(channel, "mention", None)
    return mention or f"`{getattr(channel, 'name', 'unknown')}`"


def role_text(role):
    if role is None:
        return "غير معروف"
    return getattr(role, "mention", f"`{getattr(role, 'name', 'unknown')}`")


def color_for(event_key):
    return LOG_COLORS.get(event_key, discord.Color.blurple())


def permission_ok(guild, channel):
    me = guild.me
    if me is None:
        return False
    permissions = channel.permissions_for(me)
    return permissions.view_channel and permissions.send_messages and permissions.embed_links


def is_admin(member):
    return bool(member and member.guild_permissions.administrator)


def is_owner(member):
    return bool(member and member.guild and member.id == member.guild.owner_id)


def can_moderate(actor, target):
    if target is None:
        return False, "العضو غير موجود."
    if target.id == actor.id:
        return False, "لا يمكنك تنفيذ العقوبة على نفسك."
    if target.id == target.guild.owner_id:
        return False, "لا يمكن معاقبة مالك السيرفر."
    if actor.id != target.guild.owner_id and target.top_role >= actor.top_role:
        return False, "رتبة العضو أعلى منك أو مساوية لرتبتك."
    me = target.guild.me
    if me and target.top_role >= me.top_role:
        return False, "رتبة البوت يجب أن تكون أعلى من رتبة العضو."
    return True, ""


def parse_duration(text):
    if not text:
        return None
    match = re.fullmatch(r"\s*(\d+)\s*([smhdw])\s*", text.lower())
    if not match:
        return None
    number = int(match.group(1))
    unit = match.group(2)
    seconds = {
        "s": number,
        "m": number * 60,
        "h": number * 3600,
        "d": number * 86400,
        "w": number * 604800,
    }[unit]
    return seconds


# =========================================================
# Persistent interactive buttons
# =========================================================

class PanelButton(discord.ui.Button):
    def __init__(self, cog, guild_id, panel_id, index, label, response):
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"fimepanel:{guild_id}:{panel_id}:{index}",
        )
        self.cog = cog
        self.guild_id = guild_id
        self.panel_id = panel_id
        self.index = index
        self.button_response = response

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("❌ هذا الزر غير متاح هنا.", ephemeral=True)
            return

        await interaction.response.send_message(
            self.button_response[:1900],
            ephemeral=True,
        )


class PersistentPanel(discord.ui.View):
    def __init__(self, cog, guild_id, panel_id, buttons):
        super().__init__(timeout=None)
        for index, item in enumerate(buttons):
            self.add_item(
                PanelButton(
                    cog,
                    guild_id,
                    panel_id,
                    index,
                    item["label"],
                    item["response"],
                )
            )


# =========================================================
# Main Cog
# =========================================================

class ServerLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_messages = {}
        self._message_times = defaultdict(deque)
        self._repeat_messages = defaultdict(deque)
        self._chat_xp_cooldown = {}
        self._voice_xp_loop_started = False
        self._raid_joins = defaultdict(deque)
        self._security_actions = defaultdict(deque)

    async def cog_load(self):
        print("✅ Team Fime bot2 systems loaded.")

    async def cog_unload(self):
        if self.voice_xp_loop.is_running():
            self.voice_xp_loop.cancel()

    async def restore_persistent_panels(self):
        data = load_config()
        guilds = data.get("guilds", {})
        count = 0

        for guild_id, cfg in guilds.items():
            panels = cfg.get("button_panels", {})
            if not isinstance(panels, dict):
                continue

            for panel_id, panel in panels.items():
                try:
                    buttons = panel.get("buttons", [])
                    if not buttons:
                        continue
                    self.bot.add_view(
                        PersistentPanel(
                            self,
                            int(guild_id),
                            panel_id,
                            buttons,
                        ),
                        message_id=int(panel.get("message_id")),
                    )
                    count += 1
                except Exception as error:
                    print(f"⚠️ تعذر استعادة panel {panel_id}: {error}")

        print(f"✅ تم استعادة {count} لوحة أزرار.")

    # =====================================================
    # Logs
    # =====================================================

    def get_log_settings(self, guild):
        return guild_config(guild)

    def get_log_channel(self, guild):
        cfg = guild_config(guild)
        channel_id = cfg.get("server_log_channel_id")

        if channel_id:
            try:
                channel = guild.get_channel(int(channel_id))
            except (TypeError, ValueError):
                channel = None
            if isinstance(channel, discord.TextChannel):
                return channel

        old_id = cfg.get("log_channel_id")
        if old_id:
            try:
                channel = guild.get_channel(int(old_id))
            except (TypeError, ValueError):
                channel = None
            if isinstance(channel, discord.TextChannel):
                return channel

        return None

    def event_enabled(self, guild, event_key):
        cfg = guild_config(guild)
        return bool(cfg.get("server_log_events", {}).get(event_key, True))

    async def send_log(
        self,
        guild,
        event_key,
        description,
        *,
        actor=None,
        fields=None,
        footer=None,
        thumbnail=None,
    ):
        if guild is None or not self.event_enabled(guild, event_key):
            return

        channel = self.get_log_channel(guild)
        if channel is None or not permission_ok(guild, channel):
            return

        embed = discord.Embed(
            title=EVENT_LABELS.get(event_key, "📋 Server Log"),
            description=truncate(description, 3900),
            color=color_for(event_key),
            timestamp=datetime.now(timezone.utc),
        )

        if actor is not None:
            embed.add_field(
                name="👤 المنفذ",
                value=mention_user(actor),
                inline=True,
            )

        if fields:
            for name, value, inline in fields:
                embed.add_field(
                    name=truncate(name, 256),
                    value=truncate(value, 1024),
                    inline=inline,
                )

        if thumbnail:
            try:
                embed.set_thumbnail(url=thumbnail)
            except Exception:
                pass

        embed.set_footer(text=footer or f"{guild.name} • Team Fime")

        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # =====================================================
    # /serverlog
    # =====================================================

    @app_commands.command(name="serverlog", description="تحديد روم لوق أحداث السيرفر")
    @app_commands.describe(channel="روم اللوق")
    @app_commands.default_permissions(administrator=True)
    async def serverlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        set_value(interaction.guild, ["server_log_channel_id"], channel.id)
        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} كروم Server Logs.",
            ephemeral=True,
        )

        await self.send_log(
            interaction.guild,
            "guild_update",
            f"تم تغيير روم Server Logs إلى {channel.mention}.",
            actor=interaction.user,
        )

    @app_commands.command(name="serverlogoff", description="إيقاف Server Logs")
    @app_commands.default_permissions(administrator=True)
    async def serverlogoff(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        set_value(interaction.guild, ["server_log_channel_id"], None)
        await interaction.response.send_message("✅ تم إيقاف Server Logs.", ephemeral=True)

    @app_commands.command(name="serverlogstatus", description="عرض حالة Server Logs")
    @app_commands.default_permissions(administrator=True)
    async def serverlogstatus(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        cfg = guild_config(interaction.guild)
        channel = self.get_log_channel(interaction.guild)

        embed = discord.Embed(
            title="📋 Server Logs Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="📌 روم اللوق",
            value=channel.mention if channel else "❌ غير محدد",
            inline=False,
        )
        embed.add_field(
            name="🚫 خروج السيرفر",
            value="غير مسجل حسب طلبك",
            inline=True,
        )
        embed.add_field(
            name="📊 الأحداث",
            value=f"{sum(bool(v) for v in cfg.get('server_log_events', {}).values())} مفعلة",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # Commands overview
    # =====================================================

    @app_commands.command(name="commands", description="عرض أوامر وأنظمة البوت")
    async def commands_list(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Team Fime Bot",
            description="قائمة مختصرة بأنظمة البوت وحالتها.",
            color=discord.Color.blurple(),
        )

        cfg = guild_config(interaction.guild)
        protection = cfg["protection"]
        ai = cfg["ai"]

        embed.add_field(
            name="📋 Logs",
            value="`/serverlog` • `/serverlogstatus` • `/serverlogoff`",
            inline=False,
        )
        embed.add_field(
            name="⭐ Levels",
            value="`/level` • `/setxp` • `/resetlevel` • `/levelreward` • `/levelchannel`",
            inline=False,
        )
        embed.add_field(
            name="⚖️ Moderation",
            value="`/warn` • `/warnings` • `/clearwarnings` • `/timeout` • `/ban` • `/unban` • `/kick`",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Protection",
            value=f"{'🟢 مفعلة' if protection['enabled'] else '🔴 معطلة'}",
            inline=True,
        )
        embed.add_field(
            name="🤖 AI",
            value=f"{'🟢 مفعلة' if ai['enabled'] else '🔴 معطلة'}",
            inline=True,
        )
        embed.add_field(
            name="🏓 Ping",
            value="`/ping`",
            inline=True,
        )
        embed.add_field(
            name="🏷️ Roles",
            value="`/roles` • `/roleinfo`",
            inline=True,
        )
        embed.add_field(
            name="🔘 Buttons",
            value="`/buttonpanel`",
            inline=True,
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ping", description="عرض سرعة البوت")
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 **Pong!**\n`{latency}ms`"
        )

    # =====================================================
    # Button panels
    # =====================================================

    @app_commands.command(name="buttonpanel", description="إنشاء Embed تفاعلي بأزرار")
    @app_commands.describe(
        title="عنوان الـEmbed",
        description="نص الـEmbed",
        button1="اسم الزر الأول",
        response1="رد الزر الأول",
        button2="اسم الزر الثاني اختياري",
        response2="رد الزر الثاني اختياري",
        button3="اسم الزر الثالث اختياري",
        response3="رد الزر الثالث اختياري",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def buttonpanel(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        button1: str,
        response1: str,
        button2: str | None = None,
        response2: str | None = None,
        button3: str | None = None,
        response3: str | None = None,
    ):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ تحتاج Manage Server.", ephemeral=True)
            return

        pairs = [(button1, response1)]
        if button2 and response2:
            pairs.append((button2, response2))
        if button3 and response3:
            pairs.append((button3, response3))

        panel_id = str(int(time.time() * 1000))
        buttons = [
            {"label": label[:80], "response": response[:1900]}
            for label, response in pairs
        ]

        embed = discord.Embed(
            title=title[:256],
            description=description[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Team Fime • Interactive Panel")

        view = PersistentPanel(
            self,
            interaction.guild.id,
            panel_id,
            buttons,
        )

        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()

        def writer(cfg):
            panels = cfg.setdefault("button_panels", {})
            panels[panel_id] = {
                "message_id": message.id,
                "channel_id": message.channel.id,
                "title": title,
                "description": description,
                "buttons": buttons,
            }

        update_guild_config(interaction.guild, writer)

    # =====================================================
    # Roles
    # =====================================================

    @app_commands.command(name="roles", description="عرض رتب السيرفر")
    async def roles(self, interaction: discord.Interaction):
        roles = sorted(
            [r for r in interaction.guild.roles if r != interaction.guild.default_role],
            key=lambda r: r.position,
            reverse=True,
        )

        lines = []
        for role in roles[:50]:
            lines.append(
                f"{role.mention} — `{len(role.members)} عضو` — `{role.id}`"
            )

        embed = discord.Embed(
            title="🏷️ رتب السيرفر",
            description="\n".join(lines) if lines else "لا توجد رتب.",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"الإجمالي: {len(roles)} رتبة")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="عرض معلومات رتبة")
    @app_commands.describe(role="الرتبة")
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        permissions = []
        for name, value in role.permissions:
            if value:
                permissions.append(name.replace("_", " ").title())

        embed = discord.Embed(
            title=f"🏷️ {role.name}",
            color=role.color if role.color.value else discord.Color.blurple(),
        )
        embed.add_field(name="🆔 ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="👥 الأعضاء", value=str(len(role.members)), inline=True)
        embed.add_field(name="📌 الترتيب", value=str(role.position), inline=True)
        embed.add_field(name="🎨 اللون", value=str(role.color), inline=True)
        embed.add_field(name="📣 Mentionable", value=str(role.mentionable), inline=True)
        embed.add_field(name="🤖 Managed", value=str(role.managed), inline=True)
        embed.add_field(
            name="🔐 أهم الصلاحيات",
            value=", ".join(permissions[:20]) or "لا توجد",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    # =====================================================
    # Levels
    # =====================================================

    @staticmethod
    def level_from_xp(xp):
        # منحنى بسيط ومفهوم: المستوى يرتفع كلما زاد XP.
        level = 0
        while xp >= (level + 1) * (level + 1) * 100:
            level += 1
        return level

    @staticmethod
    def xp_for_level(level):
        return level * level * 100

    def get_user_xp(self, guild, user_id):
        data = get_value(guild, ["level_xp"], {})
        return int(data.get(str(user_id), 0))

    def set_user_xp(self, guild, user_id, xp):
        xp = max(0, int(xp))

        def writer(cfg):
            levels = cfg.setdefault("level_xp", {})
            levels[str(user_id)] = xp

        update_guild_config(guild, writer)

    def add_user_xp(self, guild, user_id, amount):
        old_xp = self.get_user_xp(guild, user_id)
        new_xp = max(0, old_xp + int(amount))
        self.set_user_xp(guild, user_id, new_xp)
        return old_xp, new_xp

    async def check_level_reward(self, guild, member, old_level, new_level):
        rewards = get_value(guild, ["level_rewards"], {})
        for level_text, role_id in rewards.items():
            try:
                reward_level = int(level_text)
                role = guild.get_role(int(role_id))
            except (ValueError, TypeError):
                continue

            if old_level < reward_level <= new_level and role:
                if role not in member.roles and role < guild.me.top_role:
                    try:
                        await member.add_roles(role, reason=f"Level {reward_level} reward")
                    except discord.HTTPException:
                        pass

    async def announce_level_up(self, guild, member, old_level, new_level, xp, source):
        channel_id = get_value(guild, ["level_channel_id"], None)
        channel = None
        if channel_id:
            channel = guild.get_channel(int(channel_id))
        if channel is not None and isinstance(channel, discord.TextChannel):
            if permission_ok(guild, channel):
                embed = discord.Embed(
                    title="🎉 Level Up!",
                    description=f"مبروك {member.mention}! ارتفع مستواك من **{old_level}** إلى **{new_level}**.",
                    color=discord.Color.gold(),
                )
                embed.add_field(name="✨ XP", value=f"`{xp}`", inline=True)
                embed.add_field(name="📌 المصدر", value=source, inline=True)
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                    return
                except discord.HTTPException:
                    pass

        await self.send_log(
            guild,
            "level",
            f"ارتفع مستوى {member.mention}!",
            fields=[
                ("⭐ المستوى", f"`{old_level}` → `{new_level}`", True),
                ("✨ XP", f"`{xp}`", True),
                ("📌 المصدر", source, True),
            ],
        )

    @app_commands.command(name="levelchannel", description="تحديد روم إعلانات الارتقاء باللفل")
    @app_commands.describe(channel="الروم الذي تظهر فيه رسائل Level Up")
    @app_commands.default_permissions(administrator=True)
    async def levelchannel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        if channel is None:
            set_value(interaction.guild, ["level_channel_id"], None)
            await interaction.response.send_message("♻️ تم إلغاء روم إعلانات اللفل. ستعود رسائل اللفل إلى اللوق.", ephemeral=True)
            return
        set_value(interaction.guild, ["level_channel_id"], channel.id)
        await interaction.response.send_message(f"✅ روم اللفل أصبح {channel.mention}.", ephemeral=True)

    async def award_chat_xp(self, message):
        guild = message.guild
        member = message.author
        if not guild or not member or member.bot:
            return
        if not get_value(guild, ["levels_enabled"], True):
            return

        now = time.monotonic()
        key = (guild.id, member.id)
        cooldown = int(get_value(guild, ["level_chat_cooldown"], 45))

        if now - self._chat_xp_cooldown.get(key, 0) < cooldown:
            return

        self._chat_xp_cooldown[key] = now

        import random
        minimum = int(get_value(guild, ["level_chat_xp_min"], 8))
        maximum = int(get_value(guild, ["level_chat_xp_max"], 15))
        amount = random.randint(minimum, max(minimum, maximum))

        old_xp, new_xp = self.add_user_xp(guild, member.id, amount)
        old_level = self.level_from_xp(old_xp)
        new_level = self.level_from_xp(new_xp)

        if new_level > old_level:
            await self.check_level_reward(guild, member, old_level, new_level)
            await self.announce_level_up(guild, member, old_level, new_level, new_xp, "💬 الشات")

    @app_commands.command(name="level", description="عرض Level وXP لعضو")
    @app_commands.describe(member="العضو اختياري")
    async def level(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        xp = self.get_user_xp(interaction.guild, member.id)
        level = self.level_from_xp(xp)
        next_xp = self.xp_for_level(level + 1)
        current_floor = self.xp_for_level(level)
        progress = max(0, xp - current_floor)
        required = max(1, next_xp - current_floor)

        embed = discord.Embed(
            title="⭐ Level",
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="👤 العضو", value=member.mention, inline=True)
        embed.add_field(name="⭐ المستوى", value=f"`{level}`", inline=True)
        embed.add_field(name="✨ XP", value=f"`{xp}`", inline=True)
        embed.add_field(
            name="📈 التقدم",
            value=f"`{progress}/{required}` نحو Level {level + 1}",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setxp", description="تحديد XP لعضو")
    @app_commands.describe(member="العضو", xp="قيمة XP الجديدة")
    @app_commands.default_permissions(administrator=True)
    async def setxp(self, interaction: discord.Interaction, member: discord.Member, xp: int):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        if xp < 0:
            await interaction.response.send_message("❌ لا يمكن أن يكون XP سالبًا.", ephemeral=True)
            return

        old = self.get_user_xp(interaction.guild, member.id)
        self.set_user_xp(interaction.guild, member.id, xp)

        await interaction.response.send_message(
            f"✅ تم تعديل XP لـ {member.mention}: `{old}` → `{xp}`"
        )

    @app_commands.command(name="resetlevel", description="إعادة تعيين Level وXP لعضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(administrator=True)
    async def resetlevel(self, interaction: discord.Interaction, member: discord.Member):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        self.set_user_xp(interaction.guild, member.id, 0)
        await interaction.response.send_message(f"♻️ تم تصفير Level وXP لـ {member.mention}.")

    @app_commands.command(name="levelreward", description="تحديد رتبة كمكافأة لمستوى")
    @app_commands.describe(level="رقم المستوى", role="الرتبة")
    @app_commands.default_permissions(administrator=True)
    async def levelreward(self, interaction: discord.Interaction, level: int, role: discord.Role):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        if level < 1:
            await interaction.response.send_message("❌ المستوى يجب أن يكون 1 أو أكثر.", ephemeral=True)
            return
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ رتبة البوت يجب أن تكون أعلى من رتبة المكافأة.",
                ephemeral=True,
            )
            return

        def writer(cfg):
            cfg.setdefault("level_rewards", {})[str(level)] = role.id

        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(
            f"🎁 Level `{level}` → {role.mention}"
        )

    # =====================================================
    # Moderation
    # =====================================================

    def warning_list(self, guild, member_id):
        warnings = get_value(guild, ["warnings"], {})
        return list(warnings.get(str(member_id), []))

    def add_warning(self, guild, member, moderator, reason):
        warning = {
            "id": int(time.time() * 1000),
            "reason": reason[:500],
            "moderator_id": moderator.id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        def writer(cfg):
            warnings = cfg.setdefault("warnings", {})
            warnings.setdefault(str(member.id), []).append(warning)

        update_guild_config(guild, writer)
        return warning

    @app_commands.command(name="warn", description="تسجيل تحذير على عضو")
    @app_commands.describe(member="العضو", reason="سبب التحذير")
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ تحتاج Moderate Members.", ephemeral=True)
            return

        ok, message = can_moderate(interaction.user, member)
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        warning = self.add_warning(interaction.guild, member, interaction.user, reason)

        await interaction.response.send_message(
            f"⚠️ تم تسجيل تحذير على {member.mention}.\n"
            f"**السبب:** {reason}\n"
            f"**رقم التحذير:** `{warning['id']}`"
        )

        await self.send_log(
            interaction.guild,
            "warning",
            f"تم تسجيل تحذير على {member.mention}.",
            actor=interaction.user,
            fields=[("السبب", reason, False)],
        )

    @app_commands.command(name="warnings", description="عرض تحذيرات عضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ تحتاج Moderate Members.", ephemeral=True)
            return

        items = self.warning_list(interaction.guild, member.id)

        if not items:
            await interaction.response.send_message(
                f"✅ {member.mention} ليس لديه تحذيرات."
            )
            return

        lines = []
        for item in items[-15:]:
            moderator = interaction.guild.get_member(item["moderator_id"])
            lines.append(
                f"**#{item['id']}** — {item['reason']}\n"
                f"المشرف: {mention_user(moderator)}"
            )

        embed = discord.Embed(
            title=f"⚠️ تحذيرات {member}",
            description="\n\n".join(lines),
            color=discord.Color.orange(),
        )
        embed.set_footer(text=f"إجمالي التحذيرات: {len(items)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clearwarnings", description="مسح تحذيرات عضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(administrator=True)
    async def clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        def writer(cfg):
            cfg.setdefault("warnings", {})[str(member.id)] = []

        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(
            f"🧹 تم مسح جميع تحذيرات {member.mention}."
        )

    @app_commands.command(name="timeout", description="إعطاء Timeout لعضو")
    @app_commands.describe(member="العضو", duration="مثال: 10m أو 2h أو 1d", reason="السبب")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: str,
        reason: str = "بدون سبب",
    ):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ تحتاج Moderate Members.", ephemeral=True)
            return

        ok, message = can_moderate(interaction.user, member)
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        seconds = parse_duration(duration)
        if seconds is None or seconds <= 0 or seconds > 28 * 86400:
            await interaction.response.send_message(
                "❌ مدة غير صحيحة. مثال: `10m` أو `2h` أو `1d`، والحد 28 يوم.",
                ephemeral=True,
            )
            return

        until = discord.utils.utcnow() + timedelta(seconds=seconds)

        try:
            await member.timeout(until, reason=reason)
        except discord.HTTPException as error:
            await interaction.response.send_message(
                f"❌ تعذر إعطاء Timeout: `{error}`",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"🔇 تم إعطاء Timeout لـ {member.mention} لمدة `{duration}`."
        )
        await self.send_log(
            interaction.guild,
            "moderation",
            f"Timeout لـ {member.mention}.",
            actor=interaction.user,
            fields=[("المدة", duration, True), ("السبب", reason, False)],
        )

    @app_commands.command(name="untimeout", description="إزالة Timeout من عضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("❌ تحتاج Moderate Members.", ephemeral=True)
            return

        try:
            await member.timeout(None, reason=f"Removed by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر إزالة Timeout: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔊 تم إزالة Timeout من {member.mention}.")

    @app_commands.command(name="kick", description="طرد عضو")
    @app_commands.describe(member="العضو", reason="السبب")
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("❌ تحتاج Kick Members.", ephemeral=True)
            return

        ok, message = can_moderate(interaction.user, member)
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        try:
            await member.kick(reason=reason)
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر الطرد: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"👢 تم طرد `{member}`.")

    @app_commands.command(name="ban", description="حظر عضو")
    @app_commands.describe(member="العضو", reason="السبب")
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "بدون سبب"):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ تحتاج Ban Members.", ephemeral=True)
            return

        ok, message = can_moderate(interaction.user, member)
        if not ok:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
            return

        try:
            await member.ban(reason=reason)
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر الحظر: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔨 تم حظر `{member}`.")

    @app_commands.command(name="unban", description="فك حظر مستخدم عبر ID")
    @app_commands.describe(user_id="Discord User ID", reason="السبب")
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "بدون سبب"):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("❌ تحتاج Ban Members.", ephemeral=True)
            return

        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
        except (ValueError, discord.NotFound):
            await interaction.response.send_message("❌ لم أجد هذا المستخدم في قائمة الحظر.", ephemeral=True)
            return
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر فك الحظر: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔓 تم فك حظر `{user}`.")

    @app_commands.command(name="unbanall", description="فك حظر جميع المستخدمين")
    @app_commands.default_permissions(administrator=True)
    async def unbanall(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        count = 0
        try:
            async for entry in interaction.guild.bans(limit=None):
                try:
                    await interaction.guild.unban(
                        entry.user,
                        reason=f"Unban All by {interaction.user}",
                    )
                    count += 1
                except discord.HTTPException:
                    continue
        except discord.HTTPException as error:
            await interaction.followup.send(f"❌ حدث خطأ: `{error}`", ephemeral=True)
            return

        await interaction.followup.send(
            f"🔓 تم فك حظر `{count}` مستخدم.",
            ephemeral=True,
        )

    # =====================================================
    # Voice moderation
    # =====================================================

    @app_commands.command(name="voicemute", description="كتم عضو في الفويس")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(mute_members=True)
    async def voicemute(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.mute_members:
            await interaction.response.send_message("❌ تحتاج Mute Members.", ephemeral=True)
            return
        if not member.voice:
            await interaction.response.send_message("❌ العضو ليس في فويس.", ephemeral=True)
            return

        try:
            await member.edit(mute=True, reason=f"Voice mute by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر الكتم: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔇 تم كتم {member.mention}.")

    @app_commands.command(name="voiceunmute", description="إلغاء كتم عضو في الفويس")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(mute_members=True)
    async def voiceunmute(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.mute_members:
            await interaction.response.send_message("❌ تحتاج Mute Members.", ephemeral=True)
            return

        try:
            await member.edit(mute=False, reason=f"Voice unmute by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر إلغاء الكتم: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔊 تم إلغاء كتم {member.mention}.")

    @app_commands.command(name="deafen", description="عمل Deafen لعضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(deafen_members=True)
    async def deafen(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.deafen_members:
            await interaction.response.send_message("❌ تحتاج Deafen Members.", ephemeral=True)
            return

        try:
            await member.edit(deafen=True, reason=f"Deafen by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر Deafen: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔇 تم عمل Deafen لـ {member.mention}.")

    @app_commands.command(name="undeafen", description="إلغاء Deafen لعضو")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(deafen_members=True)
    async def undeafen(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.deafen_members:
            await interaction.response.send_message("❌ تحتاج Deafen Members.", ephemeral=True)
            return

        try:
            await member.edit(deafen=False, reason=f"Undeafen by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر Undeafen: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔊 تم إلغاء Deafen لـ {member.mention}.")

    @app_commands.command(name="disconnect", description="فصل عضو من الفويس")
    @app_commands.describe(member="العضو")
    @app_commands.default_permissions(move_members=True)
    async def disconnect(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.move_members:
            await interaction.response.send_message("❌ تحتاج Move Members.", ephemeral=True)
            return
        if not member.voice:
            await interaction.response.send_message("❌ العضو ليس في فويس.", ephemeral=True)
            return

        try:
            await member.move_to(None, reason=f"Disconnected by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر الفصل: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(f"🔌 تم فصل {member.mention} من الفويس.")

    # =====================================================
    # Slowmode
    # =====================================================

    @app_commands.command(name="slowmode", description="تحديد Slowmode لروم")
    @app_commands.describe(channel="الروم", seconds="عدد الثواني من 0 إلى 21600")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        seconds: int,
    ):
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("❌ تحتاج Manage Channels.", ephemeral=True)
            return
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("❌ الحد من 0 إلى 21600 ثانية.", ephemeral=True)
            return

        try:
            await channel.edit(slowmode_delay=seconds, reason=f"Slowmode by {interaction.user}")
        except discord.HTTPException as error:
            await interaction.response.send_message(f"❌ تعذر التعديل: `{error}`", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🐌 تم ضبط Slowmode في {channel.mention} على `{seconds}s`."
        )

    # =====================================================
    # Protection
    # =====================================================

    def protection_exempt(self, message, protection=None, kind=None):
        if not message.guild or not message.author:
            return True
        if message.author.bot or is_admin(message.author):
            return True
        protection = protection or guild_config(message.guild)["protection"]
        role_ids = protection.get("exempt_spam_role_ids", []) if kind == "spam" else protection.get("exempt_link_role_ids", [])
        member_role_ids = {role.id for role in getattr(message.author, "roles", [])}
        return bool(member_role_ids.intersection({int(x) for x in role_ids}))

    def is_exempt_from(self, member, protection, kind):
        if member.bot or is_admin(member):
            return True
        role_ids = protection.get("exempt_spam_role_ids", []) if kind == "spam" else protection.get("exempt_link_role_ids", [])
        return bool({role.id for role in member.roles}.intersection({int(x) for x in role_ids}))

    def has_link(self, content):
        return bool(
            re.search(
                r"(https?://|www\.|discord\.gg/|discord\.com/invite/)",
                content.lower(),
            )
        )

    def allowed_link(self, content, allowed_domains):
        lower = content.lower()
        return any(domain.lower() in lower for domain in allowed_domains)

    async def punish_protection(self, message, reason, seconds):
        member = message.author
        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(seconds=seconds),
                reason=f"Team Fime Protection: {reason}",
            )
        except discord.HTTPException:
            return False

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        await self.send_log(
            message.guild,
            "protection",
            f"🛡️ تم تفعيل الحماية على {member.mention}.",
            fields=[
                ("السبب", reason, True),
                ("العقوبة", f"Timeout {int(seconds)} ثانية", True),
                ("الروم", channel_text(message.channel), True),
            ],
        )
        return True

    async def process_protection(self, message):
        guild = message.guild
        cfg = guild_config(guild)
        protection = cfg["protection"]

        if not protection.get("enabled", True):
            return

        key = (guild.id, message.author.id)
        now = time.monotonic()

        # Anti spam
        if protection.get("anti_spam", True) and not self.is_exempt_from(message.author, protection, "spam"):
            queue = self._message_times[key]
            window = int(protection.get("spam_window", 5))
            limit = int(protection.get("spam_limit", 5))

            queue.append(now)
            while queue and now - queue[0] > window:
                queue.popleft()

            if len(queue) >= limit:
                queue.clear()
                await self.punish_protection(
                    message,
                    f"Spam ({limit} رسائل خلال {window} ثواني)",
                    int(protection.get("spam_timeout_seconds", 600)),
                )
                return

        # Anti repeat
        if protection.get("anti_repeat", True) and not self.is_exempt_from(message.author, protection, "spam") and message.content.strip():
            repeats = self._repeat_messages[key]
            normalized = re.sub(r"\s+", " ", message.content.strip().lower())
            repeats.append((now, normalized))

            while repeats and now - repeats[0][0] > 15:
                repeats.popleft()

            count = sum(1 for _, value in repeats if value == normalized)
            if count >= int(protection.get("repeat_limit", 3)):
                repeats.clear()
                await self.punish_protection(
                    message,
                    "تكرار نفس الرسالة بشكل متتابع",
                    int(protection.get("spam_timeout_seconds", 600)),
                )
                return

        # Anti link
        if protection.get("anti_links", True) and not self.is_exempt_from(message.author, protection, "links") and self.has_link(message.content):
            allowed = protection.get("allowed_domains", [])
            if not self.allowed_link(message.content, allowed):
                await self.punish_protection(
                    message,
                    "رابط غير مسموح",
                    int(protection.get("spam_timeout_seconds", 600)),
                )
                return

        # Anti mentions
        if protection.get("anti_mentions", True):
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count >= int(protection.get("mention_limit", 5)):
                await self.punish_protection(
                    message,
                    "منشنات كثيرة",
                    int(protection.get("mention_timeout_minutes", 10)) * 60,
                )

    # =====================================================
    # Protection settings
    # =====================================================

    @app_commands.command(name="protection", description="عرض حالة حماية السيرفر")
    @app_commands.default_permissions(administrator=True)
    async def protection(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        cfg = guild_config(interaction.guild)["protection"]

        embed = discord.Embed(
            title="🛡️ Server Protection",
            color=discord.Color.red(),
        )
        embed.add_field(name="النظام", value="🟢 ON" if cfg["enabled"] else "🔴 OFF", inline=True)
        embed.add_field(name="Anti Spam", value="🟢" if cfg["anti_spam"] else "🔴", inline=True)
        embed.add_field(name="Anti Repeat", value="🟢" if cfg["anti_repeat"] else "🔴", inline=True)
        embed.add_field(name="Anti Link", value="🟢" if cfg["anti_links"] else "🔴", inline=True)
        embed.add_field(name="Anti Mention", value="🟢" if cfg["anti_mentions"] else "🔴", inline=True)
        embed.add_field(
            name="Spam",
            value=f"{cfg['spam_limit']} رسائل / {cfg['spam_window']}s",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="protectiontoggle", description="تشغيل أو إيقاف حماية السيرفر")
    @app_commands.describe(enabled="True للتشغيل، False للإيقاف")
    @app_commands.default_permissions(administrator=True)
    async def protectiontoggle(self, interaction: discord.Interaction, enabled: bool):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        set_value(interaction.guild, ["protection", "enabled"], enabled)
        await interaction.response.send_message(
            f"🛡️ الحماية الآن: {'🟢 مفعلة' if enabled else '🔴 معطلة'}"
        )

    @app_commands.command(name="antispam", description="تعديل Anti-Spam")
    @app_commands.describe(
        limit="عدد الرسائل مثل 5",
        window="خلال كم ثانية مثل 5",
        timeout_minutes="العقوبة بالدقائق (اختياري)",
        timeout_seconds="العقوبة بالثواني (اختياري)",
    )
    @app_commands.default_permissions(administrator=True)
    async def antispam(
        self,
        interaction: discord.Interaction,
        limit: int,
        window: int,
        timeout_minutes: int | None = None,
        timeout_seconds: int | None = None,
    ):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        if (timeout_minutes is None) == (timeout_seconds is None):
            await interaction.response.send_message("❌ اختر مدة العقوبة بالدقائق **أو** بالثواني، وليس الاثنين معًا.", ephemeral=True)
            return
        if not 2 <= limit <= 30 or not 1 <= window <= 60:
            await interaction.response.send_message("❌ عدد الرسائل يجب أن يكون 2-30 والفترة 1-60 ثانية.", ephemeral=True)
            return
        if timeout_minutes is not None:
            if not 1 <= timeout_minutes <= 10080:
                await interaction.response.send_message("❌ مدة الدقائق يجب أن تكون من 1 إلى 10080 دقيقة.", ephemeral=True)
                return
            seconds = timeout_minutes * 60
            label = f"{timeout_minutes} دقيقة"
        else:
            if not 1 <= timeout_seconds <= 604800:
                await interaction.response.send_message("❌ مدة الثواني يجب أن تكون من 1 إلى 604800 ثانية.", ephemeral=True)
                return
            seconds = timeout_seconds
            label = f"{timeout_seconds} ثانية"

        def writer(cfg):
            protection = cfg.setdefault("protection", {})
            protection["anti_spam"] = True
            protection["spam_limit"] = limit
            protection["spam_window"] = window
            protection["spam_timeout_seconds"] = seconds

        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(
            f"🛡️ Anti-Spam تم ضبطه: **{limit} رسائل خلال {window} ثواني** → Timeout **{label}**.",
            ephemeral=True,
        )

    @app_commands.command(name="antilink", description="تشغيل أو إيقاف حماية الروابط")
    @app_commands.describe(enabled="True للتشغيل، False للإيقاف")
    @app_commands.default_permissions(administrator=True)
    async def antilink(self, interaction: discord.Interaction, enabled: bool):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        set_value(interaction.guild, ["protection", "anti_links"], enabled)
        await interaction.response.send_message(
            f"🔗 Anti-Link: {'🟢 ON' if enabled else '🔴 OFF'}"
        )

    @app_commands.command(name="allowdomain", description="إضافة دومين مسموح للروابط")
    @app_commands.describe(domain="مثال: youtube.com")
    @app_commands.default_permissions(administrator=True)
    async def allowdomain(self, interaction: discord.Interaction, domain: str):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        domain = domain.lower().replace("https://", "").replace("http://", "").strip("/")
        cfg = guild_config(interaction.guild)
        allowed = cfg["protection"].setdefault("allowed_domains", [])

        if domain not in allowed:
            allowed.append(domain)

            def writer(guild_cfg):
                guild_cfg.setdefault("protection", {})["allowed_domains"] = allowed

            update_guild_config(interaction.guild, writer)

        await interaction.response.send_message(f"✅ تم السماح بـ `{domain}`.")

    
    # ==================================================================================================
    # Permanent Server Invite
    # =====================================================

              async def find_invite_channel(self, guild, preferred=None):
        candidates = []

        if isinstance(preferred, discord.TextChannel):
            candidates.append(preferred)

        for channel in guild.text_channels:
            if channel not in candidates:
                candidates.append(channel)

        for channel in candidates:
            try:
                me = guild.me
                if me is None:
                    continue

                permissions = channel.permissions_for(me)

                if permissions.view_channel and permissions.create_instant_invite:
                    return channel

            except Exception:
                continue

        return None


    async def ensure_permanent_invite(self, guild, preferred=None, force_new=False):
        cfg = guild_config(guild)

        saved_code = cfg.get("permanent_invite_code")

        # استخدام الرابط المحفوظ إذا كان ما زال صالحًا
        if saved_code and not force_new:
            try:
                invite = await self.bot.fetch_invite(
                    saved_code,
                    with_counts=False
                )

                if invite and invite.guild and invite.guild.id == guild.id:
                    return invite, False

            except discord.NotFound:
                # الرابط انحذف فعلًا، لذلك يمكن إنشاء رابط جديد
                pass

            except (discord.Forbidden, discord.HTTPException):
                # لا تنشئ رابطًا جديدًا بسبب خطأ مؤقت
                return None, False

        saved_channel_id = cfg.get("permanent_invite_channel_id")

        channel = preferred

        if channel is None and saved_channel_id:
            try:
                channel = guild.get_channel(int(saved_channel_id))
            except (TypeError, ValueError):
                channel = None

        channel = await self.find_invite_channel(guild, channel)

        if channel is None:
            return None, False

        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=True,
                reason="Team Fime Permanent Server Invite",
            )

        except discord.Forbidden:
            return None, False

        except discord.HTTPException:
            return None, False

        def writer(cfg):
            cfg["permanent_invite_code"] = invite.code
            cfg["permanent_invite_channel_id"] = channel.id

            if getattr(invite, "id", None):
                cfg["permanent_invite_id"] = invite.id

        update_guild_config(guild, writer)

        return invite, True


    @app_commands.command(
        name="permanentinvite",
        description="إنشاء أو عرض رابط الدعوة الدائم للسيرفر"
    )
    @app_commands.describe(
        channel="الروم الذي سيتم إنشاء الدعوة منه، اختياري"
    )
    async def permanentinvite(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None
    ):
        if not is_owner(interaction.user):
            await interaction.response.send_message(
                "❌ هذا الأمر لمالك السيرفر فقط.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        invite, created = await self.ensure_permanent_invite(
            interaction.guild,
            channel,
            force_new=False
        )

        if invite is None:
            await interaction.followup.send(
                "❌ ما قدرت أجيب أو أنشئ الرابط.\n"
                "تأكد أن البوت عنده صلاحية **Create Invite** في أحد الرومات.",
                ephemeral=True
            )
            return

        status = (
            "🆕 تم إنشاء رابط دائم جديد."
            if created
            else "♾️ تم استخدام الرابط الدائم المحفوظ."
        )

        await interaction.followup.send(
            "🔗 **رابط الدعوة الدائم لسيرفر Team Fime**\n"
            f"https://discord.gg/{invite.code}\n\n"
            f"{status}\n"
            "♾️ بدون انتهاء\n"
            "♾️ بدون حد لعدد الاستخدامات",
            ephemeral=True
        )


    @app_commands.command(
        name="invite",
        description="عرض رابط الدعوة الدائم للسيرفر"
    )
    async def invite(self, interaction: discord.Interaction):
        invite, created = await self.ensure_permanent_invite(
            interaction.guild,
            force_new=False
        )

        if invite is None:
            await interaction.response.send_message(
                "❌ لا يوجد رابط دائم حاليًا، "
                "ولا أستطيع إنشاء واحد بسبب صلاحيات البوت.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔗 **رابط سيرفر Team Fime**\n"
            f"https://discord.gg/{invite.code}\n\n"
            "♾️ رابط دائم"
        )


    @app_commands.command(
        name="invitebot",
        description="الحصول على رابط دعوة البوت"
    )
    async def invitebot(self, interaction: discord.Interaction):
        bot_id = self.bot.user.id

        invite_url = discord.utils.oauth_url(
            bot_id,
            permissions=discord.Permissions(administrator=True),
            scopes=("bot", "applications.commands")
        )

        view = discord.ui.View()

        button = discord.ui.Button(
            label="➕ إضافة البوت للسيرفر",
            style=discord.ButtonStyle.link,
            url=invite_url
        )

        view.add_item(button)

        await interaction.response.send_message(
            "🤖 **دعوة Team Fime Bot**\n\n"
            "اضغط على الزر بالأسفل لإضافة البوت إلى سيرفرك.\n"
            "🛡️ البوت سيطلب صلاحية Administrator.",
            view=view,
            ephemeral=True
        )
    # =====================================================
    # Welcome message customization
    # =====================================================

    @app_commands.command(name="welcomemessage", description="تعديل رسالة الترحيب التي يستخدمها bot.py")
    @app_commands.describe(message="رسالة الترحيب. المتغيرات: {mention} {username} {display_name} {server}")
    @app_commands.default_permissions(administrator=True)
    async def welcomemessage(self, interaction: discord.Interaction, message: str):
        if not is_owner(interaction.user):
            await interaction.response.send_message("❌ تعديل رسالة الترحيب لمالك السيرفر فقط.", ephemeral=True)
            return
        if len(message) > 1900:
            await interaction.response.send_message("❌ رسالة الترحيب طويلة جدًا. الحد 1900 حرف.", ephemeral=True)
            return

        # bot.py هو المسؤول عن إرسال الترحيب، وهذا الأمر يغيّر القالب الذي يقرأه bot.py.
        old_cfg = guild_config(interaction.guild)
        old_message = old_cfg.get("welcome_message", "")
        set_value(interaction.guild, ["welcome_message"], message)
        preview = message.replace("{mention}", interaction.user.mention).replace("{username}", interaction.user.name).replace("{display_name}", interaction.user.display_name).replace("{server}", interaction.guild.name)

        # سجل التعديل في Server Logs حتى يظهر تغيير نص الترحيب في اللوق.
        await self.send_log(
            interaction.guild,
            "message_edit",
            f"تم تعديل نص رسالة الترحيب بواسطة {mention_user(interaction.user)}.",
            actor=interaction.user,
            fields=[
                ("قبل", truncate(old_message or "غير محدد", 900), False),
                ("بعد", truncate(message, 900), False),
            ],
        )

        await interaction.response.send_message(
            f"✅ تم حفظ رسالة الترحيب.\n\n**المعاينة:**\n{preview[:1900]}",
            ephemeral=True,
        )

    @app_commands.command(name="protectionexempt", description="استثناء رتبة من حماية السبام أو الروابط")
    @app_commands.describe(role="الرتبة المستثناة", protection="نوع الحماية")
    @app_commands.choices(protection=[
        app_commands.Choice(name="Spam + Repeat", value="spam"),
        app_commands.Choice(name="Links", value="links"),
        app_commands.Choice(name="Spam + Repeat + Links", value="both"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def protectionexempt(self, interaction: discord.Interaction, role: discord.Role, protection: app_commands.Choice[str]):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        value = protection.value
        def writer(cfg):
            p = cfg.setdefault("protection", {})
            if value in ("spam", "both") and role.id not in p.setdefault("exempt_spam_role_ids", []):
                p["exempt_spam_role_ids"].append(role.id)
            if value in ("links", "both") and role.id not in p.setdefault("exempt_link_role_ids", []):
                p["exempt_link_role_ids"].append(role.id)
        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(f"✅ تم استثناء {role.mention} من: **{protection.name}**.", ephemeral=True)

    @app_commands.command(name="protectionexemptremove", description="إلغاء استثناء رتبة من الحماية")
    @app_commands.describe(role="الرتبة", protection="نوع الحماية")
    @app_commands.choices(protection=[
        app_commands.Choice(name="Spam + Repeat", value="spam"),
        app_commands.Choice(name="Links", value="links"),
        app_commands.Choice(name="الكل", value="both"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def protectionexemptremove(self, interaction: discord.Interaction, role: discord.Role, protection: app_commands.Choice[str]):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        value = protection.value
        def writer(cfg):
            p = cfg.setdefault("protection", {})
            if value in ("spam", "both"):
                p["exempt_spam_role_ids"] = [x for x in p.setdefault("exempt_spam_role_ids", []) if int(x) != role.id]
            if value in ("links", "both"):
                p["exempt_link_role_ids"] = [x for x in p.setdefault("exempt_link_role_ids", []) if int(x) != role.id]
        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(f"♻️ تم إلغاء استثناء {role.mention}.", ephemeral=True)

    @app_commands.command(name="protectionexemptlist", description="عرض الرتب المستثناة من الحماية")
    @app_commands.default_permissions(administrator=True)
    async def protectionexemptlist(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        p = guild_config(interaction.guild)["protection"]
        spam_roles = [interaction.guild.get_role(int(x)) for x in p.get("exempt_spam_role_ids", [])]
        link_roles = [interaction.guild.get_role(int(x)) for x in p.get("exempt_link_role_ids", [])]
        embed = discord.Embed(title="🛡️ Protection Exempt Roles", color=discord.Color.blurple())
        embed.add_field(name="Spam / Repeat", value=", ".join(r.mention for r in spam_roles if r) or "لا يوجد", inline=False)
        embed.add_field(name="Links", value=", ".join(r.mention for r in link_roles if r) or "لا يوجد", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # AI Chat — Team Fime Assistant
    # =====================================================

    # معلومات السيرفر التي يعرفها المساعد حتى بدون API.
    AI_SERVER_GUIDE = {
        "scripts": "<#{scripts}>",
        "search": "<#{search}>",
        "updates": "<#{updates}>",
        "human_help": "<#{human_help}>",
        "chat": "<#{chat}>",
        "delta_key": "<#{delta_key}>",
        "rules": "<#{rules}>",
        "minecraft": "<#{minecraft}>",
    }

    AI_CHANNEL_IDS = {
        "scripts": 1537157629963538432,
        "search": 1537546827593818154,
        "updates": 1537167568950001664,
        "human_help": 1537177338545053756,
        "chat": 1529802314729964230,
        "delta_key": 1530187925474771164,
        "rules": 1537173539826835597,
        "minecraft": 1537396033661829180,
    }

    def _ai_channels(self):
        return {
            key: f"<#{channel_id}>"
            for key, channel_id in self.AI_CHANNEL_IDS.items()
        }

    def _normalize_ai_text(self, text):
        text = (text or "").strip().lower()
        replacements = {
            "أ": "ا", "إ": "ا", "آ": "ا",
            "ة": "ه", "ى": "ي",
            "ؤ": "و", "ئ": "ي",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"[\u064b-\u065f\u0670]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text

    def local_ai_response(self, text):
        """مساعد محلي فعلي: يعرف أقسام Team Fime ويرد مباشرة بدون كلام تقني."""
        t = self._normalize_ai_text(text)
        ch = self._ai_channels()

        # ترحيب / تعريف المساعد — بدون كشف طريقة تشغيله للمستخدم.
        if (
            t in {"طلسم", "هلا", "هلا والله", "السلام عليكم", "السلام عليكم ورحمة الله",
                 "مرحبا", "مراحب", "الو", "hello", "hi", "hey"}
            or any(x in t for x in ["من انت", "وش انت", "منو انت", "وش تسوي", "وش تقدر تسوي"])
        ):
            return "هلا 👋 أنا مساعد 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞، موجود عشان أجاوبك على أسئلتك وأدلك على المكان الصحيح في السيرفر. اكتب سؤالك مباشرة."

        # السكربتات / Delta.
        if any(x in t for x in [
            "وين احط السكربت", "وين احط سكربت", "كيف احط السكربت", "كيف احط سكربت",
            "مكان السكربت", "مكان سكربت", "ارسله وين", "احط السكربت وين",
            "وين ارسل السكربت", "كيف ارسل السكربت",
        ]):
            return f"حط السكربت في روم السكربتات {ch['scripts']} . وإذا ما عرفت الطريقة أو واجهتك مشكلة، توجه لروم حل المشاكل {ch['human_help']} وبنساعدك."

        if any(x in t for x in ["دلتا", "delta", "مفتاح دلتا", "key دلتا", "مفتاح delta"]):
            return f"إذا تقصد مفتاح دلتا، تلقى كل ما يخصه في {ch['delta_key']}."

        # البحث عن سكربت.
        if any(x in t for x in [
            "ابحث عن سكربت", "البحث عن سكربت", "ابي سكربت", "ابغى سكربت",
            "وين السكربت", "وين القى سكربت", "دور لي سكربت", "سكريبت",
        ]) and not any(x in t for x in ["وين احط", "كيف احط"]):
            return f"للبحث عن سكربت استخدم روم البحث {ch['search']}."

        # تحديثات السكربتات.
        if any(x in t for x in ["تحديث السكربت", "تحديثات السكربت", "اخر تحديث", "اخر تحديث للسكربت", "التحديث عن السكربت"]):
            return f"تحديثات السكربتات تنزل في روم التحديثات {ch['updates']}."

        # Minecraft.
        if any(x in t for x in ["ماينكرفت", "ماين كرفت", "minecraft", "ماينكرافت"]):
            return f"كل ما يخص Minecraft موجود في روم ماينكرفت {ch['minecraft']}."

        # القوانين.
        if any(x in t for x in ["القوانين", "قوانين السيرفر", "قوانين", "rules"]):
            return f"تقدر تشوف قوانين السيرفر هنا {ch['rules']}."

        # الشات.
        if any(x in t for x in ["الشات", "وين الشات", "روم الشات", "chat"]):
            return f"الشات العام هنا {ch['chat']}."

        # التذاكر / الدعم.
        if any(x in t for x in ["تذكره", "تذكرة", "ticket", "دعم فني", "الدعم"]):
            return "إذا تحتاج دعم إداري، افتح تذكرة من نظام التذاكر في السيرفر."

        # اللفلات.
        if any(x in t for x in ["لفل", "لفلات", "level", "xp", "خبره"]):
            return "نظام اللفل يعطيك XP من نشاطك في الشات والفويس، وكل ما ارتفع مستواك تقدر توصل لمكافآت اللفل المحددة في السيرفر."

        # أوامر البوت / الحماية.
        if any(x in t for x in ["اوامر البوت", "اوامر البوت", "commands", "وش اوامر البوت"]):
            return "إذا تقصد أوامر الإدارة والبوت، استخدم أمر /commands عشان تشوف الأنظمة المتوفرة."

        if any(x in t for x in ["حمايه", "حماية", "anti spam", "سبام", "حظر الروابط"]):
            return "الحماية تشمل مكافحة السبام وتكرار الرسائل والروابط والمنشنات، ويتم التحكم فيها من أوامر الإدارة."

        if any(x in t for x in ["مساعده", "مساعدة", "help", "ما عرفت", "ماعرف", "مو فاهم", "ما فهمت", "مشكله", "مشكلة", "مشكلتي"]):
            return f"إذا ما لقيت جواب لمشكلتك، توجه لروم المساعدة البشرية {ch['human_help']} وبيساعدك أحد من الفريق."

        # لا تخترع جوابًا عند عدم معرفة السؤال.
        return f"ما عندي جواب مؤكد على سؤالك حاليًا. توجه لروم المساعدة البشرية {ch['human_help']} وبيساعدك الفريق هناك."

    def build_ai_system_prompt(self, system_prompt):
        ch = self._ai_channels()
        guide = f"""
أنت مساعد 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞 داخل Discord.

أسلوبك:
- تكلم بالعربية البسيطة والطبيعية، وبلهجة خليجية خفيفة إذا كان المستخدم يتكلم بها.
- لا تتكلم عن API Key أو النموذج أو أنك مساعد محلي أو سحابي، إلا إذا سأل المستخدم عن ذلك بشكل مباشر.
- لا تقل للمستخدم إنك تحتاج API أو إنك لا تملك نموذجًا.
- جاوب مباشرة وباختصار، بدون مقدمات تقنية أو حشو.
- لا تخترع أسماء رومات أو معلومات غير موجودة في الدليل.
- إذا كان السؤال عن مكان شيء في السيرفر، استخدم منشن الروم الصحيح من الدليل.
- إذا لم تكن متأكدًا من الإجابة، لا تخمّن؛ وجّه المستخدم إلى روم المساعدة البشرية.

دليل Team Fime:
- السكربتات: {ch['scripts']}
- البحث عن سكربت: {ch['search']}
- تحديثات السكربتات: {ch['updates']}
- المساعدة البشرية: {ch['human_help']}
- الشات: {ch['chat']}
- مفتاح/رابط Delta: {ch['delta_key']}
- القوانين: {ch['rules']}
- Minecraft: {ch['minecraft']}

قاعدة مهمة:
إذا سأل المستخدم "وين أحط السكربت؟" أو سؤالًا مشابهًا عن مكان السكربت، وجّهه إلى روم السكربتات {ch['scripts']}. وإذا كان يسأل عن مشكلة أو لا يعرف الطريقة، وجّهه إلى {ch['human_help']}.
إذا لم تعرف الإجابة، استخدم هذه الصيغة بمعنى قريب منها: "ما عندي جواب مؤكد على سؤالك حاليًا. توجه لروم المساعدة البشرية {ch['human_help']} وبيساعدك الفريق هناك."

{system_prompt}
"""
        return guide.strip()

    async def openai_response(self, user_text, system_prompt):
        # الأسئلة التي نعرفها بشكل مؤكد تأخذ جواب Team Fime المحدد حتى مع وجود API.
        local_answer = self.local_ai_response(user_text)
        normalized = self._normalize_ai_text(user_text)

        known_markers = [
            "سكربت", "سكريبت", "دلتا", "delta", "ماينكرفت", "minecraft",
            "القوانين", "قوانين", "الشات", "تذكرة", "ticket", "لفل", "level",
            "مساعده", "مساعدة", "مشكله", "مشكلة", "اوامر البوت", "commands",
            "طلسم", "هلا", "مرحبا", "من انت", "وش انت",
        ]
        if any(marker in normalized for marker in known_markers):
            return local_answer, None

        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return local_answer, None

        model = os.getenv("AI_MODEL", "gpt-5.6-luna")
        payload = {
            "model": model,
            "instructions": self.build_ai_system_prompt(system_prompt),
            "input": user_text,
            "max_output_tokens": 500,
        }

        def request():
            request_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/responses",
                data=request_data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            data = await asyncio.to_thread(request)
        except urllib.error.HTTPError as error:
            # لا نعرض تفاصيل API للمستخدم؛ نعطيه مسار المساعدة الصحيح.
            return f"صار عندي تعذر مؤقت في الإجابة. إذا سؤالك مهم، توجه لروم المساعدة البشرية {self._ai_channels()['human_help']}." , None
        except Exception:
            return f"ما قدرت أجيب إجابة الآن. إذا ما تبي تنتظر، توجه لروم المساعدة البشرية {self._ai_channels()['human_help']}." , None

        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    value = content.get("text", "")
                    if value:
                        chunks.append(value)

        result = "\n".join(chunks).strip()
        if not result:
            return f"ما عندي جواب مؤكد على سؤالك حاليًا. توجه لروم المساعدة البشرية {self._ai_channels()['human_help']} وبيساعدك الفريق هناك.", None

        return result[:3900], None

    @app_commands.command(name="aisetup", description="تحديد روم AI")
    @app_commands.describe(channel="روم الذكاء الاصطناعي")
    @app_commands.default_permissions(administrator=True)
    async def aisetup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        def writer(cfg):
            ai = cfg.setdefault("ai", {})
            ai["enabled"] = True
            ai["channel_id"] = channel.id

        update_guild_config(interaction.guild, writer)

        await interaction.response.send_message(
            f"🤖 تم تفعيل AI في {channel.mention}."
        )

    @app_commands.command(name="aioff", description="إيقاف AI")
    @app_commands.default_permissions(administrator=True)
    async def aioff(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        set_value(interaction.guild, ["ai", "enabled"], False)
        await interaction.response.send_message("🤖 تم إيقاف AI.")

    @app_commands.command(name="aistatus", description="عرض حالة AI")
    @app_commands.default_permissions(administrator=True)
    async def aistatus(self, interaction: discord.Interaction):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        ai = guild_config(interaction.guild)["ai"]
        channel = interaction.guild.get_channel(ai.get("channel_id")) if ai.get("channel_id") else None

        embed = discord.Embed(
            title="🤖 AI Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="الحالة", value="🟢 ON" if ai["enabled"] else "🔴 OFF", inline=True)
        embed.add_field(name="الروم", value=channel.mention if channel else "غير محدد", inline=True)
        embed.add_field(
            name="API Key",
            value="🟢 GPT API" if os.getenv("AI_API_KEY") else "🟡 Local Assistant (بدون API Key)",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # Anti-Raid / Anti-Hack defensive security
    # =====================================================

    def security_record(self, guild, key, window, limit):
        bucket = self._security_actions[(guild.id, key)]
        now = time.monotonic()
        bucket.append(now)
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        return len(bucket) >= limit

    async def security_alert(self, guild, title, description):
        await self.send_log(
            guild,
            "protection",
            description,
            fields=[("🛡️ الإجراء", title, False)],
        )

    @app_commands.command(name="security", description="إعداد الحماية الأمنية ضد الهجمات الجماعية")
    @app_commands.describe(enabled="تشغيل أو إيقاف الحماية الأمنية")
    @app_commands.default_permissions(administrator=True)
    async def security(self, interaction: discord.Interaction, enabled: bool):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        set_value(interaction.guild, ["protection", "security_enabled"], enabled)
        await interaction.response.send_message(f"🛡️ الحماية الأمنية: {'🟢 مفعلة' if enabled else '🔴 معطلة'}", ephemeral=True)

    @app_commands.command(name="securityconfig", description="تحديد حد هجوم دخول الأعضاء")
    @app_commands.describe(join_limit="عدد الأعضاء خلال الفترة", window_seconds="الفترة بالثواني", timeout_minutes="Timeout للأعضاء الجدد أثناء الهجوم")
    @app_commands.default_permissions(administrator=True)
    async def securityconfig(self, interaction: discord.Interaction, join_limit: int, window_seconds: int, timeout_minutes: int):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return
        if not 3 <= join_limit <= 100 or not 5 <= window_seconds <= 120 or not 1 <= timeout_minutes <= 1440:
            await interaction.response.send_message("❌ القيم: الأعضاء 3-100، الفترة 5-120 ثانية، العقوبة 1-1440 دقيقة.", ephemeral=True)
            return
        def writer(cfg):
            p=cfg.setdefault("protection", {})
            p["raid_join_limit"]=join_limit
            p["raid_window_seconds"]=window_seconds
            p["raid_timeout_minutes"]=timeout_minutes
        update_guild_config(interaction.guild, writer)
        await interaction.response.send_message(f"🛡️ Anti-Raid: `{join_limit}` دخول خلال `{window_seconds}` ثانية → Timeout `{timeout_minutes}` دقيقة للأعضاء الجدد أثناء الهجوم.", ephemeral=True)

    # =====================================================
    # Events
    # =====================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        cfg = guild_config(member.guild)
        protection = cfg.get("protection", {})
        if protection.get("security_enabled", True) and not member.bot:
            bucket = self._raid_joins[member.guild.id]
            now = time.monotonic()
            bucket.append(now)
            window = int(protection.get("raid_window_seconds", 15))
            while bucket and now - bucket[0] > window:
                bucket.popleft()
            if len(bucket) >= int(protection.get("raid_join_limit", 8)):
                timeout_minutes = int(protection.get("raid_timeout_minutes", 10))
                try:
                    await member.timeout(discord.utils.utcnow() + timedelta(minutes=timeout_minutes), reason="Team Fime Anti-Raid")
                except discord.HTTPException:
                    pass
                await self.security_alert(member.guild, "Anti-Raid", f"تم رصد دخول جماعي: `{len(bucket)}` أعضاء خلال `{window}` ثانية. تم تطبيق حماية على العضو الجديد {member.mention}.")

        await self.send_log(
            member.guild,
            "member_join",
            f"دخل عضو جديد إلى السيرفر: {member.mention}",
            fields=[
                ("👤 الاسم", f"{member}\n`{member.id}`", True),
                ("📅 إنشاء الحساب", discord.utils.format_dt(member.created_at, "F"), True),
            ],
            thumbnail=member.display_avatar.url,
        )

    # لا يوجد on_member_remove عمدًا.

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.send_log(
            role.guild,
            "role_create",
            f"تم إنشاء رتبة جديدة: {role_text(role)}",
            fields=[
                ("🏷️ الاسم", role.name, True),
                ("🆔 ID", f"`{role.id}`", True),
                ("🎨 اللون", str(role.color), True),
                ("📌 المركز", str(role.position), True),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        cfg = guild_config(role.guild)
        if cfg["protection"].get("security_enabled", True) and self.security_record(role.guild, "role_delete", 20, 4):
            await self.security_alert(role.guild, "Anti-Nuke", "تم رصد حذف عدة رتب بسرعة. راجع صلاحيات الإدارة فورًا.")
        await self.send_log(
            role.guild,
            "role_delete",
            f"تم حذف رتبة: **{role.name}**",
            fields=[
                ("🆔 ID", f"`{role.id}`", True),
                ("🎨 اللون", str(role.color), True),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        changes = []

        if before.name != after.name:
            changes.append(f"الاسم: `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"اللون: `{before.color}` → `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"إظهار منفصلة: `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"قابلة للمنشن: `{before.mentionable}` → `{after.mentionable}`")
        if before.permissions != after.permissions:
            changes.append("تم تعديل صلاحيات الرتبة")

        if changes:
            await self.send_log(
                after.guild,
                "role_update",
                f"تم تعديل الرتبة {role_text(after)}.",
                fields=[("📝 التغييرات", "\n".join(changes), False)],
            )

    def channel_type(self, channel):
        if isinstance(channel, discord.CategoryChannel):
            return "الـCategory"
        if isinstance(channel, discord.VoiceChannel):
            return "الروم الصوتي"
        if isinstance(channel, discord.StageChannel):
            return "Stage Channel"
        if isinstance(channel, discord.ForumChannel):
            return "Forum Channel"
        if isinstance(channel, discord.TextChannel):
            return "الروم النصي"
        return "الروم"

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        key = "category_create" if isinstance(channel, discord.CategoryChannel) else "channel_create"

        await self.send_log(
            channel.guild,
            key,
            f"تم إنشاء {self.channel_type(channel)}: {channel_text(channel)}",
            fields=[
                ("📝 الاسم", getattr(channel, "name", "غير معروف"), True),
                ("🆔 ID", f"`{channel.id}`", True),
                ("📁 التصنيف", channel_text(getattr(channel, "category", None)), True),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        key = "category_delete" if isinstance(channel, discord.CategoryChannel) else "channel_delete"

        await self.send_log(
            channel.guild,
            key,
            f"تم حذف {self.channel_type(channel)}: **{getattr(channel, 'name', 'غير معروف')}**",
            fields=[
                ("🆔 ID", f"`{channel.id}`", True),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []

        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"الاسم: `{before.name}` → `{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("تم تعديل Topic")
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(
                f"Slowmode: `{getattr(before, 'slowmode_delay', 0)}s` → `{getattr(after, 'slowmode_delay', 0)}s`"
            )
        if getattr(before, "category_id", None) != getattr(after, "category_id", None):
            changes.append("تم تغيير الـCategory")

        if not changes:
            return

        key = "category_update" if isinstance(after, discord.CategoryChannel) else "channel_update"

        await self.send_log(
            after.guild,
            key,
            f"تم تعديل {self.channel_type(after)}: {channel_text(after)}",
            fields=[("📝 التغييرات", "\n".join(changes), False)],
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        before_channel = before.channel
        after_channel = after.channel

        if before_channel is None and after_channel is not None:
            await self.send_log(
                member.guild,
                "voice_join",
                f"دخل {member.mention} إلى {after_channel.mention}",
                fields=[
                    ("👤 العضو", member.mention, True),
                    ("🔊 الروم", after_channel.mention, True),
                ],
            )
        elif before_channel is not None and after_channel is None:
            await self.send_log(
                member.guild,
                "voice_leave",
                f"خرج {member.mention} من {before_channel.mention}",
                fields=[
                    ("👤 العضو", member.mention, True),
                    ("🔊 الروم", before_channel.mention, True),
                ],
            )
        elif before_channel and after_channel and before_channel.id != after_channel.id:
            await self.send_log(
                member.guild,
                "voice_move",
                f"انتقل {member.mention} من {before_channel.mention} إلى {after_channel.mention}",
            )

        # Voice XP
        if after_channel is not None and not member.bot:
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []

        if before.nick != after.nick:
            changes.append(
                f"الاسم المستعار: `{before.nick or 'لا يوجد'}` → `{after.nick or 'لا يوجد'}`"
            )

        before_roles = {r.id: r for r in before.roles}
        after_roles = {r.id: r for r in after.roles}

        added = [
            r for r in after.roles
            if r.id not in before_roles and r != after.guild.default_role
        ]
        removed = [
            r for r in before.roles
            if r.id not in after_roles and r != before.guild.default_role
        ]

        if added:
            changes.append("إضافة رتب: " + ", ".join(role_text(r) for r in added[:10]))
        if removed:
            changes.append("إزالة رتب: " + ", ".join(role_text(r) for r in removed[:10]))

        if before.timed_out_until != after.timed_out_until:
            changes.append("تم تغيير حالة Timeout")

        if changes:
            await self.send_log(
                after.guild,
                "member_update",
                f"تم تعديل العضو {after.mention}.",
                fields=[("📝 التغييرات", "\n".join(changes), False)],
                thumbnail=after.display_avatar.url,
            )

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.send_log(
            guild,
            "ban",
            f"تم حظر العضو: **{user}**",
            fields=[("🆔 ID", f"`{user.id}`", True)],
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.send_log(
            guild,
            "unban",
            f"تم فك حظر العضو: **{user}**",
            fields=[("🆔 ID", f"`{user.id}`", True)],
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return

        await self.send_log(
            message.guild,
            "message_delete",
            f"تم حذف رسالة من {mention_user(message.author)} في {channel_text(message.channel)}.",
            fields=[
                ("📝 المحتوى", truncate(message.content, 700), False),
            ],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot:
            return

        # تجاهل تعديلات Discord الداخلية التي لا تغيّر محتوى الرسالة فعليًا.
        if before.content == after.content:
            return

        jump = getattr(after, "jump_url", None)
        jump_text = f"\n[فتح الرسالة]({jump})" if jump else ""

        await self.send_log(
            before.guild,
            "message_edit",
            f"تم تعديل رسالة بواسطة {mention_user(before.author)} في {channel_text(after.channel)}.{jump_text}",
            actor=before.author,
            fields=[
                ("قبل", truncate(before.content or "(بدون نص)", 700), False),
                ("بعد", truncate(after.content or "(بدون نص)", 700), False),
            ],
        )

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild:
            await self.send_log(
                invite.guild,
                "invite_create",
                f"تم إنشاء دعوة `{invite.code}`.",
                fields=[
                    ("👤 المنشئ", mention_user(invite.inviter), True),
                    ("💬 الروم", channel_text(invite.channel), True),
                ],
            )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild:
            await self.send_log(
                invite.guild,
                "invite_delete",
                f"تم حذف الدعوة `{invite.code}`.",
            )

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []

        if before.name != after.name:
            changes.append(f"اسم السيرفر: `{before.name}` → `{after.name}`")
        if before.description != after.description:
            changes.append("تم تعديل وصف السيرفر")
        if before.verification_level != after.verification_level:
            changes.append("تم تغيير Verification Level")

        if changes:
            await self.send_log(
                after,
                "guild_update",
                "تم تعديل إعدادات السيرفر.",
                fields=[("📝 التغييرات", "\n".join(changes), False)],
            )

    # =====================================================
    # Message master listener
    # =====================================================

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return

        # حماية
        try:
            await self.process_protection(message)
        except Exception as error:
            print(f"⚠️ Protection error: {error}")

        # XP
        try:
            await self.award_chat_xp(message)
        except Exception as error:
            print(f"⚠️ Level XP error: {error}")

        # AI
        try:
            cfg = guild_config(message.guild)
            ai = cfg["ai"]

            if (
                ai.get("enabled")
                and ai.get("channel_id")
                and message.channel.id == int(ai["channel_id"])
            ):
                text = message.content.strip()

                if text:
                    async with message.channel.typing():
                        answer, error = await self.openai_response(
                            text,
                            ai.get("system_prompt", ""),
                        )

                    if error:
                        await message.reply(
                            f"⚠️ {error}",
                            mention_author=False,
                        )
                    elif answer:
                        await message.reply(
                            answer[:3900],
                            mention_author=False,
                        )
        except Exception as error:
            print(f"⚠️ AI error: {error}")

    # =====================================================
    # Voice XP loop
    # =====================================================

    @tasks.loop(minutes=1)
    async def voice_xp_loop(self):
        for guild in list(self.bot.guilds):
            try:
                cfg = guild_config(guild)
                if not cfg.get("levels_enabled", True):
                    continue

                amount = int(cfg.get("level_voice_xp_per_minute", 3))
                if amount <= 0:
                    continue

                for member in guild.members:
                    if member.bot or not member.voice or not member.voice.channel:
                        continue
                    if member.voice.afk:
                        continue

                    old_xp, new_xp = self.add_user_xp(guild, member.id, amount)

                    old_level = self.level_from_xp(old_xp)
                    new_level = self.level_from_xp(new_xp)

                    if new_level > old_level:
                        await self.check_level_reward(
                            guild,
                            member,
                            old_level,
                            new_level,
                        )
                        await self.announce_level_up(guild, member, old_level, new_level, new_xp, "🔊 الفويس")
            except Exception as error:
                print(f"⚠️ Voice XP error in {guild.name}: {error}")

    @voice_xp_loop.before_loop
    async def before_voice_xp_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.voice_xp_loop.is_running():
            self.voice_xp_loop.start()

        # استعادة اللوحات مرة واحدة فقط.
        if not getattr(self, "_panels_restored", False):
            self._panels_restored = True
            await self.restore_persistent_panels()

        # تأكد من وجود رابط دائم محفوظ لكل سيرفر، وإذا كان الرابط القديم صالحًا يتم الاحتفاظ به.
        if not getattr(self, "_invites_checked", False):
            self._invites_checked = True
            for guild in list(self.bot.guilds):
                try:
                    await self.ensure_permanent_invite(guild)
                except Exception as error:
                    print(f"⚠️ Permanent invite error in {guild.name}: {error}")


# =========================================================
# Setup
# =========================================================

async def setup(bot):
    await bot.add_cog(ServerLogger(bot))
    print("✅ تم تشغيل Team Fime bot2.py بالكامل.")
