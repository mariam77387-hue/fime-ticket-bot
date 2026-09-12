import os
import io
import json
import asyncio
from copy import deepcopy
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
from discord import app_commands
from flask import Flask

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "embed_title": "نظام التذاكر 🎫",
    "embed_description": "اضغط على الزر تحت لفتح تذكرة جديدة والتواصل مع فريق الإدارة.",
    "embed_color": "5865F2",
    "category_name": "Tickets",
    "staff_role_name": "Staff",
    "log_channel_name": "ticket-logs",
    "auto_close_days": 7,
    "admin_role_name": "skibidi admin",
    "welcome_message": "👋 منور/ه مرحبا بك في 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞🌀\n“{display_name}” |\n~\n👋 Welcome to 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞 🌀",
    "welcome_enabled": True,
    "guilds": {}
}

DEFAULT_GUILD_CONFIG = {
    "next_ticket_number": 1,
    "log_channel_id": None,
    "welcome_channel_id": None,
    "category_name": "Tickets",
    "staff_role_name": "Staff",
    "log_channel_name": "ticket-logs",
    "auto_close_days": 7,
    "embed_title": "نظام التذاكر 🎫",
    "embed_description": "اضغط على الزر تحت لفتح تذكرة جديدة والتواصل مع فريق الإدارة.",
    "embed_color": "5865F2",
    "admin_role_name": "skibidi admin",
    "welcome_message": "👋 منور/ه مرحبا بك في 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞🌀\n“{display_name}” |\n~\n👋 Welcome to 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞 🌀",
    "welcome_enabled": True,
    "stats": {
        "opened": 0,
        "closed": 0,
        "claimed": {},
        "categories": {},
        "total": 0,
        "total_duration_seconds": 0
    }
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        loaded = deepcopy(DEFAULT_CONFIG)
        if isinstance(data, dict):
            loaded.update(data)
        if not isinstance(loaded.get("guilds"), dict):
            loaded["guilds"] = {}
        return loaded
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ تعذر قراءة config.json: {e}")
        return deepcopy(DEFAULT_CONFIG)


config = load_config()


def save_config():
    tmp = CONFIG_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except OSError as e:
        print(f"❌ تعذر حفظ config.json: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def make_guild_config():
    result = deepcopy(DEFAULT_GUILD_CONFIG)
    # Preserve old global settings when migrating an older config.
    for key in DEFAULT_GUILD_CONFIG:
        if key in config and key != "stats":
            result[key] = deepcopy(config[key])
    return result


def get_guild_config(guild_id: int):
    guilds = config.setdefault("guilds", {})
    key = str(guild_id)
    changed = False
    if not isinstance(guilds.get(key), dict):
        guilds[key] = make_guild_config()
        changed = True
    current = guilds[key]
    if current.get("welcome_message") == OLD_WELCOME_MESSAGE:
        current["welcome_message"] = DEFAULT_WELCOME_MESSAGE
        changed = True
    for name, default in DEFAULT_GUILD_CONFIG.items():
        if name not in current:
            current[name] = deepcopy(default)
            changed = True
    if not isinstance(current.get("stats"), dict):
        current["stats"] = deepcopy(DEFAULT_GUILD_CONFIG["stats"])
        changed = True
    for name, default in DEFAULT_GUILD_CONFIG["stats"].items():
        if name not in current["stats"]:
            current["stats"][name] = deepcopy(default)
            changed = True
    if changed:
        save_config()
    return current


def get_setting(guild, key, fallback=None):
    return get_guild_config(guild.id).get(key, fallback) if guild else fallback


def set_setting(guild, key, value):
    get_guild_config(guild.id)[key] = value
    save_config()


def get_stats(guild):
    return get_guild_config(guild.id)["stats"]


def increment_stat(guild, key, amount=1):
    stats = get_stats(guild)
    stats[key] = int(stats.get(key, 0)) + amount
    save_config()


def increment_dict_stat(guild, key, item):
    stats = get_stats(guild)
    mapping = stats.setdefault(key, {})
    item = str(item)
    mapping[item] = int(mapping.get(item, 0)) + 1
    save_config()


def get_next_ticket_number(guild):
    cfg = get_guild_config(guild.id)
    try:
        number = max(1, int(cfg.get("next_ticket_number", 1)))
    except (TypeError, ValueError):
        number = 1
    cfg["next_ticket_number"] = number + 1
    save_config()
    return number


TICKET_CATEGORIES = [
    {"label": "دعم فني", "value": "support", "emoji": "🛠️", "description": "مشاكل تقنية أو دعم عام"},
    {"label": "استفسار عن الشراء", "value": "purchase", "emoji": "🛒", "description": "أسئلة قبل أو بعد الشراء"},
    {"label": "شكوى", "value": "complaint", "emoji": "⚠️", "description": "الإبلاغ عن مشكلة أو شكوى"},
    {"label": "استفسار عام", "value": "inquiry", "emoji": "❓", "description": "أي سؤال عام آخر"},
]


def get_category_label(value):
    for c in TICKET_CATEGORIES:
        if c["value"] == value:
            return f'{c["emoji"]} {c["label"]}'
    return value or "غير معروف"


def role_matches(role, expected):
    return role.name.strip().casefold() == str(expected or "").strip().casefold()


def get_admin_role(guild):
    return discord.utils.find(lambda r: role_matches(r, get_setting(guild, "admin_role_name", "skibidi admin")), guild.roles)


def get_staff_role(guild):
    return discord.utils.find(lambda r: role_matches(r, get_setting(guild, "staff_role_name", "Staff")), guild.roles)


def get_ticket_category(guild):
    expected = str(get_setting(guild, "category_name", "Tickets")).strip().casefold()
    return discord.utils.find(lambda c: c.name.strip().casefold() == expected, guild.categories)


def get_log_channel_cached(guild):
    cfg = get_guild_config(guild.id)
    cid = cfg.get("log_channel_id")
    if cid:
        try:
            ch = guild.get_channel(int(cid))
        except (TypeError, ValueError):
            ch = None
        if isinstance(ch, discord.TextChannel):
            return ch
    expected = str(get_setting(guild, "log_channel_name", "ticket-logs")).strip().casefold()
    return discord.utils.find(lambda c: c.name.strip().casefold() == expected, guild.text_channels)


async def resolve_text_channel(guild, channel_id):
    if not guild or not channel_id:
        return None
    try:
        channel_id = int(channel_id)
    except (TypeError, ValueError):
        return None
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel
    try:
        channel = await guild.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None
    return channel if isinstance(channel, discord.TextChannel) else None


async def get_log_channel(guild):
    channel = get_log_channel_cached(guild)
    if channel:
        return channel
    return await resolve_text_channel(guild, get_setting(guild, "log_channel_id"))


def is_admin(member):
    return isinstance(member, discord.Member) and (
        member.guild_permissions.administrator or
        (get_admin_role(member.guild) is not None and get_admin_role(member.guild) in member.roles)
    )


def is_staff(member):
    if not isinstance(member, discord.Member):
        return False
    return is_admin(member) or (get_staff_role(member.guild) is not None and get_staff_role(member.guild) in member.roles)


def admin_only():
    async def predicate(ctx):
        return is_admin(ctx.author)
    return commands.check(predicate)


def is_ticket_channel(channel):
    return isinstance(channel, discord.TextChannel) and bool(channel.topic) and "ticket_id:" in channel.topic


def topic_value(channel, key):
    if not channel.topic:
        return None
    prefix = key + ":"
    for part in channel.topic.split("|"):
        part = part.strip()
        if part.startswith(prefix):
            return part[len(prefix):]
    return None


def get_ticket_owner_id(channel):
    try:
        return int(topic_value(channel, "opener_id"))
    except (TypeError, ValueError):
        return None


def get_ticket_category_value(channel):
    return topic_value(channel, "category")


def get_ticket_claimed_id(channel):
    try:
        return int(topic_value(channel, "claimed_id"))
    except (TypeError, ValueError):
        return None


def get_ticket_number(channel):
    try:
        return int(topic_value(channel, "number"))
    except (TypeError, ValueError):
        return None


def update_ticket_topic(channel, owner_id=None, category_value=None, claimed_id=None, keep_claimed=True, number=None):
    owner_id = owner_id if owner_id is not None else get_ticket_owner_id(channel)
    category_value = category_value if category_value is not None else get_ticket_category_value(channel)
    if claimed_id is None and keep_claimed:
        claimed_id = get_ticket_claimed_id(channel)
    number = number if number is not None else get_ticket_number(channel)
    parts = [f"ticket_id:{channel.id}", f"opener_id:{owner_id}", f"category:{category_value}"]
    if number:
        parts.append(f"number:{number}")
    if claimed_id:
        parts.append(f"claimed_id:{claimed_id}")
    return " | ".join(parts)


def find_open_ticket(guild, user_id):
    for channel in guild.text_channels:
        if is_ticket_channel(channel) and get_ticket_owner_id(channel) == user_id:
            return channel
    return None


def color_from_config(guild):
    try:
        return discord.Color(int(str(get_setting(guild, "embed_color", "5865F2")).replace("#", ""), 16))
    except (ValueError, TypeError):
        return discord.Color.blurple()


async def build_transcript(channel):
    lines = [
        f"Ticket: {channel.name}",
        f"Channel ID: {channel.id}",
        f"Created: {channel.created_at.isoformat()}",
        "=" * 80,
    ]
    try:
        async for message in channel.history(limit=5000, oldest_first=True):
            timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = message.content.strip() or "[بدون نص]"
            lines.append(f"[{timestamp}] {message.author} ({message.author.id}): {content}")
            for attachment in message.attachments:
                lines.append(f"    Attachment: {attachment.url}")
    except (discord.Forbidden, discord.HTTPException) as e:
        lines.append(f"[Transcript error: {e}]")
    data = "\n".join(lines).encode("utf-8")
    return discord.File(io.BytesIO(data), filename=f"{channel.name}-transcript.txt")


async def send_ticket_log(guild, title, description, color=discord.Color.blurple(), file=None, fields=None):
    channel = await get_log_channel(guild)
    if channel is None:
        print(f"⚠️ Logs: no valid log channel in guild {guild.id}")
        return False
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=str(value)[:1024], inline=inline)
    try:
        if file:
            await channel.send(embed=embed, file=file)
        else:
            await channel.send(embed=embed)
        return True
    except discord.Forbidden as e:
        print(f"❌ Logs Forbidden #{channel.name}: {e}")
    except discord.HTTPException as e:
        print(f"❌ Logs HTTP error #{channel.name}: {e}")
    return False


async def close_ticket_channel(channel, closer):
    if not is_ticket_channel(channel):
        return
    guild = channel.guild
    owner_id = get_ticket_owner_id(channel)
    category_value = get_ticket_category_value(channel)
    number = get_ticket_number(channel)
    claimed_id = get_ticket_claimed_id(channel)
    try:
        transcript = await build_transcript(channel)
        await send_ticket_log(
            guild,
            "🔒 تم إغلاق تذكرة",
            f"**الروم:** #{channel.name}\n**صاحب التذكرة:** <@{owner_id}>\n**النوع:** {get_category_label(category_value)}\n**المستلم:** <@{claimed_id}>\n**أغلقها:** {getattr(closer, 'mention', str(closer))}",
            discord.Color.red(),
            transcript,
            [("رقم التذكرة", f"#{number:04d}" if number else "غير معروف", True)],
        )
    except Exception as e:
        print(f"❌ Close/Transcript Error: {e}")
    increment_stat(guild, "closed")
    stats = get_stats(guild)
    duration = max(0, int((datetime.now(timezone.utc) - channel.created_at).total_seconds()))
    stats["total_duration_seconds"] = int(stats.get("total_duration_seconds", 0)) + duration
    save_config()
    try:
        await channel.send("🔒 سيتم حذف التذكرة خلال **5 ثوانٍ**...")
    except discord.HTTPException:
        pass
    await asyncio.sleep(5)
    try:
        await channel.delete(reason=f"Ticket closed by {closer}")
    except discord.NotFound:
        pass
    except discord.Forbidden:
        print(f"❌ لا أستطيع حذف {channel.name}")
    except discord.HTTPException as e:
        print(f"❌ Ticket delete error: {e}")


class TicketReasonModal(discord.ui.Modal, title="سبب فتح التذكرة"):
    reason = discord.ui.TextInput(label="سبب فتح التذكرة", style=discord.TextStyle.paragraph, placeholder="اشرح مشكلتك أو طلبك بالتفصيل...", max_length=1000, required=True)

    def __init__(self, category_value):
        super().__init__()
        self.category_value = category_value

    async def on_submit(self, interaction):
        await create_ticket_channel(interaction, self.category_value, str(self.reason))


class TicketCategorySelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="اختر نوع التذكرة...",
            options=[discord.SelectOption(label=c["label"], value=c["value"], emoji=c["emoji"], description=c["description"]) for c in TICKET_CATEGORIES]
        )

    async def callback(self, interaction):
        await interaction.response.send_modal(TicketReasonModal(self.values[0]))


class TicketCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(TicketCategorySelect())


async def create_ticket_channel(interaction, category_value, reason):
    guild = interaction.guild
    member = interaction.user
    if guild is None:
        await interaction.response.send_message("❌ هذا النظام يعمل داخل السيرفر فقط.", ephemeral=True)
        return
    existing = find_open_ticket(guild, member.id)
    if existing:
        await interaction.response.send_message(f"❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}", ephemeral=True)
        return
    category = get_ticket_category(guild)
    if category is None:
        try:
            category = await guild.create_category(get_setting(guild, "category_name", "Tickets"), reason="إنشاء كاتيجوري التذاكر")
        except discord.Forbidden:
            await interaction.response.send_message("❌ البوت لا يملك صلاحية إنشاء الكاتيجوري.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("❌ تعذر إنشاء كاتيجوري التذاكر.", ephemeral=True)
            return
    number = get_next_ticket_number(guild)
    staff_role = get_staff_role(guild)
    me = guild.me
    if me is None:
        await interaction.response.send_message("❌ تعذر تحديد البوت داخل السيرفر.", ephemeral=True)
        return
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True, embed_links=True, attach_files=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
    admin_role = get_admin_role(guild)
    if admin_role and admin_role != guild.default_role:
        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True, manage_messages=True)
    try:
        ticket_channel = await guild.create_text_channel(name=f"ticket-{number:04d}", category=category, overwrites=overwrites, reason=f"Ticket opened by {member}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ ما قدرت أنشئ التذكرة. تأكد من Manage Channels و View Channel.", ephemeral=True)
        return
    except discord.HTTPException as e:
        print(f"❌ Ticket create error: {e}")
        await interaction.response.send_message("❌ حدث خطأ أثناء إنشاء التذكرة.", ephemeral=True)
        return
    try:
        await ticket_channel.edit(topic=update_ticket_topic(ticket_channel, owner_id=member.id, category_value=category_value, claimed_id=None, keep_claimed=False, number=number))
    except discord.HTTPException as e:
        print(f"⚠️ Topic error: {e}")
    embed = discord.Embed(title=f"🎫 تذكرة #{number:04d}", description=f"أهلاً {member.mention} 👋\n\nانتظر أحد أعضاء فريق الإدارة لمساعدتك.", color=color_from_config(guild))
    embed.add_field(name="📂 النوع", value=get_category_label(category_value), inline=True)
    embed.add_field(name="👤 صاحب التذكرة", value=member.mention, inline=True)
    embed.add_field(name="👨‍💼 الموظف المسؤول", value="لم يتم الاستلام بعد", inline=False)
    embed.add_field(name="📝 السبب", value=reason[:1024], inline=False)
    embed.add_field(name="🆔 رقم التذكرة", value=f"#{number:04d}", inline=True)
    embed.add_field(name="📅 الإنشاء", value=discord.utils.format_dt(ticket_channel.created_at, style="R"), inline=True)
    embed.set_footer(text="استخدم الأزرار أسفل الرسالة.")
    try:
        await ticket_channel.send(content=staff_role.mention if staff_role else None, embed=embed, view=TicketActionView())
    except discord.HTTPException as e:
        print(f"❌ Ticket message error: {e}")
    increment_stat(guild, "opened")
    increment_stat(guild, "total")
    increment_dict_stat(guild, "categories", category_value)
    await send_ticket_log(guild, "🎫 تم فتح تذكرة", f"**الروم:** {ticket_channel.mention}\n**صاحب التذكرة:** {member.mention}\n**النوع:** {get_category_label(category_value)}", discord.Color.green(), fields=[("رقم التذكرة", f"#{number:04d}", True), ("السبب", reason, False)])
    await interaction.response.send_message(f"✅ تم إنشاء تذكرتك: {ticket_channel.mention}", ephemeral=True)


class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة جديدة 🎫", style=discord.ButtonStyle.green, custom_id="open_ticket_button")
    async def open_ticket(self, interaction, button):
        existing = find_open_ticket(interaction.guild, interaction.user.id)
        if existing:
            await interaction.response.send_message(f"❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}", ephemeral=True)
            return
        await interaction.response.send_message("اختر نوع التذكرة:", view=TicketCategoryView(), ephemeral=True)


class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="استلام التذكرة 👤", style=discord.ButtonStyle.blurple, custom_id="claim_ticket_button")
    async def claim_ticket(self, interaction, button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ هذا الزر للموظفين أو الإداريين فقط.", ephemeral=True)
            return
        channel = interaction.channel
        if not is_ticket_channel(channel):
            await interaction.response.send_message("❌ هذا الروم ليس تذكرة.", ephemeral=True)
            return
        claimed_id = get_ticket_claimed_id(channel)
        if claimed_id:
            await interaction.response.send_message("أنت مستلم هذه التذكرة بالفعل." if claimed_id == interaction.user.id else f"❌ هذه التذكرة مستلمة من <@{claimed_id}>.", ephemeral=True)
            return
        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed(title=f"🎫 {channel.name}")
        found = False
        for i, field in enumerate(embed.fields):
            if "الموظف" in field.name:
                embed.set_field_at(i, name="👨‍💼 الموظف المسؤول", value=interaction.user.mention, inline=field.inline)
                found = True
                break
        if not found:
            embed.add_field(name="👨‍💼 الموظف المسؤول", value=interaction.user.mention, inline=False)
        try:
            await channel.edit(topic=update_ticket_topic(channel, claimed_id=interaction.user.id))
        except discord.HTTPException as e:
            print(f"⚠️ Claim topic error: {e}")
        increment_dict_stat(interaction.guild, "claimed", str(interaction.user.id))
        button.disabled = True
        button.label = "تم الاستلام ✅"
        await interaction.response.edit_message(embed=embed, view=self)
        try:
            await channel.send(f"👤 **تم استلام التذكرة بواسطة {interaction.user.mention}**")
        except discord.HTTPException:
            pass
        await send_ticket_log(interaction.guild, "👤 تم استلام تذكرة", f"**التذكرة:** {channel.mention}\n**الموظف:** {interaction.user.mention}", discord.Color.blurple(), fields=[("رقم التذكرة", f"#{get_ticket_number(channel):04d}" if get_ticket_number(channel) else "غير معروف", True)])

    @discord.ui.button(label="إغلاق التذكرة 🔒", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_ticket(self, interaction, button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ إغلاق التذاكر متاح للموظفين أو الإداريين فقط.", ephemeral=True)
            return
        if not is_ticket_channel(interaction.channel):
            await interaction.response.send_message("❌ هذا الروم ليس تذكرة.", ephemeral=True)
            return
        await interaction.response.send_message("هل أنت متأكد من إغلاق التذكرة؟", view=ConfirmCloseView(), ephemeral=True)


class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="تأكيد الإغلاق ✅", style=discord.ButtonStyle.red)
    async def confirm(self, interaction, button):
        if not is_staff(interaction.user):
            await interaction.response.send_message("❌ إغلاق التذاكر متاح للموظفين أو الإداريين فقط.", ephemeral=True)
            return
        if not is_ticket_channel(interaction.channel):
            await interaction.response.send_message("❌ هذه التذكرة لم تعد موجودة.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 جارٍ إغلاق التذكرة...", ephemeral=True)
        await close_ticket_channel(interaction.channel, interaction.user)

    @discord.ui.button(label="إلغاء ❌", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="✅ تم إلغاء الإغلاق.", view=None)


# ------------------------- Welcome -------------------------
DEFAULT_WELCOME_MESSAGE = DEFAULT_CONFIG["welcome_message"]


def render_welcome_message(guild, member):
    template = str(get_setting(guild, "welcome_message", DEFAULT_WELCOME_MESSAGE) or DEFAULT_WELCOME_MESSAGE)
    values = {
        "{mention}": member.mention,
        "{username}": member.name,
        "{display_name}": member.display_name,
        "{server}": guild.name,
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return template[:2000]


async def get_welcome_channel(guild):
    if guild is None:
        return None
    return await resolve_text_channel(guild, get_setting(guild, "welcome_channel_id"))


class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, owner_id):
        self.owner_id = owner_id
        super().__init__(placeholder="اختر روم الترحيب...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text])

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
            return
        selected = self.values[0]
        channel_id = getattr(selected, "id", None)
        channel = await resolve_text_channel(interaction.guild, channel_id)
        if channel is None:
            await interaction.response.send_message("❌ اختر روم نصي عادي.", ephemeral=True)
            return
        me = interaction.guild.me
        permissions = channel.permissions_for(me) if me else None
        missing = [] if permissions else ["View Channel", "Send Messages", "Embed Links"]
        if permissions:
            for name, ok in [("View Channel", permissions.view_channel), ("Send Messages", permissions.send_messages), ("Embed Links", permissions.embed_links)]:
                if not ok:
                    missing.append(name)
        if missing:
            await interaction.response.send_message("❌ البوت ناقصه صلاحيات:\n" + "\n".join(f"• `{x}`" for x in missing), ephemeral=True)
            return
        set_setting(interaction.guild, "welcome_channel_id", channel.id)
        set_setting(interaction.guild, "welcome_enabled", True)
        await interaction.response.edit_message(content=f"✅ **تم تحديد روم الترحيب**\n\n📍 الروم: {channel.mention}\n🟢 الترحيب مفعل الآن.\n\nاستخدم `/testwelcome` للتأكد.", view=None)


class WelcomeChannelSelectView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=120)
        self.add_item(WelcomeChannelSelect(owner_id))


# ------------------------- Logs setup -------------------------
class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, owner_id):
        self.owner_id = owner_id
        super().__init__(placeholder="اختر روم الـLogs...", min_values=1, max_values=1, channel_types=[discord.ChannelType.text])

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
            return
        selected = self.values[0]
        channel_id = getattr(selected, "id", None)
        # ChannelSelect may return AppCommandChannel. Never call permissions_for on it.
        channel = await resolve_text_channel(interaction.guild, channel_id)
        if channel is None:
            await interaction.response.send_message("❌ تعذر تحويل الروم المحدد إلى TextChannel حقيقي.", ephemeral=True)
            return
        me = interaction.guild.me
        permissions = channel.permissions_for(me) if me else None
        required = [("View Channel", getattr(permissions, "view_channel", False)), ("Send Messages", getattr(permissions, "send_messages", False)), ("Embed Links", getattr(permissions, "embed_links", False))]
        missing = [name for name, ok in required if not ok]
        if missing:
            await interaction.response.send_message("❌ البوت يحتاج:\n" + "\n".join(f"• `{x}`" for x in missing), ephemeral=True)
            return
        set_setting(interaction.guild, "log_channel_id", channel.id)
        # Real test: prove the configured channel can receive the log.
        test = await send_ticket_log(interaction.guild, "📋 Logs جاهزة", "تم اختبار نظام الـLogs بنجاح.", discord.Color.green())
        if not test:
            await interaction.response.send_message("⚠️ تم حفظ الروم، لكن فشل إرسال Log تجريبي. راجع صلاحيات الروم.", ephemeral=True)
            return
        await interaction.response.edit_message(content=f"✅ تم تحديد روم الـLogs وتشغيل الاختبار: {channel.mention}", view=None)


class LogChannelSelectView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=120)
        self.add_item(LogChannelSelect(owner_id))


# ------------------------- Lock / Unlock -------------------------
def is_lockable_channel(channel):
    return isinstance(channel, (discord.TextChannel, discord.Thread))


def can_manage_lock(member, channel):
    if not isinstance(member, discord.Member):
        return False
    if is_admin(member):
        return True
    return member.guild_permissions.manage_threads if isinstance(channel, discord.Thread) else member.guild_permissions.manage_channels


def bot_can_manage_lock(channel):
    me = channel.guild.me
    if me is None:
        return False
    if me.guild_permissions.administrator:
        return True
    return me.guild_permissions.manage_threads if isinstance(channel, discord.Thread) else me.guild_permissions.manage_channels


async def lock_any_channel(channel):
    try:
        if isinstance(channel, discord.Thread):
            if channel.archived:
                await channel.edit(archived=False, reason="Preparing thread for lock")
            await channel.edit(locked=True, reason="Lock Thread")
            return True
        if isinstance(channel, discord.TextChannel):
            overwrite = channel.overwrites_for(channel.guild.default_role)
            overwrite.view_channel = True
            overwrite.send_messages = False
            await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason="Lock: read only")
            return True
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"❌ Lock error: {e}")
    return False


async def unlock_any_channel(channel):
    try:
        if isinstance(channel, discord.Thread):
            await channel.edit(locked=False, archived=False, reason="Unlock Thread")
            return True
        if isinstance(channel, discord.TextChannel):
            overwrite = channel.overwrites_for(channel.guild.default_role)
            overwrite.view_channel = True
            overwrite.send_messages = None
            await channel.set_permissions(channel.guild.default_role, overwrite=overwrite, reason="Unlock: open chat")
            return True
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"❌ Unlock error: {e}")
    return False


async def send_lock_result(channel, user, locked):
    text = f"{'🔒 تم قفل' if locked else '🔓 تم فتح'} **{channel.name}**\n👤 بواسطة: {user.mention}"
    try:
        await channel.send(text, delete_after=6)
    except (discord.Forbidden, discord.HTTPException):
        pass


class ChannelLockView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)
        self.channel_id, self.owner_id = channel_id, owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="قفل الكتابة", emoji="🔒", style=discord.ButtonStyle.danger)
    async def lock(self, interaction, button):
        channel = interaction.guild.get_channel(self.channel_id)
        if channel is None:
            await interaction.response.send_message("❌ ما قدرت ألقى الروم.", ephemeral=True)
            return
        await perform_lock(interaction, channel, interaction.user)

    @discord.ui.button(label="فتح الكلام", emoji="💬", style=discord.ButtonStyle.success)
    async def unlock(self, interaction, button):
        channel = interaction.guild.get_channel(self.channel_id)
        if channel is None:
            await interaction.response.send_message("❌ ما قدرت ألقى الروم.", ephemeral=True)
            return
        await perform_unlock(interaction, channel, interaction.user)

    @discord.ui.button(label="إلغاء", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="تم إلغاء العملية.", view=None)


async def perform_lock(interaction, channel, user):
    if not is_lockable_channel(channel):
        await interaction.response.send_message("❌ هذا النظام يعمل على Text Channels و Threads.", ephemeral=True)
        return False
    if not can_manage_lock(user, channel):
        await interaction.response.send_message("❌ ما عندك الصلاحية المناسبة.", ephemeral=True)
        return False
    if not bot_can_manage_lock(channel):
        await interaction.response.send_message("❌ البوت لا يملك الصلاحية المناسبة.", ephemeral=True)
        return False
    if not await lock_any_channel(channel):
        await interaction.response.send_message("❌ فشل القفل.", ephemeral=True)
        return False
    await interaction.response.send_message(f"🔒 تم قفل {channel.mention}.", ephemeral=True)
    await send_lock_result(channel, user, True)
    return True


async def perform_unlock(interaction, channel, user):
    if not is_lockable_channel(channel):
        await interaction.response.send_message("❌ هذا النظام يعمل على Text Channels و Threads.", ephemeral=True)
        return False
    if not can_manage_lock(user, channel):
        await interaction.response.send_message("❌ ما عندك الصلاحية المناسبة.", ephemeral=True)
        return False
    if not bot_can_manage_lock(channel):
        await interaction.response.send_message("❌ البوت لا يملك الصلاحية المناسبة.", ephemeral=True)
        return False
    if not await unlock_any_channel(channel):
        await interaction.response.send_message("❌ فشل الفتح.", ephemeral=True)
        return False
    await interaction.response.send_message(f"🔓 تم فتح {channel.mention}.", ephemeral=True)
    await send_lock_result(channel, user, False)
    return True


# ------------------------- Bot -------------------------
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot is alive!"


def run_web_server():
    web_app.run(host="0.0.0.0", port=PORT)


def keep_alive():
    import threading
    threading.Thread(target=run_web_server, daemon=True).start()


async def run_setup_checks(guild):
    me = guild.me
    category = get_ticket_category(guild)
    logs = await get_log_channel(guild)
    welcome = await get_welcome_channel(guild)
    checks = []
    checks.append(("Admin Role", get_admin_role(guild) is not None, "رتبة skibidi admin"))
    checks.append(("Ticket Category", category is not None, get_setting(guild, "category_name", "Tickets")))
    checks.append(("Logs", logs is not None, "استخدم /log"))
    checks.append(("Welcome", welcome is not None, "استخدم /welcome"))
    if me:
        for name, ok in [("View Channel", me.guild_permissions.view_channel), ("Send Messages", me.guild_permissions.send_messages), ("Manage Channels", me.guild_permissions.manage_channels), ("Manage Roles", me.guild_permissions.manage_roles), ("Embed Links", me.guild_permissions.embed_links), ("Attach Files", me.guild_permissions.attach_files), ("Read Message History", me.guild_permissions.read_message_history)]:
            checks.append((name, ok, "Bot permission"))
    return checks


def setup_check_embed(guild, checks):
    failed = [x for x in checks if not x[1]]
    embed = discord.Embed(title="🛠️ Setup Check", color=discord.Color.green() if not failed else discord.Color.orange())
    embed.description = "\n".join(f"{'🟢' if ok else '🔴'} {name}" for name, ok, _ in checks)
    if failed:
        embed.add_field(name="⚠️ يحتاج إصلاح", value="\n".join(f"• **{name}** — {hint}" for name, _, hint in failed)[:1024], inline=False)
    else:
        embed.add_field(name="✅ جاهز", value="كل الفحوصات الأساسية ناجحة. تقدر تنشر لوحة التذاكر.", inline=False)
    return embed


@bot.command(name="setup")
@admin_only()
async def setup_cmd(ctx):
    checks = await run_setup_checks(ctx.guild)
    failed = [x for x in checks if not x[1]]
    if failed:
        await ctx.send(embed=setup_check_embed(ctx.guild, checks))
        return

    embed = discord.Embed(title=get_setting(ctx.guild, "embed_title", DEFAULT_CONFIG["embed_title"]), description=get_setting(ctx.guild, "embed_description", DEFAULT_CONFIG["embed_description"]), color=color_from_config(ctx.guild))
    embed.set_footer(text="نظام التذاكر")
    await ctx.send(embed=embed, view=OpenTicketView())
    try: await ctx.message.delete()
    except discord.HTTPException: pass


@bot.command(name="embed")
@admin_only()
async def embed_cmd(ctx, channel: discord.TextChannel):
    prompt = await ctx.send("تمام ✅\nأرسل الآن نص الرسالة كامل.\n\nأول سطر = العنوان\nوالباقي = المحتوى\n\n⏰ لديك 5 دقائق.")
    def check(message): return message.author.id == ctx.author.id and message.channel.id == ctx.channel.id
    try: reply = await bot.wait_for("message", check=check, timeout=300)
    except asyncio.TimeoutError:
        await prompt.edit(content="⏰ انتهى الوقت."); return
    lines = reply.content.split("\n")
    title = lines[0].strip() if lines else None
    description = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    if not description: description, title = title, None
    await channel.send(embed=discord.Embed(title=title, description=description, color=discord.Color.gold()))
    await ctx.send(f"✅ تم نشر الـEmbed في {channel.mention}")
    try: await ctx.message.delete(); await reply.delete()
    except discord.HTTPException: pass


@bot.tree.command(name="welcome", description="اختيار روم الترحيب وتفعيل الترحيب")
@app_commands.check(lambda i: is_admin(i.user))
async def welcome_command(interaction):
    await interaction.response.send_message("👋 **إعداد الترحيب**\n\nاختر الروم الذي تريد أن تظهر فيه رسائل الترحيب:", view=WelcomeChannelSelectView(interaction.user.id), ephemeral=True)


@bot.tree.command(name="testwelcome", description="اختبار رسالة الترحيب")
@app_commands.check(lambda i: is_admin(i.user))
async def test_welcome_command(interaction):
    channel = await get_welcome_channel(interaction.guild)
    if channel is None:
        await interaction.response.send_message("❌ ما تم تحديد روم ترحيب. استخدم `/welcome` أولًا.", ephemeral=True); return
    try:
        await channel.send(render_welcome_message(interaction.guild, interaction.user), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    except discord.Forbidden:
        await interaction.response.send_message("❌ البوت لا يستطيع الإرسال في روم الترحيب.", ephemeral=True); return
    except discord.HTTPException as e:
        print(f"❌ Welcome Test Error: {e}"); await interaction.response.send_message("❌ صار خطأ أثناء الاختبار.", ephemeral=True); return
    await interaction.response.send_message(f"✅ تم إرسال الاختبار إلى {channel.mention}.", ephemeral=True)


@bot.tree.command(name="welcomestatus", description="عرض حالة نظام الترحيب")
@app_commands.check(lambda i: is_admin(i.user))
async def welcome_status_command(interaction):
    channel = await get_welcome_channel(interaction.guild)
    enabled = bool(get_setting(interaction.guild, "welcome_enabled", True))
    embed = discord.Embed(title="👋 حالة الترحيب", color=discord.Color.green() if channel and enabled else discord.Color.red())
    embed.add_field(name="الحالة", value="🟢 مفعل" if channel and enabled else "🔴 غير مفعل", inline=True)
    embed.add_field(name="الروم", value=channel.mention if channel else "❌ غير محدد", inline=True)
    embed.add_field(name="المتغيرات", value="`{mention}` `{username}` `{display_name}` `{server}`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="welcomeoff", description="إيقاف رسائل الترحيب")
@app_commands.check(lambda i: is_admin(i.user))
async def welcome_off_command(interaction):
    set_setting(interaction.guild, "welcome_enabled", False)
    await interaction.response.send_message("🔴 تم إيقاف الترحيب. استخدم `/welcome` لتفعيله من جديد.", ephemeral=True)


@bot.event
async def on_member_join(member):
    if member.bot:
        role = discord.utils.find(lambda r: r.name.strip().casefold() == "bot", member.guild.roles)
        if role:
            try: await member.add_roles(role, reason="Auto role on bot join")
            except (discord.Forbidden, discord.HTTPException) as e: print(f"⚠️ Bot Auto Role Error: {e}")
        return
    role = discord.utils.find(lambda r: r.name.strip().casefold() == "member", member.guild.roles)
    if role:
        try: await member.add_roles(role, reason="Auto role on member join")
        except (discord.Forbidden, discord.HTTPException) as e: print(f"⚠️ Auto Role Error: {e}")
    if not get_setting(member.guild, "welcome_enabled", True): return
    channel = await get_welcome_channel(member.guild)
    if channel is None: return
    me = member.guild.me
    permissions = channel.permissions_for(me) if me else None
    if not permissions or not permissions.view_channel or not permissions.send_messages:
        print(f"⚠️ البوت لا يملك صلاحية إرسال الترحيب في #{channel.name}."); return
    try:
        await channel.send(render_welcome_message(member.guild, member), allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
    except (discord.Forbidden, discord.HTTPException) as e: print(f"❌ Welcome Error: {e}")


@bot.tree.command(name="log", description="اختيار روم الـLogs")
@app_commands.check(lambda i: is_admin(i.user))
async def log_command(interaction):
    await interaction.response.send_message("📋 **إعداد الـLogs**\n\nاختر الروم الذي تريد إرسال Logs البوت إليه:", view=LogChannelSelectView(interaction.user.id), ephemeral=True)


@bot.tree.command(name="logstatus", description="فحص روم الـLogs")
@app_commands.check(lambda i: is_admin(i.user))
async def log_status_command(interaction):
    channel = await get_log_channel(interaction.guild)
    cfg_id = get_setting(interaction.guild, "log_channel_id")
    if channel:
        me = interaction.guild.me
        p = channel.permissions_for(me) if me else None
        ok = p and p.view_channel and p.send_messages and p.embed_links
        text = f"🟢 روم الـLogs: {channel.mention}\n🟢 الصلاحيات الأساسية موجودة." if ok else f"🟡 الروم: {channel.mention}\n🔴 توجد صلاحيات ناقصة."
        await interaction.response.send_message(text, ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ لا يوجد روم Logs صالح. ID المحفوظ: `{cfg_id}`. استخدم `/log`.", ephemeral=True)


@bot.tree.command(name="botstatus", description="فحص إعدادات البوت وصلاحياته")
@app_commands.check(lambda i: is_admin(i.user))
async def bot_status_command(interaction):
    guild = interaction.guild
    me = guild.me
    admin = get_admin_role(guild)
    staff = get_staff_role(guild)
    category = get_ticket_category(guild)
    logs = await get_log_channel(guild)
    welcome = await get_welcome_channel(guild)
    checks = []
    checks.append(("Admin Role", bool(admin)))
    checks.append(("Staff Role (optional)", bool(staff)))
    checks.append(("Ticket Category", bool(category)))
    checks.append(("Logs", bool(logs)))
    checks.append(("Welcome", bool(welcome) and bool(get_setting(guild, "welcome_enabled", True))))
    if me:
        for name, value in [("View Channel", me.guild_permissions.view_channel), ("Send Messages", me.guild_permissions.send_messages), ("Manage Channels", me.guild_permissions.manage_channels), ("Manage Roles", me.guild_permissions.manage_roles), ("Manage Messages", me.guild_permissions.manage_messages), ("Manage Threads", me.guild_permissions.manage_threads), ("Read Message History", me.guild_permissions.read_message_history), ("Embed Links", me.guild_permissions.embed_links), ("Attach Files", me.guild_permissions.attach_files)]:
            checks.append((name, value))
    ok_count = sum(v for _, v in checks)
    embed = discord.Embed(title="🩺 Bot Diagnostics", description=f"**{ok_count}/{len(checks)}** checks passed", color=discord.Color.green() if ok_count == len(checks) else discord.Color.orange())
    lines = []
    for name, value in checks:
        lines.append(f"{'🟢' if value else '🔴'} {name}")
    embed.description = "\n".join(lines)
    embed.add_field(name="👑 Admin", value=admin.mention if admin else "❌ skibidi admin غير موجودة", inline=True)
    embed.add_field(name="🛡️ Staff", value=staff.mention if staff else "⚪ اختيارية / غير موجودة", inline=True)
    embed.add_field(name="🎫 Category", value=category.name if category else "❌ غير موجودة", inline=True)
    embed.add_field(name="📋 Logs", value=logs.mention if logs else "❌ غير محدد", inline=True)
    embed.add_field(name="👋 Welcome", value=welcome.mention if welcome else "❌ غير محدد", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="ticketinfo", description="عرض معلومات التذكرة الحالية")
async def ticket_info_command(interaction):
    channel = interaction.channel
    if not is_ticket_channel(channel):
        await interaction.response.send_message("❌ هذا الأمر يعمل داخل التذاكر فقط.", ephemeral=True); return
    owner, category, claimed, number = get_ticket_owner_id(channel), get_ticket_category_value(channel), get_ticket_claimed_id(channel), get_ticket_number(channel)
    embed = discord.Embed(title="🎫 معلومات التذكرة", color=discord.Color.blurple())
    embed.add_field(name="🆔 رقم التذكرة", value=f"#{number:04d}" if number else "غير معروف", inline=True)
    embed.add_field(name="👤 صاحب التذكرة", value=f"<@{owner}>" if owner else "غير معروف", inline=True)
    embed.add_field(name="📂 النوع", value=get_category_label(category), inline=True)
    embed.add_field(name="👤 المستلم", value=f"<@{claimed}>" if claimed else "لم يتم الاستلام", inline=True)
    embed.add_field(name="📅 الإنشاء", value=discord.utils.format_dt(channel.created_at, style="F"), inline=True)
    embed.add_field(name="🆔 Channel ID", value=str(channel.id), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ------------------------- Ticket Config -------------------------
@bot.group(name="ticketconfig", invoke_without_command=True)
@admin_only()
async def ticketconfig(ctx):
    embed = discord.Embed(title="⚙️ إعدادات نظام التذاكر", color=color_from_config(ctx.guild))
    fields = [("العنوان", get_setting(ctx.guild, "embed_title", "")[:1024], False), ("الوصف", get_setting(ctx.guild, "embed_description", "")[:1024], False), ("اللون", f'#{get_setting(ctx.guild, "embed_color", "5865F2")}', True), ("الكاتيجوري", get_setting(ctx.guild, "category_name", "Tickets"), True), ("رتبة الموظفين", get_setting(ctx.guild, "staff_role_name", "Staff"), True), ("روم Logs", get_setting(ctx.guild, "log_channel_name", "ticket-logs"), True), ("الإغلاق التلقائي", f'{get_setting(ctx.guild, "auto_close_days", 7)} يوم', True)]
    for n, v, inline in fields: embed.add_field(name=n, value=v, inline=inline)
    await ctx.send(embed=embed)


@ticketconfig.command(name="help")
async def ticketconfig_help(ctx):
    if not is_admin(ctx.author): return
    await ctx.send("**⚙️ أوامر إعدادات التذاكر:**\n`!ticketconfig title <النص>`\n`!ticketconfig desc <النص>`\n`!ticketconfig color <HEX>`\n`!ticketconfig category <الاسم>`\n`!ticketconfig staffrole <الاسم>`\n`!ticketconfig logchannel <الاسم>`\n`!ticketconfig autoclose <الأيام>`")


@ticketconfig.command(name="title")
@admin_only()
async def tc_title(ctx, *, value): set_setting(ctx.guild, "embed_title", value); await ctx.send("✅ تم تحديث العنوان.")

@ticketconfig.command(name="desc")
@admin_only()
async def tc_desc(ctx, *, value): set_setting(ctx.guild, "embed_description", value); await ctx.send("✅ تم تحديث الوصف.")

@ticketconfig.command(name="color")
@admin_only()
async def tc_color(ctx, value):
    value = value.strip().replace("#", "").upper()
    if len(value) != 6:
        await ctx.send("❌ استخدم لون HEX من 6 خانات."); return
    try: int(value, 16)
    except ValueError:
        await ctx.send("❌ كود اللون غير صحيح."); return
    set_setting(ctx.guild, "embed_color", value); await ctx.send(f"✅ تم تحديث اللون إلى `#{value}`")

@ticketconfig.command(name="category")
@admin_only()
async def tc_category(ctx, *, value): set_setting(ctx.guild, "category_name", value); await ctx.send(f"✅ تم تحديث الكاتيجوري إلى `{value}`")

@ticketconfig.command(name="staffrole")
@admin_only()
async def tc_staffrole(ctx, *, value): set_setting(ctx.guild, "staff_role_name", value); await ctx.send(f"✅ تم تحديث رتبة الموظفين إلى `{value}`")

@ticketconfig.command(name="logchannel")
@admin_only()
async def tc_logchannel(ctx, *, value): set_setting(ctx.guild, "log_channel_name", value); await ctx.send(f"✅ تم تحديث اسم روم Logs إلى `{value}`. يفضل استخدام `/log` لتحديده بالـID.")

@ticketconfig.command(name="autoclose")
@admin_only()
async def tc_autoclose(ctx, days: int):
    if days < 1:
        await ctx.send("❌ لازم يكون العدد 1 أو أكثر."); return
    set_setting(ctx.guild, "auto_close_days", days); await ctx.send(f"✅ سيتم إغلاق التذاكر الخاملة بعد {days} يوم.")


# ------------------------- Statistics / Dashboard -------------------------
def top_stat(mapping, guild):
    if not mapping: return "لا توجد بيانات بعد."
    pairs = sorted(mapping.items(), key=lambda x: int(x[1]), reverse=True)[:5]
    return "\n".join(f"<@{uid}> — **{count}**" for uid, count in pairs)


def top_categories(mapping):
    if not mapping: return "لا توجد بيانات بعد."
    pairs = sorted(mapping.items(), key=lambda x: int(x[1]), reverse=True)[:5]
    return "\n".join(f"{get_category_label(k)} — **{v}**" for k, v in pairs)


async def diagnostics_embed(guild):
    me = guild.me
    logs = await get_log_channel(guild)
    welcome = await get_welcome_channel(guild)
    checks = {
        "Admin Role": get_admin_role(guild) is not None,
        "Staff Role (optional)": True,
        "Ticket Category": get_ticket_category(guild) is not None,
        "Logs": logs is not None,
        "Welcome": welcome is not None and bool(get_setting(guild, "welcome_enabled", True)),
    }
    if me:
        checks.update({"View Channel": me.guild_permissions.view_channel, "Send Messages": me.guild_permissions.send_messages, "Manage Channels": me.guild_permissions.manage_channels, "Manage Roles": me.guild_permissions.manage_roles, "Manage Messages": me.guild_permissions.manage_messages, "Manage Threads": me.guild_permissions.manage_threads, "Read Messages": me.guild_permissions.read_message_history, "Embed Links": me.guild_permissions.embed_links})
    return checks


class DashboardView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ هذه اللوحة ليست لك.", ephemeral=True); return False
        if not is_admin(interaction.user):
            await interaction.response.send_message("❌ لوحة الإدارة للإداريين فقط.", ephemeral=True); return False
        return True

    @discord.ui.button(label="Tickets", emoji="🎫", style=discord.ButtonStyle.primary)
    async def tickets(self, interaction, button):
        stats = get_stats(interaction.guild)
        open_count = sum(1 for c in interaction.guild.text_channels if is_ticket_channel(c))
        embed = discord.Embed(title="🎫 Tickets", color=discord.Color.blurple())
        embed.add_field(name="المفتوحة الآن", value=str(open_count), inline=True)
        embed.add_field(name="المغلقة", value=str(stats.get("closed", 0)), inline=True)
        embed.add_field(name="الإجمالي", value=str(stats.get("total", 0)), inline=True)
        embed.add_field(name="الأكثر استخدامًا", value=top_categories(stats.get("categories", {})), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Welcome", emoji="👋", style=discord.ButtonStyle.secondary)
    async def welcome(self, interaction, button):
        ch = await get_welcome_channel(interaction.guild)
        enabled = bool(get_setting(interaction.guild, "welcome_enabled", True))
        embed = discord.Embed(title="👋 Welcome", color=discord.Color.green() if ch and enabled else discord.Color.red())
        embed.description = f"الحالة: {'🟢 مفعل' if ch and enabled else '🔴 غير مفعل'}\nالروم: {ch.mention if ch else '❌ غير محدد'}\n\nللتغيير استخدم `/welcome`."
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Logs", emoji="📋", style=discord.ButtonStyle.secondary)
    async def logs(self, interaction, button):
        ch = await get_log_channel(interaction.guild)
        embed = discord.Embed(title="📋 Logs", color=discord.Color.green() if ch else discord.Color.red())
        embed.description = f"الروم: {ch.mention if ch else '❌ غير محدد'}\n\nللتغيير استخدم `/log`."
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Statistics", emoji="📊", style=discord.ButtonStyle.success, row=1)
    async def statistics(self, interaction, button):
        stats = get_stats(interaction.guild)
        embed = discord.Embed(title="📊 Ticket Statistics", color=discord.Color.green())
        embed.add_field(name="🎫 الإجمالي", value=str(stats.get("total", 0)), inline=True)
        embed.add_field(name="🟢 المفتوحة سابقًا", value=str(stats.get("opened", 0)), inline=True)
        embed.add_field(name="🔴 المغلقة", value=str(stats.get("closed", 0)), inline=True)
        embed.add_field(name="🏆 أكثر Staff استلامًا", value=top_stat(stats.get("claimed", {}), interaction.guild), inline=False)
        embed.add_field(name="📂 أكثر الأنواع", value=top_categories(stats.get("categories", {})), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Settings", emoji="🛠️", style=discord.ButtonStyle.secondary, row=1)
    async def settings(self, interaction, button):
        guild = interaction.guild
        embed = discord.Embed(title="🛠️ Settings", color=color_from_config(guild))
        embed.description = f"**Category:** `{get_setting(guild, 'category_name', 'Tickets')}`\n**Staff:** `{get_setting(guild, 'staff_role_name', 'Staff')}`\n**Admin:** `{get_setting(guild, 'admin_role_name', 'skibidi admin')}`\n**Auto Close:** `{get_setting(guild, 'auto_close_days', 7)} days`\n\n**Admin** لا يحتاج Staff. رتبة Staff اختيارية."
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Diagnostics", emoji="🩺", style=discord.ButtonStyle.primary, row=2)
    async def diagnostics(self, interaction, button):
        checks = await diagnostics_embed(interaction.guild)
        embed = discord.Embed(title="🩺 Diagnostics", color=discord.Color.green() if all(checks.values()) else discord.Color.orange())
        embed.description = "\n".join(f"{'🟢' if ok else '🔴'} {name}" for name, ok in checks.items())
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction, button):
        embed = discord.Embed(title="⚙️ Bot Control Panel", description="اختر القسم الذي تريد إدارته.", color=color_from_config(interaction.guild))
        await interaction.response.edit_message(embed=embed, view=self)


@bot.tree.command(name="setup", description="فحص وتجهيز نظام التذاكر ثم نشر لوحة التذاكر")
@app_commands.check(lambda i: is_admin(i.user))
async def slash_setup(interaction):
    checks = await run_setup_checks(interaction.guild)
    failed = [x for x in checks if not x[1]]
    if failed:
        await interaction.response.send_message(embed=setup_check_embed(interaction.guild, checks), ephemeral=True)
        return
    embed = discord.Embed(title=get_setting(interaction.guild, "embed_title", DEFAULT_CONFIG["embed_title"]), description=get_setting(interaction.guild, "embed_description", DEFAULT_CONFIG["embed_description"]), color=color_from_config(interaction.guild))
    embed.set_footer(text="نظام التذاكر")
    await interaction.response.send_message(embed=embed, view=OpenTicketView())


@bot.tree.command(name="dashboard", description="فتح لوحة تحكم البوت")
@app_commands.check(lambda i: is_admin(i.user))
async def dashboard(interaction):
    embed = discord.Embed(title="⚙️ Bot Control Panel", description="اختر القسم الذي تريد إدارته.", color=color_from_config(interaction.guild))
    await interaction.response.send_message(embed=embed, view=DashboardView(interaction.user.id), ephemeral=True)


@bot.tree.command(name="stats", description="عرض إحصائيات التذاكر")
@app_commands.check(lambda i: is_admin(i.user))
async def stats_command(interaction):
    stats = get_stats(interaction.guild)
    open_count = sum(1 for c in interaction.guild.text_channels if is_ticket_channel(c))
    embed = discord.Embed(title="📊 إحصائيات التذاكر", color=discord.Color.blurple())
    embed.add_field(name="🟢 المفتوحة الآن", value=str(open_count), inline=True)
    embed.add_field(name="🔴 المغلقة", value=str(stats.get("closed", 0)), inline=True)
    embed.add_field(name="🎫 الإجمالي", value=str(stats.get("total", 0)), inline=True)
    closed = int(stats.get("closed", 0))
    avg_hours = (int(stats.get("total_duration_seconds", 0)) / closed / 3600) if closed else 0
    embed.add_field(name="⏱️ متوسط عمر التذكرة", value=f"{avg_hours:.1f} ساعة", inline=True)
    embed.add_field(name="🏆 أكثر Staff استلامًا", value=top_stat(stats.get("claimed", {}), interaction.guild), inline=False)
    embed.add_field(name="📂 أكثر نوع استخدامًا", value=top_categories(stats.get("categories", {})), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ------------------------- Lock commands -------------------------
@bot.tree.command(name="lock", description="إدارة قفل وفتح الكتابة في الروم")
@app_commands.describe(channel="الروم، اتركه فارغًا للروم الحالي")
async def slash_lock(interaction, channel: discord.TextChannel = None):
    target = channel or interaction.channel
    if isinstance(target, discord.Thread):
        await interaction.response.send_message("🧵 اختر الإجراء:", view=ChannelLockView(target.id, interaction.user.id), ephemeral=True); return
    if not isinstance(target, discord.TextChannel):
        await interaction.response.send_message("❌ هذا ليس Text Channel أو Thread.", ephemeral=True); return
    if not can_manage_lock(interaction.user, target):
        await interaction.response.send_message("❌ تحتاج Manage Channels أو صلاحية Admin.", ephemeral=True); return
    if not bot_can_manage_lock(target):
        await interaction.response.send_message("❌ البوت يحتاج Manage Channels أو Administrator.", ephemeral=True); return
    await interaction.response.send_message(f"⚙️ **إدارة {target.mention}**\n\nاختر الحالة:", view=ChannelLockView(target.id, interaction.user.id), ephemeral=True)


@bot.tree.command(name="unlock", description="فتح الكتابة في الروم")
@app_commands.describe(channel="الروم، اتركه فارغًا للروم الحالي")
async def slash_unlock(interaction, channel: discord.TextChannel = None):
    await perform_unlock(interaction, channel or interaction.channel, interaction.user)


@bot.command(name="lock")
async def prefix_lock(ctx):
    if await perform_lock_prefix(ctx, True):
        try: await ctx.message.delete()
        except discord.HTTPException: pass


@bot.command(name="unlock")
async def prefix_unlock(ctx):
    if await perform_lock_prefix(ctx, False):
        try: await ctx.message.delete()
        except discord.HTTPException: pass


async def perform_lock_prefix(ctx, locked):
    target = ctx.channel
    if not is_lockable_channel(target): return False
    if not can_manage_lock(ctx.author, target):
        await ctx.send("❌ ما عندك الصلاحية.", delete_after=5); return False
    if not bot_can_manage_lock(target):
        await ctx.send("❌ البوت يحتاج الصلاحية المناسبة.", delete_after=5); return False
    success = await (lock_any_channel(target) if locked else unlock_any_channel(target))
    if success: await send_lock_result(target, ctx.author, locked)
    return success


@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.strip().casefold()
    if content in {"قفل", "lock"} and is_lockable_channel(message.channel):
        if can_manage_lock(message.author, message.channel) and bot_can_manage_lock(message.channel):
            if await lock_any_channel(message.channel):
                try: await message.delete()
                except discord.HTTPException: pass
                await send_lock_result(message.channel, message.author, True)
        return
    if content in {"فتح", "unlock"} and is_lockable_channel(message.channel):
        if can_manage_lock(message.author, message.channel) and bot_can_manage_lock(message.channel):
            if await unlock_any_channel(message.channel):
                try: await message.delete()
                except discord.HTTPException: pass
                await send_lock_result(message.channel, message.author, False)
        return
    await bot.process_commands(message)


@tasks.loop(hours=1)
async def auto_cleanup():
    now = datetime.now(timezone.utc)
    for guild in bot.guilds:
        category = get_ticket_category(guild)
        if not category: continue
        for channel in list(category.text_channels):
            if not is_ticket_channel(channel): continue
            try:
                last_message = None
                async for message in channel.history(limit=1): last_message = message
                last_activity = last_message.created_at if last_message else channel.created_at
                max_idle = int(get_setting(guild, "auto_close_days", 7)) * 86400
                if (now - last_activity).total_seconds() >= max_idle:
                    await close_ticket_channel(channel, bot.user)
                    await asyncio.sleep(1)
            except (discord.NotFound, discord.Forbidden): continue
            except Exception as e: print(f"❌ Auto Cleanup Error: {e}")


@auto_cleanup.before_loop
async def before_auto_cleanup():
    await bot.wait_until_ready()


_views_registered = False
_commands_synced = False


@bot.event
async def on_ready():
    global _views_registered, _commands_synced
    if not _commands_synced:
        try:
            synced = await bot.tree.sync()
            print(f"✅ تمت مزامنة {len(synced)} من أوامر Slash.")
            _commands_synced = True
        except Exception as e: print(f"❌ تعذر مزامنة Slash: {e}")
    if not _views_registered:
        bot.add_view(OpenTicketView())
        bot.add_view(TicketActionView())
        _views_registered = True
        print("✅ تم تسجيل Persistent Views.")
    if not auto_cleanup.is_running():
        auto_cleanup.start()
        print("✅ تم تشغيل Auto Cleanup.")
    print(f"🤖 Logged in as {bot.user} (ID: {bot.user.id})")
    print("✅ البوت جاهز ويعمل.")


@bot.tree.error
async def on_app_command_error(interaction, error):
    print(f"❌ App Command Error: {error}")
    message = "❌ هذا الأمر للإداريين فقط. تحتاج Administrator أو رتبة `skibidi admin`." if isinstance(error, app_commands.CheckFailure) else "❌ صار خطأ غير متوقع أثناء تنفيذ الأمر."
    try:
        if interaction.response.is_done(): await interaction.followup.send(message, ephemeral=True)
        else: await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException: pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
        await ctx.send("❌ ما عندك الصلاحية لاستخدام هذا الأمر.", delete_after=5); return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ ناقصك معلومات في الأمر.", delete_after=5); return
    if isinstance(error, commands.BadArgument):
        await ctx.send("❌ فيه معلومة غير صحيحة في الأمر.", delete_after=5); return
    print(f"❌ Command Error: {error}")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("❌ لم يتم العثور على TOKEN. أضفه في Environment Variables.")
    keep_alive()
    bot.run(TOKEN)
