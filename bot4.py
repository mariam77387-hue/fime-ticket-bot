# ============================================================
# Team Fime — bot4.py
# Game Search System
# ============================================================

import os
import re
import sqlite3
import discord

from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

DB_FILE = "bot4.db"


# ============================================================
# 🔐 المواقع الآمنة الخاصة بك
# 
# أضف مواقعك هنا فقط.
#
# مثال:
#
# SAFE_SITES = [
#     "https://rscripts.net",
#     "https://scriptblox.com",
# ]
#
# {query} سيتم استبداله باسم اللعبة الذي كتبه العضو.
#
# مهم:
# لا تضع أي موقع لا تثق فيه.
# ============================================================

SAFE_SITES = [

    # 👇 ضع روابطك هنا

    # "https://example.com/search?q={query}",

    # "https://example2.com/search/{query}",

]


# ============================================================
# أسماء الألعاب والاختصارات
# ============================================================

GAME_ALIASES = {

    "doors": [
        "doors",
        "دورز",
        "دور",
        "الباب",
    ],

    "mm2": [
        "mm2",
        "mm 2",
        "ام ام تو",
        "ام ام 2",
        "مستر م",
    ],

    "brookhaven": [
        "brookhaven",
        "بروكهافن",
        "بروك هافن",
    ],

    "blox fruits": [
        "blox fruits",
        "bloxfruit",
        "بلوك فروت",
        "بلوك فروتس",
        "بلوكس فروت",
    ],

    "grow a garden": [
        "grow a garden",
        "growagarden",
        "جرو جاردن",
        "جرو اي جاردن",
        "جرو",
    ],

    "steal a brainrot": [
        "steal a brainrot",
        "stealabrainrot",
        "سرقة برينروت",
        "ستيل برينروت",
    ],

    "steal an egg": [
        "steal an egg",
        "stealanegg",
        "ستيل ان ايق",
        "ستيل ان ايغ",
    ],

}


# ============================================================
# تنظيف النص
# ============================================================

def normalize_text(text: str) -> str:
    text = text.lower().strip()

    text = re.sub(r"\s+", " ", text)

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


# ============================================================
# معرفة اللعبة من كلام العضو
# ============================================================

def find_game(message: str):

    normalized_message = normalize_text(message)

    for game_name, aliases in GAME_ALIASES.items():

        for alias in aliases:

            normalized_alias = normalize_text(alias)

            if normalized_message == normalized_alias:
                return game_name

            if normalized_alias in normalized_message:
                return game_name

    return None


# ============================================================
# قاعدة البيانات
# ============================================================

def init_database():

    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    connection.commit()
    connection.close()


def get_setting(key):

    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    )

    result = cursor.fetchone()

    connection.close()

    if result:
        return result[0]

    return None


def set_setting(key, value):

    connection = sqlite3.connect(DB_FILE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    connection.commit()
    connection.close()


# ============================================================
# بناء رابط البحث
# ============================================================

def build_search_url(site, game_name):

    query = game_name.replace(" ", "+")

    return site.replace("{query}", query)


# ============================================================
# إنشاء أزرار المواقع
# ============================================================

class SearchButtons(discord.ui.View):

    def __init__(self, game_name):

        super().__init__(timeout=180)

        if not SAFE_SITES:
            return

        for index, site in enumerate(SAFE_SITES, start=1):

            url = build_search_url(site, game_name)

            button = discord.ui.Button(
                label=f"بحث {index}",
                style=discord.ButtonStyle.link,
                url=url
            )

            self.add_item(button)


# ============================================================
# Cog
# ============================================================

class Bot4(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        init_database()

    # ========================================================
    # /setscriptroom
    # ========================================================

    @app_commands.command(
        name="setscriptroom",
        description="تحديد روم البحث عن الألعاب"
    )
    @app_commands.describe(
        channel="الروم الذي سيتم البحث داخله"
    )
    @app_commands.default_permissions(manage_guild=True)
    async def setscriptroom(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        set_setting(
            "search_channel_id",
            channel.id
        )

        await interaction.response.send_message(
            f"✅ تم تحديد روم البحث:\n{channel.mention}",
            ephemeral=True
        )

    # ========================================================
    # /scriptroom
    # ========================================================

    @app_commands.command(
        name="scriptroom",
        description="عرض روم البحث الحالي"
    )
    async def scriptroom(
        self,
        interaction: discord.Interaction
    ):

        channel_id = get_setting("search_channel_id")

        if not channel_id:

            await interaction.response.send_message(
                "❌ لم يتم تحديد روم البحث حتى الآن.",
                ephemeral=True
            )

            return

        channel = self.bot.get_channel(
            int(channel_id)
        )

        if not channel:

            await interaction.response.send_message(
                "⚠️ روم البحث المحفوظ لم يعد موجودًا.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"🔎 روم البحث الحالي: {channel.mention}",
            ephemeral=True
        )

    # ========================================================
    # /searchscript
    # ========================================================

    @app_commands.command(
        name="searchscript",
        description="البحث عن لعبة"
    )
    @app_commands.describe(
        game="اسم اللعبة"
    )
    async def searchscript(
        self,
        interaction: discord.Interaction,
        game: str
    ):

        await self.perform_search(
            interaction.channel,
            game,
            interaction.user
        )

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "✅ تم البحث.",
                ephemeral=True
            )

    # ========================================================
    # البحث التلقائي
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):

        # تجاهل البوتات
        if message.author.bot:
            return

        search_channel_id = get_setting(
            "search_channel_id"
        )

        if not search_channel_id:
            return

        try:
            search_channel_id = int(
                search_channel_id
            )
        except ValueError:
            return

        # التأكد أن الرسالة في الروم المحدد
        if message.channel.id != search_channel_id:
            return

        content = message.content.strip()

        if not content:
            return

        game = find_game(content)

        if not game:
            return

        await self.perform_search(
            message.channel,
            game,
            message.author
        )

    # ========================================================
    # تنفيذ البحث
    # ========================================================

    async def perform_search(
        self,
        channel,
        game_name,
        user
    ):

        # لا توجد مواقع
        if not SAFE_SITES:

            embed = discord.Embed(
                title="⚠️ لم يتم إضافة مواقع البحث",
                description=(
                    "صاحب البوت لم يضف مواقع البحث الآمنة "
                    "حتى الآن."
                ),
                color=discord.Color.orange()
            )

            await channel.send(
                embed=embed
            )

            return

        embed = discord.Embed(
            title="🔎 تم العثور على اللعبة",
            description=(
                f"**اللعبة:** `{game_name}`\n\n"
                "اختر الموقع الذي تريد البحث فيه:"
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text=f"طلب البحث بواسطة {user.display_name}"
        )

        view = SearchButtons(game_name)

        await channel.send(
            embed=embed,
            view=view
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):

    await bot.add_cog(
        Bot4(bot)
    )