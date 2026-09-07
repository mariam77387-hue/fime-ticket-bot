import os
import io
import json
import asyncio
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks
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

    # أرقام التذاكر لكل سيرفر
    "guilds": {}
}


# =========================================================
# إدارة الإعدادات
# =========================================================

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        config = DEFAULT_CONFIG.copy()
        config.update(data)

        if "guilds" not in config:
            config["guilds"] = {}

        return config

    except (json.JSONDecodeError, OSError):
        print("⚠️ تعذر قراءة config.json، سيتم استخدام الإعدادات الافتراضية.")
        return DEFAULT_CONFIG.copy()


def save_config():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=2
            )
    except OSError as error:
        print(f"❌ تعذر حفظ config.json: {error}")


config = load_config()


def get_guild_config(guild_id: int):
    guild_id = str(guild_id)

    if guild_id not in config["guilds"]:
        config["guilds"][guild_id] = {
            "next_ticket_number": 1
        }
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
# Discord Bot
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.message_content = True

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
# أدوات مساعدة
# =========================================================

def get_staff_role(guild: discord.Guild):
    return discord.utils.get(
        guild.roles,
        name="Staff"
    )


def get_ticket_category(guild: discord.Guild):
    return discord.utils.get(
        guild.categories,
        name="Tickets"
    )


def get_log_channel(guild: discord.Guild):
    return discord.utils.get(
        guild.text_channels,
        name="ticket-logs"
    )


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
    claimed_id=None
):
    current_owner = owner_id
    current_category = category_value
    current_claimed = claimed_id

    if owner_id is None:
        current_owner = get_ticket_owner_id(channel)

    if category_value is None:
        current_category = get_ticket_category_value(channel)

    if claimed_id is None:
        current_claimed = get_ticket_claimed_id(channel)

    parts = [
        f"ticket_id:{channel.id}",
        f"opener_id:{current_owner}",
        f"category:{current_category}",
    ]

    if current_claimed:
        parts.append(f"claimed_id:{current_claimed}")

    return " | ".join(parts)


# =========================================================
# البحث عن تذكرة العضو
# =========================================================

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

    text = "\n".join(lines)

    buffer = io.BytesIO(
        text.encode("utf-8")
    )

    buffer.seek(0)

    return discord.File(
        buffer,
        filename=f"{channel.name}-transcript.txt"
    )


# =========================================================
# إرسال Log
# =========================================================

async def send_ticket_log(
    guild,
    title,
    description,
    color=discord.Color.blurple(),
    file=None
):

    log_channel = get_log_channel(guild)

    if log_channel is None:
        print(
            f"⚠️ لم يتم العثور على روم Logs في {guild.name}"
        )
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )

    try:
        await log_channel.send(
            embed=embed,
            file=file
        )

    except discord.Forbidden:
        print("❌ البوت لا يملك صلاحية إرسال Logs.")

    except discord.HTTPException as error:
        print(f"❌ خطأ أثناء إرسال Log: {error}")


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

        await send_ticket_log(
            guild,
            "🔒 تم إغلاق تذكرة",
            (
                f"**الروم:** `{channel.name}`\n"
                f"**صاحب التذكرة:** {owner_text}\n"
                f"**النوع:** {category_text}\n"
                f"**أغلقها:** {closer.mention}"
            ),
            discord.Color.red(),
            transcript
        )

    except Exception as error:
        print(
            f"❌ حدث خطأ أثناء إنشاء Transcript: {error}"
        )

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
        print(
            f"❌ البوت لا يستطيع حذف الروم {channel.name}"
        )


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

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        await create_ticket_channel(
            interaction,
            self.category_value,
            str(self.reason)
        )


# =========================================================
# Select Menu
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
        interaction: discord.Interaction
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
    interaction: discord.Interaction,
    category_value,
    reason
):

    guild = interaction.guild
    member = interaction.user

    if guild is None:
        return

    # منع التذاكر المكررة
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

    # البحث عن الكاتيجوري
    category = get_ticket_category(guild)

    if category is None:

        try:

            category = await guild.create_category(
                "Tickets",
                reason="إنشاء كاتيجوري التذاكر"
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ البوت لا يملك صلاحية إنشاء الكاتيجوري.",
                ephemeral=True
            )

            return

    # رقم التذكرة
    number = get_next_ticket_number(guild)

    channel_name = f"ticket-{number:04d}"

    # الصلاحيات
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
            ),

        guild.me:
            discord.PermissionOverwrite(
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

    # Topic
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

    # Embed
    try:

        embed_color = int(
            config["embed_color"],
            16
        )

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

    mention = (
        staff_role.mention
        if staff_role
        else None
    )

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
        interaction: discord.Interaction,
        button: discord.ui.Button
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
# Claim / Close
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
        interaction: discord.Interaction,
        button: discord.ui.Button
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

        # تعديل Embed
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

        # تحديث الـ topic
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not is_staff(interaction.user):

            owner_id = get_ticket_owner_id(
                interaction.channel
            )

            if owner_id != interaction.user.id:

                await interaction.response.send_message(
                    "❌ ما عندك صلاحية إغلاق هذه التذكرة.",
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="✅ تم إلغاء الإغلاق.",
            view=None
        )


# =========================================================
# أمر Setup
# =========================================================

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup_cmd(ctx):

    try:

        color = int(
            config["embed_color"],
            16
        )

    except (ValueError, TypeError):

        color = 0x5865F2

    embed = discord.Embed(
        title=config["embed_title"],
        description=config["embed_description"],
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


@setup_cmd.error
async def setup_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ هذا الأمر للإداريين فقط.",
            delete_after=5
        )


# =========================================================
# أمر Embed
# =========================================================

@bot.command(name="embed")
@commands.has_permissions(administrator=True)
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

    await channel.send(
        embed=embed
    )

    await ctx.send(
        f"✅ تم نشر الـ Embed في {channel.mention}"
    )

    try:

        await ctx.message.delete()
        await reply.delete()

    except discord.HTTPException:
        pass


@embed_cmd.error
async def embed_cmd_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ هذا الأمر للإداريين فقط.",
            delete_after=5
        )

    elif isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ الاستخدام الصحيح:\n"
            "`!embed #الروم`",
            delete_after=8
        )

    elif isinstance(
        error,
        commands.ChannelNotFound
    ):

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

    await ctx.send(
        embed=embed
    )


@ticketconfig.command(name="help")
async def ticketconfig_help(ctx):

    text = (
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
        "تغيير روم الـ Logs.\n\n"

        "`!ticketconfig autoclose <الأيام>`\n"
        "تغيير مدة الإغلاق التلقائي."
    )

    await ctx.send(text)


@ticketconfig.command(name="title")
@commands.has_permissions(administrator=True)
async def tc_title(
    ctx,
    *,
    value
):

    config["embed_title"] = value

    save_config()

    await ctx.send(
        "✅ تم تحديث العنوان."
    )


@ticketconfig.command(name="desc")
@commands.has_permissions(administrator=True)
async def tc_desc(
    ctx,
    *,
    value
):

    config["embed_description"] = value

    save_config()

    await ctx.send(
        "✅ تم تحديث الوصف."
    )


@ticketconfig.command(name="color")
@commands.has_permissions(administrator=True)
async def tc_color(
    ctx,
    value
):

    value = value.strip().replace(
        "#",
        ""
    ).upper()

    if len(value) != 6:

        await ctx.send(
            "❌ استخدم لون HEX من 6 خانات، مثال: `5865F2`"
        )

        return

    try:

        int(value, 16)

    except ValueError:

        await ctx.send(
            "❌ كود اللون غير صحيح."
        )

        return

    config["embed_color"] = value

    save_config()

    await ctx.send(
        f"✅ تم تحديث اللون إلى `#{value}`"
    )


@ticketconfig.command(name="category")
@commands.has_permissions(administrator=True)
async def tc_category(
    ctx,
    *,
    value
):

    config["category_name"] = value

    save_config()

    await ctx.send(
        f"✅ تم تحديث الكاتيجوري إلى `{value}`"
    )


@ticketconfig.command(name="staffrole")
@commands.has_permissions(administrator=True)
async def tc_staffrole(
    ctx,
    *,
    value
):

    config["staff_role_name"] = value

    save_config()

    await ctx.send(
        f"✅ تم تحديث رتبة الموظفين إلى `{value}`"
    )


@ticketconfig.command(name="logchannel")
@commands.has_permissions(administrator=True)
async def tc_logchannel(
    ctx,
    *,
    value
):

    config["log_channel_name"] = value

    save_config()

    await ctx.send(
        f"✅ تم تحديث روم Logs إلى `{value}`"
    )


@ticketconfig.command(name="autoclose")
@commands.has_permissions(administrator=True)
async def tc_autoclose(
    ctx,
    days: int
):

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


@ticketconfig.error
async def ticketconfig_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ هذا الأمر للإداريين فقط.",
            delete_after=5
        )

    elif isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ ناقص معلومات.\n"
            "استخدم `!ticketconfig help`",
            delete_after=8
        )


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

                async for message in channel.history(
                    limit=1
                ):

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

                print(
                    f"❌ لا أستطيع الوصول إلى {channel.name}"
                )

            except Exception as error:

                print(
                    f"❌ Auto Cleanup Error: {error}"
                )


@auto_cleanup.before_loop
async def before_auto_cleanup():

    await bot.wait_until_ready()


# =========================================================
# Bot Events
# =========================================================

_views_registered = False


@bot.event
async def on_ready():

    global _views_registered

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