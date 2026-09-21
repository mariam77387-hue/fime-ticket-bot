# ============================================================
# FIME STOCK SYSTEM
# bot6.py
#
# Games:
# 🌱 Grow a Garden
# 🍎 Blox Fruits
# 🥚 Steal An Egg
#
# FEATURES:
# - Live stock polling
# - Automatic shop posting
# - Custom shop channel per guild/game
# - Personal stock alerts
# - Egg Reset alerts
# - Rift alerts
# - SQLite persistence
# - Discord role compatibility
# - Admin status commands
#
# IMPORTANT:
# This is a Discord.py EXTENSION.
#
# bot.py must load it using:
#
#     await bot.load_extension("bot6")
#
# DO NOT use bot.run() in this file.
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
# Stock checking interval
# ------------------------------------------------------------

STOCK_CHECK_SECONDS = int(
    os.getenv(
        "STOCK_CHECK_SECONDS",
        "30"
    )
)

# ------------------------------------------------------------
# Steal An Egg
#
# Community-reported/predicted cycles:
# Egg Reset = 5 minutes
# Rift = 30 minutes
#
# These are not official live API values.
# ------------------------------------------------------------

STEAL_EGG_RESET_MINUTES = 5
STEAL_RIFT_MINUTES = 30


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

    # ========================================================
    # PERSONAL STOCK SUBSCRIPTIONS
    # ========================================================

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

    # ========================================================
    # EVENT SUBSCRIPTIONS
    # ========================================================

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

    # ========================================================
    # STOCK CACHE
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_cache (

            game TEXT PRIMARY KEY,

            stock TEXT NOT NULL,

            updated_at TEXT NOT NULL
        )
    """)

    # ========================================================
    # EVENT CACHE
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_cache (

            event_type TEXT PRIMARY KEY,

            last_event INTEGER NOT NULL
        )
    """)

    # ========================================================
    # AUTOMATIC SHOP CHANNELS
    #
    # One channel per guild per game.
    #
    # Example:
    #
    # Guild 123
    # Grow A Garden -> Channel 555
    # Blox Fruits   -> Channel 777
    # ========================================================

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_channels (

            guild_id INTEGER NOT NULL,

            game TEXT NOT NULL,

            channel_id INTEGER NOT NULL,

            enabled INTEGER DEFAULT 1,

            created_at TEXT NOT NULL,

            PRIMARY KEY(
                guild_id,
                game
            )
        )
    """)

    db.commit()
    db.close()


# ============================================================
# DATABASE
# STOCK SUBSCRIPTIONS
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
# DATABASE
# EVENT SUBSCRIPTIONS
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
# DATABASE
# SHOP CHANNELS
# ============================================================

def set_shop_channel(
    guild_id,
    game,
    channel_id
):

    db = db_connect()
    cursor = db.cursor()

    now = datetime.now(
        timezone.utc
    ).isoformat()

    cursor.execute("""
        INSERT OR REPLACE INTO shop_channels
        (
            guild_id,
            game,
            channel_id,
            enabled,
            created_at
        )

        VALUES (?, ?, ?, 1, ?)
    """, (
        guild_id,
        game,
        channel_id,
        now
    ))

    db.commit()
    db.close()


def remove_shop_channel(
    guild_id,
    game
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        DELETE FROM shop_channels

        WHERE guild_id = ?
        AND game = ?
    """, (
        guild_id,
        game
    ))

    deleted = cursor.rowcount

    db.commit()
    db.close()

    return deleted > 0


def get_shop_channel(
    guild_id,
    game
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            channel_id

        FROM shop_channels

        WHERE guild_id = ?
        AND game = ?
        AND enabled = 1
    """, (
        guild_id,
        game
    ))

    row = cursor.fetchone()

    db.close()

    if not row:
        return None

    return row[0]


def get_all_shop_channels(
    game
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            guild_id,
            channel_id

        FROM shop_channels

        WHERE game = ?
        AND enabled = 1
    """, (
        game
    ))

    rows = cursor.fetchall()

    db.close()

    return rows


# ============================================================
# CACHE
# ============================================================

def get_cached_stock(
    game
):

    db = db_connect()
    cursor = db.cursor()

    cursor.execute("""
        SELECT
            stock

        FROM stock_cache

        WHERE game = ?
    """, (
        game
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

async def fetch_json(
    url
):

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
                    "User-Agent":
                        "Fime-Stock-Bot/1.0",

                    "Accept":
                        "application/json"
                }
            ) as response:

                if response.status != 200:

                    print(
                        f"[API] {url} -> "
                        f"{response.status}"
                    )

                    return None

                try:

                    return await response.json(
                        content_type=None
                    )

                except Exception:

                    text = await response.text()

                    print(
                        f"[API] Invalid JSON: "
                        f"{text[:200]}"
                    )

                    return None

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
# NORMALIZE
# GROW A GARDEN
# ============================================================

def normalize_gag(
    data
):

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
                    or item.get("item")
                    or item.get("itemName")
                    or item.get("displayName")
                )

                quantity = (
                    item.get("quantity")
                    if item.get("quantity") is not None
                    else item.get("stock")
                )

                if quantity is None:

                    quantity = item.get(
                        "amount"
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

    elif isinstance(
        data,
        dict
    ):

        stock = data.get(
            "stock"
        )

        if isinstance(
            stock,
            list
        ):

            result.extend(
                normalize_gag(
                    stock
                )
            )

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

    return list(
        dict.fromkeys(
            result
        )
    )


# ============================================================
# NORMALIZE
# BLOX FRUITS
# ============================================================

def normalize_blox(
    data
):

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

    return list(
        dict.fromkeys(
            result
        )
    )


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


def seconds_until_next_cycle(
    minutes
):

    now = datetime.now(
        timezone.utc
    )

    total_seconds = (
        now.hour * 3600
        + now.minute * 60
        + now.second
    )

    cycle_seconds = (
        minutes * 60
    )

    remainder = (
        total_seconds % cycle_seconds
    )

    return (
        cycle_seconds - remainder
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
        seconds_until_next_cycle(
            STEAL_EGG_RESET_MINUTES
        )
    )

    rift_remaining = (
        seconds_until_next_cycle(
            STEAL_RIFT_MINUTES
        )
    )

    return {

        "egg_id":
            egg_id,

        "rift_id":
            rift_id,

        "egg_remaining":
            egg_remaining,

        "rift_remaining":
            rift_remaining,

        "now":
            now
    }


# ============================================================
# STOCK SYSTEM
# ============================================================

class FimeStock(
    commands.Cog
):

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        setup_database()

        print(
            "📦 Fime Stock System initialized."
        )

    # ========================================================
    # COG LOAD
    # ========================================================

    async def cog_load(
        self
    ):

        setup_database()

        if not self.stock_loop.is_running():

            self.stock_loop.start()

            print(
                "📦 Fime Stock loop started."
            )

    # ========================================================
    # COG UNLOAD
    # ========================================================

    def cog_unload(
        self
    ):

        if self.stock_loop.is_running():

            self.stock_loop.cancel()

            print(
                "🛑 Fime Stock loop stopped."
            )

    # ========================================================
    # GAME NAME
    # ========================================================

    @staticmethod
    def game_name(
        game
    ):

        return {

            "growagarden":
                "🌱 Grow a Garden",

            "bloxfruits":
                "🍎 Blox Fruits"

        }.get(
            game,
            game
        )

    # ========================================================
    # SEND AUTOMATIC SHOP
    # ========================================================

    async def send_shop_update(
        self,
        game,
        stock
    ):

        if not stock:

            return

        channels = get_all_shop_channels(
            game
        )

        if not channels:

            return

        game_name = self.game_name(
            game
        )

        # ----------------------------------------------------
        # Build stock text
        # ----------------------------------------------------

        lines = []

        for item in stock[:100]:

            lines.append(
                f"🟢 {item}"
            )

        description = "\n".join(
            lines
        )

        # ----------------------------------------------------
        # Discord embed limit protection
        # ----------------------------------------------------

        if len(description) > 3900:

            description = (
                description[:3890]
                + "\n..."
            )

        embed = discord.Embed(

            title=(
                f"🛒 {game_name} — Shop Update"
            ),

            description=description,

            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.set_footer(
            text=(
                "Fime Stock • "
                "تم تحديث الشوب تلقائيًا"
            )
        )

        # ----------------------------------------------------
        # Send to every configured guild channel
        # ----------------------------------------------------

        for (
            guild_id,
            channel_id
        ) in channels:

            channel = self.bot.get_channel(
                channel_id
            )

            if not channel:

                print(
                    f"[SHOP] Channel not found: "
                    f"{channel_id}"
                )

                continue

            try:

                await channel.send(
                    embed=embed
                )

                print(
                    f"[SHOP] Sent {game} update "
                    f"to guild {guild_id}"
                )

            except discord.Forbidden:

                print(
                    f"[SHOP] Missing permission "
                    f"in channel {channel_id}"
                )

            except discord.NotFound:

                print(
                    f"[SHOP] Channel deleted: "
                    f"{channel_id}"
                )

            except Exception as error:

                print(
                    f"[SHOP SEND ERROR] "
                    f"{error}"
                )

    # ========================================================
    # EVENT ALERTS
    # ========================================================

    async def send_event_alerts(
        self
    ):

        status = steal_egg_status()

        # ----------------------------------------------------
        # Egg Reset
        # ----------------------------------------------------

        if status["egg_remaining"] <= 60:

            await self.trigger_event(
                "egg_reset",
                status["egg_id"]
            )

        # ----------------------------------------------------
        # Rift
        # ----------------------------------------------------

        if status["rift_remaining"] <= 60:

            await self.trigger_event(
                "rift",
                status["rift_id"]
            )

    # ========================================================
    # TRIGGER EVENT
    # ========================================================

    async def trigger_event(
        self,
        event_type,
        event_id
    ):

        db = db_connect()
        cursor = db.cursor()

        cursor.execute("""
            SELECT
                last_event

            FROM event_cache

            WHERE event_type = ?
        """, (
            event_type
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

            channel = self.bot.get_channel(
                channel_id
            )

            if not channel:

                continue

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
                text="Fime • Steal An Egg"
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

    # ========================================================
    # PROCESS STOCK
    # ========================================================

    async def process_stock(
        self,
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

        # ----------------------------------------------------
        # FIRST RUN
        #
        # Cache only.
        #
        # This prevents the bot from sending a shop message
        # immediately when it starts.
        # ----------------------------------------------------

        if previous_text is None:

            save_cached_stock(
                game,
                current_text
            )

            print(
                f"[CACHE] {game} "
                f"({len(current)} items)"
            )

            return

        previous = set(
            previous_text.splitlines()
        )

        # ----------------------------------------------------
        # Detect changes
        # ----------------------------------------------------

        added = (
            current - previous
        )

        removed = (
            previous - current
        )

        changed = bool(
            added
            or removed
        )

        # ----------------------------------------------------
        # No change
        # ----------------------------------------------------

        if not changed:

            return

        # ----------------------------------------------------
        # Save new cache
        # ----------------------------------------------------

        save_cached_stock(
            game,
            current_text
        )

        print(
            f"[STOCK] {game} changed | "
            f"Added: {len(added)} | "
            f"Removed: {len(removed)}"
        )

        # ----------------------------------------------------
        # AUTOMATIC SHOP MESSAGE
        # ----------------------------------------------------
        #
        # This sends the FULL current shop to the configured
        # shop channel.
        # ----------------------------------------------------

        await self.send_shop_update(
            game,
            stock
        )

        # ----------------------------------------------------
        # PERSONAL ALERTS
        # ----------------------------------------------------

        if not added:

            return

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

            wanted = (
                wanted_item.lower()
            )

            matches = []

            for item in added:

                if wanted in item.lower():

                    matches.append(
                        item
                    )

            if not matches:

                continue

            channel = self.bot.get_channel(
                channel_id
            )

            if not channel:

                continue

            mention = (
                f"<@{user_id}>"
            )

            game_name = self.game_name(
                game
            )

            embed = discord.Embed(

                title="🚨 Stock Alert",

                description=(

                    f"{mention}\n\n"

                    f"🎮 **{game_name}**\n\n"

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

    # ========================================================
    # STOCK LOOP
    # ========================================================

    @tasks.loop(
        seconds=STOCK_CHECK_SECONDS
    )
    async def stock_loop(
        self
    ):

        # ----------------------------------------------------
        # Grow A Garden
        # ----------------------------------------------------

        try:

            gag_stock = (
                await get_grow_a_garden_stock()
            )

            await self.process_stock(

                "growagarden",

                gag_stock
            )

        except Exception as error:

            print(
                f"[GAG ERROR] "
                f"{error}"
            )

        # ----------------------------------------------------
        # Blox Fruits
        # ----------------------------------------------------

        try:

            blox_stock = (
                await get_blox_fruits_stock()
            )

            await self.process_stock(

                "bloxfruits",

                blox_stock
            )

        except Exception as error:

            print(
                f"[BLOX ERROR] "
                f"{error}"
            )

        # ----------------------------------------------------
        # Steal An Egg
        # ----------------------------------------------------

        try:

            await self.send_event_alerts()

        except Exception as error:

            print(
                f"[STEAL EGG ERROR] "
                f"{error}"
            )

    @stock_loop.before_loop
    async def before_stock_loop(
        self
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # /stock
    # ========================================================

    @app_commands.command(
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
        self,
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

    # ========================================================
    # /steal-egg
    # ========================================================

    @app_commands.command(
        name="steal-egg",
        description="عرض مواعيد Steal An Egg المتوقعة"
    )
    async def steal_egg(
        self,
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

                "🥚 **Egg Reset**\n"

                f"`{egg_minutes:02d}:"
                f"{egg_seconds:02d}`\n\n"

                "🌀 **Rift**\n"

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

    # ========================================================
    # /stock-alert
    # ========================================================

    @app_commands.command(
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
        self,
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

        item = item.strip()

        if not item:

            await interaction.response.send_message(

                "❌ اكتب اسم العنصر.",

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

    # ========================================================
    # /stock-alert-remove
    # ========================================================

    @app_commands.command(
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
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        item: str
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

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

    # ========================================================
    # /stock-alerts
    # ========================================================

    @app_commands.command(
        name="stock-alerts",
        description="عرض تنبيهاتك"
    )
    async def stock_alerts(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

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

            game_name = self.game_name(
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

        embed.set_footer(
            text="Fime Stock System"
        )

        await interaction.response.send_message(

            embed=embed,

            ephemeral=True
        )

    # ========================================================
    # /steal-alert
    # ========================================================

    @app_commands.command(
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
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
        channel: discord.TextChannel
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

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

    # ========================================================
    # /steal-alert-remove
    # ========================================================

    @app_commands.command(
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
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str]
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

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

    # ========================================================
    # /stock-channel
    #
    # ADMIN:
    # Select game + channel.
    #
    # After that:
    #
    # Whenever the shop changes,
    # the bot posts the FULL current shop there.
    # ========================================================

    @app_commands.command(
        name="stock-channel",
        description="تحديد روم نشر الشوب التلقائي"
    )
    @app_commands.describe(
        game="اللعبة",
        channel="روم الشوب"
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
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_channel(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        channel: discord.TextChannel
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

            return

        set_shop_channel(

            interaction.guild.id,

            game.value,

            channel.id
        )

        game_name = self.game_name(
            game.value
        )

        embed = discord.Embed(

            title="✅ تم تحديد روم الشوب",

            description=(

                f"🎮 **اللعبة:** {game_name}\n"

                f"📢 **الروم:** {channel.mention}\n\n"

                "🔄 من الآن، عندما يتغير الشوب "
                "سيتم نشر المخزون الجديد تلقائيًا "
                "في هذا الروم."
            )
        )

        embed.set_footer(
            text="Fime Stock System"
        )

        await interaction.response.send_message(

            embed=embed,

            ephemeral=True
        )

    # ========================================================
    # /stock-channel-remove
    # ========================================================

    @app_commands.command(
        name="stock-channel-remove",
        description="إزالة روم الشوب التلقائي"
    )
    @app_commands.describe(
        game="اللعبة"
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
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_channel_remove(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str]
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

            return

        removed = remove_shop_channel(

            interaction.guild.id,

            game.value
        )

        if removed:

            message = (
                f"🗑️ تم إيقاف نشر شوب "
                f"**{self.game_name(game.value)}**."
            )

        else:

            message = (
                "⚠️ ما فيه روم محدد لهذه اللعبة."
            )

        await interaction.response.send_message(

            message,

            ephemeral=True
        )

    # ========================================================
    # /stock-channel-status
    # ========================================================

    @app_commands.command(
        name="stock-channel-status",
        description="عرض رومات نشر الشوب"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_channel_status(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            await interaction.response.send_message(

                "❌ هذا الأمر داخل السيرفر فقط.",

                ephemeral=True
            )

            return

        gag_channel = get_shop_channel(

            interaction.guild.id,

            "growagarden"
        )

        blox_channel = get_shop_channel(

            interaction.guild.id,

            "bloxfruits"
        )

        gag_text = (

            f"<#{gag_channel}>"

            if gag_channel

            else

            "❌ غير محدد"
        )

        blox_text = (

            f"<#{blox_channel}>"

            if blox_channel

            else

            "❌ غير محدد"
        )

        embed = discord.Embed(

            title="📢 Fime Stock Channels",

            description=(

                f"🌱 **Grow a Garden:** "
                f"{gag_text}\n\n"

                f"🍎 **Blox Fruits:** "
                f"{blox_text}"
            )
        )

        embed.set_footer(
            text="Fime Stock System"
        )

        await interaction.response.send_message(

            embed=embed,

            ephemeral=True
        )

    # ========================================================
    # /stock-status
    # ========================================================

    @app_commands.command(
        name="stock-status",
        description="فحص حالة نظام الـStock"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_status(
        self,
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

        if BLOX_API_URL:

            blox_status = (

                f"🟢 {len(blox)} عنصر"

                if blox

                else

                "🔴 المصدر لم يُرجع بيانات"
            )

        else:

            blox_status = (
                "🟡 BLOX_API_URL غير مضبوط"
            )

        gag_channel = get_shop_channel(

            interaction.guild.id,

            "growagarden"
        )

        blox_channel = get_shop_channel(

            interaction.guild.id,

            "bloxfruits"
        )

        gag_channel_text = (

            f"<#{gag_channel}>"

            if gag_channel

            else

            "❌ غير محدد"
        )

        blox_channel_text = (

            f"<#{blox_channel}>"

            if blox_channel

            else

            "❌ غير محدد"
        )

        egg_seconds = (
            steal["egg_remaining"]
        )

        rift_seconds = (
            steal["rift_remaining"]
        )

        embed = discord.Embed(

            title="📊 Fime Stock Status",

            description=(

                f"🌱 **Grow a Garden:** "
                f"{gag_status}\n"

                f"📢 Shop Room: "
                f"{gag_channel_text}\n\n"

                f"🍎 **Blox Fruits:** "
                f"{blox_status}\n"

                f"📢 Shop Room: "
                f"{blox_channel_text}\n\n"

                f"🥚 **Steal An Egg:** "
                f"🟢 المؤقت يعمل\n\n"

                f"⏱️ Egg Reset القادم: "
                f"`{egg_seconds // 60:02d}:"
                f"{egg_seconds % 60:02d}`\n"

                f"🌀 Rift القادم: "
                f"`{rift_seconds // 60:02d}:"
                f"{rift_seconds % 60:02d}`"
            )
        )

        embed.set_footer(
            text="Fime Stock System"
        )

        await interaction.followup.send(

            embed=embed,

            ephemeral=True
        )

    # ========================================================
    # COMMAND ERROR
    # ========================================================

    async def cog_app_command_error(
        self,
        interaction,
        error
    ):

        original = getattr(
            error,
            "original",
            error
        )

        if isinstance(
            original,
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

            return

        print(
            f"[BOT6 COMMAND ERROR] "
            f"{original}"
        )


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(
    bot
):

    await bot.add_cog(
        FimeStock(bot)
    )

    print(
        "✅ bot6.py loaded successfully."
    )