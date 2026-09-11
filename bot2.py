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

    # Protection
    protection = cfg.setdefault("protection", {})
    protection.setdefault("enabled", True)
    protection.setdefault("anti_spam", True)
    protection.setdefault("spam_limit", 5)
    protection.setdefault("spam_window", 5)
    protection.setdefault("spam_timeout_minutes", 10)
    protection.setdefault("anti_repeat", True)
    protection.setdefault("repeat_limit", 3)
    protection.setdefault("anti_links", True)
    protection.setdefault("allowed_domains", [])
    protection.setdefault("anti_mentions", True)
    protection.setdefault("mention_limit", 5)
    protection.setdefault("mention_timeout_minutes", 10)

    # AI
    ai = cfg.setdefault("ai", {})
    ai.setdefault("enabled", False)
    ai.setdefault("channel_id", None)
    ai.setdefault("system_prompt", "أنت مساعد مفيد وودود داخل سيرفر Discord. كن مختصرًا وواضحًا.")

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
            value="`/level` • `/setxp` • `/resetlevel` • `/levelreward`",
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
            await self.send_log(
                guild,
                "level",
                f"ارتفع مستوى {member.mention}!",
                fields=[
                    ("⭐ المستوى", f"`{old_level}` → `{new_level}`", True),
                    ("✨ XP", f"`{new_xp}`", True),
                ],
            )

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

    def protection_exempt(self, message):
        if not message.guild or not message.author:
            return True
        if message.author.bot:
            return True
        if is_admin(message.author):
            return True
        return False

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

    async def punish_protection(self, message, reason, minutes):
        member = message.author
        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(minutes=minutes),
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
                ("العقوبة", f"Timeout {minutes} دقيقة", True),
                ("الروم", channel_text(message.channel), True),
            ],
        )
        return True

    async def process_protection(self, message):
        if self.protection_exempt(message):
            return

        guild = message.guild
        cfg = guild_config(guild)
        protection = cfg["protection"]

        if not protection.get("enabled", True):
            return

        key = (guild.id, message.author.id)
        now = time.monotonic()

        # Anti spam
        if protection.get("anti_spam", True):
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
                    int(protection.get("spam_timeout_minutes", 10)),
                )
                return

        # Anti repeat
        if protection.get("anti_repeat", True) and message.content.strip():
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
                    int(protection.get("spam_timeout_minutes", 10)),
                )
                return

        # Anti link
        if protection.get("anti_links", True) and self.has_link(message.content):
            allowed = protection.get("allowed_domains", [])
            if not self.allowed_link(message.content, allowed):
                await self.punish_protection(
                    message,
                    "رابط غير مسموح",
                    int(protection.get("spam_timeout_minutes", 10)),
                )
                return

        # Anti mentions
        if protection.get("anti_mentions", True):
            mention_count = len(message.mentions) + len(message.role_mentions)
            if mention_count >= int(protection.get("mention_limit", 5)):
                await self.punish_protection(
                    message,
                    "منشنات كثيرة",
                    int(protection.get("mention_timeout_minutes", 10)),
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
        limit="عدد الرسائل",
        window="الفترة بالثواني",
        timeout_minutes="مدة Timeout بالدقائق",
    )
    @app_commands.default_permissions(administrator=True)
    async def antispam(
        self,
        interaction: discord.Interaction,
        limit: int,
        window: int,
        timeout_minutes: int,
    ):
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ للإداريين فقط.", ephemeral=True)
            return

        if not 2 <= limit <= 30 or not 1 <= window <= 60 or not 1 <= timeout_minutes <= 10080:
            await interaction.response.send_message("❌ القيم خارج الحدود المسموحة.", ephemeral=True)
            return

        def writer(cfg):
            protection = cfg.setdefault("protection", {})
            protection["anti_spam"] = True
            protection["spam_limit"] = limit
            protection["spam_window"] = window
            protection["spam_timeout_minutes"] = timeout_minutes

        update_guild_config(interaction.guild, writer)

        await interaction.response.send_message(
            f"🛡️ Anti-Spam: `{limit}` رسائل خلال `{window}s` → Timeout `{timeout_minutes}m`."
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

    # =====================================================
    # AI Chat
    # =====================================================

    async def openai_response(self, user_text, system_prompt):
        api_key = os.getenv("AI_API_KEY")
        if not api_key:
            return None, "لم يتم ضبط `AI_API_KEY` في Environment Variables."

        model = os.getenv("AI_MODEL", "gpt-5.6-luna")

        payload = {
            "model": model,
            "instructions": system_prompt,
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
            try:
                body = error.read().decode("utf-8")
            except Exception:
                body = str(error)
            return None, f"خطأ من AI API: {truncate(body, 500)}"
        except Exception as error:
            return None, f"تعذر الاتصال بالذكاء الاصطناعي: `{error}`"

        # Responses API returns output items; collect output_text safely.
        chunks = []
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    text = content.get("text", "")
                    if text:
                        chunks.append(text)

        result = "\n".join(chunks).strip()
        if not result:
            return None, "لم يصل نص من نموذج الذكاء الاصطناعي."

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
            value="🟢 موجود" if os.getenv("AI_API_KEY") else "🔴 غير موجود",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # Events
    # =====================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
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
        if before.content == after.content:
            return

        await self.send_log(
            before.guild,
            "message_edit",
            f"تم تعديل رسالة بواسطة {mention_user(before.author)}.",
            fields=[
                ("قبل", truncate(before.content, 450), False),
                ("بعد", truncate(after.content, 450), False),
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
                        await self.send_log(
                            guild,
                            "level",
                            f"ارتفع مستوى {member.mention} بسبب نشاط الفويس.",
                            fields=[
                                ("⭐ المستوى", f"`{old_level}` → `{new_level}`", True),
                                ("✨ XP", f"`{new_xp}`", True),
                            ],
                        )
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


# =========================================================
# Setup
# =========================================================

async def setup(bot):
    await bot.add_cog(ServerLogger(bot))
    print("✅ تم تشغيل Team Fime bot2.py بالكامل.")