# ============================================================
# FIME STOCK SYSTEM
# bot6.py
#
# Games:
# 🌱 Grow a Garden
# 🍎 Blox Fruits
# 🥚 Steal An Egg
#
# Features:
# - Live stock polling
# - Personal stock alerts
# - Egg Reset alerts
# - Rift alerts
# - SQLite persistence
# - Discord role compatibility
# - Admin status commands
# ============================================================

import os
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("TOKEN")

DB_FILE = "fime_stock.db"

# ------------------------------------------------------------
# Grow A Garden
# ------------------------------------------------------------

GAG_API_URL = os.getenv(
    "GAG_API_URL",
    "https://gagapi-production.up.railway.app/stock"
)

# ------------------------------------------------------------
# Blox Fruits
# ------------------------------------------------------------

BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    ""
)

# ------------------------------------------------------------
# Checking
# ------------------------------------------------------------

STOCK_CHECK_SECONDS = int(
    os.getenv("STOCK_CHECK_SECONDS", "30")
)

# ------------------------------------------------------------
# Steal An Egg
#
# Community-reported cycles:
# Egg Reset = 5 minutes
# Rift = 30 minutes
# ------------------------------------------------------------

STEAL_EGG_RESET_MINUTES = 5
STEAL_RIFT_MINUTES = 30


# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# DATABASE
# ============================================================

def db_connect():
    return sqlite3.connect(
        DB_FILE
    )


def setup_database():

    db = db_connect()
    cursor = db.cursor()

    # --------------------------------------------------------
    # User stock subscriptions
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            game TEXT NOT NULL,
            item TEXT NOT NULL,

            channel_id INTEGER NOT NULL,

            enabled INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,

            UNIQUE(
                guild_id,
                user_id,
                game,
                item
            )
        )
    """)

    # --------------------------------------------------------
    # Event subscriptions
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,

            event_type TEXT NOT NULL,

            channel_id INTEGER NOT NULL,

            enabled INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,

            UNIQUE(
                guild_id,
                user_id,
                event_type
            )
        )
    """)

    # --------------------------------------------------------
    # Stock cache
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_cache (
            game TEXT PRIMARY KEY,

            stock TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
    """)

    # --------------------------------------------------------
    # Event cache
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_cache (
            event_type TEXT PRIMARY KEY,

            last_event INTEGER NOT NULL
        )
    """)

    db.commit()
    db.close()


# ============================================================
# DATABASE - STOCK SUBSCRIPTIONS
# ============================================================

def add_stock_subscription(
    guild_id,
    user_id,
    game,
    item,
    channel_id
):

    db = db_connect()
    cursor = db.cursor()

    now = datetime.now(
        timezone.utc
    ).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions
        (
            guild_id,
            user_id,
            game,
            item,
            channel_id,
            enabled,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (
        guild_id,
        user_id,
        game,
        item.lower().strip(),
        channel_id,
        now
    ))

    db.commit()
    db.close()


def remove_stock_subscription(
    guild_id,
    user_id,
    game,
    item
):

    db = db_connect()
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
        item.lower().strip()
    ))

    deleted = cursor.rowcount

    db.commit()
    db.close()

    return deleted > 0


def get_user_stock_subscriptions(
    guild_id,
    user_id
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            game,
            item,
            channel_id,
            enabled

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


def get_all_stock_subscriptions():

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            guild_id,
            user_id,
            game,
            item,
            channel_id

        FROM subscriptions

        WHERE enabled = 1
    """)

    rows = cursor.fetchall()

    db.close()

    return rows


# ============================================================
# DATABASE - EVENT SUBSCRIPTIONS
# ============================================================

def add_event_subscription(
    guild_id,
    user_id,
    event_type,
    channel_id
):

    db = db_connect()
    cursor = db.cursor()

    now = datetime.now(
        timezone.utc
    ).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO event_subscriptions
        (
            guild_id,
            user_id,
            event_type,
            channel_id,
            enabled,
            created_at
        )

        VALUES (?, ?, ?, ?, 1, ?)
    """, (
        guild_id,
        user_id,
        event_type,
        channel_id,
        now
    ))

    db.commit()
    db.close()


def remove_event_subscription(
    guild_id,
    user_id,
    event_type
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM event_subscriptions

        WHERE guild_id = ?
        AND user_id = ?
        AND event_type = ?
    """, (
        guild_id,
        user_id,
        event_type
    ))

    deleted = cursor.rowcount

    db.commit()
    db.close()

    return deleted > 0


def get_user_event_subscriptions(
    guild_id,
    user_id
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            event_type,
            channel_id,
            enabled

        FROM event_subscriptions

        WHERE guild_id = ?
        AND user_id = ?

        ORDER BY event_type
    """, (
        guild_id,
        user_id
    ))

    rows = cursor.fetchall()

    db.close()

    return rows


def get_all_event_subscriptions():

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            guild_id,
            user_id,
            event_type,
            channel_id

        FROM event_subscriptions

        WHERE enabled = 1
    """)

    rows = cursor.fetchall()

    db.close()

    return rows


# ============================================================
# CACHE
# ============================================================

def get_cached_stock(game):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT stock
        FROM stock_cache
        WHERE game = ?
    """, (
        game,
    ))

    row = cursor.fetchone()

    db.close()

    if not row:
        return None

    return row[0]


def save_cached_stock(
    game,
    stock
):

    db = db_connect()
    cursor = db.cursor()

    now = datetime.now(
        timezone.utc
    ).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO stock_cache
        (
            game,
            stock,
            updated_at
        )

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

    timeout = aiohttp.ClientTimeout(
        total=15
    )

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                headers={
                    "User-Agent": (
                        "Fime-Stock-Bot/1.0"
                    ),
                    "Accept": "application/json"
                }
            ) as response:

                if response.status != 200:

                    print(
                        f"[API] {url} -> "
                        f"{response.status}"
                    )

                    return None

                return await response.json()

    except asyncio.TimeoutError:

        print(
            f"[API] Timeout: {url}"
        )

        return None

    except Exception as error:

        print(
            f"[API] Error: {error}"
        )

        return None


# ============================================================
# NORMALIZE GROW A GARDEN
# ============================================================

def normalize_gag(data):

    if not data:
        return []

    result = []

    # --------------------------------------------------------
    # API returns list
    # --------------------------------------------------------

    if isinstance(data, list):

        for item in data:

            if isinstance(
                item,
                str
            ):

                result.append(
                    item
                )

            elif isinstance(
                item,
                dict
            ):

                name = (
                    item.get("name")
                    or item.get("item")
                    or item.get("itemName")
                    or item.get("displayName")
                )

                quantity = (
                    item.get("quantity")
                    or item.get("stock")
                    or item.get("amount")
                )

                if name:

                    if quantity is not None:

                        result.append(
                            f"{name} x{quantity}"
                        )

                    else:

                        result.append(
                            str(name)
                        )

    # --------------------------------------------------------
    # API returns object
    # --------------------------------------------------------

    elif isinstance(
        data,
        dict
    ):

        # Common "stock" property

        if isinstance(
            data.get("stock"),
            list
        ):

            return normalize_gag(
                data["stock"]
            )

        # Other possible sections

        sections = [
            "seeds",
            "gear",
            "eggs",
            "eventShop",
            "event_shop",
            "cosmetics",
            "items",
            "honey",
            "travelingMerchant"
        ]

        for section in sections:

            value = data.get(
                section
            )

            if isinstance(
                value,
                list
            ):

                result.extend(
                    normalize_gag(
                        value
                    )
                )

    return result


# ============================================================
# BLOX FRUITS
# ============================================================

def normalize_blox(data):

    if not data:
        return []

    result = []

    if isinstance(
        data,
        list
    ):

        for item in data:

            if isinstance(
                item,
                str
            ):

                result.append(
                    item
                )

            elif isinstance(
                item,
                dict
            ):

                name = (
                    item.get("name")
                    or item.get("fruit")
                    or item.get("item")
                )

                if name:

                    result.append(
                        str(name)
                    )

    elif isinstance(
        data,
        dict
    ):

        # Normal stock

        for key in [
            "normal",
            "stock",
            "fruits",
            "items"
        ]:

            value = data.get(
                key
            )

            if isinstance(
                value,
                list
            ):

                result.extend(
                    normalize_blox(
                        value
                    )
                )

        # Mirage

        mirage = data.get(
            "mirage"
        )

        if isinstance(
            mirage,
            list
        ):

            for item in mirage:

                if isinstance(
                    item,
                    str
                ):

                    result.append(
                        f"Mirage: {item}"
                    )

                elif isinstance(
                    item,
                    dict
                ):

                    name = (
                        item.get("name")
                        or item.get("fruit")
                    )

                    if name:

                        result.append(
                            f"Mirage: {name}"
                        )

    return result


# ============================================================
# GAME FETCHERS
# ============================================================

async def get_grow_a_garden_stock():

    data = await fetch_json(
        GAG_API_URL
    )

    return normalize_gag(
        data
    )


async def get_blox_fruits_stock():

    if not BLOX_API_URL:

        return []

    data = await fetch_json(
        BLOX_API_URL
    )

    return normalize_blox(
        data
    )


# ============================================================
# STEAL AN EGG
# ============================================================

def current_cycle_id(
    minutes
):

    now = datetime.now(
        timezone.utc
    )

    total_minutes = (
        now.hour * 60
        + now.minute
    )

    return (
        total_minutes // minutes
    )


def minutes_until_next_cycle(
    minutes
):

    now = datetime.now(
        timezone.utc
    )

    current_minute = (
        now.hour * 60
        + now.minute
    )

    current_second = (
        now.second
    )

    remainder = (
        current_minute % minutes
    )

    remaining_minutes = (
        minutes - remainder - 1
    )

    remaining_seconds = (
        60 - current_second
    )

    if remaining_seconds == 60:

        remaining_seconds = 0

    total_seconds = (
        remaining_minutes * 60
        + remaining_seconds
    )

    return max(
        0,
        total_seconds
    )


def steal_egg_status():

    now = datetime.now(
        timezone.utc
    )

    egg_id = current_cycle_id(
        STEAL_EGG_RESET_MINUTES
    )

    rift_id = current_cycle_id(
        STEAL_RIFT_MINUTES
    )

    egg_remaining = (
        minutes_until_next_cycle(
            STEAL_EGG_RESET_MINUTES
        )
    )

    rift_remaining = (
        minutes_until_next_cycle(
            STEAL_RIFT_MINUTES
        )
    )

    return {
        "egg_id": egg_id,
        "rift_id": rift_id,
        "egg_remaining": egg_remaining,
        "rift_remaining": rift_remaining,
        "now": now
    }


# ============================================================
# STEAL AN EGG EVENTS
# ============================================================

async def send_event_alerts():

    status = steal_egg_status()

    # --------------------------------------------------------
    # Egg Reset
    # --------------------------------------------------------

    if status["egg_remaining"] <= 2:

        await trigger_event(
            "egg_reset",
            status["egg_id"]
        )

    # --------------------------------------------------------
    # Rift
    # --------------------------------------------------------

    if status["rift_remaining"] <= 2:

        await trigger_event(
            "rift",
            status["rift_id"]
        )


async def trigger_event(
    event_type,
    event_id
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT last_event
        FROM event_cache
        WHERE event_type = ?
    """, (
        event_type,
    ))

    row = cursor.fetchone()

    if row and row[0] == event_id:

        db.close()
        return

    cursor.execute("""
        INSERT OR REPLACE INTO event_cache
        (
            event_type,
            last_event
        )

        VALUES (?, ?)
    """, (
        event_type,
        event_id
    ))

    db.commit()
    db.close()

    subscriptions = (
        get_all_event_subscriptions()
    )

    for (
        guild_id,
        user_id,
        subscribed_event,
        channel_id
    ) in subscriptions:

        if subscribed_event != event_type:
            continue

        channel = bot.get_channel(
            channel_id
        )

        if not channel:
            continue

        user = bot.get_user(
            user_id
        )

        if user:

            mention = user.mention

        else:

            mention = (
                f"<@{user_id}>"
            )

        if event_type == "egg_reset":

            title = (
                "🥚 Egg Reset"
            )

            description = (
                f"{mention}\n\n"
                "🔔 حان وقت دورة البيض "
                "المتوقعة في Steal An Egg."
            )

        else:

            title = (
                "🌀 Rift"
            )

            description = (
                f"{mention}\n\n"
                "🌀 حان وقت دورة Rift "
                "المتوقعة في Steal An Egg."
            )

        embed = discord.Embed(
            title=title,
            description=description,
            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.set_footer(
            text=(
                "Fime • Steal An Egg"
            )
        )

        try:

            await channel.send(
                embed=embed
            )

        except Exception as error:

            print(
                f"[EVENT SEND ERROR] "
                f"{error}"
            )


# ============================================================
# STOCK ALERT PROCESSOR
# ============================================================

async def process_stock(
    game,
    stock
):

    if not stock:
        return

    current = set(
        stock
    )

    current_text = "\n".join(
        sorted(current)
    )

    previous_text = (
        get_cached_stock(
            game
        )
    )

    # First run:
    # cache only.
    if previous_text is None:

        save_cached_stock(
            game,
            current_text
        )

        print(
            f"[CACHE] {game}"
        )

        return

    previous = set(
        previous_text.splitlines()
    )

    added = (
        current - previous
    )

    if not added:

        return

    save_cached_stock(
        game,
        current_text
    )

    subscriptions = (
        get_all_stock_subscriptions()
    )

    for (
        guild_id,
        user_id,
        subscribed_game,
        wanted_item,
        channel_id
    ) in subscriptions:

        if subscribed_game != game:
            continue

        matches = []

        wanted = (
            wanted_item.lower()
        )

        for item in added:

            if wanted in item.lower():

                matches.append(
                    item
                )

        if not matches:
            continue

        channel = bot.get_channel(
            channel_id
        )

        if not channel:
            continue

        user = bot.get_user(
            user_id
        )

        if user:

            mention = user.mention

        else:

            mention = (
                f"<@{user_id}>"
            )

        embed = discord.Embed(
            title="🚨 Stock Alert",
            description=(
                f"{mention}\n\n"
                + "\n".join(
                    f"🟢 {item}"
                    for item in matches
                )
            ),
            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.set_footer(
            text="Fime Stock Alerts"
        )

        try:

            await channel.send(
                embed=embed
            )

        except Exception as error:

            print(
                f"[STOCK SEND ERROR] "
                f"{error}"
            )


# ============================================================
# STOCK LOOP
# ============================================================

@tasks.loop(
    seconds=STOCK_CHECK_SECONDS
)
async def stock_loop():

    # --------------------------------------------------------
    # Grow A Garden
    # --------------------------------------------------------

    try:

        gag_stock = (
            await get_grow_a_garden_stock()
        )

        await process_stock(
            "growagarden",
            gag_stock
        )

    except Exception as error:

        print(
            f"[GAG ERROR] {error}"
        )

    # --------------------------------------------------------
    # Blox Fruits
    # --------------------------------------------------------

    try:

        blox_stock = (
            await get_blox_fruits_stock()
        )

        await process_stock(
            "bloxfruits",
            blox_stock
        )

    except Exception as error:

        print(
            f"[BLOX ERROR] {error}"
        )

    # --------------------------------------------------------
    # Steal An Egg events
    # --------------------------------------------------------

    try:

        await send_event_alerts()

    except Exception as error:

        print(
            f"[STEAL EGG ERROR] "
            f"{error}"
        )


@stock_loop.before_loop
async def before_stock_loop():

    await bot.wait_until_ready()


# ============================================================
# /stock
# ============================================================

@bot.tree.command(
    name="stock",
    description="عرض المخزون المتوفر"
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
        )
    ]
)
async def stock_command(
    interaction: discord.Interaction,
    game: app_commands.Choice[str]
):

    await interaction.response.defer()

    if game.value == "growagarden":

        stock = (
            await get_grow_a_garden_stock()
        )

    else:

        stock = (
            await get_blox_fruits_stock()
        )

    if not stock:

        await interaction.followup.send(
            "⚠️ ما قدرت أجيب الـStock حاليًا."
        )

        return

    text = "\n".join(
        f"• {item}"
        for item in stock[:50]
    )

    embed = discord.Embed(
        title=game.name,
        description=text,
        timestamp=datetime.now(
            timezone.utc
        )
    )

    embed.set_footer(
        text="Fime Stock"
    )

    await interaction.followup.send(
        embed=embed
    )


# ============================================================
# /steal-egg
# ============================================================

@bot.tree.command(
    name="steal-egg",
    description="عرض مواعيد Steal An Egg المتوقعة"
)
async def steal_egg(
    interaction: discord.Interaction
):

    status = steal_egg_status()

    egg_minutes = (
        status["egg_remaining"] // 60
    )

    egg_seconds = (
        status["egg_remaining"] % 60
    )

    rift_minutes = (
        status["rift_remaining"] // 60
    )

    rift_seconds = (
        status["rift_remaining"] % 60
    )

    embed = discord.Embed(
        title="🥚 Steal An Egg",
        description=(
            "التوقيتات التالية تقديرية "
            "ومبنية على دورة المجتمع.\n\n"

            f"🥚 **Egg Reset**\n"
            f"`{egg_minutes:02d}:"
            f"{egg_seconds:02d}`\n\n"

            f"🌀 **Rift**\n"
            f"`{rift_minutes:02d}:"
            f"{rift_seconds:02d}`"
        ),
        timestamp=datetime.now(
            timezone.utc
        )
    )

    embed.set_footer(
        text="Fime • Steal An Egg"
    )

    await interaction.response.send_message(
        embed=embed
    )


# ============================================================
# /stock-alert
# ============================================================

@bot.tree.command(
    name="stock-alert",
    description="الاشتراك بتنبيه عنصر معين"
)
@app_commands.describe(
    game="اللعبة",
    item="اسم الفاكهة أو الغرض",
    channel="روم التنبيه"
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
        )
    ]
)
async def stock_alert(
    interaction: discord.Interaction,
    game: app_commands.Choice[str],
    item: str,
    channel: discord.TextChannel
):

    if not interaction.guild:

        await interaction.response.send_message(
            "❌ هذا الأمر داخل السيرفر فقط.",
            ephemeral=True
        )

        return

    add_stock_subscription(
        interaction.guild.id,
        interaction.user.id,
        game.value,
        item,
        channel.id
    )

    await interaction.response.send_message(
        (
            "✅ تم الاشتراك.\n\n"
            f"🎮 **اللعبة:** {game.name}\n"
            f"📦 **العنصر:** {item}\n"
            f"📢 **الروم:** {channel.mention}"
        ),
        ephemeral=True
    )


# ============================================================
# /stock-alert-remove
# ============================================================

@bot.tree.command(
    name="stock-alert-remove",
    description="إلغاء تنبيه عنصر"
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
        )
    ]
)
async def stock_alert_remove(
    interaction: discord.Interaction,
    game: app_commands.Choice[str],
    item: str
):

    if not interaction.guild:
        return

    removed = remove_stock_subscription(
        interaction.guild.id,
        interaction.user.id,
        game.value,
        item
    )

    if removed:

        message = (
            f"🗑️ تم حذف تنبيه **{item}**."
        )

    else:

        message = (
            "⚠️ ما لقيت اشتراك بهذا الاسم."
        )

    await interaction.response.send_message(
        message,
        ephemeral=True
    )


# ============================================================
# /stock-alerts
# ============================================================

@bot.tree.command(
    name="stock-alerts",
    description="عرض تنبيهاتك"
)
async def stock_alerts(
    interaction: discord.Interaction
):

    if not interaction.guild:
        return

    stock_rows = (
        get_user_stock_subscriptions(
            interaction.guild.id,
            interaction.user.id
        )
    )

    event_rows = (
        get_user_event_subscriptions(
            interaction.guild.id,
            interaction.user.id
        )
    )

    if not stock_rows and not event_rows:

        await interaction.response.send_message(
            "📭 ما عندك أي تنبيهات.",
            ephemeral=True
        )

        return

    lines = []

    for (
        game,
        item,
        channel_id,
        enabled
    ) in stock_rows:

        game_name = {
            "growagarden":
                "🌱 Grow a Garden",
            "bloxfruits":
                "🍎 Blox Fruits"
        }.get(
            game,
            game
        )

        lines.append(
            f"📦 {game_name} — "
            f"`{item}` — <#{channel_id}>"
        )

    for (
        event_type,
        channel_id,
        enabled
    ) in event_rows:

        event_name = {
            "egg_reset":
                "🥚 Egg Reset",
            "rift":
                "🌀 Rift"
        }.get(
            event_type,
            event_type
        )

        lines.append(
            f"🔔 {event_name} — "
            f"<#{channel_id}>"
        )

    embed = discord.Embed(
        title="🔔 تنبيهاتك",
        description="\n".join(
            lines
        )
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# /steal-alert
# ============================================================

@bot.tree.command(
    name="steal-alert",
    description="الاشتراك بتنبيه Steal An Egg"
)
@app_commands.describe(
    event="نوع التنبيه",
    channel="روم التنبيه"
)
@app_commands.choices(
    event=[
        app_commands.Choice(
            name="🥚 Egg Reset",
            value="egg_reset"
        ),
        app_commands.Choice(
            name="🌀 Rift",
            value="rift"
        )
    ]
)
async def steal_alert(
    interaction: discord.Interaction,
    event: app_commands.Choice[str],
    channel: discord.TextChannel
):

    if not interaction.guild:
        return

    add_event_subscription(
        interaction.guild.id,
        interaction.user.id,
        event.value,
        channel.id
    )

    event_name = {
        "egg_reset":
            "🥚 Egg Reset",
        "rift":
            "🌀 Rift"
    }.get(
        event.value,
        event.value
    )

    await interaction.response.send_message(
        (
            "✅ تم تفعيل التنبيه.\n\n"
            f"🔔 **النوع:** {event_name}\n"
            f"📢 **الروم:** {channel.mention}"
        ),
        ephemeral=True
    )


# ============================================================
# /steal-alert-remove
# ============================================================

@bot.tree.command(
    name="steal-alert-remove",
    description="إلغاء تنبيه Steal An Egg"
)
@app_commands.describe(
    event="نوع التنبيه"
)
@app_commands.choices(
    event=[
        app_commands.Choice(
            name="🥚 Egg Reset",
            value="egg_reset"
        ),
        app_commands.Choice(
            name="🌀 Rift",
            value="rift"
        )
    ]
)
async def steal_alert_remove(
    interaction: discord.Interaction,
    event: app_commands.Choice[str]
):

    if not interaction.guild:
        return

    removed = remove_event_subscription(
        interaction.guild.id,
        interaction.user.id,
        event.value
    )

    if removed:

        message = (
            "🗑️ تم إلغاء التنبيه."
        )

    else:

        message = (
            "⚠️ ما عندك هذا التنبيه."
        )

    await interaction.response.send_message(
        message,
        ephemeral=True
    )


# ============================================================
# /stock-status
# ============================================================

@bot.tree.command(
    name="stock-status",
    description="فحص حالة نظام الـStock"
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

    gag = (
        await get_grow_a_garden_stock()
    )

    blox = (
        await get_blox_fruits_stock()
    )

    steal = steal_egg_status()

    gag_status = (
        f"🟢 {len(gag)} عنصر"
        if gag
        else
        "🔴 لا توجد بيانات"
    )

    blox_status = (
        f"🟢 {len(blox)} عنصر"
        if blox
        else
        "🟡 المصدر غير مضبوط"
    )

    steal_status = (
        "🟢 المؤقت يعمل"
    )

    embed = discord.Embed(
        title="📊 Fime Stock Status",
        description=(
            f"🌱 **Grow a Garden:** "
            f"{gag_status}\n\n"

            f"🍎 **Blox Fruits:** "
            f"{blox_status}\n\n"

            f"🥚 **Steal An Egg:** "
            f"{steal_status}"
        )
    )

    await interaction.followup.send(
        embed=embed,
        ephemeral=True
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    setup_database()

    print(
        "================================"
    )

    print(
        f"🤖 Logged in as {bot.user}"
    )

    print(
        f"🆔 ID: {bot.user.id}"
    )

    try:

        synced = (
            await bot.tree.sync()
        )

        print(
            f"✅ Synced {len(synced)} commands"
        )

    except Exception as error:

        print(
            f"❌ Sync error: {error}"
        )

    if not stock_loop.is_running():

        stock_loop.start()

        print(
            "📦 Stock loop started"
        )

    print(
        "================================"
    )


# ============================================================
# ERRORS
# ============================================================

@stock_status.error
async def stock_status_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        message = (
            "❌ تحتاج صلاحية "
            "**Manage Server**."
        )

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True
            )

        else:

            await interaction.response.send_message(
                message,
                ephemeral=True
            )


# ============================================================
# START
# ============================================================

if not TOKEN:

    raise RuntimeError(
        "❌ TOKEN غير موجود في "
        "Environment Variables."
    )


setup_database()

bot.run(TOKEN)