import asyncio
import json
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


# =========================================================
# Server Logs Pro
# bot2.py — نظام لوق السيرفر فقط
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
}

# لا يوجد هنا member leave عمدًا حسب طلب المستخدم.
ENABLED_DEFAULTS = {key: True for key in EVENT_LABELS}


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
        import os
        os.replace(temp, CONFIG_FILE)
        return True
    except OSError as error:
        print(f"❌ Server Logs config error: {error}")
        return False


def get_log_settings(guild):
    data = load_config()
    guilds = data.setdefault("guilds", {})
    cfg = guilds.setdefault(str(guild.id), {})

    if "server_log_channel_id" not in cfg:
        cfg["server_log_channel_id"] = None
    if not isinstance(cfg.get("server_log_events"), dict):
        cfg["server_log_events"] = dict(ENABLED_DEFAULTS)
    else:
        for key, value in ENABLED_DEFAULTS.items():
            cfg["server_log_events"].setdefault(key, value)

    save_config(data)
    return cfg


def set_log_channel(guild, channel_id):
    data = load_config()
    guilds = data.setdefault("guilds", {})
    cfg = guilds.setdefault(str(guild.id), {})
    cfg["server_log_channel_id"] = channel_id
    cfg.setdefault("server_log_events", dict(ENABLED_DEFAULTS))
    save_config(data)


def get_log_channel(guild):
    cfg = get_log_settings(guild)
    channel_id = cfg.get("server_log_channel_id")

    if channel_id:
        try:
            channel = guild.get_channel(int(channel_id))
        except (TypeError, ValueError):
            channel = None
        if isinstance(channel, discord.TextChannel):
            return channel

    # إذا لم يتم ضبط اللوق الجديد، استخدم ticket-logs القديم كـ fallback.
    old_id = cfg.get("log_channel_id")
    if old_id:
        try:
            channel = guild.get_channel(int(old_id))
        except (TypeError, ValueError):
            channel = None
        if isinstance(channel, discord.TextChannel):
            return channel

    return None


def event_enabled(guild, event_key):
    cfg = get_log_settings(guild)
    return bool(cfg.get("server_log_events", {}).get(event_key, True))


def truncate(value, limit=900):
    if value is None:
        return "غير متوفر"
    value = str(value)
    if not value:
        return "بدون قيمة"
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def mention_user(user):
    if user is None:
        return "غير معروف"
    return getattr(user, "mention", f"`{getattr(user, 'id', 'unknown')}`")


def channel_text(channel):
    if channel is None:
        return "غير معروف"
    mention = getattr(channel, "mention", None)
    if mention:
        return mention
    return f"`{getattr(channel, 'name', 'unknown')}`"


def role_text(role):
    if role is None:
        return "غير معروف"
    return getattr(role, "mention", f"`{role.name}`")


def color_for(event_key):
    return LOG_COLORS.get(event_key, discord.Color.blurple())


def permission_ok(guild, channel):
    me = guild.me
    if me is None:
        return False
    permissions = channel.permissions_for(me)
    return permissions.view_channel and permissions.send_messages and permissions.embed_links


class ServerLogger(commands.Cog):
    """نظام مراقبة أحداث السيرفر وإرسالها إلى روم اللوق."""

    def __init__(self, bot):
        self.bot = bot
        self._last_messages = {}
        self._startup_lock = asyncio.Lock()
        self._ready_once = False

    async def cog_load(self):
        print("✅ Server Logs Pro loaded from bot2.py")

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
        if guild is None:
            return
        if not event_enabled(guild, event_key):
            return

        channel = get_log_channel(guild)
        if channel is None:
            return
        if not permission_ok(guild, channel):
            print(f"❌ Server Logs: لا أستطيع الكتابة في #{channel.name} داخل {guild.name}")
            return

        embed = discord.Embed(
            title=EVENT_LABELS.get(event_key, "📋 Server Log"),
            description=truncate(description, 3900),
            color=color_for(event_key),
            timestamp=datetime.now(timezone.utc),
        )

        if actor is not None:
            embed.add_field(name="👤 المنفذ", value=mention_user(actor), inline=True)

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

        if footer:
            embed.set_footer(text=truncate(footer, 200))
        else:
            embed.set_footer(text=f"{guild.name} • Server Logs")

        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print(f"❌ Server Logs: Forbidden في #{channel.name}")
        except discord.HTTPException as error:
            print(f"❌ Server Logs HTTP Error: {error}")

    # =====================================================
    # إعداد النظام
    # =====================================================

    @app_commands.command(name="serverlog", description="تحديد روم لوق أحداث السيرفر")
    @app_commands.describe(channel="روم اللوق الجديد")
    @app_commands.default_permissions(administrator=True)
    async def serverlog(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ الأمر للإداريين فقط.", ephemeral=True)
            return

        set_log_channel(interaction.guild, channel.id)
        get_log_settings(interaction.guild)

        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} كروم **Server Logs**.\n"
            "من الآن ستصل إليه إشعارات أحداث السيرفر.",
            ephemeral=True,
        )

        await self.send_log(
            interaction.guild,
            "guild_update",
            f"تم تفعيل نظام Server Logs في {channel.mention}.",
            actor=interaction.user,
        )

    @app_commands.command(name="serverlogoff", description="إيقاف لوق أحداث السيرفر")
    @app_commands.default_permissions(administrator=True)
    async def serverlogoff(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ الأمر للإداريين فقط.", ephemeral=True)
            return

        data = load_config()
        cfg = data.setdefault("guilds", {}).setdefault(str(interaction.guild.id), {})
        cfg["server_log_channel_id"] = None
        save_config(data)

        await interaction.response.send_message("✅ تم إيقاف Server Logs.", ephemeral=True)

    @app_commands.command(name="serverlogstatus", description="عرض حالة Server Logs")
    @app_commands.default_permissions(administrator=True)
    async def serverlogstatus(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ الأمر للإداريين فقط.", ephemeral=True)
            return

        cfg = get_log_settings(interaction.guild)
        channel = get_log_channel(interaction.guild)
        enabled_count = sum(1 for value in cfg.get("server_log_events", {}).values() if value)
        total_count = len(cfg.get("server_log_events", {}))

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
            name="⚙️ الأحداث",
            value=f"**{enabled_count}** مفعلة من **{total_count}**",
            inline=True,
        )
        embed.add_field(
            name="🚫 خروج الأعضاء",
            value="معطل حسب طلبك",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # دخول عضو — بدون خروج عضو
    # =====================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.send_log(
            member.guild,
            "member_join",
            f"دخل عضو جديد إلى السيرفر: {member.mention}",
            fields=[
                ("👤 الاسم", f"{member}\\n`{member.id}`", True),
                ("📅 إنشاء الحساب", discord.utils.format_dt(member.created_at, "F"), True),
                ("📊 ترتيب العضو", f"#{len(member.guild.members)} تقريبًا", True),
            ],
            thumbnail=member.display_avatar.url,
        )

    # =====================================================
    # الرتب
    # =====================================================

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
                ("📌 المركز", str(role.position), True),
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

        if not changes:
            return

        await self.send_log(
            after.guild,
            "role_update",
            f"تم تعديل الرتبة {role_text(after)}.",
            fields=[("📝 التغييرات", "\n".join(changes), False)],
        )

    # =====================================================
    # الرومات والكاتيجوري
    # =====================================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if isinstance(channel, discord.CategoryChannel):
            key = "category_create"
        else:
            key = "channel_create"

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
        if isinstance(channel, discord.CategoryChannel):
            key = "category_delete"
        else:
            key = "channel_delete"

        await self.send_log(
            channel.guild,
            key,
            f"تم حذف {self.channel_type(channel)}: **{getattr(channel, 'name', 'غير معروف')}**",
            fields=[
                ("🆔 ID", f"`{channel.id}`", True),
                ("📁 التصنيف", getattr(getattr(channel, "category", None), "name", "غير معروف"), True),
            ],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"الاسم: `{before.name}` → `{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("تم تعديل وصف/Topic الروم")
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(
                f"Slowmode: `{getattr(before, 'slowmode_delay', 0)}s` → `{getattr(after, 'slowmode_delay', 0)}s`"
            )
        if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
            changes.append(f"NSFW: `{before.nsfw}` → `{after.nsfw}`")
        if getattr(before, "category_id", None) != getattr(after, "category_id", None):
            changes.append("تم نقل الروم إلى Category مختلفة")
        if getattr(before, "position", None) != getattr(after, "position", None):
            changes.append("تم تغيير ترتيب الروم")

        if not changes:
            return

        key = "category_update" if isinstance(after, discord.CategoryChannel) else "channel_update"
        await self.send_log(
            after.guild,
            key,
            f"تم تعديل {self.channel_type(after)}: {channel_text(after)}",
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

    # =====================================================
    # الصوتيات
    # =====================================================

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        before_channel = before.channel
        after_channel = after.channel

        # دخول فويس
        if before_channel is None and after_channel is not None:
            await self.send_log(
                member.guild,
                "voice_join",
                f"دخل {member.mention} إلى {after_channel.mention}",
                fields=[
                    ("👤 العضو", mention_user(member), True),
                    ("🔊 الروم", channel_text(after_channel), True),
                ],
            )
            return

        # خروج فويس
        if before_channel is not None and after_channel is None:
            await self.send_log(
                member.guild,
                "voice_leave",
                f"خرج {member.mention} من {before_channel.mention}",
                fields=[
                    ("👤 العضو", mention_user(member), True),
                    ("🔊 الروم", channel_text(before_channel), True),
                ],
            )
            return

        # انتقال من فويس إلى فويس
        if before_channel is not None and after_channel is not None and before_channel.id != after_channel.id:
            await self.send_log(
                member.guild,
                "voice_move",
                f"انتقل {member.mention} من {before_channel.mention} إلى {after_channel.mention}",
                fields=[
                    ("من", channel_text(before_channel), True),
                    ("إلى", channel_text(after_channel), True),
                ],
            )
            return

        # تغييرات داخل الفويس مثل mute/deaf/stream.
        changes = []
        if before.self_mute != after.self_mute:
            changes.append(f"Self Mute: `{before.self_mute}` → `{after.self_mute}`")
        if before.self_deaf != after.self_deaf:
            changes.append(f"Self Deaf: `{before.self_deaf}` → `{after.self_deaf}`")
        if before.self_stream != after.self_stream:
            changes.append(f"Streaming: `{before.self_stream}` → `{after.self_stream}`")
        if before.self_video != after.self_video:
            changes.append(f"Camera: `{before.self_video}` → `{after.self_video}`")

        if changes and after_channel is not None:
            await self.send_log(
                member.guild,
                "voice_move",
                f"تغيرت حالة {member.mention} داخل الفويس.",
                fields=[
                    ("🔊 الروم", channel_text(after_channel), True),
                    ("📝 التغييرات", "\n".join(changes), False),
                ],
            )

    # =====================================================
    # Threads
    # =====================================================

    @commands.Cog.listener()
    async def on_thread_create(self, thread):
        await self.send_log(
            thread.guild,
            "thread_create",
            f"تم إنشاء Thread: **{thread.name}**",
            fields=[
                ("🧵 Thread", channel_text(thread), True),
                ("📌 الروم الأب", channel_text(thread.parent), True),
                ("🆔 ID", f"`{thread.id}`", True),
            ],
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread):
        await self.send_log(
            thread.guild,
            "thread_delete",
            f"تم حذف Thread: **{thread.name}**",
            fields=[
                ("🆔 ID", f"`{thread.id}`", True),
                ("📌 الروم الأب", channel_text(thread.parent), True),
            ],
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"الاسم: `{before.name}` → `{after.name}`")
        if before.archived != after.archived:
            changes.append(f"Archived: `{before.archived}` → `{after.archived}`")
        if before.locked != after.locked:
            changes.append(f"Locked: `{before.locked}` → `{after.locked}`")
        if not changes:
            return
        await self.send_log(
            after.guild,
            "thread_update",
            f"تم تعديل Thread: {channel_text(after)}",
            fields=[("📝 التغييرات", "\n".join(changes), False)],
        )

    # =====================================================
    # أعضاء — تعديل فقط، بدون member leave
    # =====================================================

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        changes = []

        if before.nick != after.nick:
            changes.append(f"الاسم المستعار: `{before.nick or 'لا يوجد'}` → `{after.nick or 'لا يوجد'}`")

        before_roles = {role.id: role for role in before.roles}
        after_roles = {role.id: role for role in after.roles}
        added = [role for role_id, role in after_roles.items() if role_id not in before_roles and role != after.guild.default_role]
        removed = [role for role_id, role in before_roles.items() if role_id not in after_roles and role != before.guild.default_role]

        if added:
            changes.append("إضافة رتب: " + ", ".join(role_text(role) for role in added[:10]))
        if removed:
            changes.append("إزالة رتب: " + ", ".join(role_text(role) for role in removed[:10]))

        if before.timed_out_until != after.timed_out_until:
            changes.append("تم تغيير حالة Timeout للعضو")

        if not changes:
            return

        await self.send_log(
            after.guild,
            "member_update",
            f"تم تعديل العضو {after.mention}.",
            fields=[("📝 التغييرات", "\n".join(changes), False)],
            thumbnail=after.display_avatar.url,
        )

    # =====================================================
    # حظر وفك الحظر
    # =====================================================

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.send_log(
            guild,
            "ban",
            f"تم حظر العضو: **{user}**",
            fields=[("🆔 ID", f"`{user.id}`", True)],
            thumbnail=getattr(user.display_avatar, "url", None),
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        await self.send_log(
            guild,
            "unban",
            f"تم فك حظر العضو: **{user}**",
            fields=[("🆔 ID", f"`{user.id}`", True)],
            thumbnail=getattr(user.display_avatar, "url", None),
        )

    # =====================================================
    # الرسائل
    # =====================================================

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return

        content = truncate(message.content, 700) if message.content else "[بدون نص / قد تكون مرفقات فقط]"
        await self.send_log(
            message.guild,
            "message_delete",
            f"تم حذف رسالة من {mention_user(message.author)} في {channel_text(message.channel)}.",
            fields=[
                ("👤 المرسل", mention_user(message.author), True),
                ("💬 الروم", channel_text(message.channel), True),
                ("📝 المحتوى", content, False),
            ],
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if not messages:
            return
        guild = getattr(messages[0], "guild", None)
        channel = getattr(messages[0], "channel", None)
        if guild is None:
            return

        await self.send_log(
            guild,
            "message_bulk_delete",
            f"تم حذف **{len(messages)}** رسالة دفعة واحدة.",
            fields=[("💬 الروم", channel_text(channel), True)],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return
        if not before.content and not after.content:
            return

        await self.send_log(
            before.guild,
            "message_edit",
            f"تم تعديل رسالة بواسطة {mention_user(before.author)} في {channel_text(before.channel)}.",
            fields=[
                ("قبل", truncate(before.content, 450), False),
                ("بعد", truncate(after.content, 450), False),
            ],
        )

    # =====================================================
    # الدعوات
    # =====================================================

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        guild = invite.guild
        if guild is None:
            return
        await self.send_log(
            guild,
            "invite_create",
            f"تم إنشاء دعوة جديدة: `{invite.code}`",
            fields=[
                ("👤 المنشئ", mention_user(invite.inviter), True),
                ("💬 الروم", channel_text(invite.channel), True),
                ("🔗 الكود", f"`{invite.code}`", True),
                ("⏳ الاستخدامات", str(invite.max_uses or "غير محدد"), True),
            ],
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        guild = invite.guild
        if guild is None:
            return
        await self.send_log(
            guild,
            "invite_delete",
            f"تم حذف الدعوة `{invite.code}`.",
            fields=[("💬 الروم", channel_text(invite.channel), True)],
        )

    # =====================================================
    # السيرفر نفسه
    # =====================================================

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        changes = []
        if before.name != after.name:
            changes.append(f"اسم السيرفر: `{before.name}` → `{after.name}`")
        if before.description != after.description:
            changes.append("تم تعديل وصف السيرفر")
        if before.verification_level != after.verification_level:
            changes.append(f"Verification Level: `{before.verification_level}` → `{after.verification_level}`")
        if before.default_role.permissions != after.default_role.permissions:
            changes.append("تم تعديل صلاحيات @everyone")
        if not changes:
            return

        await self.send_log(
            after,
            "guild_update",
            "تم تعديل إعدادات السيرفر.",
            fields=[("📝 التغييرات", "\n".join(changes), False)],
        )

    # =====================================================
    # Emojis / Stickers
    # =====================================================

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        before_map = {emoji.id: emoji for emoji in before}
        after_map = {emoji.id: emoji for emoji in after}

        created = [emoji for emoji_id, emoji in after_map.items() if emoji_id not in before_map]
        deleted = [emoji for emoji_id, emoji in before_map.items() if emoji_id not in after_map]
        updated = []

        for emoji_id in set(before_map) & set(after_map):
            old = before_map[emoji_id]
            new = after_map[emoji_id]
            if old.name != new.name:
                updated.append((old, new))

        for emoji in created:
            await self.send_log(
                guild,
                "emoji_create",
                f"تم إنشاء Emoji جديد: {emoji}",
                fields=[("🆔 ID", f"`{emoji.id}`", True), ("🏷️ الاسم", emoji.name, True)],
            )

        for emoji in deleted:
            await self.send_log(
                guild,
                "emoji_delete",
                f"تم حذف Emoji: **{emoji.name}**",
                fields=[("🆔 ID", f"`{emoji.id}`", True)],
            )

        for old, new in updated:
            await self.send_log(
                guild,
                "emoji_update",
                f"تم تعديل Emoji: `{old.name}` → `{new.name}`",
                fields=[("🆔 ID", f"`{new.id}`", True)],
            )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        before_map = {sticker.id: sticker for sticker in before}
        after_map = {sticker.id: sticker for sticker in after}

        for sticker_id, sticker in after_map.items():
            if sticker_id not in before_map:
                await self.send_log(
                    guild,
                    "sticker_create",
                    f"تم إنشاء Sticker جديد: **{sticker.name}**",
                    fields=[("🆔 ID", f"`{sticker.id}`", True)],
                )

        for sticker_id, sticker in before_map.items():
            if sticker_id not in after_map:
                await self.send_log(
                    guild,
                    "sticker_delete",
                    f"تم حذف Sticker: **{sticker.name}**",
                    fields=[("🆔 ID", f"`{sticker.id}`", True)],
                )

        for sticker_id in set(before_map) & set(after_map):
            old = before_map[sticker_id]
            new = after_map[sticker_id]
            if old.name != new.name:
                await self.send_log(
                    guild,
                    "sticker_update",
                    f"تم تعديل Sticker: `{old.name}` → `{new.name}`",
                    fields=[("🆔 ID", f"`{new.id}`", True)],
                )


async def setup(bot):
    """يتم استدعاؤها من bot.py قبل تشغيل البوت."""
    await bot.add_cog(ServerLogger(bot))
    print("✅ تم تشغيل نظام Server Logs Pro.")
