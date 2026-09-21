# ============================================================
# Fime Stock Alerts
# bot6.py
# ============================================================

import os
import sqlite3
import asyncio
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("TOKEN")

# رابط Grow a Garden API
# غيّره من Environment Variables إذا استخدمت API مختلف.
GAG_API_URL = os.getenv(
    "GAG_API_URL",
    "https://gagapi-production.up.railway.app/stock"
)

# رابط Blox Fruits API
# هذا متغير حتى نقدر نبدله إذا تغير المصدر.
BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    ""
)

CHECK_INTERVAL = 60  # ثانية

DB_FILE = "stock_alerts.db"


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# DATABASE
# ============================================================

def get_db():
    return sqlite3.connect(DB_FILE)


def setup_database():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            item TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            enabled INTEGER DEFAULT 1,
            UNIQUE(guild_id, user_id, game, item)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            game TEXT PRIMARY KEY,
            stock TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    db.commit()
    db.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def add_subscription(
    guild_id: int,
    user_id: int,
    game: str,
    item: str,
    channel_id: int
):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions
        (guild_id, user_id, game, item, channel_id, enabled)
        VALUES (?, ?, ?, ?, ?, 1)
    """, (
        guild_id,
        user_id,
        game,
        item.lower(),
        channel_id
    ))

    db.commit()
    db.close()


def remove_subscription(
    guild_id: int,
    user_id: int,
    game: str,
    item: str
):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM subscriptions
        WHERE guild_id = ?
        AND user_id = ?
        AND game = ?
        AND item = ?
    """, (
        guild_id,
        user_id,
        game,
        item.lower()
    ))

    db.commit()
    db.close()


def get_user_subscriptions(
    guild_id: int,
    user_id: int
):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT game, item, channel_id, enabled
        FROM subscriptions
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY game, item
    """, (
        guild_id,
        user_id
    ))

    rows = cursor.fetchall()

    db.close()

    return rows


def get_all_subscriptions():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT guild_id, user_id, game, item, channel_id
        FROM subscriptions
        WHERE enabled = 1
    """)

    rows = cursor.fetchall()

    db.close()

    return rows


# ============================================================
# CACHE
# ============================================================

def get_cached_stock(game):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT stock
        FROM cache
        WHERE game = ?
    """, (game,))

    row = cursor.fetchone()

    db.close()

    if not row:
        return None

    return row[0]


def save_cached_stock(game, stock):
    db = get_db()
    cursor = db.cursor()

    now = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO cache
        (game, stock, updated_at)
        VALUES (?, ?, ?)
    """, (
        game,
        stock,
        now
    ))

    db.commit()
    db.close()


# ============================================================
# HTTP
# ============================================================

async def fetch_json(url):
    if not url:
        return None

    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                headers={
                    "User-Agent": "FimeStockBot/1.0"
                }
            ) as response:

                if response.status != 200:
                    print(
                        f"[HTTP] {url} -> {response.status}"
                    )
                    return None

                return await response.json()

    except Exception as error:
        print(
            f"[HTTP ERROR] {url}: {error}"
        )
        return None


# ============================================================
# NORMALIZE STOCK
# ============================================================

def normalize_grow_garden(data):
    """
    نحاول تحويل أكثر من شكل JSON
    إلى قائمة أسماء عناصر.
    """

    if not data:
        return []

    result = []

    if isinstance(data, list):

        for item in data:

            if isinstance(item, str):
                result.append(item)

            elif isinstance(item, dict):

                name = (
                    item.get("name")
                    or item.get("item")
                    or item.get("itemName")
                )

                quantity = (
                    item.get("quantity")
                    or item.get("stock")
                    or item.get("amount")
                )

                if name:
                    if quantity is not None:
                        result.append(
                            f"{name} ({quantity})"
                        )
                    else:
                        result.append(name)

    elif isinstance(data, dict):

        # بعض APIs ترجع:
        # {"stock": [...]}

        stock = data.get("stock")

        if isinstance(stock, list):
            return normalize_grow_garden(stock)

        # أو:
        # {"seeds": [...], "gear": [...]}

        for key in (
            "seeds",
            "gear",
            "eggs",
            "cosmetics",
            "eventShop",
            "items"
        ):

            value = data.get(key)

            if isinstance(value, list):
                result.extend(
                    normalize_grow_garden(value)
                )

    return result


def normalize_blox_fruits(data):
    """
    يحول بيانات Blox Fruits
    إلى قائمة أسماء الفواكه.
    """

    if not data:
        return []

    result = []

    if isinstance(data, dict):

        normal = data.get("normal")
        mirage = data.get("mirage")

        if isinstance(normal, list):
            for fruit in normal:

                if isinstance(fruit, dict):
                    name = fruit.get("name")

                    if name:
                        result.append(
                            f"Normal: {name}"
                        )

                elif isinstance(fruit, str):
                    result.append(
                        f"Normal: {fruit}"
                    )

        if isinstance(mirage, list):
            for fruit in mirage:

                if isinstance(fruit, dict):
                    name = fruit.get("name")

                    if name:
                        result.append(
                            f"Mirage: {name}"
                        )

                elif isinstance(fruit, str):
                    result.append(
                        f"Mirage: {fruit}"
                    )

    return result


# ============================================================
# GAME FETCHERS
# ============================================================

async def get_grow_a_garden_stock():

    data = await fetch_json(
        GAG_API_URL
    )

    return normalize_grow_garden(data)


async def get_blox_fruits_stock():

    if not BLOX_API_URL:
        return []

    data = await fetch_json(
        BLOX_API_URL
    )

    return normalize_blox_fruits(data)


async def get_game_stock(game):

    if game == "growagarden":
        return await get_grow_a_garden_stock()

    if game == "bloxfruits":
        return await get_blox_fruits_stock()

    # Steal An Egg:
    # لا يوجد مصدر Stock موثوق موصل هنا حاليًا.
    if game == "stealanegg":
        return []

    return []


# ============================================================
# ALERT SYSTEM
# ============================================================

async def process_stock_change(
    game,
    new_stock
):

    if not new_stock:
        return

    new_stock_text = "\n".join(
        sorted(new_stock)
    )

    old_stock_text = get_cached_stock(
        game
    )

    # أول تشغيل:
    # نحفظ فقط بدون إرسال آلاف التنبيهات.
    if old_stock_text is None:

        save_cached_stock(
            game,
            new_stock_text
        )

        print(
            f"[STOCK] Initial cache: {game}"
        )

        return

    old_stock = set(
        old_stock_text.splitlines()
    )

    current_stock = set(
        new_stock
    )

    added = current_stock - old_stock

    if not added:
        return

    save_cached_stock(
        game,
        new_stock_text
    )

    subscriptions = get_all_subscriptions()

    for (
        guild_id,
        user_id,
        sub_game,
        item,
        channel_id
    ) in subscriptions:

        if sub_game != game:
            continue

        wanted = item.lower()

        matched = []

        for stock_item in added:

            if wanted in stock_item.lower():
                matched.append(stock_item)

        if not matched:
            continue

        channel = bot.get_channel(
            channel_id
        )

        if channel is None:
            continue

        user = bot.get_user(
            user_id
        )

        mention = (
            user.mention
            if user
            else f"<@{user_id}>"
        )

        embed = discord.Embed(
            title="🚨 توفر عنصر جديد!",
            description=(
                f"{mention}\n\n"
                + "\n".join(
                    f"🟢 {x}"
                    for x in matched
                )
            ),
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_footer(
            text="Fime Stock Alerts"
        )

        try:
            await channel.send(
                embed=embed
            )

        except discord.HTTPException as error:
            print(
                f"[DISCORD ERROR] {error}"
            )


# ============================================================
# STOCK LOOP
# ============================================================

@tasks.loop(seconds=CHECK_INTERVAL)
async def stock_checker():

    games = [
        "growagarden",
        "bloxfruits",
        "stealanegg"
    ]

    for game in games:

        try:

            stock = await get_game_stock(
                game
            )

            await process_stock_change(
                game,
                stock
            )

        except Exception as error:

            print(
                f"[CHECK ERROR] {game}: {error}"
            )


@stock_checker.before_loop
async def before_stock_checker():

    await bot.wait_until_ready()


# ============================================================
# /stock
# ============================================================

@bot.tree.command(
    name="stock",
    description="عرض آخر بيانات المخزون المتاحة"
)
@app_commands.describe(
    game="اختر اللعبة"
)
@app_commands.choices(
    game=[
        app_commands.Choice(
            name="🌱 Grow a Garden",
            value="growagarden"
        ),
        app_commands.Choice(
            name="🍎 Blox Fruits",
            value="bloxfruits"
        ),
        app_commands.Choice(
            name="🥚 Steal An Egg",
            value="stealanegg"
        )
    ]
)
async def stock_command(
    interaction: discord.Interaction,
    game: app_commands.Choice[str]
):

    await interaction.response.defer()

    stock = await get_game_stock(
        game.value
    )

    if not stock:

        await interaction.followup.send(
            "⚠️ ما قدرت أجيب مخزون اللعبة حاليًا."
        )

        return

    text = "\n".join(
        f"• {item}"
        for item in stock[:40]
    )

    embed = discord.Embed(
        title=f"🛒 {game.name}",
        description=text,
        timestamp=datetime.now(timezone.utc)
    )

    embed.set_footer(
        text="Fime Stock"
    )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# /stock_alert
# ============================================================

@bot.tree.command(
    name="stock-alert",
    description="اشترك بتنبيه عند توفر عنصر معين"
)
@app_commands.describe(
    game="اللعبة",
    item="اسم الفاكهة أو الغرض",
    channel="الروم الذي تصلك فيه التنبيهات"
)
@app_commands.choices(
    game=[
        app_commands.Choice(
            name="🌱 Grow a Garden",
            value="growagarden"
        ),
        app_commands.Choice(
            name="🍎 Blox Fruits",
            value="bloxfruits"
        ),
        app_commands.Choice(
            name="🥚 Steal An Egg",
            value="stealanegg"
        )
    ]
)
async def stock_alert(
    interaction: discord.Interaction,
    game: app_commands.Choice[str],
    item: str,
    channel: discord.TextChannel
):

    if interaction.guild is None:

        await interaction.response.send_message(
            "هذا الأمر داخل السيرفر فقط.",
            ephemeral=True
        )

        return

    add_subscription(
        interaction.guild.id,
        interaction.user.id,
        game.value,
        item,
        channel.id
    )

    await interaction.response.send_message(
        (
            "✅ تم الاشتراك!\n\n"
            f"🎮 اللعبة: **{game.name}**\n"
            f"📦 العنصر: **{item}**\n"
            f"📢 التنبيهات: {channel.mention}"
        ),
        ephemeral=True
    )


# ============================================================
# /stock-alert-remove
# ============================================================

@bot.tree.command(
    name="stock-alert-remove",
    description="إلغاء تنبيه عنصر معين"
)
@app_commands.describe(
    game="اللعبة",
    item="اسم العنصر"
)
@app_commands.choices(
    game=[
        app_commands.Choice(
            name="🌱 Grow a Garden",
            value="growagarden"
        ),
        app_commands.Choice(
            name="🍎 Blox Fruits",
            value="bloxfruits"
        ),
        app_commands.Choice(
            name="🥚 Steal An Egg",
            value="stealanegg"
        )
    ]
)
async def stock_alert_remove(
    interaction: discord.Interaction,
    game: app_commands.Choice[str],
    item: str
):

    if interaction.guild is None:
        return

    remove_subscription(
        interaction.guild.id,
        interaction.user.id,
        game.value,
        item
    )

    await interaction.response.send_message(
        (
            "🗑️ تم إلغاء الاشتراك.\n"
            f"**{item}** — {game.name}"
        ),
        ephemeral=True
    )


# ============================================================
# /my-alerts
# ============================================================

@bot.tree.command(
    name="my-alerts",
    description="عرض اشتراكاتك في تنبيهات المخزون"
)
async def my_alerts(
    interaction: discord.Interaction
):

    if interaction.guild is None:
        return

    rows = get_user_subscriptions(
        interaction.guild.id,
        interaction.user.id
    )

    if not rows:

        await interaction.response.send_message(
            "📭 ما عندك أي تنبيهات مفعلة.",
            ephemeral=True
        )

        return

    lines = []

    for game, item, channel_id, enabled in rows:

        game_name = {
            "growagarden": "🌱 Grow a Garden",
            "bloxfruits": "🍎 Blox Fruits",
            "stealanegg": "🥚 Steal An Egg"
        }.get(game, game)

        lines.append(
            f"• **{game_name}** — `{item}` — <#{channel_id}>"
        )

    embed = discord.Embed(
        title="🔔 تنبيهاتك",
        description="\n".join(lines)
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# /stock-status
# ============================================================

@bot.tree.command(
    name="stock-status",
    description="فحص حالة مصادر المخزون"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def stock_status(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    results = []

    for game in (
        "growagarden",
        "bloxfruits",
        "stealanegg"
    ):

        stock = await get_game_stock(
            game
        )

        if stock:
            results.append(
                f"🟢 **{game}** — {len(stock)} عنصر"
            )
        else:
            results.append(
                f"🔴 **{game}** — لا توجد بيانات"
            )

    await interaction.followup.send(
        "\n".join(results),
        ephemeral=True
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    setup_database()

    try:
        synced = await bot.tree.sync()

        print(
            f"✅ Logged in as {bot.user}"
        )

        print(
            f"✅ Synced {len(synced)} slash commands"
        )

    except Exception as error:

        print(
            f"❌ Slash command sync error: {error}"
        )

    if not stock_checker.is_running():

        stock_checker.start()

        print(
            "📦 Stock checker started"
        )


# ============================================================
# ERROR HANDLER
# ============================================================

@stock_status.error
async def stock_status_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        if interaction.response.is_done():
            await interaction.followup.send(
                "❌ تحتاج صلاحية إدارة السيرفر.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ تحتاج صلاحية إدارة السيرفر.",
                ephemeral=True
            )


# ============================================================
# START
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "❌ TOKEN غير موجود في Environment Variables."
    )


setup_database()

bot.run(TOKEN)