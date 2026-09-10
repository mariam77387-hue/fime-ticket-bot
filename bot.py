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


# =========================================================
# الإعدادات الأساسية
# =========================================================

TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", "8080"))
CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "embed_title": "نظام التذاكر 🎫",
    "embed_description": "اضغط على الزر تحت لفتح تذكرة جديدة والتواصل مع فريق الإدارة.",
    "embed_color": "5865F2",

    "category_name": "Tickets",
    "staff_role_name": "Staff",
    "admin_role_name": "skibidi admin",
    "log_channel_name": "ticket-logs",

    "auto_close_days": 7,

    "guilds": {}
}


# =========================================================
# إدارة الإعدادات
# =========================================================

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return deepcopy(DEFAULT_CONFIG)

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        loaded = deepcopy(DEFAULT_CONFIG)

        if isinstance(data, dict):
            for key, value in data.items():
                if key == "guilds":
                    continue

                loaded[key] = value

            if isinstance(data.get("guilds"), dict):
                loaded["guilds"] = data["guilds"]

        return loaded

    except (json.JSONDecodeError, OSError) as error:
        print(f"⚠️ تعذر قراءة config.json: {error}")
        print("⚠️ سيتم استخدام الإعدادات الافتراضية.")

        return deepcopy(DEFAULT_CONFIG)


config = load_config()


def save_config():
    """
    حفظ آمن نسبيًا:
    يكتب إلى ملف مؤقت ثم يستبدله بالملف الأصلي.
    """
    temp_file = f"{CONFIG_FILE}.tmp"

    try:
        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, CONFIG_FILE)

    except OSError as error:
        print(f"❌ تعذر حفظ config.json: {error}")

        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass


def get_guild_config(guild_id: int):
    """
    كل إعدادات السيرفر تكون داخل guilds.
    مع الحفاظ على الإعدادات القديمة الموجودة في المستوى العام.
    """

    guild_id = str(guild_id)

    if guild_id not in config["guilds"]:
        config["guilds"][guild_id] = {
            "next_ticket_number": 1,

            "log_channel_id": None,
            "welcome_channel_id": None,

            "embed_title": config.get(
                "embed_title",
                DEFAULT_CONFIG["embed_title"]
            ),

            "embed_description": config.get(
                "embed_description",
                DEFAULT_CONFIG["embed_description"]
            ),

            "embed_color": config.get(
                "embed_color",
                DEFAULT_CONFIG["embed_color"]
            ),

            "category_name": config.get(
                "category_name",
                DEFAULT_CONFIG["category_name"]
            ),

            "staff_role_name": config.get(
                "staff_role_name",
                DEFAULT_CONFIG["staff_role_name"]
            ),

            "admin_role_name": config.get(
                "admin_role_name",
                DEFAULT_CONFIG["admin_role_name"]
            ),

            "log_channel_name": config.get(
                "log_channel_name",
                DEFAULT_CONFIG["log_channel_name"]
            ),

            "auto_close_days": config.get(
                "auto_close_days",
                DEFAULT_CONFIG["auto_close_days"]
            )
        }

        save_config()

    guild_cfg = config["guilds"][guild_id]

    defaults = {
        "next_ticket_number": 1,
        "log_channel_id": None,
        "welcome_channel_id": None,

        "embed_title": DEFAULT_CONFIG["embed_title"],
        "embed_description": DEFAULT_CONFIG["embed_description"],
        "embed_color": DEFAULT_CONFIG["embed_color"],

        "category_name": DEFAULT_CONFIG["category_name"],
        "staff_role_name": DEFAULT_CONFIG["staff_role_name"],
        "admin_role_name": DEFAULT_CONFIG["admin_role_name"],
        "log_channel_name": DEFAULT_CONFIG["log_channel_name"],

        "auto_close_days": DEFAULT_CONFIG["auto_close_days"]
    }

    changed = False

    for key, value in defaults.items():
        if key not in guild_cfg:
            guild_cfg[key] = value
            changed = True

    if changed:
        save_config()

    return guild_cfg


def get_setting(guild: discord.Guild, key):
    guild_cfg = get_guild_config(guild.id)
    return guild_cfg.get(
        key,
        DEFAULT_CONFIG.get(key)
    )


def set_setting(guild: discord.Guild, key, value):
    guild_cfg = get_guild_config(guild.id)
    guild_cfg[key] = value
    save_config()


def get_next_ticket_number(guild: discord.Guild):
    guild_cfg = get_guild_config(guild.id)

    number = guild_cfg.get(
        "next_ticket_number",
        1
    )

    guild_cfg["next_ticket_number"] = number + 1

    save_config()

    return number


# =========================================================
# أنواع التذاكر
# =========================================================

TICKET_CATEGORIES = [
    {
        "label": "دعم فني",
        "value": "support",
        "emoji": "🛠️",
        "description": "مشاكل تقنية أو دعم عام"
    },
    {
        "label": "استفسار عن الشراء",
        "value": "purchase",
        "emoji": "🛒",
        "description": "أسئلة قبل أو بعد الشراء"
    },
    {
        "label": "شكوى",
        "value": "complaint",
        "emoji": "⚠️",
        "description": "الإبلاغ عن مشكلة أو شكوى"
    },
    {
        "label": "استفسار عام",
        "value": "inquiry",
        "emoji": "❓",
        "description": "أي سؤال عام آخر"
    }
]


def get_category_label(value):
    for category in TICKET_CATEGORIES:
        if category["value"] == value:
            return f'{category["emoji"]} {category["label"]}'

    return value


# =========================================================
# الرتب
# =========================================================

MEMBER_ROLE_NAME = "member"
BOT_ROLE_NAME = "Bot"


# =========================================================
# الترحيب
# =========================================================

WELCOME_MESSAGE_TEMPLATE = (
    "👋 منور/ه مرحبا بك في 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞🌀\n"
    "{mention} |\n"
    "~\n"
    "👋 Welcome to 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞 🌀."
)


# =========================================================
# كلمات Lock / Unlock
# =========================================================

LOCK_TRIGGER_WORDS = {
    "قفل",
    "lock",
    "فتح",
    "unlock",
    "!lock",
    "!unlock"
}


# =========================================================
# Discord Bot
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.message_content = True
intents.bans = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None
)


# =========================================================
# Flask / Render
# =========================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot is alive!"


@web_app.route("/healthz")
def healthz():
    return {
        "status": "ok",
        "discord": bot.is_ready()
    }


def run_web_server():
    web_app.run(
        host="0.0.0.0",
        port=PORT
    )


def keep_alive():
    import threading

    thread = threading.Thread(
        target=run_web_server,
        daemon=True
    )

    thread.start()


# =========================================================
# أدوات الرتب والإدارة
# =========================================================

def normalize_name(value):
    if not value:
        return ""

    return " ".join(
        str(value).strip().lower().split()
    )


def get_staff_role(guild: discord.Guild):
    role_name = get_setting(
        guild,
        "staff_role_name"
    )

    return discord.utils.find(
        lambda role: normalize_name(role.name)
        == normalize_name(role_name),
        guild.roles
    )


def get_admin_role(guild: discord.Guild):
    role_name = get_setting(
        guild,
        "admin_role_name"
    )

    return discord.utils.find(
        lambda role: normalize_name(role.name)
        == normalize_name(role_name),
        guild.roles
    )


def is_admin(member: discord.Member):
    if member.guild_permissions.administrator:
        return True

    role = get_admin_role(member.guild)

    if role is None:
        return False

    return role in member.roles


def is_staff(member: discord.Member):
    if is_admin(member):
        return True

    role = get_staff_role(member.guild)

    if role is None:
        return False

    return role in member.roles


def admin_check():
    async def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False

        return is_admin(ctx.author)

    return commands.check(predicate)


# =========================================================
# أدوات القنوات
# =========================================================

def get_ticket_category(guild: discord.Guild):
    category_name = get_setting(
        guild,
        "category_name"
    )

    return discord.utils.find(
        lambda category:
        normalize_name(category.name)
        == normalize_name(category_name),
        guild.categories
    )


def get_log_channel(guild: discord.Guild):
    channel_name = get_setting(
        guild,
        "log_channel_name"
    )

    return discord.utils.find(
        lambda channel:
        normalize_name(channel.name)
        == normalize_name(channel_name),
        guild.text_channels
    )


def get_configured_log_channel(guild: discord.Guild):
    guild_config = get_guild_config(guild.id)

    channel_id = guild_config.get(
        "log_channel_id"
    )

    if channel_id:
        channel = guild.get_channel(channel_id)

        if isinstance(
            channel,
            discord.TextChannel
        ):
            return channel

    return get_log_channel(guild)


def get_configured_welcome_channel(guild: discord.Guild):
    guild_config = get_guild_config(guild.id)

    channel_id = guild_config.get(
        "welcome_channel_id"
    )

    if not channel_id:
        return None

    channel = guild.get_channel(channel_id)

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return channel

    return None


# =========================================================
# Ticket Helpers
# =========================================================

def is_ticket_channel(channel):
    return (
        isinstance(
            channel,
            discord.TextChannel
        )
        and channel.topic
        and "ticket_id:" in channel.topic
    )


def get_ticket_owner_id(channel):
    if not channel.topic:
        return None

    for part in channel.topic.split("|"):
        part = part.strip()

        if part.startswith("opener_id:"):
            try:
                return int(
                    part.split(":", 1)[1]
                )
            except ValueError:
                return None

    return None


def get_ticket_category_value(channel):
    if not channel.topic:
        return None

    for part in channel.topic.split("|"):
        part = part.strip()

        if part.startswith("category:"):
            return part.split(":", 1)[1]

    return None


def get_ticket_claimed_id(channel):
    if not channel.topic:
        return None

    for part in channel.topic.split("|"):
        part = part.strip()

        if part.startswith("claimed_id:"):
            try:
                return int(
                    part.split(":", 1)[1]
                )
            except ValueError:
                return None

    return None


def update_ticket_topic(
    channel,
    owner_id=None,
    category_value=None,
    claimed_id=None,
    keep_claimed=True
):
    current_owner = owner_id
    current_category = category_value

    if current_owner is None:
        current_owner = get_ticket_owner_id(
            channel
        )

    if current_category is None:
        current_category = get_ticket_category_value(
            channel
        )

    if claimed_id is None and keep_claimed:
        claimed_id = get_ticket_claimed_id(
            channel
        )

    parts = [
        f"ticket_id:{channel.id}",
        f"opener_id:{current_owner}",
        f"category:{current_category}"
    ]

    if claimed_id:
        parts.append(
            f"claimed_id:{claimed_id}"
        )

    return " | ".join(parts)


def is_in_ticket_category(channel):
    category = get_ticket_category(
        channel.guild
    )

    return (
        category is not None
        and getattr(
            channel,
            "category_id",
            None
        ) == category.id
    )


def find_open_ticket(
    guild: discord.Guild,
    user_id: int
):
    for channel in guild.text_channels:
        if not is_ticket_channel(channel):
            continue

        if get_ticket_owner_id(channel) == user_id:
            return channel

    return None


# =========================================================
# Transcript
# =========================================================

async def build_transcript(
    channel: discord.TextChannel
):
    lines = []

    try:
        async for message in channel.history(
            limit=5000,
            oldest_first=True
        ):
            timestamp = message.created_at.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

            author = (
                f"{message.author} "
                f"({message.author.id})"
            )

            content = (
                message.content.strip()
                if message.content
                else ""
            )

            if not content:
                content = "[بدون نص]"

            lines.append(
                f"[{timestamp}] "
                f"{author}: {content}"
            )

            for attachment in message.attachments:
                lines.append(
                    f"    مرفق: {attachment.url}"
                )

    except discord.HTTPException as error:
        lines.append(
            f"[Transcript Error] {error}"
        )

    if not lines:
        lines.append(
            "لا توجد رسائل في التذكرة."
        )

    buffer = io.BytesIO(
        "\n".join(lines).encode(
            "utf-8",
            errors="replace"
        )
    )

    buffer.seek(0)

    return discord.File(
        buffer,
        filename=f"{channel.name}-transcript.txt"
    )


# =========================================================
# Logs
# =========================================================

async def send_event_log(
    guild,
    title,
    color,
    description=None,
    fields=None,
    file=None
):
    try:
        log_channel = get_configured_log_channel(
            guild
        )

        if log_channel is None:
            return False

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(
                timezone.utc
            )
        )

        if description:
            embed.description = description[:4096]

        if fields:
            for name, value, inline in fields:
                safe_value = (
                    str(value)
                    if value not in (None, "")
                    else "—"
                )

                embed.add_field(
                    name=str(name)[:256],
                    value=safe_value[:1024],
                    inline=inline
                )

        if file:
            await log_channel.send(
                embed=embed,
                file=file
            )
        else:
            await log_channel.send(
                embed=embed
            )

        return True

    except discord.Forbidden:
        print(
            f"❌ لا توجد صلاحية إرسال Logs "
            f"في {guild.name}"
        )

    except discord.HTTPException as error:
        print(
            f"❌ خطأ HTTP في Logs: {error}"
        )

    except Exception as error:
        print(
            f"❌ خطأ غير متوقع في Logs: {error}"
        )

    return False


async def send_ticket_log(
    guild,
    title,
    description,
    color=discord.Color.blurple(),
    file=None
):
    return await send_event_log(
        guild,
        title,
        color,
        description=description,
        file=file
    )


# =========================================================
# إغلاق التذكرة
# =========================================================

async def close_ticket_channel(
    channel: discord.TextChannel,
    closer
):
    guild = channel.guild

    owner_id = get_ticket_owner_id(
        channel
    )

    category_value = get_ticket_category_value(
        channel
    )

    owner_text = (
        f"<@{owner_id}>"
        if owner_id
        else "غير معروف"
    )

    category_text = (
        get_category_label(
            category_value
        )
        if category_value
        else "غير معروف"
    )

    closer_text = (
        closer.mention
        if hasattr(
            closer,
            "mention"
        )
        else str(closer)
    )

    try:
        transcript = await build_transcript(
            channel
        )

        await send_ticket_log(
            guild,
            "🔒 تم إغلاق تذكرة",
            (
                f"**الروم:** {channel.mention}\n"
                f"**صاحب التذكرة:** {owner_text}\n"
                f"**النوع:** {category_text}\n"
                f"**أغلقها:** {closer_text}"
            ),
            discord.Color.red(),
            transcript
        )

    except Exception as error:
        print(
            f"❌ Transcript Error: {error}"
        )

    try:
        await channel.send(
            "🔒 سيتم حذف التذكرة خلال **5 ثوانٍ**..."
        )

    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass

    await asyncio.sleep(5)

    try:
        await channel.delete(
            reason=f"Ticket closed by {closer}"
        )

    except discord.NotFound:
        pass

    except discord.Forbidden:
        print(
            f"❌ لا أستطيع حذف {channel.name}"
        )

    except discord.HTTPException as error:
        print(
            f"❌ Ticket Delete Error: {error}"
        )


# =========================================================
# Modal
# =========================================================

class TicketReasonModal(
    discord.ui.Modal,
    title="سبب فتح التذكرة"
):
    reason = discord.ui.TextInput(
        label="سبب فتح التذكرة",
        style=discord.TextStyle.paragraph,
        placeholder="اشرح مشكلتك أو طلبك بالتفصيل...",
        max_length=1000,
        required=True
    )

    def __init__(
        self,
        category_value
    ):
        super().__init__()

        self.category_value = (
            category_value
        )

    async def on_submit(
        self,
        interaction
    ):
        await create_ticket_channel(
            interaction,
            self.category_value,
            str(self.reason)
        )


# =========================================================
# Ticket Select
# =========================================================

class TicketCategorySelect(
    discord.ui.Select
):
    def __init__(self):
        options = []

        for category in TICKET_CATEGORIES:
            options.append(
                discord.SelectOption(
                    label=category["label"],
                    value=category["value"],
                    emoji=category["emoji"],
                    description=category["description"]
                )
            )

        super().__init__(
            placeholder="اختر نوع التذكرة...",
            options=options
        )

    async def callback(
        self,
        interaction
    ):
        await interaction.response.send_modal(
            TicketReasonModal(
                self.values[0]
            )
        )


class TicketCategoryView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=180
        )

        self.add_item(
            TicketCategorySelect()
        )


# =========================================================
# إنشاء التذكرة
# =========================================================

async def create_ticket_channel(
    interaction,
    category_value,
    reason
):
    guild = interaction.guild
    member = interaction.user

    if guild is None:
        await interaction.response.send_message(
            "❌ لا يمكن فتح تذكرة خارج السيرفر.",
            ephemeral=True
        )
        return

    existing = find_open_ticket(
        guild,
        member.id
    )

    if existing:
        await interaction.response.send_message(
            f"❌ عندك تذكرة مفتوحة بالفعل: "
            f"{existing.mention}",
            ephemeral=True
        )
        return

    category = get_ticket_category(
        guild
    )

    if category is None:
        try:
            category = await guild.create_category(
                get_setting(
                    guild,
                    "category_name"
                ),
                reason="إنشاء كاتيجوري التذاكر"
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ البوت لا يملك صلاحية إنشاء الكاتيجوري.",
                ephemeral=True
            )
            return

        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ حدث خطأ أثناء إنشاء كاتيجوري التذاكر.",
                ephemeral=True
            )
            return

    number = get_next_ticket_number(
        guild
    )

    channel_name = (
        f"ticket-{number:04d}"
    )

    overwrites = {
        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        member:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
    }

    if guild.me:
        overwrites[guild.me] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )
        )

    staff_role = get_staff_role(
        guild
    )

    if staff_role:
        overwrites[staff_role] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        )

    admin_role = get_admin_role(
        guild
    )

    if admin_role:
        overwrites[admin_role] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True,
                manage_messages=True
            )
        )

    try:
        ticket_channel = (
            await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket opened by {member}"
            )
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ ما قدرت أنشئ التذكرة. "
            "تأكد من صلاحيات البوت وترتيب الرتب.",
            ephemeral=True
        )
        return

    except discord.HTTPException as error:
        print(
            f"❌ Create Ticket Error: {error}"
        )

        await interaction.response.send_message(
            "❌ حدث خطأ أثناء إنشاء التذكرة.",
            ephemeral=True
        )
        return

    topic = (
        f"ticket_id:{ticket_channel.id} | "
        f"opener_id:{member.id} | "
        f"category:{category_value}"
    )

    try:
        await ticket_channel.edit(
            topic=topic
        )

    except discord.HTTPException:
        pass

    try:
        embed_color = int(
            get_setting(
                guild,
                "embed_color"
            ),
            16
        )

    except (
        ValueError,
        TypeError
    ):
        embed_color = 0x5865F2

    embed = discord.Embed(
        title=f"🎫 تذكرة #{number:04d}",
        description=(
            f"أهلاً {member.mention} 👋\n\n"
            "انتظر أحد أعضاء فريق الإدارة لمساعدتك."
        ),
        color=embed_color
    )

    embed.add_field(
        name="📂 النوع",
        value=get_category_label(
            category_value
        ),
        inline=True
    )

    embed.add_field(
        name="👤 صاحب التذكرة",
        value=member.mention,
        inline=True
    )

    embed.add_field(
        name="👨‍💼 الموظف المسؤول",
        value="لم يتم الاستلام بعد",
        inline=False
    )

    embed.add_field(
        name="📝 السبب",
        value=reason[:1024],
        inline=False
    )

    embed.set_footer(
        text="يمكنك استخدام الأزرار أسفل الرسالة."
    )

    mention_roles = []

    if staff_role:
        mention_roles.append(
            staff_role.mention
        )

    if admin_role:
        mention_roles.append(
            admin_role.mention
        )

    content = (
        " ".join(mention_roles)
        if mention_roles
        else None
    )

    try:
        await ticket_channel.send(
            content=content,
            embed=embed,
            view=TicketActionView()
        )

    except discord.HTTPException as error:
        print(
            f"❌ Ticket Message Error: {error}"
        )

    await send_ticket_log(
        guild,
        "🎫 تم فتح تذكرة",
        (
            f"**الروم:** {ticket_channel.mention}\n"
            f"**صاحب التذكرة:** {member.mention}\n"
            f"**النوع:** "
            f"{get_category_label(category_value)}"
        ),
        discord.Color.green()
    )

    await interaction.response.send_message(
        f"✅ تم إنشاء تذكرتك: "
        f"{ticket_channel.mention}",
        ephemeral=True
    )


# =========================================================
# زر فتح التذكرة
# =========================================================

class OpenTicketView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="فتح تذكرة جديدة 🎫",
        style=discord.ButtonStyle.green,
        custom_id="open_ticket_button"
    )
    async def open_ticket(
        self,
        interaction,
        button
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ هذا الزر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        existing = find_open_ticket(
            interaction.guild,
            interaction.user.id
        )

        if existing:
            await interaction.response.send_message(
                f"❌ عندك تذكرة مفتوحة بالفعل: "
                f"{existing.mention}",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "اختر نوع التذكرة:",
            view=TicketCategoryView(),
            ephemeral=True
        )


# =========================================================
# Ticket Actions
# =========================================================

class TicketActionView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=None
        )

    @discord.ui.button(
        label="استلام التذكرة 👤",
        style=discord.ButtonStyle.blurple,
        custom_id="claim_ticket_button"
    )
    async def claim_ticket(
        self,
        interaction,
        button
    ):
        if not isinstance(
            interaction.user,
            discord.Member
        ):
            return

        if not is_staff(
            interaction.user
        ):
            await interaction.response.send_message(
                "❌ هذا الزر للموظفين فقط.",
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not is_ticket_channel(
            channel
        ):
            await interaction.response.send_message(
                "❌ هذا الروم ليس تذكرة.",
                ephemeral=True
            )
            return

        claimed_id = get_ticket_claimed_id(
            channel
        )

        if claimed_id:
            if claimed_id == interaction.user.id:
                await interaction.response.send_message(
                    "أنت مستلم هذه التذكرة بالفعل.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ هذه التذكرة مستلمة من "
                    f"<@{claimed_id}>.",
                    ephemeral=True
                )

            return

        message = interaction.message

        if not message.embeds:
            await interaction.response.send_message(
                "❌ تعذر تعديل رسالة التذكرة.",
                ephemeral=True
            )
            return

        embed = message.embeds[0]

        try:
            embed.set_field_at(
                2,
                name="👨‍💼 الموظف المسؤول",
                value=interaction.user.mention,
                inline=False
            )

        except IndexError:
            embed.add_field(
                name="👨‍💼 الموظف المسؤول",
                value=interaction.user.mention,
                inline=False
            )

        new_topic = update_ticket_topic(
            channel,
            claimed_id=interaction.user.id
        )

        try:
            await channel.edit(
                topic=new_topic
            )

        except discord.HTTPException:
            pass

        button.disabled = True
        button.label = "تم الاستلام ✅"

        await interaction.response.edit_message(
            embed=embed,
            view=self
        )

        try:
            await channel.send(
                f"👤 **تم استلام التذكرة بواسطة "
                f"{interaction.user.mention}**"
            )

        except discord.HTTPException:
            pass

        await send_ticket_log(
            interaction.guild,
            "👤 تم استلام تذكرة",
            (
                f"**التذكرة:** {channel.mention}\n"
                f"**الموظف:** {interaction.user.mention}"
            ),
            discord.Color.blurple()
        )

    @discord.ui.button(
        label="إغلاق التذكرة 🔒",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket_button"
    )
    async def close_ticket(
        self,
        interaction,
        button
    ):
        if not isinstance(
            interaction.user,
            discord.Member
        ):
            return

        if not is_staff(
            interaction.user
        ):
            await interaction.response.send_message(
                "❌ إغلاق التذاكر متاح لفريق الإدارة فقط.",
                ephemeral=True
            )
            return

        if not is_ticket_channel(
            interaction.channel
        ):
            await interaction.response.send_message(
                "❌ هذا الروم ليس تذكرة.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "هل أنت متأكد من إغلاق التذكرة؟",
            view=ConfirmCloseView(),
            ephemeral=True
        )


# =========================================================
# تأكيد الإغلاق
# =========================================================

class ConfirmCloseView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=60
        )

    @discord.ui.button(
        label="تأكيد الإغلاق ✅",
        style=discord.ButtonStyle.red
    )
    async def confirm(
        self,
        interaction,
        button
    ):
        if not isinstance(
            interaction.user,
            discord.Member
        ):
            return

        if not is_staff(
            interaction.user
        ):
            await interaction.response.send_message(
                "❌ إغلاق التذاكر متاح لفريق الإدارة فقط.",
                ephemeral=True
            )
            return

        if not is_ticket_channel(
            interaction.channel
        ):
            await interaction.response.send_message(
                "❌ التذكرة غير موجودة.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "🔒 جارٍ إغلاق التذكرة...",
            ephemeral=True
        )

        await close_ticket_channel(
            interaction.channel,
            interaction.user
        )

    @discord.ui.button(
        label="إلغاء ❌",
        style=discord.ButtonStyle.grey
    )
    async def cancel(
        self,
        interaction,
        button
    ):
        await interaction.response.edit_message(
            content="✅ تم إلغاء الإغلاق.",
            view=None
        )


# =========================================================
# Setup
# =========================================================

@bot.command(
    name="setup"
)
@admin_check()
async def setup_cmd(ctx):
    guild = ctx.guild

    color = get_setting(
        guild,
        "embed_color"
    )

    try:
        color = int(
            color,
            16
        )
    except (
        ValueError,
        TypeError
    ):
        color = 0x5865F2

    embed = discord.Embed(
        title=get_setting(
            guild,
            "embed_title"
        ),
        description=get_setting(
            guild,
            "embed_description"
        ),
        color=color
    )

    embed.set_footer(
        text="نظام التذاكر"
    )

    await ctx.send(
        embed=embed,
        view=OpenTicketView()
    )

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


# =========================================================
# Embed Command
# =========================================================

@bot.command(
    name="embed"
)
@admin_check()
async def embed_cmd(
    ctx,
    channel: discord.TextChannel
):
    prompt = await ctx.send(
        "تمام ✅\n"
        "أرسل الآن نص الرسالة كامل.\n\n"
        "أول سطر = العنوان\n"
        "والباقي = المحتوى\n\n"
        "⏰ لديك 5 دقائق."
    )

    def check(message):
        return (
            message.author.id
            == ctx.author.id
            and message.channel.id
            == ctx.channel.id
        )

    try:
        reply = await bot.wait_for(
            "message",
            check=check,
            timeout=300
        )

    except asyncio.TimeoutError:
        await prompt.edit(
            content="⏰ انتهى الوقت."
        )
        return

    lines = reply.content.split("\n")

    title = (
        lines[0].strip()
        if lines
        else None
    )

    description = (
        "\n".join(
            lines[1:]
        ).strip()
        if len(lines) > 1
        else ""
    )

    if not description:
        description = title
        title = None

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.gold()
    )

    try:
        await channel.send(
            embed=embed
        )

    except discord.Forbidden:
        await ctx.send(
            "❌ البوت لا يملك صلاحية الإرسال في هذا الروم.",
            delete_after=8
        )
        return

    await ctx.send(
        f"✅ تم نشر الـEmbed في "
        f"{channel.mention}"
    )

    try:
        await ctx.message.delete()
        await reply.delete()
        await prompt.delete()
    except discord.HTTPException:
        pass


# =========================================================
# Ticket Config
# =========================================================

@bot.group(
    name="ticketconfig",
    invoke_without_command=True
)
@admin_check()
async def ticketconfig(ctx):
    guild = ctx.guild

    embed = discord.Embed(
        title="⚙️ إعدادات نظام التذاكر",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="العنوان",
        value=str(
            get_setting(
                guild,
                "embed_title"
            )
        )[:1024],
        inline=False
    )

    embed.add_field(
        name="الوصف",
        value=str(
            get_setting(
                guild,
                "embed_description"
            )
        )[:1024],
        inline=False
    )

    embed.add_field(
        name="اللون",
        value=f'#{get_setting(guild, "embed_color")}',
        inline=True
    )

    embed.add_field(
        name="الكاتيجوري",
        value=get_setting(
            guild,
            "category_name"
        ),
        inline=True
    )

    embed.add_field(
        name="رتبة الموظفين",
        value=get_setting(
            guild,
            "staff_role_name"
        ),
        inline=True
    )

    embed.add_field(
        name="رتبة الإدارة",
        value=get_setting(
            guild,
            "admin_role_name"
        ),
        inline=True
    )

    embed.add_field(
        name="روم Logs",
        value=get_setting(
            guild,
            "log_channel_name"
        ),
        inline=True
    )

    embed.add_field(
        name="الإغلاق التلقائي",
        value=f'{get_setting(guild, "auto_close_days")} يوم',
        inline=True
    )

    embed.set_footer(
        text="استخدم !ticketconfig help"
    )

    await ctx.send(
        embed=embed
    )


@ticketconfig.command(
    name="help"
)
@admin_check()
async def ticketconfig_help(ctx):
    await ctx.send(
        "**⚙️ أوامر إعدادات التذاكر:**\n\n"

        "`!ticketconfig title <النص>`\n"
        "تغيير عنوان رسالة التذاكر.\n\n"

        "`!ticketconfig desc <النص>`\n"
        "تغيير وصف رسالة التذاكر.\n\n"

        "`!ticketconfig color <HEX>`\n"
        "مثال: `5865F2`\n\n"

        "`!ticketconfig category <الاسم>`\n"
        "تغيير اسم كاتيجوري التذاكر.\n\n"

        "`!ticketconfig staffrole <الاسم>`\n"
        "تغيير رتبة الموظفين.\n\n"

        "`!ticketconfig adminrole <الاسم>`\n"
        "تغيير رتبة الإدارة.\n\n"

        "`!ticketconfig logchannel <الاسم>`\n"
        "تغيير اسم روم Logs الاحتياطي.\n\n"

        "`!ticketconfig autoclose <الأيام>`\n"
        "تغيير مدة الإغلاق التلقائي."
    )


@ticketconfig.command(
    name="title"
)
@admin_check()
async def tc_title(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "embed_title",
        value
    )

    await ctx.send(
        "✅ تم تحديث العنوان."
    )


@ticketconfig.command(
    name="desc"
)
@admin_check()
async def tc_desc(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "embed_description",
        value
    )

    await ctx.send(
        "✅ تم تحديث الوصف."
    )


@ticketconfig.command(
    name="color"
)
@admin_check()
async def tc_color(
    ctx,
    value
):
    value = (
        value.strip()
        .replace("#", "")
        .upper()
    )

    if len(value) != 6:
        await ctx.send(
            "❌ استخدم لون HEX من 6 خانات."
        )
        return

    try:
        int(value, 16)
    except ValueError:
        await ctx.send(
            "❌ كود اللون غير صحيح."
        )
        return

    set_setting(
        ctx.guild,
        "embed_color",
        value
    )

    await ctx.send(
        f"✅ تم تحديث اللون إلى `#{value}`"
    )


@ticketconfig.command(
    name="category"
)
@admin_check()
async def tc_category(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "category_name",
        value
    )

    await ctx.send(
        f"✅ تم تحديث الكاتيجوري إلى `{value}`"
    )


@ticketconfig.command(
    name="staffrole"
)
@admin_check()
async def tc_staffrole(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "staff_role_name",
        value
    )

    await ctx.send(
        f"✅ تم تحديث رتبة الموظفين إلى `{value}`"
    )


@ticketconfig.command(
    name="adminrole"
)
@admin_check()
async def tc_adminrole(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "admin_role_name",
        value
    )

    await ctx.send(
        f"✅ تم تحديث رتبة الإدارة إلى `{value}`"
    )


@ticketconfig.command(
    name="logchannel"
)
@admin_check()
async def tc_logchannel(
    ctx,
    *,
    value
):
    set_setting(
        ctx.guild,
        "log_channel_name",
        value
    )

    await ctx.send(
        f"✅ تم تحديث روم Logs الاحتياطي إلى `{value}`"
    )


@ticketconfig.command(
    name="autoclose"
)
@admin_check()
async def tc_autoclose(
    ctx,
    days: int
):
    if days < 1:
        await ctx.send(
            "❌ لازم يكون العدد 1 أو أكثر."
        )
        return

    if days > 365:
        await ctx.send(
            "❌ الحد الأعلى هو 365 يوم."
        )
        return

    set_setting(
        ctx.guild,
        "auto_close_days",
        days
    )

    await ctx.send(
        f"✅ سيتم إغلاق التذاكر الخاملة "
        f"بعد {days} يوم."
    )


# =========================================================
# Lock / Unlock
# =========================================================

def is_lockable_channel(channel):
    return isinstance(
        channel,
        (
            discord.TextChannel,
            discord.Thread
        )
    )


def can_manage_lock(
    member: discord.Member,
    channel
):
    if is_admin(member):
        return True

    if isinstance(
        channel,
        discord.Thread
    ):
        return member.guild_permissions.manage_threads

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return member.guild_permissions.manage_channels

    return False


def bot_can_manage_lock(channel):
    me = channel.guild.me

    if me is None:
        return False

    if me.guild_permissions.administrator:
        return True

    if isinstance(
        channel,
        discord.Thread
    ):
        return me.guild_permissions.manage_threads

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return me.guild_permissions.manage_channels

    return False


async def lock_text_channel(channel):
    everyone = (
        channel.guild.default_role
    )

    overwrite = channel.overwrites_for(
        everyone
    )

    overwrite.view_channel = True
    overwrite.send_messages = False

    try:
        await channel.set_permissions(
            everyone,
            overwrite=overwrite,
            reason="Lock: read only"
        )

        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException as error:
        print(
            f"❌ Text Lock Error: {error}"
        )
        return False


async def unlock_text_channel(channel):
    everyone = (
        channel.guild.default_role
    )

    overwrite = channel.overwrites_for(
        everyone
    )

    overwrite.view_channel = True
    overwrite.send_messages = None

    try:
        await channel.set_permissions(
            everyone,
            overwrite=overwrite,
            reason="Unlock: open chat"
        )

        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException as error:
        print(
            f"❌ Text Unlock Error: {error}"
        )
        return False


async def lock_thread(thread):
    try:
        if thread.archived:
            await thread.edit(
                archived=False,
                reason="Preparing thread for lock"
            )

        await thread.edit(
            locked=True,
            reason="Lock Thread"
        )

        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException as error:
        print(
            f"❌ Thread Lock Error: {error}"
        )
        return False


async def unlock_thread(thread):
    try:
        await thread.edit(
            locked=False,
            archived=False,
            reason="Unlock Thread"
        )

        return True

    except discord.Forbidden:
        return False

    except discord.HTTPException as error:
        print(
            f"❌ Thread Unlock Error: {error}"
        )
        return False


async def lock_any_channel(channel):
    if isinstance(
        channel,
        discord.Thread
    ):
        return await lock_thread(
            channel
        )

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return await lock_text_channel(
            channel
        )

    return False


async def unlock_any_channel(channel):
    if isinstance(
        channel,
        discord.Thread
    ):
        return await unlock_thread(
            channel
        )

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return await unlock_text_channel(
            channel
        )

    return False


def channel_type_name(channel):
    if isinstance(
        channel,
        discord.Thread
    ):
        return "Thread"

    if isinstance(
        channel,
        discord.TextChannel
    ):
        return "Text Channel"

    return "Channel"


async def send_lock_result(
    channel,
    user,
    locked
):
    if locked:
        message = (
            f"🔒 **تم قفل "
            f"{channel_type_name(channel)}**\n"
            f"👤 بواسطة: {user.mention}"
        )

        title = "🔒 قفل روم"
        color = discord.Color.red()

    else:
        message = (
            f"🔓 **تم فتح "
            f"{channel_type_name(channel)}**\n"
            f"👤 بواسطة: {user.mention}"
        )

        title = "🔓 فتح روم"
        color = discord.Color.green()

    try:
        await channel.send(
            message,
            delete_after=6
        )
    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass

    await send_event_log(
        channel.guild,
        title,
        color,
        fields=[
            (
                "النوع",
                channel_type_name(channel),
                True
            ),
            (
                "الروم/الـThread",
                getattr(
                    channel,
                    "mention",
                    channel.name
                ),
                True
            ),
            (
                "بواسطة",
                user.mention,
                True
            )
        ]
    )


async def perform_lock(
    interaction,
    channel,
    user,
    response=True
):
    if not is_lockable_channel(
        channel
    ):
        if response:
            await interaction.response.send_message(
                "❌ هذا النظام يعمل فقط على Text Channels و Threads.",
                ephemeral=True
            )
        return False

    if not can_manage_lock(
        user,
        channel
    ):
        needed = (
            "Manage Threads"
            if isinstance(
                channel,
                discord.Thread
            )
            else "Manage Channels"
        )

        if response:
            await interaction.response.send_message(
                f"❌ تحتاج صلاحية **{needed}**.",
                ephemeral=True
            )

        return False

    if not bot_can_manage_lock(
        channel
    ):
        if response:
            await interaction.response.send_message(
                "❌ البوت نفسه لا يملك الصلاحية الكافية.",
                ephemeral=True
            )

        return False

    success = await lock_any_channel(
        channel
    )

    if not success:
        if response:
            await interaction.response.send_message(
                "❌ فشل قفل الروم. تأكد من صلاحيات البوت.",
                ephemeral=True
            )

        return False

    if response:
        await interaction.response.send_message(
            f"🔒 تم قفل "
            f"**{channel_type_name(channel)}** "
            f"{channel.mention}.\n"
            "👁️ الروم ما زال ظاهرًا، لكن الكتابة مقفلة.",
            ephemeral=True
        )

    await send_lock_result(
        channel,
        user,
        True
    )

    return True


async def perform_unlock(
    interaction,
    channel,
    user,
    response=True
):
    if not is_lockable_channel(
        channel
    ):
        if response:
            await interaction.response.send_message(
                "❌ هذا النظام يعمل فقط على Text Channels و Threads.",
                ephemeral=True
            )

        return False

    if not can_manage_lock(
        user,
        channel
    ):
        needed = (
            "Manage Threads"
            if isinstance(
                channel,
                discord.Thread
            )
            else "Manage Channels"
        )

        if response:
            await interaction.response.send_message(
                f"❌ تحتاج صلاحية **{needed}**.",
                ephemeral=True
            )

        return False

    if not bot_can_manage_lock(
        channel
    ):
        if response:
            await interaction.response.send_message(
                "❌ البوت نفسه لا يملك الصلاحية الكافية.",
                ephemeral=True
            )

        return False

    success = await unlock_any_channel(
        channel
    )

    if not success:
        if response:
            await interaction.response.send_message(
                "❌ فشل فتح الروم. تأكد من صلاحيات البوت.",
                ephemeral=True
            )

        return False

    if response:
        await interaction.response.send_message(
            f"🔓 تم فتح "
            f"**{channel_type_name(channel)}** "
            f"{channel.mention}.\n"
            "💬 الكتابة مفتوحة الآن.",
            ephemeral=True
        )

    await send_lock_result(
        channel,
        user,
        False
    )

    return True


# =========================================================
# Channel Lock View
# =========================================================

class ChannelLockView(
    discord.ui.View
):
    def __init__(
        self,
        channel_id,
        owner_id
    ):
        super().__init__(
            timeout=120
        )

        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(
        self,
        interaction
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return False

        return True

    def get_channel(self, guild):
        return guild.get_channel(
            self.channel_id
        )

    @discord.ui.button(
        label="قفل الكتابة",
        emoji="🔒",
        style=discord.ButtonStyle.danger
    )
    async def read_only(
        self,
        interaction,
        button
    ):
        channel = self.get_channel(
            interaction.guild
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ ما قدرت ألقى الروم.",
                ephemeral=True
            )
            return

        await perform_lock(
            interaction,
            channel,
            interaction.user
        )

    @discord.ui.button(
        label="فتح الكلام",
        emoji="💬",
        style=discord.ButtonStyle.success
    )
    async def open_chat(
        self,
        interaction,
        button
    ):
        channel = self.get_channel(
            interaction.guild
        )

        if channel is None:
            await interaction.response.send_message(
                "❌ ما قدرت ألقى الروم.",
                ephemeral=True
            )
            return

        await perform_unlock(
            interaction,
            channel,
            interaction.user
        )

    @discord.ui.button(
        label="إلغاء",
        emoji="✖️",
        style=discord.ButtonStyle.secondary
    )
    async def cancel(
        self,
        interaction,
        button
    ):
        await interaction.response.edit_message(
            content="تم إلغاء العملية.",
            view=None
        )


# =========================================================
# Threads
# =========================================================

def get_active_threads(guild):
    threads = list(
        guild.threads
    )

    unique = {}

    for thread in threads:
        unique[thread.id] = thread

    threads = list(
        unique.values()
    )

    threads.sort(
        key=lambda thread:
        thread.created_at
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    return threads


class ThreadSelect(
    discord.ui.Select
):
    def __init__(
        self,
        threads,
        owner_id
    ):
        self.owner_id = owner_id

        options = []

        for thread in threads[:25]:
            parent_name = (
                thread.parent.name
                if thread.parent
                else "Unknown"
            )

            description = (
                f"#{parent_name} • "
                f"{'مقفول' if thread.locked else 'مفتوح'}"
            )[:100]

            options.append(
                discord.SelectOption(
                    label=thread.name[:100],
                    description=description,
                    value=str(thread.id),
                    emoji="🧵"
                )
            )

        super().__init__(
            placeholder="اختر الـThread...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        thread_id = int(
            self.values[0]
        )

        thread = (
            interaction.guild.get_thread(
                thread_id
            )
        )

        if thread is None:
            try:
                thread = (
                    await interaction.guild.fetch_channel(
                        thread_id
                    )
                )
            except (
                discord.NotFound,
                discord.Forbidden,
                discord.HTTPException
            ):
                thread = None

        if not isinstance(
            thread,
            discord.Thread
        ):
            await interaction.response.send_message(
                "❌ ما قدرت ألقى الـThread.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content=(
                f"🧵 **{thread.name}**\n"
                f"الروم الأب: "
                f"{thread.parent.mention if thread.parent else 'غير معروف'}\n\n"
                "اختر الإجراء:"
            ),
            view=ThreadActionView(
                thread.id,
                self.owner_id
            )
        )


class ThreadSelectorView(
    discord.ui.View
):
    def __init__(
        self,
        guild,
        owner_id
    ):
        super().__init__(
            timeout=180
        )

        self.owner_id = owner_id

        threads = get_active_threads(
            guild
        )

        if threads:
            self.add_item(
                ThreadSelect(
                    threads,
                    owner_id
                )
            )

    @discord.ui.button(
        label="تحديث القائمة",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def refresh(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        threads = get_active_threads(
            interaction.guild
        )

        if not threads:
            await interaction.response.edit_message(
                content=(
                    "🧵 **اختيار Thread**\n\n"
                    "❌ ما فيه Threads نشطة حاليًا."
                ),
                view=None
            )
            return

        await interaction.response.edit_message(
            content=(
                "🧵 **اختيار Thread**\n\n"
                "اختر الـThread الذي تريد التحكم فيه:"
            ),
            view=ThreadSelectorView(
                interaction.guild,
                self.owner_id
            )
        )

    @discord.ui.button(
        label="إلغاء",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def cancel(
        self,
        interaction,
        button
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content="تم إلغاء العملية.",
            view=None
        )


class ThreadActionView(
    discord.ui.View
):
    def __init__(
        self,
        thread_id,
        owner_id
    ):
        super().__init__(
            timeout=120
        )

        self.thread_id = thread_id
        self.owner_id = owner_id

    async def interaction_check(
        self,
        interaction
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return False

        return True

    async def get_thread(
        self,
        guild
    ):
        thread = guild.get_thread(
            self.thread_id
        )

        if thread:
            return thread

        try:
            channel = (
                await guild.fetch_channel(
                    self.thread_id
                )
            )

            if isinstance(
                channel,
                discord.Thread
            ):
                return channel

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass

        return None

    @discord.ui.button(
        label="قفل الـThread",
        emoji="🔒",
        style=discord.ButtonStyle.danger
    )
    async def lock_thread_button(
        self,
        interaction,
        button
    ):
        thread = await self.get_thread(
            interaction.guild
        )

        if thread is None:
            await interaction.response.send_message(
                "❌ الـThread غير موجود.",
                ephemeral=True
            )
            return

        await perform_lock(
            interaction,
            thread,
            interaction.user
        )

    @discord.ui.button(
        label="فتح الـThread",
        emoji="💬",
        style=discord.ButtonStyle.success
    )
    async def unlock_thread_button(
        self,
        interaction,
        button
    ):
        thread = await self.get_thread(
            interaction.guild
        )

        if thread is None:
            await interaction.response.send_message(
                "❌ الـThread غير موجود.",
                ephemeral=True
            )
            return

        await perform_unlock(
            interaction,
            thread,
            interaction.user
        )

    @discord.ui.button(
        label="رجوع",
        emoji="↩️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def back(
        self,
        interaction,
        button
    ):
        await interaction.response.edit_message(
            content=(
                "🧵 **اختيار Thread**\n\n"
                "اختر الـThread الذي تريد التحكم فيه:"
            ),
            view=ThreadSelectorView(
                interaction.guild,
                self.owner_id
            )
        )


# =========================================================
# Slash /lock
# =========================================================

@bot.tree.command(
    name="lock",
    description="إدارة قفل وفتح الكتابة في الروم"
)
@app_commands.describe(
    channel="الروم الذي تريد التحكم فيه"
)
async def slash_lock(
    interaction,
    channel: discord.TextChannel = None
):
    target = (
        channel
        or interaction.channel
    )

    if target is None:
        await interaction.response.send_message(
            "❌ ما قدرت أحدد الروم.",
            ephemeral=True
        )
        return

    if isinstance(
        target,
        discord.Thread
    ):
        await interaction.response.send_message(
            "🧵 **Thread**\n\n"
            "اختر الإجراء الذي تريده:",
            view=ThreadActionView(
                target.id,
                interaction.user.id
            ),
            ephemeral=True
        )
        return

    if not isinstance(
        target,
        discord.TextChannel
    ):
        await interaction.response.send_message(
            "❌ هذا ليس Text Channel أو Thread.",
            ephemeral=True
        )
        return

    if not can_manage_lock(
        interaction.user,
        target
    ):
        await interaction.response.send_message(
            "❌ تحتاج صلاحية **Manage Channels**.",
            ephemeral=True
        )
        return

    if not bot_can_manage_lock(
        target
    ):
        await interaction.response.send_message(
            "❌ البوت يحتاج `Manage Channels` أو `Administrator`.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        f"⚙️ **إدارة الروم {target.mention}**\n\n"
        "اختر الحالة المطلوبة:\n\n"
        "🔒 **قفل الكتابة** — الروم يبقى ظاهرًا، لكن الأعضاء لا يستطيعون الكلام.\n"
        "💬 **فتح الكلام** — يسمح للأعضاء بالكلام من جديد.",
        view=ChannelLockView(
            target.id,
            interaction.user.id
        ),
        ephemeral=True
    )


# =========================================================
# Slash /unlock
# =========================================================

@bot.tree.command(
    name="unlock",
    description="فتح الكتابة في الروم"
)
@app_commands.describe(
    channel="الروم الذي تريد فتحه"
)
async def slash_unlock(
    interaction,
    channel: discord.TextChannel = None
):
    target = (
        channel
        or interaction.channel
    )

    if target is None:
        await interaction.response.send_message(
            "❌ ما قدرت أحدد الروم.",
            ephemeral=True
        )
        return

    await perform_unlock(
        interaction,
        target,
        interaction.user
    )


# =========================================================
# Slash /threadlock
# =========================================================

@bot.tree.command(
    name="threadlock",
    description="اختيار Thread وقفل أو فتح الكتابة فيه"
)
async def slash_threadlock(
    interaction
):
    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return

    if not is_admin(
        interaction.user
    ) and not interaction.user.guild_permissions.manage_threads:
        await interaction.response.send_message(
            "❌ تحتاج صلاحية **Manage Threads**.",
            ephemeral=True
        )
        return

    threads = get_active_threads(
        interaction.guild
    )

    if not threads:
        await interaction.response.send_message(
            "🧵 **اختيار Thread**\n\n"
            "❌ ما فيه Threads نشطة حاليًا.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "🧵 **اختيار Thread**\n\n"
        "اختر الـThread الذي تريد التحكم فيه:",
        view=ThreadSelectorView(
            interaction.guild,
            interaction.user.id
        ),
        ephemeral=True
    )


# =========================================================
# Log / Welcome Selectors
# =========================================================

class LogChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        owner_id
    ):
        super().__init__(
            placeholder="اختر روم الـLogs...",
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1
        )

        self.owner_id = owner_id

    async def callback(
        self,
        interaction
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        selected = self.values[0]

        guild_config = get_guild_config(
            interaction.guild.id
        )

        guild_config[
            "log_channel_id"
        ] = selected.id

        save_config()

        me = interaction.guild.me

        permission_text = ""

        if me:
            permissions = selected.permissions_for(
                me
            )

            if not permissions.view_channel:
                permission_text = (
                    "\n⚠️ البوت لا يملك View Channel."
                )

            elif not permissions.send_messages:
                permission_text = (
                    "\n⚠️ البوت لا يملك Send Messages."
                )

        await interaction.response.edit_message(
            content=(
                f"✅ تم تحديد {selected.mention} "
                f"كروم الـLogs الرسمي."
                f"{permission_text}"
            ),
            view=None
        )


class LogChannelSelectView(
    discord.ui.View
):
    def __init__(
        self,
        owner_id
    ):
        super().__init__(
            timeout=120
        )

        self.add_item(
            LogChannelSelect(
                owner_id
            )
        )


class WelcomeChannelSelect(
    discord.ui.ChannelSelect
):
    def __init__(
        self,
        owner_id
    ):
        super().__init__(
            placeholder="اختر روم الترحيب...",
            channel_types=[
                discord.ChannelType.text
            ],
            min_values=1,
            max_values=1
        )

        self.owner_id = owner_id

    async def callback(
        self,
        interaction
    ):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        selected = self.values[0]

        guild_config = get_guild_config(
            interaction.guild.id
        )

        guild_config[
            "welcome_channel_id"
        ] = selected.id

        save_config()

        me = interaction.guild.me

        warning = ""

        if me:
            permissions = selected.permissions_for(
                me
            )

            missing = []

            if not permissions.view_channel:
                missing.append(
                    "View Channel"
                )

            if not permissions.send_messages:
                missing.append(
                    "Send Messages"
                )

            if missing:
                warning = (
                    "\n⚠️ الصلاحيات الناقصة: "
                    + ", ".join(missing)
                )

        await interaction.response.edit_message(
            content=(
                f"✅ تم تحديد {selected.mention} "
                f"كروم الترحيب."
                f"{warning}"
            ),
            view=None
        )


class WelcomeChannelSelectView(
    discord.ui.View
):
    def __init__(
        self,
        owner_id
    ):
        super().__init__(
            timeout=120
        )

        self.add_item(
            WelcomeChannelSelect(
                owner_id
            )
        )


# =========================================================
# Slash /log
# =========================================================

@bot.tree.command(
    name="log",
    description="تحديد روم تسجيل أحداث السيرفر"
)
async def slash_log(
    interaction
):
    if not is_admin(
        interaction.user
    ):
        await interaction.response.send_message(
            "❌ هذا الأمر للإداريين فقط.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "📋 اختر الروم الذي تريده ليكون روم الـLogs:",
        view=LogChannelSelectView(
            interaction.user.id
        ),
        ephemeral=True
    )


# =========================================================
# Slash /welcome
# =========================================================

@bot.tree.command(
    name="welcome",
    description="تحديد روم الترحيب بالأعضاء الجدد"
)
async def slash_welcome(
    interaction
):
    if not is_admin(
        interaction.user
    ):
        await interaction.response.send_message(
            "❌ هذا الأمر للإداريين فقط.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "👋 اختر روم الترحيب بالأعضاء الجدد:",
        view=WelcomeChannelSelectView(
            interaction.user.id
        ),
        ephemeral=True
    )


# =========================================================
# Auto Roles
# =========================================================

async def assign_auto_role(
    member: discord.Member
):
    guild = member.guild

    role_name = (
        BOT_ROLE_NAME
        if member.bot
        else MEMBER_ROLE_NAME
    )

    role = discord.utils.find(
        lambda r:
        normalize_name(r.name)
        == normalize_name(role_name),
        guild.roles
    )

    if role is None:
        print(
            f"⚠️ لم يتم العثور على رتبة "
            f"'{role_name}' في {guild.name}"
        )

        await send_event_log(
            guild,
            "⚠️ رتبة تلقائية غير موجودة",
            discord.Color.orange(),
            description=(
                f"لم يتم العثور على رتبة "
                f"`{role_name}`."
            ),
            fields=[
                (
                    "العضو",
                    member.mention,
                    True
                )
            ]
        )

        return False

    me = guild.me

    if me is None:
        return False

    if role >= me.top_role:
        print(
            f"⚠️ رتبة البوت ليست أعلى من "
            f"'{role_name}' في {guild.name}"
        )

        await send_event_log(
            guild,
            "⚠️ تعذر إعطاء رتبة تلقائية",
            discord.Color.orange(),
            description=(
                f"رتبة البوت يجب أن تكون أعلى من "
                f"`{role_name}`."
            ),
            fields=[
                (
                    "العضو",
                    member.mention,
                    True
                )
            ]
        )

        return False

    try:
        await member.add_roles(
            role,
            reason="إعطاء رتبة تلقائية عند الدخول"
        )

        return True

    except discord.Forbidden:
        print(
            f"❌ لا صلاحية لإعطاء "
            f"'{role_name}' في {guild.name}"
        )

    except discord.HTTPException as error:
        print(
            f"❌ Auto Role Error: {error}"
        )

    return False


# =========================================================
# Welcome
# =========================================================

async def send_welcome_message(
    member: discord.Member
):
    guild = member.guild

    channel = get_configured_welcome_channel(
        guild
    )

    if channel is None:
        print(
            f"⚠️ لم يتم تحديد روم ترحيب "
            f"صالح في {guild.name}"
        )

        return False

    me = guild.me

    if me is None:
        return False

    permissions = channel.permissions_for(
        me
    )

    missing = []

    if not permissions.view_channel:
        missing.append(
            "View Channel"
        )

    if not permissions.send_messages:
        missing.append(
            "Send Messages"
        )

    if missing:
        print(
            f"❌ صلاحيات الترحيب ناقصة في "
            f"{guild.name}: "
            f"{', '.join(missing)}"
        )

        await send_event_log(
            guild,
            "⚠️ تعذر إرسال الترحيب",
            discord.Color.orange(),
            description=(
                f"لا يستطيع البوت إرسال الترحيب "
                f"في {channel.mention}."
            ),
            fields=[
                (
                    "الصلاحيات الناقصة",
                    ", ".join(missing),
                    False
                )
            ]
        )

        return False

    content = (
        WELCOME_MESSAGE_TEMPLATE.format(
            mention=member.mention
        )
    )

    try:
        await channel.send(
            content
        )

        return True

    except discord.Forbidden:
        print(
            f"❌ Forbidden Welcome "
            f"in {guild.name}"
        )

    except discord.HTTPException as error:
        print(
            f"❌ Welcome HTTP Error: {error}"
        )

    return False


# =========================================================
# Member Join
# =========================================================

@bot.event
async def on_member_join(
    member
):
    try:
        await assign_auto_role(
            member
        )
    except Exception as error:
        print(
            f"❌ Auto Role Error: {error}"
        )

    if not member.bot:
        try:
            await send_welcome_message(
                member
            )
        except Exception as error:
            print(
                f"❌ Welcome Error: {error}"
            )

    await send_event_log(
        member.guild,
        "👋 دخول عضو جديد",
        discord.Color.green(),
        fields=[
            (
                "العضو",
                member.mention,
                True
            ),
            (
                "النوع",
                "Bot"
                if member.bot
                else "Member",
                True
            ),
            (
                "الـID",
                str(member.id),
                True
            )
        ]
    )


# =========================================================
# Ban / Unban
# =========================================================

@bot.event
async def on_member_ban(
    guild,
    user
):
    await send_event_log(
        guild,
        "🔨 حظر عضو",
        discord.Color.red(),
        fields=[
            (
                "العضو",
                f"{user} ({user.mention})",
                True
            ),
            (
                "الـID",
                str(user.id),
                True
            )
        ]
    )


@bot.event
async def on_member_unban(
    guild,
    user
):
    await send_event_log(
        guild,
        "🔓 فك حظر عضو",
        discord.Color.green(),
        fields=[
            (
                "العضو",
                f"{user} ({user.mention})",
                True
            ),
            (
                "الـID",
                str(user.id),
                True
            )
        ]
    )


# =========================================================
# Message Logs
# =========================================================

@bot.event
async def on_message_delete(
    message
):
    if message.guild is None:
        return

    if message.author.bot:
        return

    content = (
        message.content or ""
    ).strip()

    if content.lower() in LOCK_TRIGGER_WORDS:
        return

    if content.startswith(
        bot.command_prefix
    ):
        return

    preview = (
        content
        if content
        else "[بدون نص / مرفق فقط]"
    )

    await send_event_log(
        message.guild,
        "🗑️ حذف رسالة",
        discord.Color.dark_red(),
        fields=[
            (
                "العضو",
                message.author.mention,
                True
            ),
            (
                "الروم",
                message.channel.mention,
                True
            ),
            (
                "المحتوى",
                preview[:500],
                False
            )
        ]
    )


@bot.event
async def on_message_edit(
    before,
    after
):
    if before.guild is None:
        return

    if before.author.bot:
        return

    if before.content == after.content:
        return

    await send_event_log(
        before.guild,
        "✏️ تعديل رسالة",
        discord.Color.orange(),
        fields=[
            (
                "العضو",
                before.author.mention,
                True
            ),
            (
                "الروم",
                before.channel.mention,
                True
            ),
            (
                "قبل",
                (before.content or "—")[:400],
                False
            ),
            (
                "بعد",
                (after.content or "—")[:400],
                False
            )
        ]
    )


# =========================================================
# Channel Logs
# =========================================================

@bot.event
async def on_guild_channel_create(
    channel
):
    if is_in_ticket_category(
        channel
    ):
        return

    await send_event_log(
        channel.guild,
        "📁 إنشاء روم",
        discord.Color.green(),
        fields=[
            (
                "الروم",
                getattr(
                    channel,
                    "mention",
                    channel.name
                ),
                True
            ),
            (
                "النوع",
                str(channel.type),
                True
            )
        ]
    )


@bot.event
async def on_guild_channel_delete(
    channel
):
    if is_in_ticket_category(
        channel
    ):
        return

    await send_event_log(
        channel.guild,
        "🗑️ حذف روم",
        discord.Color.dark_red(),
        fields=[
            (
                "اسم الروم",
                channel.name,
                True
            ),
            (
                "النوع",
                str(channel.type),
                True
            )
        ]
    )


@bot.event
async def on_guild_channel_update(
    before,
    after
):
    if is_in_ticket_category(
        after
    ):
        return

    changes = []

    if before.name != after.name:
        changes.append(
            f"**الاسم:** "
            f"`{before.name}` ➜ "
            f"`{after.name}`"
        )

    before_topic = getattr(
        before,
        "topic",
        None
    )

    after_topic = getattr(
        after,
        "topic",
        None
    )

    if before_topic != after_topic:
        changes.append(
            "**تم تغيير وصف/موضوع الروم.**"
        )

    if not changes:
        return

    await send_event_log(
        after.guild,
        "⚙️ تعديل روم",
        discord.Color.blue(),
        description="\n".join(changes),
        fields=[
            (
                "الروم",
                getattr(
                    after,
                    "mention",
                    after.name
                ),
                True
            )
        ]
    )


# =========================================================
# Role Logs
# =========================================================

@bot.event
async def on_guild_role_create(
    role
):
    await send_event_log(
        role.guild,
        "🟢 إنشاء Role",
        discord.Color.green(),
        fields=[
            (
                "الرتبة",
                role.mention,
                True
            )
        ]
    )


@bot.event
async def on_guild_role_delete(
    role
):
    await send_event_log(
        role.guild,
        "🔴 حذف Role",
        discord.Color.red(),
        fields=[
            (
                "اسم الرتبة",
                role.name,
                True
            )
        ]
    )


@bot.event
async def on_guild_role_update(
    before,
    after
):
    if (
        before.name == after.name
        and before.color == after.color
    ):
        return

    changes = []

    if before.name != after.name:
        changes.append(
            f"**الاسم:** "
            f"`{before.name}` ➜ "
            f"`{after.name}`"
        )

    if before.color != after.color:
        changes.append(
            f"**اللون:** "
            f"`{before.color}` ➜ "
            f"`{after.color}`"
        )

    await send_event_log(
        after.guild,
        "⚙️ تعديل Role",
        discord.Color.blue(),
        description="\n".join(changes),
        fields=[
            (
                "الرتبة",
                after.mention,
                True
            )
        ]
    )


# =========================================================
# Voice Logs
# =========================================================

@bot.event
async def on_voice_state_update(
    member,
    before,
    after
):
    if (
        before.channel is None
        and after.channel is not None
    ):
        await send_event_log(
            member.guild,
            "🔊 دخول Voice",
            discord.Color.green(),
            fields=[
                (
                    "العضو",
                    member.mention,
                    True
                ),
                (
                    "الروم",
                    after.channel.mention,
                    True
                )
            ]
        )

    elif (
        before.channel is not None
        and after.channel is None
    ):
        await send_event_log(
            member.guild,
            "🔇 خروج Voice",
            discord.Color.dark_grey(),
            fields=[
                (
                    "العضو",
                    member.mention,
                    True
                ),
                (
                    "الروم",
                    before.channel.mention,
                    True
                )
            ]
        )

    elif (
        before.channel is not None
        and after.channel is not None
        and before.channel.id
        != after.channel.id
    ):
        await send_event_log(
            member.guild,
            "🔄 انتقال Voice",
            discord.Color.blue(),
            fields=[
                (
                    "العضو",
                    member.mention,
                    True
                ),
                (
                    "من",
                    before.channel.mention,
                    True
                ),
                (
                    "إلى",
                    after.channel.mention,
                    True
                )
            ]
        )


# =========================================================
# Prefix Lock / Unlock
# =========================================================

@bot.command(
    name="lock"
)
async def prefix_lock(
    ctx
):
    target = ctx.channel

    if not is_lockable_channel(
        target
    ):
        return

    if not can_manage_lock(
        ctx.author,
        target
    ):
        await ctx.send(
            "❌ ما عندك صلاحية قفل هذا الروم.",
            delete_after=5
        )
        return

    if not bot_can_manage_lock(
        target
    ):
        await ctx.send(
            "❌ البوت يحتاج الصلاحية المناسبة.",
            delete_after=5
        )
        return

    success = await lock_any_channel(
        target
    )

    if success:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        await send_lock_result(
            target,
            ctx.author,
            True
        )


@bot.command(
    name="unlock"
)
async def prefix_unlock(
    ctx
):
    target = ctx.channel

    if not is_lockable_channel(
        target
    ):
        return

    if not can_manage_lock(
        ctx.author,
        target
    ):
        await ctx.send(
            "❌ ما عندك صلاحية فتح هذا الروم.",
            delete_after=5
        )
        return

    if not bot_can_manage_lock(
        target
    ):
        await ctx.send(
            "❌ البوت يحتاج الصلاحية المناسبة.",
            delete_after=5
        )
        return

    success = await unlock_any_channel(
        target
    )

    if success:
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        await send_lock_result(
            target,
            ctx.author,
            False
        )


# =========================================================
# on_message
# =========================================================

@bot.event
async def on_message(
    message
):
    if message.author.bot:
        return

    content = (
        message.content
        .strip()
        .lower()
    )

    channel = message.channel

    if content in {
        "قفل",
        "lock"
    }:
        if is_lockable_channel(
            channel
        ):
            if can_manage_lock(
                message.author,
                channel
            ):
                if bot_can_manage_lock(
                    channel
                ):
                    success = await lock_any_channel(
                        channel
                    )

                    if success:
                        try:
                            await message.delete()
                        except discord.HTTPException:
                            pass

                        await send_lock_result(
                            channel,
                            message.author,
                            True
                        )

        return

    if content in {
        "فتح",
        "unlock"
    }:
        if is_lockable_channel(
            channel
        ):
            if can_manage_lock(
                message.author,
                channel
            ):
                if bot_can_manage_lock(
                    channel
                ):
                    success = await unlock_any_channel(
                        channel
                    )

                    if success:
                        try:
                            await message.delete()
                        except discord.HTTPException:
                            pass

                        await send_lock_result(
                            channel,
                            message.author,
                            False
                        )

        return

    await bot.process_commands(
        message
    )


# =========================================================
# Bot Status
# =========================================================

@bot.tree.command(
    name="botstatus",
    description="فحص إعدادات وصلاحيات البوت في السيرفر"
)
async def botstatus(
    interaction
):
    if not is_admin(
        interaction.user
    ):
        await interaction.response.send_message(
            "❌ هذا الأمر للإداريين فقط.",
            ephemeral=True
        )
        return

    guild = interaction.guild
    me = guild.me

    embed = discord.Embed(
        title="🩺 حالة البوت",
        color=discord.Color.green()
    )

    category = get_ticket_category(
        guild
    )

    staff_role = get_staff_role(
        guild
    )

    admin_role = get_admin_role(
        guild
    )

    log_channel = get_configured_log_channel(
        guild
    )

    welcome_channel = get_configured_welcome_channel(
        guild
    )

    embed.add_field(
        name="🎫 Ticket Category",
        value=(
            category.mention
            if category
            else "❌ غير موجودة"
        ),
        inline=False
    )

    embed.add_field(
        name="👥 Staff Role",
        value=(
            staff_role.mention
            if staff_role
            else "❌ غير موجودة"
        ),
        inline=True
    )

    embed.add_field(
        name="👑 Admin Role",
        value=(
            admin_role.mention
            if admin_role
            else "❌ غير موجودة"
        ),
        inline=True
    )

    embed.add_field(
        name="📋 Logs",
        value=(
            log_channel.mention
            if log_channel
            else "❌ غير محدد"
        ),
        inline=True
    )

    embed.add_field(
        name="👋 Welcome",
        value=(
            welcome_channel.mention
            if welcome_channel
            else "❌ غير محدد"
        ),
        inline=True
    )

    if me:
        required = {
            "View Channel":
                me.guild_permissions.view_channel,

            "Send Messages":
                me.guild_permissions.send_messages,

            "Manage Channels":
                me.guild_permissions.manage_channels,

            "Manage Roles":
                me.guild_permissions.manage_roles,

            "Manage Messages":
                me.guild_permissions.manage_messages,

            "Manage Threads":
                me.guild_permissions.manage_threads
        }

        missing = [
            name
            for name, value in required.items()
            if not value
        ]

        if missing:
            permission_text = (
                "⚠️ ناقصة:\n"
                + "\n".join(
                    f"• {permission}"
                    for permission in missing
                )
            )
        else:
            permission_text = (
                "✅ الصلاحيات الأساسية تبدو جيدة."
            )

    else:
        permission_text = (
            "❌ تعذر العثور على عضو البوت."
        )

    embed.add_field(
        name="🛡️ صلاحيات البوت",
        value=permission_text[:1024],
        inline=False
    )

    embed.add_field(
        name="🔢 رقم التذكرة القادم",
        value=str(
            get_guild_config(
                guild.id
            )["next_ticket_number"]
        ),
        inline=True
    )

    embed.add_field(
        name="⏰ Auto Close",
        value=f'{get_setting(guild, "auto_close_days")} يوم',
        inline=True
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# =========================================================
# Auto Close
# =========================================================

@tasks.loop(hours=1)
async def auto_cleanup():
    now = datetime.now(
        timezone.utc
    )

    for guild in list(
        bot.guilds
    ):
        try:
            category = get_ticket_category(
                guild
            )

            if category is None:
                continue

            auto_close_days = get_setting(
                guild,
                "auto_close_days"
            )

            try:
                auto_close_days = int(
                    auto_close_days
                )
            except (
                ValueError,
                TypeError
            ):
                auto_close_days = 7

            max_idle_seconds = (
                auto_close_days
                * 24
                * 60
                * 60
            )

            for channel in list(
                category.text_channels
            ):
                if not is_ticket_channel(
                    channel
                ):
                    continue

                try:
                    last_message = None

                    async for message in channel.history(
                        limit=1
                    ):
                        last_message = message

                    if last_message:
                        last_activity = (
                            last_message.created_at
                        )
                    else:
                        last_activity = (
                            channel.created_at
                        )

                    idle_seconds = (
                        now - last_activity
                    ).total_seconds()

                    if (
                        idle_seconds
                        >= max_idle_seconds
                    ):
                        await send_event_log(
                            guild,
                            "⏰ إغلاق تلقائي لتذكرة",
                            discord.Color.orange(),
                            fields=[
                                (
                                    "التذكرة",
                                    channel.mention,
                                    True
                                ),
                                (
                                    "المدة",
                                    f"{auto_close_days} يوم",
                                    True
                                )
                            ]
                        )

                        await close_ticket_channel(
                            channel,
                            bot.user
                        )

                        await asyncio.sleep(1)

                except discord.NotFound:
                    continue

                except discord.Forbidden:
                    continue

                except Exception as error:
                    print(
                        f"❌ Auto Cleanup Error: {error}"
                    )

        except Exception as error:
            print(
                f"❌ Guild Cleanup Error "
                f"({guild.id}): {error}"
            )


@auto_cleanup.before_loop
async def before_auto_cleanup():
    await bot.wait_until_ready()


# =========================================================
# Ready
# =========================================================

_views_registered = False
_commands_synced = False


@bot.event
async def on_ready():
    global _views_registered
    global _commands_synced

    if not _commands_synced:
        try:
            synced = await bot.tree.sync()

            print(
                f"✅ تمت مزامنة "
                f"{len(synced)} من أوامر Slash."
            )

            _commands_synced = True

        except Exception as error:
            print(
                f"❌ تعذر مزامنة Slash: {error}"
            )

    if not _views_registered:
        bot.add_view(
            OpenTicketView()
        )

        bot.add_view(
            TicketActionView()
        )

        _views_registered = True

        print(
            "✅ تم تسجيل Persistent Views."
        )

    if not auto_cleanup.is_running():
        auto_cleanup.start()

        print(
            "✅ تم تشغيل Auto Cleanup."
        )

    print(
        f"🤖 Logged in as "
        f"{bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        f"🏠 Connected to "
        f"{len(bot.guilds)} server(s)."
    )

    print(
        "✅ البوت جاهز ويعمل."
    )


# =========================================================
# أخطاء الأوامر
# =========================================================

@bot.event
async def on_command_error(
    ctx,
    error
):
    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.CheckFailure
    ):
        await ctx.send(
            "❌ ما عندك صلاحية لاستخدام هذا الأمر.",
            delete_after=5
        )
        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):
        await ctx.send(
            "❌ ناقصك معلومات في الأمر.",
            delete_after=5
        )
        return

    if isinstance(
        error,
        commands.BadArgument
    ):
        await ctx.send(
            "❌ فيه معلومة غير صحيحة في الأمر.",
            delete_after=5
        )
        return

    if isinstance(
        error,
        commands.NoPrivateMessage
    ):
        return

    print(
        f"❌ Command Error: "
        f"{type(error).__name__}: {error}"
    )


# =========================================================
# تشغيل البوت
# =========================================================

if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "❌ لم يتم العثور على TOKEN. "
            "أضفه في Environment Variables."
        )

    keep_alive()

    print(
        "🚀 Starting Discord Bot..."
    )

    bot.run(
        TOKEN
    )