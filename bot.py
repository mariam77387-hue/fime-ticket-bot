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

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        loaded_config = deepcopy(DEFAULT_CONFIG)
        loaded_config.update(data)

        if "guilds" not in loaded_config:
            loaded_config["guilds"] = {}

        return loaded_config

    except (json.JSONDecodeError, OSError):

        print(
            "⚠️ تعذر قراءة config.json، سيتم استخدام الإعدادات الافتراضية."
        )

        return deepcopy(DEFAULT_CONFIG)


def save_config():

    try:

        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                config,
                file,
                ensure_ascii=False,
                indent=2
            )

    except OSError as error:

        print(
            f"❌ تعذر حفظ config.json: {error}"
        )


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

            return (
                f'{category["emoji"]} '
                f'{category["label"]}'
            )

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


def is_staff(member: discord.Member):

    if member.guild_permissions.administrator:
        return True

    role = get_staff_role(member.guild)

    if role is None:
        return False

    return role in member.roles


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

            return part.split(
                ":",
                1
            )[1]

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

    if owner_id is None:

        current_owner = get_ticket_owner_id(
            channel
        )

    if category_value is None:

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


def find_open_ticket(
    guild: discord.Guild,
    user_id: int
):

    for channel in guild.text_channels:

        if not is_ticket_channel(channel):
            continue

        owner_id = get_ticket_owner_id(
            channel
        )

        if owner_id == user_id:
            return channel

    return None


# =========================================================
# Transcript
# =========================================================

async def build_transcript(
    channel: discord.TextChannel
):

    lines = []

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

        lines.append(
            "لا توجد رسائل في التذكرة."
        )

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
# Logs
# =========================================================

async def send_ticket_log(
    guild,
    title,
    description,
    color=discord.Color.blurple(),
    file=None
):

    log_channel = get_log_channel(
        guild
    )

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

    except discord.HTTPException as error:

        print(
            f"❌ خطأ في إرسال Log: {error}"
        )


# =========================================================
# إغلاق التذكرة
# =========================================================

async def close_ticket_channel(
    channel: discord.TextChannel,
    closer
):

    guild = channel.guild

    try:

        transcript = await build_transcript(
            channel
        )

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

        print(
            f"❌ Transcript Error: {error}"
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
            f"❌ لا أستطيع حذف {channel.name}"
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

                config["category_name"],

                reason="إنشاء كاتيجوري التذاكر"
            )

        except discord.Forbidden:

            await interaction.response.send_message(

                "❌ البوت لا يملك صلاحية إنشاء الكاتيجوري.",

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

    try:

        ticket_channel = await guild.create_text_channel(

            name=channel_name,

            category=category,

            overwrites=overwrites,

            reason=f"Ticket opened by {member}"
        )

    except discord.Forbidden:

        await interaction.response.send_message(

            "❌ ما قدرت أنشئ التذكرة. "
            "تأكد من صلاحيات البوت.",

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

    # =====================================================
    # Claim
    # =====================================================

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

        # الرسالة الدائمة داخل التذكرة

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

    # =====================================================
    # Close
    # =====================================================

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

        interaction: discord.Interaction,

        button: discord.ui.Button
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
# Embed Command
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

    await channel.send(
        embed=embed
    )

    await ctx.send(

        f"✅ تم نشر الـ Embed في "
        f"{channel.mention}"
    )

    try:

        await ctx.message.delete()
        await reply.delete()

    except discord.HTTPException:
        pass


@embed_cmd.error
async def embed_cmd_error(ctx, error):

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


@ticketconfig.command(
    name="help"
)
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

    await ctx.send(
        "✅ تم تحديث العنوان."
    )


@ticketconfig.command(name="desc")
@commands.has_permissions(administrator=True)
async def tc_desc(ctx, *, value):

    config["embed_description"] = value
    save_config()

    await ctx.send(
        "✅ تم تحديث الوصف."
    )


@ticketconfig.command(name="color")
@commands.has_permissions(administrator=True)
async def tc_color(ctx, value):

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

        f"✅ سيتم إغلاق التذاكر الخاملة "
        f"بعد {days} يوم."
    )


# =========================================================
# 🔥 نظام Lock / Unlock الاحترافي
# =========================================================

def is_lockable_channel(channel):

    return isinstance(
        channel,
        (
            discord.TextChannel,
            discord.Thread
        )
    )


def is_thread(channel):

    return isinstance(
        channel,
        discord.Thread
    )


def can_manage_lock(
    member: discord.Member,
    channel
):

    # Administrator = أعلى مستوى عمليًا داخل Discord

    if member.guild_permissions.administrator:

        return True

    # Threads

    if isinstance(
        channel,
        discord.Thread
    ):

        return member.guild_permissions.manage_threads

    # Text Channels

    return member.guild_permissions.manage_channels


def bot_can_manage_lock(channel):

    guild = channel.guild
    me = guild.me

    if me is None:

        return False

    # إذا البوت Administrator

    if me.guild_permissions.administrator:

        return True

    # Thread

    if isinstance(
        channel,
        discord.Thread
    ):

        return me.guild_permissions.manage_threads

    # Text Channel

    return me.guild_permissions.manage_channels


# =========================================================
# قفل Text Channel
# =========================================================

async def lock_text_channel(channel):

    guild = channel.guild

    everyone = guild.default_role

    overwrite = channel.overwrites_for(
        everyone
    )

    # منع الكتابة على @everyone

    overwrite.send_messages = False

    try:

        await channel.set_permissions(

            everyone,

            overwrite=overwrite,

            reason="Lock command"
        )

        return True

    except discord.Forbidden:

        return False

    except discord.HTTPException as error:

        print(
            f"❌ Text Lock Error: {error}"
        )

        return False


# =========================================================
# فتح Text Channel
# =========================================================

async def unlock_text_channel(channel):

    guild = channel.guild

    everyone = guild.default_role

    overwrite = channel.overwrites_for(
        everyone
    )

    # إزالة منع الكتابة الذي وضعه البوت

    overwrite.send_messages = None

    try:

        await channel.set_permissions(

            everyone,

            overwrite=overwrite,

            reason="Unlock command"
        )

        return True

    except discord.Forbidden:

        return False

    except discord.HTTPException as error:

        print(
            f"❌ Text Unlock Error: {error}"
        )

        return False


# =========================================================
# قفل Thread
# =========================================================

async def lock_thread(thread):

    try:

        # إذا كان Archived نحاول إلغاء الأرشفة أولاً

        if thread.archived:

            await thread.edit(
                archived=False,
                reason="Preparing thread for lock"
            )

        await thread.edit(

            locked=True,

            reason="Lock command"
        )

        return True

    except discord.Forbidden:

        return False

    except discord.HTTPException as error:

        print(
            f"❌ Thread Lock Error: {error}"
        )

        return False


# =========================================================
# فتح Thread
# =========================================================

async def unlock_thread(thread):

    try:

        # فتح الـ Thread

        await thread.edit(

            locked=False,

            archived=False,

            reason="Unlock command"
        )

        return True

    except discord.Forbidden:

        return False

    except discord.HTTPException as error:

        print(
            f"❌ Thread Unlock Error: {error}"
        )

        return False


# =========================================================
# القفل الرئيسي
# =========================================================

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


# =========================================================
# الفتح الرئيسي
# =========================================================

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


# =========================================================
# تحديد نوع الروم
# =========================================================

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


# =========================================================
# رسالة القفل
# =========================================================

async def send_lock_result(
    channel,
    user,
    locked
):

    type_name = channel_type_name(
        channel
    )

    if locked:

        message = (

            f"🔒 **تم قفل {type_name} بنجاح**\n"
            f"👤 بواسطة: {user.mention}"
        )

    else:

        message = (

            f"🔓 **تم فتح {type_name} بنجاح**\n"
            f"👤 بواسطة: {user.mention}"
        )

    try:

        await channel.send(
            message,
            delete_after=6
        )

    except discord.Forbidden:

        # طبيعي في بعض حالات Lock
        pass

    except discord.HTTPException:

        pass


# =========================================================
# تنفيذ Lock
# =========================================================

async def execute_lock(
    interaction,
    channel,
    user
):

    if not is_lockable_channel(channel):

        text = (

            "❌ هذا الأمر يعمل فقط على "
            "**Text Channels** و **Threads**."
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    if not can_manage_lock(
        user,
        channel
    ):

        if isinstance(
            channel,
            discord.Thread
        ):

            text = (

                "❌ تحتاج صلاحية "
                "**Manage Threads**."
            )

        else:

            text = (

                "❌ تحتاج صلاحية "
                "**Manage Channels**."
            )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    if not bot_can_manage_lock(
        channel
    ):

        text = (

            "❌ **البوت نفسه لا يملك الصلاحية الكافية.**\n\n"

            "أعطه `Administrator`، أو على الأقل:\n"

            "• `Manage Channels` للرومات\n"
            "• `Manage Threads` للـ Threads"
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    success = await lock_any_channel(
        channel
    )

    if not success:

        text = (

            "❌ فشل قفل الروم.\n"

            "قد تكون هناك مشكلة في صلاحيات البوت "
            "أو إعدادات Discord."
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    # Slash

    if isinstance(
        interaction,
        discord.Interaction
    ):

        await interaction.response.send_message(

            f"🔒 تم قفل "
            f"**{channel_type_name(channel)}** "
            f"{channel.mention} بنجاح.",

            ephemeral=True
        )

        # محاولة إرسال رسالة داخل الروم

        await send_lock_result(

            channel,

            user,

            True
        )


# =========================================================
# تنفيذ Unlock
# =========================================================

async def execute_unlock(
    interaction,
    channel,
    user
):

    if not is_lockable_channel(channel):

        text = (

            "❌ هذا الأمر يعمل فقط على "
            "**Text Channels** و **Threads**."
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    if not can_manage_lock(
        user,
        channel
    ):

        if isinstance(
            channel,
            discord.Thread
        ):

            text = (

                "❌ تحتاج صلاحية "
                "**Manage Threads**."
            )

        else:

            text = (

                "❌ تحتاج صلاحية "
                "**Manage Channels**."
            )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    if not bot_can_manage_lock(
        channel
    ):

        text = (

            "❌ **البوت نفسه لا يملك الصلاحية الكافية.**\n\n"

            "أعطه `Administrator`، أو على الأقل:\n"

            "• `Manage Channels`\n"
            "• `Manage Threads`"
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    success = await unlock_any_channel(
        channel
    )

    if not success:

        text = (

            "❌ فشل فتح الروم.\n"

            "تأكد من صلاحيات البوت."
        )

        if isinstance(
            interaction,
            discord.Interaction
        ):

            await interaction.response.send_message(

                text,

                ephemeral=True
            )

        return

    if isinstance(
        interaction,
        discord.Interaction
    ):

        await interaction.response.send_message(

            f"🔓 تم فتح "
            f"**{channel_type_name(channel)}** "
            f"{channel.mention} بنجاح.",

            ephemeral=True
        )

        await send_lock_result(

            channel,

            user,

            False
        )


# =========================================================
# تحديد الروم من Argument
# =========================================================

async def resolve_lock_channel(
    ctx,
    channel=None
):

    if channel is None:

        return ctx.channel

    if isinstance(
        channel,
        (
            discord.TextChannel,
            discord.Thread
        )
    ):

        return channel

    return None


# =========================================================
# !lock
# =========================================================

@bot.command(name="lock")
@commands.has_permissions(
    manage_channels=True
)
async def prefix_lock(
    ctx,
    channel: discord.TextChannel = None
):

    target = await resolve_lock_channel(
        ctx,
        channel
    )

    if target is None:

        await ctx.send(
            "❌ ما قدرت أحدد الروم.",
            delete_after=5
        )

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

            "❌ البوت يحتاج `Manage Channels` "
            "أو `Administrator`.",

            delete_after=7
        )

        return

    success = await lock_any_channel(
        target
    )

    if not success:

        await ctx.send(

            "❌ فشل قفل الروم.",

            delete_after=5
        )

        return

    try:

        await ctx.message.delete()

    except discord.HTTPException:
        pass

    await send_lock_result(

        target,

        ctx.author,

        True
    )


# =========================================================
# !unlock
# =========================================================

@bot.command(name="unlock")
@commands.has_permissions(
    manage_channels=True
)
async def prefix_unlock(
    ctx,
    channel: discord.TextChannel = None
):

    target = await resolve_lock_channel(
        ctx,
        channel
    )

    if target is None:

        await ctx.send(

            "❌ ما قدرت أحدد الروم.",

            delete_after=5
        )

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

            "❌ البوت يحتاج `Manage Channels` "
            "أو `Administrator`.",

            delete_after=7
        )

        return

    success = await unlock_any_channel(
        target
    )

    if not success:

        await ctx.send(

            "❌ فشل فتح الروم.",

            delete_after=5
        )

        return

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
# Slash /lock
# =========================================================

@bot.tree.command(

    name="lock",

    description="Lock a channel or thread"
)
@app_commands.describe(

    channel="الروم الذي تريد قفله، اتركه فارغًا لقفل الروم الحالي"
)
async def slash_lock(

    interaction: discord.Interaction,

    channel: discord.TextChannel = None
):

    target = channel or interaction.channel

    if target is None:

        await interaction.response.send_message(

            "❌ ما قدرت أحدد الروم.",

            ephemeral=True
        )

        return

    await execute_lock(

        interaction,

        target,

        interaction.user
    )


# =========================================================
# Slash /unlock
# =========================================================

@bot.tree.command(

    name="unlock",

    description="Unlock a channel or thread"
)
@app_commands.describe(

    channel="الروم الذي تريد فتحه، اتركه فارغًا لفتح الروم الحالي"
)
async def slash_unlock(

    interaction: discord.Interaction,

    channel: discord.TextChannel = None
):

    target = channel or interaction.channel

    if target is None:

        await interaction.response.send_message(

            "❌ ما قدرت أحدد الروم.",

            ephemeral=True
        )

        return

    await execute_unlock(

        interaction,

        target,

        interaction.user
    )


# =========================================================
# 🔥 أوامر القفل النصية العربية
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:

        return

    content = message.content.strip().lower()

    channel = message.channel

    # -----------------------------------------------------
    # قفل
    # -----------------------------------------------------

    if content in {

        "قفل",

        "lock",

        "!lock"
    }:

        if not is_lockable_channel(
            channel
        ):

            return

        if not can_manage_lock(
            message.author,
            channel
        ):

            return

        if not bot_can_manage_lock(
            channel
        ):

            return

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

    # -----------------------------------------------------
    # فتح
    # -----------------------------------------------------

    if content in {

        "فتح",

        "unlock",

        "!unlock"
    }:

        if not is_lockable_channel(
            channel
        ):

            return

        if not can_manage_lock(
            message.author,
            channel
        ):

            return

        if not bot_can_manage_lock(
            channel
        ):

            return

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
# Auto Close
# =========================================================

@tasks.loop(hours=1)
async def auto_cleanup():

    now = datetime.now(
        timezone.utc
    )

    for guild in bot.guilds:

        category = get_ticket_category(
            guild
        )

        if category is None:
            continue

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

    # -----------------------------------------------------
    # Slash Commands
    # -----------------------------------------------------

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

                f"❌ تعذر مزامنة أوامر Slash: "
                f"{error}"
            )

    # -----------------------------------------------------
    # Persistent Views
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Auto Cleanup
    # -----------------------------------------------------

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