import os
import asyncio
import threading
import discord
from discord.ext import commands
from flask import Flask

# ========= الإعدادات =========
TOKEN = os.getenv("TOKEN")
PORT = int(os.getenv("PORT", 8080))  # Render يجهز هذا المتغير تلقائياً

# اسم الكاتيجوري اللي بتتنشئ فيها التذاكر (تقدر تغيّره)
TICKET_CATEGORY_NAME = "Tickets"

# اسم الرول الخاص بالإداريين اللي يقدرون يشوفون التذاكر
# غيّره لاسم الرول عندك بالضبط (حساس لحالة الأحرف)
STAFF_ROLE_NAME = "Staff"

# ========= إعداد البوت =========
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ========= سيرفر وهمي بسيط عشان Render يعتبره Web Service =========
web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Bot is alive!"


def run_web_server():
    web_app.run(host="0.0.0.0", port=PORT)


def keep_alive():
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()


# ========= زر فتح التذكرة =========
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="فتح تذكرة جديدة 🎫",
        style=discord.ButtonStyle.green,
        custom_id="create_ticket_button",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        # اسم القناة: ticket-اسم_العضو
        safe_name = "".join(c for c in member.name.lower() if c.isalnum() or c in "-_") or "user"
        channel_name = f"ticket-{safe_name}"

        # تحقق إذا عنده تذكرة مفتوحة أصلاً
        existing = discord.utils.get(guild.text_channels, name=channel_name)
        if existing:
            await interaction.response.send_message(
                f"عندك تذكرة مفتوحة بالفعل: {existing.mention}", ephemeral=True
            )
            return

        # جيب الكاتيجوري أو أنشئها لو مو موجودة
        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        # صلاحيات القناة: مخفية عن الجميع إلا صاحب التذكرة والإداريين والبوت
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }

        staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE_NAME)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"تذكرة جديدة بواسطة {member}",
        )

        embed = discord.Embed(
            title="مرحباً بك 👋",
            description=(
                f"أهلاً {member.mention}، شكراً لفتح تذكرة.\n"
                "فريق الإدارة راح يتواصل معك قريباً.\n\n"
                "لإغلاق التذكرة، اضغط الزر تحت 👇"
            ),
            color=discord.Color.green(),
        )

        await ticket_channel.send(embed=embed, view=CloseView())

        await interaction.response.send_message(
            f"تم إنشاء تذكرتك: {ticket_channel.mention}", ephemeral=True
        )


# ========= زر إغلاق التذكرة =========
class CloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="إغلاق التذكرة 🔒",
        style=discord.ButtonStyle.red,
        custom_id="close_ticket_button",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "جارٍ إغلاق التذكرة خلال 5 ثوانٍ..."
        )
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"تم الإغلاق بواسطة {interaction.user}")


# ========= أمر الإعداد =========
@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx: commands.Context):
    embed = discord.Embed(
        title="نظام التذاكر 🎫",
        description="اضغط على الزر تحت لفتح تذكرة جديدة وتواصل مع فريق الإدارة.",
        color=discord.Color.blurple(),
    )
    await ctx.send(embed=embed, view=TicketView())
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass


@setup.error
async def setup_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("هذا الأمر للإداريين فقط.", delete_after=5)


# ========= تسجيل الأزرار الدائمة عند التشغيل =========
@bot.event
async def on_ready():
    bot.add_view(TicketView())
    bot.add_view(CloseView())
    print(f"تم تسجيل الدخول باسم: {bot.user} (ID: {bot.user.id})")
    print("البوت جاهز ويعمل ✅")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError(
            "ما تم العثور على التوكن! تأكد من إضافة متغير البيئة TOKEN."
        )
    keep_alive()
    bot.run(TOKEN)
