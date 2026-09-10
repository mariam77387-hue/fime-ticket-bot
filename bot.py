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

        loaded_config = deepcopy(DEFAULT_CONFIG)
        loaded_config.update(data)

        if "guilds" not in loaded_config:
            loaded_config["guilds"] = {}

        return loaded_config

    except (json.JSONDecodeError, OSError):
        print("⚠️ تعذر قراءة config.json، سيتم استخدام الإعدادات الافتراضية.")
        return deepcopy(DEFAULT_CONFIG)


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except OSError as error:
        print(f"❌ تعذر حفظ config.json: {error}")


config = load_config()


def get_guild_config(guild_id: int):
    guild_id = str(guild_id)

    if guild_id not in config["guilds"]:
        config["guilds"][guild_id] = {
            "next_ticket_number": 1,
            "log_channel_id": None,
            "welcome_channel_id": None
        }
        save_config()
        return config["guilds"][guild_id]

    # ترقية إعدادات سيرفر قديم لإضافة المفاتيح الجديدة إذا كانت ناقصة
    guild_cfg = config["guilds"][guild_id]
    changed = False

    if "next_ticket_number" not in guild_cfg:
        guild_cfg["next_ticket_number"] = 1
        changed = True

    if "log_channel_id" not in guild_cfg:
        guild_cfg["log_channel_id"] = None
        changed = True

    if "welcome_channel_id" not in guild_cfg:
        guild_cfg["welcome_channel_id"] = None
        changed = True

    if changed:
        save_config()

    return config["guilds"][guild_id]


def get_next_ticket_number(guild: discord.Guild):
    guild_config = get_guild_config(guild.id)
    number = guild_config["next_ticket_number"]
    guild_config["next_ticket_number"] = number + 1
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
# رتب الأعضاء التلقائية + رسالة الترحيب
# =========================================================

MEMBER_ROLE_NAME = "member"
BOT_ROLE_NAME = "Bot"

WELCOME_MESSAGE_TEMPLATE = (
    "👋 منور/ه مرحبا بك في 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞🌀\n"
    "{mention} |\n"
    "~\n"
    "👋 Welcome to 𝐓𝐞𝐚𝐦 𝐅𝐢𝐦𝐞 🌀."
)

# كلمات قفل/فتح المستخدمة في الرسائل النصية، تُستثنى من لوق حذف الرسائل
# حتى لا يتكرر تسجيلها مع لوق Lock/Unlock المخصص
LOCK_TRIGGER_WORDS = {"قفل", "lock", "فتح", "unlock", "!lock", "!unlock"}


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
# Flask / Render Keep Alive
# =========================================================

web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot is alive!"


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
# أدوات التذاكر
# =========================================================

def get_staff_role(guild: discord.Guild):
    return discord.utils.get(
        guild.roles,
        name=config["staff_role_name"]
    )


def get_ticket_category(guild: discord.Guild):
    return discord.utils.get(
        guild.categories,
        name=config["category_name"]
    )


def get_log_channel(guild: discord.Guild):
    return discord.utils.get(
        guild.text_channels,
        name=config["log_channel_name"]
    )


def get_configured_log_channel(guild: discord.Guild):
    """
    يرجع روم الـLogs المحدد عبر /log (بالـID) إذا كان موجودًا وصالحًا،
    وإلا يرجع للروم القديم المعتمد على الاسم (ticket-logs) للتوافق.
    """
    guild_config = get_guild_config(guild.id)
    channel_id = guild_config.get("log_channel_id")

    if channel_id:
        channel = guild.get_channel(channel_id)

        if isinstance(channel, discord.TextChannel):
            return channel

    return get_log_channel(guild)


def get_configured_welcome_channel(guild: discord.Guild):
    guild_config = get_guild_config(guild.id)
    channel_id = guild_config.get("welcome_channel_id")

    if channel_id:
        channel = guild.get_channel(channel_id)

        if isinstance(channel, discord.TextChannel):
            return channel

    return None


def is_staff(member: discord.Member):
    if member.guild_permissions.administrator:
        return True

    role = get_staff_role(member.guild)

    if role is None:
        return False

    return role in member.roles


def is_ticket_channel(channel):
    return (
        isinstance(channel, discord.TextChannel)
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
                return int(part.split(":", 1)[1])
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
                return int(part.split(":", 1)[1])
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

    if owner_id is None:
        current_owner = get_ticket_owner_id(channel)

    if category_value is None:
        current_category = get_ticket_category_value(channel)

    if claimed_id is None and keep_claimed:
        claimed_id = get_ticket_claimed_id(channel)

    parts = [
        f"ticket_id:{channel.id}",
        f"opener_id:{current_owner}",
        f"category:{current_category}"
    ]

    if claimed_id:
        parts.append(f"claimed_id:{claimed_id}")

    return " | ".join(parts)


def is_in_ticket_category(channel):
    category = get_ticket_category(channel.guild)
    return (
        category is not None
        and getattr(channel, "category_id", None) == category.id
    )


def find_open_ticket(guild: discord.Guild, user_id: int):
    for channel in guild.text_channels:
        if not is_ticket_channel(channel):
            continue

        owner_id = get_ticket_owner_id(channel)

        if owner_id == user_id:
            return channel

    return None


# =========================================================
# Transcript
# =========================================================

async def build_transcript(channel: discord.TextChannel):
    lines = []

    async for message in channel.history(
        limit=5000,
        oldest_first=True
    ):
        timestamp = message.created_at.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        author = f"{message.author} ({message.author.id})"
        content = message.content.strip()

        if not content:
            content = "[بدون نص]"

        lines.append(
            f"[{timestamp}] {author}: {content}"
        )

        if message.attachments:
            for attachment in message.attachments:
                lines.append(
                    f"    مرفق: {attachment.url}"
                )

    if not lines:
        lines.append("لا توجد رسائل في التذكرة.")

    buffer = io.BytesIO(
        "\n".join(lines).encode("utf-8")
    )

    buffer.seek(0)

    return discord.File(
        buffer,
        filename=f"{channel.name}-transcript.txt"
    )


# =========================================================
# Logs
# =========================================================

async def send_ticket_log(
    guild,
    title,
    description,
    color=discord.Color.blurple(),
    file=None
):
    log_channel = get_configured_log_channel(guild)

    if log_channel is None:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    try:
        if file:
            await log_channel.send(
                embed=embed,
                file=file
            )
        else:
            await log_channel.send(
                embed=embed
            )
    except discord.Forbidden:
        print(f"❌ لا صلاحية للإرسال في روم الـLogs بسيرفر {guild.name}")
    except discord.HTTPException as error:
        print(f"❌ خطأ في إرسال Log: {error}")
    except Exception as error:
        print(f"❌ خطأ غير متوقع في إرسال Log: {error}")


async def send_event_log(
    guild,
    title,
    color,
    description=None,
    fields=None
):
    """
    دالة عامة لإرسال Embed مرتب لأي حدث من أحداث السيرفر إلى روم الـLogs
    المحدد عبر /log. لا ترفع استثناء أبدًا حتى لا توقف بقية البوت
    إذا فشل إرسال Log واحد.
    fields: قائمة عناصر (name, value, inline)
    """
    try:
        log_channel = get_configured_log_channel(guild)

        if log_channel is None:
            return

        embed = discord.Embed(
            title=title,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )

        if description:
            embed.description = description

        if fields:
            for name, value, inline in fields:
                safe_value = str(value) if value not in (None, "") else "—"
                embed.add_field(
                    name=name,
                    value=safe_value[:1024],
                    inline=inline
                )

        await log_channel.send(embed=embed)

    except discord.Forbidden:
        print(f"❌ لا صلاحية للإرسال في روم الـLogs بسيرفر {guild.name}")
    except discord.HTTPException as error:
        print(f"❌ خطأ HTTP عند إرسال Log: {error}")
    except Exception as error:
        print(f"❌ خطأ غير متوقع عند إرسال Log: {error}")


# =========================================================
# إغلاق التذكرة
# =========================================================

async def close_ticket_channel(
    channel: discord.TextChannel,
    closer
):
    guild = channel.guild

    try:
        transcript = await build_transcript(channel)

        owner_id = get_ticket_owner_id(channel)
        category_value = get_ticket_category_value(channel)

        owner_text = (
            f"<@{owner_id}>"
            if owner_id
            else "غير معروف"
        )

        category_text = (
            get_category_label(category_value)
            if category_value
            else "غير معروف"
        )

        closer_text = (
            closer.mention
            if hasattr(closer, "mention")
            else str(closer)
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
        print(f"❌ Transcript Error: {error}")

    try:
        await channel.send(
            "🔒 سيتم حذف التذكرة خلال **5 ثوانٍ**..."
        )
    except discord.HTTPException:
        pass

    await asyncio.sleep(5)

    try:
        await channel.delete(
            reason=f"Ticket closed by {closer}"
        )
    except discord.NotFound:
        pass
    except discord.Forbidden:
        print(f"❌ لا أستطيع حذف {channel.name}")


# =========================================================
# Modal سبب التذكرة
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

    def __init__(self, category_value):
        super().__init__()
        self.category_value = category_value

    async def on_submit(self, interaction):
        await create_ticket_channel(
            interaction,
            self.category_value,
            str(self.reason)
        )


# =========================================================
# Select Menu
# =========================================================

class TicketCategorySelect(discord.ui.Select):
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

    async def callback(self, interaction):
        await interaction.response.send_modal(
            TicketReasonModal(self.values[0])
        )


class TicketCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(TicketCategorySelect())


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
        return

    existing = find_open_ticket(
        guild,
        member.id
    )

    if existing:
        await interaction.response.send_message(
            f"❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}",
            ephemeral=True
        )
        return

    category = get_ticket_category(guild)

    if category is None:
        try:
            category = await guild.create_category(
                config["category_name"],
                reason="إنشاء كاتيجوري التذاكر"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ البوت لا يملك صلاحية إنشاء الكاتيجوري.",
                ephemeral=True
            )
            return

    number = get_next_ticket_number(guild)
    channel_name = f"ticket-{number:04d}"

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),

        member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        ),

        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    staff_role = get_staff_role(guild)

    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

    try:
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Ticket opened by {member}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ ما قدرت أنشئ التذكرة. تأكد من صلاحيات البوت.",
            ephemeral=True
        )
        return

    topic = (
        f"ticket_id:{ticket_channel.id} | "
        f"opener_id:{member.id} | "
        f"category:{category_value}"
    )

    try:
        await ticket_channel.edit(topic=topic)
    except discord.HTTPException:
        pass

    try:
        embed_color = int(config["embed_color"], 16)
    except (ValueError, TypeError):
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
        value=get_category_label(category_value),
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

    mention = staff_role.mention if staff_role else None

    try:
        await ticket_channel.send(
            content=mention,
            embed=embed,
            view=TicketActionView()
        )
    except discord.HTTPException:
        pass

    await send_ticket_log(
        guild,
        "🎫 تم فتح تذكرة",
        (
            f"**الروم:** {ticket_channel.mention}\n"
            f"**صاحب التذكرة:** {member.mention}\n"
            f"**النوع:** {get_category_label(category_value)}"
        ),
        discord.Color.green()
    )

    await interaction.response.send_message(
        f"✅ تم إنشاء تذكرتك: {ticket_channel.mention}",
        ephemeral=True
    )


# =========================================================
# View فتح التذكرة
# =========================================================

class OpenTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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
        existing = find_open_ticket(
            interaction.guild,
            interaction.user.id
        )

        if existing:
            await interaction.response.send_message(
                f"❌ عندك تذكرة مفتوحة بالفعل: {existing.mention}",
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

class TicketActionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

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
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "❌ هذا الزر للموظفين فقط.",
                ephemeral=True
            )
            return

        channel = interaction.channel

        if not is_ticket_channel(channel):
            await interaction.response.send_message(
                "❌ هذا الروم ليس تذكرة.",
                ephemeral=True
            )
            return

        claimed_id = get_ticket_claimed_id(channel)

        if claimed_id:
            if claimed_id == interaction.user.id:
                await interaction.response.send_message(
                    "أنت مستلم هذه التذكرة بالفعل.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"❌ هذه التذكرة مستلمة من <@{claimed_id}>.",
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
            await channel.edit(topic=new_topic)
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
                f"👤 **تم استلام التذكرة بواسطة {interaction.user.mention}**"
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
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "❌ إغلاق التذاكر متاح لفريق الإدارة فقط.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            "هل أنت متأكد من إغلاق التذكرة؟",
            view=ConfirmCloseView(),
            ephemeral=True
        )


# =========================================================
# تأكيد إغلاق التذكرة
# =========================================================

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(
        label="تأكيد الإغلاق ✅",
        style=discord.ButtonStyle.red
    )
    async def confirm(
        self,
        interaction,
        button
    ):
        if not is_staff(interaction.user):
            await interaction.response.send_message(
                "❌ إغلاق التذاكر متاح لفريق الإدارة فقط.",
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

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_cmd(ctx):
    try:
        color = int(config["embed_color"], 16)
    except (ValueError, TypeError):
        color = 0x5865F2

    embed = discord.Embed(
        title=config["embed_title"],
        description=config["embed_description"],
        color=color
    )

    embed.set_footer(text="نظام التذاكر")

    await ctx.send(
        embed=embed,
        view=OpenTicketView()
    )

    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass


@setup_cmd.error
async def setup_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "❌ هذا الأمر للإداريين فقط.",
            delete_after=5
        )


# =========================================================
# Embed Command
# =========================================================

@bot.command(name="embed")
@commands.has_permissions(administrator=True)
async def embed_cmd(ctx, channel: discord.TextChannel):
    prompt = await ctx.send(
        "تمام ✅\n"
        "أرسل الآن نص الرسالة كامل.\n\n"
        "أول سطر = العنوان\n"
        "والباقي = المحتوى\n\n"
        "⏰ لديك 5 دقائق."
    )

    def check(message):
        return (
            message.author.id == ctx.author.id
            and message.channel.id == ctx.channel.id
        )

    try:
        reply = await bot.wait_for(
            "message",
            check=check,
            timeout=300
        )
    except asyncio.TimeoutError:
        await prompt.edit(content="⏰ انتهى الوقت.")
        return

    lines = reply.content.split("\n")

    title = lines[0].strip() if lines else None

    description = (
        "\n".join(lines[1:]).strip()
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

    await channel.send(embed=embed)

    await ctx.send(
        f"✅ تم نشر الـ Embed في {channel.mention}"
    )

    try:
        await ctx.message.delete()
        await reply.delete()
    except discord.HTTPException:
        pass


@embed_cmd.error
async def embed_cmd_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "❌ هذا الأمر للإداريين فقط.",
            delete_after=5
        )
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            "❌ الاستخدام الصحيح:\n`!embed #الروم`",
            delete_after=8
        )
    elif isinstance(error, commands.ChannelNotFound):
        await ctx.send(
            "❌ ما لقيت هذا الروم.",
            delete_after=8
        )


# =========================================================
# Ticket Config
# =========================================================

@bot.group(
    name="ticketconfig",
    invoke_without_command=True
)
@commands.has_permissions(administrator=True)
async def ticketconfig(ctx):
    embed = discord.Embed(
        title="⚙️ إعدادات نظام التذاكر",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="العنوان",
        value=config["embed_title"][:1024],
        inline=False
    )

    embed.add_field(
        name="الوصف",
        value=config["embed_description"][:1024],
        inline=False
    )

    embed.add_field(
        name="اللون",
        value=f'#{config["embed_color"]}',
        inline=True
    )

    embed.add_field(
        name="الكاتيجوري",
        value=config["category_name"],
        inline=True
    )

    embed.add_field(
        name="رتبة الموظفين",
        value=config["staff_role_name"],
        inline=True
    )

    embed.add_field(
        name="روم Logs",
        value=config["log_channel_name"],
        inline=True
    )

    embed.add_field(
        name="الإغلاق التلقائي",
        value=f'{config["auto_close_days"]} يوم',
        inline=True
    )

    embed.set_footer(
        text="استخدم !ticketconfig help"
    )

    await ctx.send(embed=embed)


@ticketconfig.command(name="help")
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
        "`!ticketconfig logchannel <الاسم>`\n"
        "تغيير روم Logs.\n\n"
        "`!ticketconfig autoclose <الأيام>`\n"
        "تغيير مدة الإغلاق التلقائي."
    )


@ticketconfig.command(name="title")
@commands.has_permissions(administrator=True)
async def tc_title(ctx, *, value):
    config["embed_title"] = value
    save_config()
    await ctx.send("✅ تم تحديث العنوان.")


@ticketconfig.command(name="desc")
@commands.has_permissions(administrator=True)
async def tc_desc(ctx, *, value):
    config["embed_description"] = value
    save_config()
    await ctx.send("✅ تم تحديث الوصف.")


@ticketconfig.command(name="color")
@commands.has_permissions(administrator=True)
async def tc_color(ctx, value):
    value = value.strip().replace("#", "").upper()

    if len(value) != 6:
        await ctx.send("❌ استخدم لون HEX من 6 خانات.")
        return

    try:
        int(value, 16)
    except ValueError:
        await ctx.send("❌ كود اللون غير صحيح.")
        return

    config["embed_color"] = value
    save_config()

    await ctx.send(
        f"✅ تم تحديث اللون إلى `#{value}`"
    )


@ticketconfig.command(name="category")
@commands.has_permissions(administrator=True)
async def tc_category(ctx, *, value):
    config["category_name"] = value
    save_config()
    await ctx.send(
        f"✅ تم تحديث الكاتيجوري إلى `{value}`"
    )


@ticketconfig.command(name="staffrole")
@commands.has_permissions(administrator=True)
async def tc_staffrole(ctx, *, value):
    config["staff_role_name"] = value
    save_config()
    await ctx.send(
        f"✅ تم تحديث رتبة الموظفين إلى `{value}`"
    )


@ticketconfig.command(name="logchannel")
@commands.has_permissions(administrator=True)
async def tc_logchannel(ctx, *, value):
    config["log_channel_name"] = value
    save_config()
    await ctx.send(
        f"✅ تم تحديث روم Logs إلى `{value}`"
    )


@ticketconfig.command(name="autoclose")
@commands.has_permissions(administrator=True)
async def tc_autoclose(ctx, days: int):
    if days < 1:
        await ctx.send(
            "❌ لازم يكون العدد 1 أو أكثر."
        )
        return

    config["auto_close_days"] = days
    save_config()

    await ctx.send(
        f"✅ سيتم إغلاق التذاكر الخاملة بعد {days} يوم."
    )


# =========================================================
# 🔥 نظام Lock / Unlock الجديد
# =========================================================
#
# Text Channel:
# 🔒 قراءة فقط = الروم ظاهر، لكن @everyone لا يستطيع الكتابة.
# 🔓 فتح الكلام = الروم ظاهر والكتابة مسموحة لـ @everyone.
#
# Thread:
# 🔒 قفل Thread = الـThread يبقى موجودًا لكن لا يمكن إرسال رسائل جديدة.
# 🔓 فتح Thread = يمكن الكتابة من جديد.
#
# ملاحظة:
# Discord لا يسمح بإخفاء Public Thread بشكل مستقل عن الروم الأب.
# لذلك خيارات الـThreads هنا هي قفل/فتح الكتابة فقط.


def is_lockable_channel(channel):
    return isinstance(
        channel,
        (discord.TextChannel, discord.Thread)
    )


def can_manage_lock(member: discord.Member, channel):
    if member.guild_permissions.administrator:
        return True

    if isinstance(channel, discord.Thread):
        return member.guild_permissions.manage_threads

    if isinstance(channel, discord.TextChannel):
        return member.guild_permissions.manage_channels

    return False


def bot_can_manage_lock(channel):
    guild = channel.guild
    me = guild.me

    if me is None:
        return False

    if me.guild_permissions.administrator:
        return True

    if isinstance(channel, discord.Thread):
        return me.guild_permissions.manage_threads

    if isinstance(channel, discord.TextChannel):
        return me.guild_permissions.manage_channels

    return False


async def lock_text_channel(channel):
    everyone = channel.guild.default_role
    overwrite = channel.overwrites_for(everyone)

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
        print(f"❌ Text Lock Error: {error}")
        return False


async def unlock_text_channel(channel):
    everyone = channel.guild.default_role
    overwrite = channel.overwrites_for(everyone)

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
        print(f"❌ Text Unlock Error: {error}")
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
        print(f"❌ Thread Lock Error: {error}")
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
        print(f"❌ Thread Unlock Error: {error}")
        return False


async def lock_any_channel(channel):
    if isinstance(channel, discord.Thread):
        return await lock_thread(channel)

    if isinstance(channel, discord.TextChannel):
        return await lock_text_channel(channel)

    return False


async def unlock_any_channel(channel):
    if isinstance(channel, discord.Thread):
        return await unlock_thread(channel)

    if isinstance(channel, discord.TextChannel):
        return await unlock_text_channel(channel)

    return False


def channel_type_name(channel):
    if isinstance(channel, discord.Thread):
        return "Thread"

    if isinstance(channel, discord.TextChannel):
        return "Text Channel"

    return "Channel"


async def send_lock_result(
    channel,
    user,
    locked
):
    if locked:
        message = (
            f"🔒 **تم قفل {channel_type_name(channel)}**\n"
            f"👤 بواسطة: {user.mention}"
        )
    else:
        message = (
            f"🔓 **تم فتح {channel_type_name(channel)}**\n"
            f"👤 بواسطة: {user.mention}"
        )

    try:
        await channel.send(
            message,
            delete_after=6
        )
    except (discord.Forbidden, discord.HTTPException):
        pass

    user_text = (
        user.mention
        if hasattr(user, "mention")
        else str(user)
    )

    await send_event_log(
        channel.guild,
        "🔒 قفل روم" if locked else "🔓 فتح روم",
        discord.Color.red() if locked else discord.Color.green(),
        fields=[
            ("النوع", channel_type_name(channel), True),
            ("الروم/الـThread", getattr(channel, "mention", channel.name), True),
            ("بواسطة", user_text, True),
        ]
    )


# =========================================================
# تنفيذ Lock / Unlock
# =========================================================

async def perform_lock(
    interaction,
    channel,
    user,
    response=True
):
    if not is_lockable_channel(channel):
        if response:
            await interaction.response.send_message(
                "❌ هذا النظام يعمل فقط على Text Channels و Threads.",
                ephemeral=True
            )
        return False

    if not can_manage_lock(user, channel):
        needed = (
            "Manage Threads"
            if isinstance(channel, discord.Thread)
            else "Manage Channels"
        )

        if response:
            await interaction.response.send_message(
                f"❌ تحتاج صلاحية **{needed}**.",
                ephemeral=True
            )
        return False

    if not bot_can_manage_lock(channel):
        if response:
            await interaction.response.send_message(
                "❌ البوت نفسه لا يملك الصلاحية الكافية.\n\n"
                "أعطه `Administrator`، أو على الأقل:\n"
                "• `Manage Channels` للرومات\n"
                "• `Manage Threads` للـThreads",
                ephemeral=True
            )
        return False

    success = await lock_any_channel(channel)

    if not success:
        if response:
            await interaction.response.send_message(
                "❌ فشل قفل الروم. تأكد من صلاحيات البوت.",
                ephemeral=True
            )
        return False

    if response:
        await interaction.response.send_message(
            f"🔒 تم قفل **{channel_type_name(channel)}** "
            f"{channel.mention}.\n"
            "👁️ الروم ما زال ظاهرًا، لكن الكتابة مقفلة.",
            ephemeral=True
        )

    await send_lock_result(channel, user, True)
    return True


async def perform_unlock(
    interaction,
    channel,
    user,
    response=True
):
    if not is_lockable_channel(channel):
        if response:
            await interaction.response.send_message(
                "❌ هذا النظام يعمل فقط على Text Channels و Threads.",
                ephemeral=True
            )
        return False

    if not can_manage_lock(user, channel):
        needed = (
            "Manage Threads"
            if isinstance(channel, discord.Thread)
            else "Manage Channels"
        )

        if response:
            await interaction.response.send_message(
                f"❌ تحتاج صلاحية **{needed}**.",
                ephemeral=True
            )
        return False

    if not bot_can_manage_lock(channel):
        if response:
            await interaction.response.send_message(
                "❌ البوت نفسه لا يملك الصلاحية الكافية.",
                ephemeral=True
            )
        return False

    success = await unlock_any_channel(channel)

    if not success:
        if response:
            await interaction.response.send_message(
                "❌ فشل فتح الروم. تأكد من صلاحيات البوت.",
                ephemeral=True
            )
        return False

    if response:
        await interaction.response.send_message(
            f"🔓 تم فتح **{channel_type_name(channel)}** "
            f"{channel.mention}.\n"
            "💬 الكتابة مفتوحة الآن.",
            ephemeral=True
        )

    await send_lock_result(channel, user, False)
    return True


# =========================================================
# لوحة اختيار حالة الروم
# =========================================================

class ChannelLockView(discord.ui.View):
    def __init__(self, channel_id, owner_id):
        super().__init__(timeout=120)

        self.channel_id = channel_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return False

        return True

    def get_channel(self, guild):
        return guild.get_channel(self.channel_id)

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
        channel = self.get_channel(interaction.guild)

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
        channel = self.get_channel(interaction.guild)

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
# Thread Selector
# =========================================================

def get_active_threads(guild):
    threads = list(guild.threads)

    # إزالة التكرار
    unique = {}
    for thread in threads:
        unique[thread.id] = thread

    threads = list(unique.values())

    threads.sort(
        key=lambda thread: thread.created_at or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    return threads


class ThreadSelect(discord.ui.Select):
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

            name = thread.name[:100]

            description = (
                f"#{parent_name} • "
                f"{'مقفول' if thread.locked else 'مفتوح'}"
            )[:100]

            options.append(
                discord.SelectOption(
                    label=name,
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

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        thread_id = int(self.values[0])
        thread = interaction.guild.get_thread(thread_id)

        if thread is None:
            try:
                thread = await interaction.guild.fetch_channel(
                    thread_id
                )
            except (discord.NotFound, discord.Forbidden):
                thread = None

        if not isinstance(thread, discord.Thread):
            await interaction.response.send_message(
                "❌ ما قدرت ألقى الـThread.",
                ephemeral=True
            )
            return

        await interaction.response.edit_message(
            content=(
                f"🧵 **{thread.name}**\n"
                f"الروم الأب: {thread.parent.mention if thread.parent else 'غير معروف'}\n\n"
                "اختر الإجراء:"
            ),
            view=ThreadActionView(
                thread.id,
                self.owner_id
            )
        )


class ThreadSelectorView(discord.ui.View):
    def __init__(
        self,
        guild,
        owner_id
    ):
        super().__init__(timeout=180)

        self.owner_id = owner_id
        threads = get_active_threads(guild)

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

        new_view = ThreadSelectorView(
            interaction.guild,
            self.owner_id
        )

        await interaction.response.edit_message(
            content=(
                "🧵 **اختيار Thread**\n\n"
                "اختر الـThread الذي تريد التحكم فيه:"
            ),
            view=new_view
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


class ThreadActionView(discord.ui.View):
    def __init__(
        self,
        thread_id,
        owner_id
    ):
        super().__init__(timeout=120)

        self.thread_id = thread_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return False

        return True

    async def get_thread(self, guild):
        thread = guild.get_thread(self.thread_id)

        if thread:
            return thread

        try:
            channel = await guild.fetch_channel(
                self.thread_id
            )
            return channel if isinstance(channel, discord.Thread) else None
        except (discord.NotFound, discord.Forbidden):
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
    channel="الروم الذي تريد التحكم فيه، اتركه فارغًا للروم الحالي"
)
async def slash_lock(
    interaction,
    channel: discord.TextChannel = None
):
    target = channel or interaction.channel

    if target is None:
        await interaction.response.send_message(
            "❌ ما قدرت أحدد الروم.",
            ephemeral=True
        )
        return

    if isinstance(target, discord.Thread):
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

    if not isinstance(target, discord.TextChannel):
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

    if not bot_can_manage_lock(target):
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
    channel="الروم الذي تريد فتحه، اتركه فارغًا للروم الحالي"
)
async def slash_unlock(
    interaction,
    channel: discord.TextChannel = None
):
    target = channel or interaction.channel

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
async def slash_threadlock(interaction):
    if (
        not interaction.user.guild_permissions.manage_threads
        and not interaction.user.guild_permissions.administrator
    ):
        await interaction.response.send_message(
            "❌ تحتاج صلاحية **Manage Threads**.",
            ephemeral=True
        )
        return

    if not bot_can_manage_lock(
        interaction.channel
    ) and isinstance(
        interaction.channel,
        discord.Thread
    ):
        await interaction.response.send_message(
            "❌ البوت يحتاج **Manage Threads**.",
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
# /log و /welcome — اختيار روم عبر قائمة Discord
# =========================================================

class LogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, owner_id):
        super().__init__(
            placeholder="اختر روم الـLogs...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )
        self.owner_id = owner_id

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        selected = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)
        guild_config["log_channel_id"] = selected.id
        save_config()

        await interaction.response.edit_message(
            content=f"✅ تم تحديد {selected.mention} كروم رسمي لتسجيل أحداث السيرفر (Logs).",
            view=None
        )


class LogChannelSelectView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=120)
        self.add_item(LogChannelSelect(owner_id))


class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, owner_id):
        super().__init__(
            placeholder="اختر روم الترحيب...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1
        )
        self.owner_id = owner_id

    async def callback(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه القائمة ليست لك.",
                ephemeral=True
            )
            return

        selected = self.values[0]

        guild_config = get_guild_config(interaction.guild.id)
        guild_config["welcome_channel_id"] = selected.id
        save_config()

        await interaction.response.edit_message(
            content=f"✅ تم تحديد {selected.mention} كروم للترحيب بالأعضاء الجدد.",
            view=None
        )


class WelcomeChannelSelectView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=120)
        self.add_item(WelcomeChannelSelect(owner_id))


@bot.tree.command(
    name="log",
    description="تحديد روم تسجيل أحداث السيرفر (Logs)"
)
async def slash_log(interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ هذا الأمر للإداريين فقط.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "📋 اختر الروم الذي تريده ليكون روم الـLogs:",
        view=LogChannelSelectView(interaction.user.id),
        ephemeral=True
    )


@bot.tree.command(
    name="welcome",
    description="تحديد روم الترحيب بالأعضاء الجدد"
)
async def slash_welcome(interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ هذا الأمر للإداريين فقط.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "👋 اختر روم الترحيب بالأعضاء الجدد:",
        view=WelcomeChannelSelectView(interaction.user.id),
        ephemeral=True
    )


# =========================================================
# رتب تلقائية + رسالة ترحيب عند دخول عضو
# =========================================================

async def assign_auto_role(member: discord.Member):
    guild = member.guild
    role_name = BOT_ROLE_NAME if member.bot else MEMBER_ROLE_NAME

    role = discord.utils.get(guild.roles, name=role_name)

    if role is None:
        print(f"⚠️ لم يتم العثور على رتبة '{role_name}' في سيرفر {guild.name}.")

        await send_event_log(
            guild,
            "⚠️ رتبة تلقائية غير موجودة",
            discord.Color.orange(),
            description=f"لم يتم العثور على رتبة باسم `{role_name}` لإعطائها للعضو الجديد.",
            fields=[("العضو", member.mention, True)]
        )
        return

    me = guild.me

    if me is None or me.top_role <= role:
        print(f"⚠️ رتبة البوت ليست أعلى من رتبة '{role_name}' في سيرفر {guild.name}.")

        await send_event_log(
            guild,
            "⚠️ تعذر إعطاء رتبة تلقائية",
            discord.Color.orange(),
            description=(
                f"رتبة البوت ليست أعلى من رتبة `{role_name}`، "
                "يرجى ترتيب الرتب حتى يستطيع البوت إعطاءها."
            ),
            fields=[("العضو", member.mention, True)]
        )
        return

    try:
        await member.add_roles(role, reason="إعطاء رتبة تلقائية عند الدخول")
    except discord.Forbidden:
        print(f"❌ لا صلاحية لإعطاء رتبة '{role_name}' في سيرفر {guild.name}.")
    except discord.HTTPException as error:
        print(f"❌ خطأ عند إعطاء رتبة تلقائية: {error}")


async def send_welcome_message(member: discord.Member):
    channel = get_configured_welcome_channel(member.guild)

    if channel is None:
        return

    content = WELCOME_MESSAGE_TEMPLATE.format(mention=member.mention)

    try:
        await channel.send(content)
    except discord.Forbidden:
        print(f"❌ لا صلاحية لإرسال رسالة الترحيب في سيرفر {member.guild.name}.")
    except discord.HTTPException as error:
        print(f"❌ خطأ عند إرسال رسالة الترحيب: {error}")


@bot.event
async def on_member_join(member):
    try:
        await assign_auto_role(member)
    except Exception as error:
        print(f"❌ Auto Role Error: {error}")

    if not member.bot:
        try:
            await send_welcome_message(member)
        except Exception as error:
            print(f"❌ Welcome Message Error: {error}")

    await send_event_log(
        member.guild,
        "👋 دخول عضو جديد",
        discord.Color.green(),
        fields=[
            ("العضو", member.mention, True),
            ("النوع", "Bot" if member.bot else "Member", True),
            ("الـID", str(member.id), True),
        ]
    )


@bot.event
async def on_member_remove(member):
    await send_event_log(
        member.guild,
        "🚪 خروج عضو",
        discord.Color.dark_grey(),
        fields=[
            ("العضو", f"{member} ({member.mention})", True),
            ("الـID", str(member.id), True),
        ]
    )


@bot.event
async def on_member_ban(guild, user):
    await send_event_log(
        guild,
        "🔨 حظر عضو",
        discord.Color.red(),
        fields=[
            ("العضو", f"{user} ({user.mention})", True),
            ("الـID", str(user.id), True),
        ]
    )


@bot.event
async def on_member_unban(guild, user):
    await send_event_log(
        guild,
        "🔓 فك حظر عضو",
        discord.Color.green(),
        fields=[
            ("العضو", f"{user} ({user.mention})", True),
            ("الـID", str(user.id), True),
        ]
    )


# =========================================================
# لوق حذف/تعديل الرسائل
# =========================================================

@bot.event
async def on_message_delete(message):
    if message.guild is None:
        return

    if message.author.bot:
        return

    content = (message.content or "").strip()

    # تجاهل رسائل أوامر القفل النصية والأوامر بالـ prefix
    # لأنها تُسجَّل أصلاً عبر لوق Lock/Unlock أو تنظيف طبيعي للأوامر
    if content.lower() in LOCK_TRIGGER_WORDS:
        return

    if content.startswith(bot.command_prefix):
        return

    preview = content if content else "[بدون نص / مرفق فقط]"

    await send_event_log(
        message.guild,
        "🗑️ حذف رسالة",
        discord.Color.dark_red(),
        fields=[
            ("العضو", message.author.mention, True),
            ("الروم", message.channel.mention, True),
            ("المحتوى", preview[:500], False),
        ]
    )


@bot.event
async def on_message_edit(before, after):
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
            ("العضو", before.author.mention, True),
            ("الروم", before.channel.mention, True),
            ("قبل", (before.content or "—")[:400], False),
            ("بعد", (after.content or "—")[:400], False),
        ]
    )


# =========================================================
# لوق الرومات (إنشاء / حذف / تعديل)
# =========================================================

@bot.event
async def on_guild_channel_create(channel):
    # لا نسجّل رومات التذاكر هنا، لأن فتح التذكرة له لوق مخصص أصلاً
    if is_in_ticket_category(channel):
        return

    await send_event_log(
        channel.guild,
        "📁 إنشاء روم",
        discord.Color.green(),
        fields=[
            ("الروم", getattr(channel, "mention", channel.name), True),
            ("النوع", str(channel.type), True),
        ]
    )


@bot.event
async def on_guild_channel_delete(channel):
    # حذف رومات التذاكر له لوق مخصص أصلاً عند الإغلاق
    if is_in_ticket_category(channel):
        return

    await send_event_log(
        channel.guild,
        "🗑️ حذف روم",
        discord.Color.dark_red(),
        fields=[
            ("اسم الروم", channel.name, True),
            ("النوع", str(channel.type), True),
        ]
    )


@bot.event
async def on_guild_channel_update(before, after):
    # نتجاهل رومات التذاكر لأن الـtopic يتغير باستمرار (Claim مثلاً)
    # وهذا يسبب سبام لا فائدة منه
    if is_in_ticket_category(after):
        return

    changes = []

    if before.name != after.name:
        changes.append(f"**الاسم:** `{before.name}` ➜ `{after.name}`")

    before_topic = getattr(before, "topic", None)
    after_topic = getattr(after, "topic", None)

    if before_topic != after_topic:
        changes.append("**تم تغيير وصف/موضوع الروم.**")

    if not changes:
        return

    await send_event_log(
        after.guild,
        "⚙️ تعديل روم",
        discord.Color.blue(),
        description="\n".join(changes),
        fields=[("الروم", getattr(after, "mention", after.name), True)]
    )


# =========================================================
# لوق الرتب (إنشاء / حذف / تعديل)
# =========================================================

@bot.event
async def on_guild_role_create(role):
    await send_event_log(
        role.guild,
        "🟢 إنشاء Role",
        discord.Color.green(),
        fields=[("الرتبة", role.mention, True)]
    )


@bot.event
async def on_guild_role_delete(role):
    await send_event_log(
        role.guild,
        "🔴 حذف Role",
        discord.Color.red(),
        fields=[("اسم الرتبة", role.name, True)]
    )


@bot.event
async def on_guild_role_update(before, after):
    if before.name == after.name and before.color == after.color:
        return

    changes = []

    if before.name != after.name:
        changes.append(f"**الاسم:** `{before.name}` ➜ `{after.name}`")

    if before.color != after.color:
        changes.append(f"**اللون:** `{before.color}` ➜ `{after.color}`")

    await send_event_log(
        after.guild,
        "⚙️ تعديل Role",
        discord.Color.blue(),
        description="\n".join(changes),
        fields=[("الرتبة", after.mention, True)]
    )


# =========================================================
# لوق الـVoice (دخول / خروج / انتقال)
# =========================================================

@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None and after.channel is not None:
        await send_event_log(
            member.guild,
            "🔊 دخول Voice",
            discord.Color.green(),
            fields=[
                ("العضو", member.mention, True),
                ("الروم", after.channel.mention, True),
            ]
        )

    elif before.channel is not None and after.channel is None:
        await send_event_log(
            member.guild,
            "🔇 خروج Voice",
            discord.Color.dark_grey(),
            fields=[
                ("العضو", member.mention, True),
                ("الروم", before.channel.mention, True),
            ]
        )

    elif (
        before.channel is not None
        and after.channel is not None
        and before.channel.id != after.channel.id
    ):
        await send_event_log(
            member.guild,
            "🔄 انتقال Voice",
            discord.Color.blue(),
            fields=[
                ("العضو", member.mention, True),
                ("من", before.channel.mention, True),
                ("إلى", after.channel.mention, True),
            ]
        )


# =========================================================
# Prefix !lock / !unlock
# =========================================================

@bot.command(name="lock")
async def prefix_lock(ctx):
    target = ctx.channel

    if not is_lockable_channel(target):
        return

    if not can_manage_lock(ctx.author, target):
        await ctx.send(
            "❌ ما عندك صلاحية قفل هذا الروم.",
            delete_after=5
        )
        return

    if not bot_can_manage_lock(target):
        await ctx.send(
            "❌ البوت يحتاج الصلاحية المناسبة.",
            delete_after=5
        )
        return

    success = await lock_any_channel(target)

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


@bot.command(name="unlock")
async def prefix_unlock(ctx):
    target = ctx.channel

    if not is_lockable_channel(target):
        return

    if not can_manage_lock(ctx.author, target):
        await ctx.send(
            "❌ ما عندك صلاحية فتح هذا الروم.",
            delete_after=5
        )
        return

    if not bot_can_manage_lock(target):
        await ctx.send(
            "❌ البوت يحتاج الصلاحية المناسبة.",
            delete_after=5
        )
        return

    success = await unlock_any_channel(target)

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
# أوامر القفل العربية
# =========================================================

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    content = message.content.strip().lower()
    channel = message.channel

    if content in {
        "قفل",
        "lock"
    }:
        if is_lockable_channel(channel):
            if can_manage_lock(message.author, channel):
                if bot_can_manage_lock(channel):
                    success = await lock_any_channel(channel)

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
        if is_lockable_channel(channel):
            if can_manage_lock(message.author, channel):
                if bot_can_manage_lock(channel):
                    success = await unlock_any_channel(channel)

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

    await bot.process_commands(message)


# =========================================================
# Auto Close
# =========================================================

@tasks.loop(hours=1)
async def auto_cleanup():
    now = datetime.now(timezone.utc)

    for guild in bot.guilds:
        category = get_ticket_category(guild)

        if category is None:
            continue

        for channel in list(category.text_channels):
            if not is_ticket_channel(channel):
                continue

            try:
                last_message = None

                async for message in channel.history(limit=1):
                    last_message = message

                if last_message:
                    last_activity = last_message.created_at
                else:
                    last_activity = channel.created_at

                idle_seconds = (
                    now - last_activity
                ).total_seconds()

                max_idle_seconds = (
                    config["auto_close_days"]
                    * 24
                    * 60
                    * 60
                )

                if idle_seconds >= max_idle_seconds:
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
                f"✅ تمت مزامنة {len(synced)} من أوامر Slash."
            )

            _commands_synced = True

        except Exception as error:
            print(
                f"❌ تعذر مزامنة أوامر Slash: {error}"
            )

    if not _views_registered:
        bot.add_view(OpenTicketView())
        bot.add_view(TicketActionView())

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
        f"🤖 Logged in as {bot.user} "
        f"(ID: {bot.user.id})"
    )

    print(
        "✅ البوت جاهز ويعمل."
    )


# =========================================================
# أخطاء عامة
# =========================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(
        error,
        commands.CommandNotFound
    ):
        return

    if isinstance(
        error,
        commands.MissingPermissions
    ):
        await ctx.send(
            "❌ ما عندك الصلاحية لاستخدام هذا الأمر.",
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

    print(
        f"❌ Command Error: {error}"
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
    bot.run(TOKEN)
