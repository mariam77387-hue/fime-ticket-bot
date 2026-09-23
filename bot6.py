# ============================================================
# Team Fime - Stock System
# bot6.py
#
# 🌱 Grow a Garden
# 🍎 Blox Fruits
# 🥚 Steal An Egg
#
# FEATURES
# ------------------------------------------------------------
# • Live stock polling
# • Automatic shop posting
# • Custom shop channel per game
# • Notification setup panel
# • Automatic notification roles
# • Stock refresh notifications
# • Rare stock notifications
# • Steal An Egg Reset notifications
# • Steal An Egg Rift notifications
# • SQLite persistence
# • Personal stock alerts
# • GAG fruit/item multi-select notifications
# • Automatic role per selected GAG fruit/item
# • Automatic role mentions when selected fruit/item appears
# • Admin status commands
# • GAG API configurable through Environment Variable
# • Multiple API JSON formats supported
# • Safe API error handling
#
# IMPORTANT
# ------------------------------------------------------------
# Discord has a 100 top-level global application-command limit.
# All bot6 commands are therefore inside ONE /stock group.
#
# Example:
# /stock view
# /stock channel
# /stock notifications-setup
# /stock alert
# /stock status
# ============================================================

import os
import json
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

DB_FILE = os.getenv(
    "STOCK_DB_FILE",
    "fime_stock.db"
)

# IMPORTANT:
# Put your CURRENT working Grow a Garden API here
# through Environment Variables.
#
# Example:
# GAG_API_URL=https://your-working-api.example/stock
#
# DO NOT put a dead/404 URL here.
GAG_API_URL = os.getenv(
    "GAG_API_URL",
    ""
).strip()

# Optional Blox Fruits API
BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    ""
).strip()

try:
    STOCK_CHECK_SECONDS = int(
        os.getenv(
            "STOCK_CHECK_SECONDS",
            "30"
        )
    )
except Exception:
    STOCK_CHECK_SECONDS = 30

STOCK_CHECK_SECONDS = max(
    10,
    STOCK_CHECK_SECONDS
)

STEAL_EGG_RESET_MINUTES = 5
STEAL_EGG_RIFT_MINUTES = 30

# Discord Select Menu maximum options
MAX_SELECT_OPTIONS = 25


# ============================================================
# GAMES
# ============================================================

GAME_GAG = "gag"
GAME_BLOX = "blox"
GAME_STEAL = "steal"

GAME_NAMES = {
    GAME_GAG: "🌱 Grow a Garden",
    GAME_BLOX: "🍎 Blox Fruits",
    GAME_STEAL: "🥚 Steal An Egg",
}


# ============================================================
# NOTIFICATION TYPES
# ============================================================

NOTIF_GAG_STOCK = "gag_stock"
NOTIF_GAG_RARE = "gag_rare"

NOTIF_BLOX_STOCK = "blox_stock"

NOTIF_STEAL_RESET = "steal_reset"
NOTIF_STEAL_RIFT = "steal_rift"

NOTIF_ALL_STOCK = "all_stock"


NOTIFICATION_INFO = {

    NOTIF_GAG_STOCK: {
        "name": "🌱 Grow a Garden — تجديد الستوك",
        "short": "Grow a Garden Stock",
        "role": "GAG Stock",
        "description": "إشعار عند تجدد ستوك Grow a Garden.",
        "color": discord.Color.green(),
    },

    NOTIF_GAG_RARE: {
        "name": "💎 Grow a Garden — الستوك النادر",
        "short": "GAG Rare Stock",
        "role": "GAG Rare",
        "description": "إشعار عند ظهور عنصر نادر.",
        "color": discord.Color.gold(),
    },

    NOTIF_BLOX_STOCK: {
        "name": "🍎 Blox Fruits — تجديد الستوك",
        "short": "Blox Fruits Stock",
        "role": "Blox Stock",
        "description": "إشعار عند تجدد ستوك Blox Fruits.",
        "color": discord.Color.red(),
    },

    NOTIF_STEAL_RESET: {
        "name": "🥚 Steal An Egg — Reset",
        "short": "Steal Egg Reset",
        "role": "Steal Egg Reset",
        "description": "إشعار عند بداية Reset.",
        "color": discord.Color.orange(),
    },

    NOTIF_STEAL_RIFT: {
        "name": "🌀 Steal An Egg — Rift",
        "short": "Steal Egg Rift",
        "role": "Steal Egg Rift",
        "description": "إشعار عند موعد Rift.",
        "color": discord.Color.blurple(),
    },

    NOTIF_ALL_STOCK: {
        "name": "🔔 جميع إشعارات الستوك",
        "short": "All Stock",
        "role": "All Stock Alerts",
        "description": "إشعار لجميع تحديثات الستوك.",
        "color": discord.Color.purple(),
    },
}


# ============================================================
# DATABASE
# ============================================================

def get_db():

    conn = sqlite3.connect(
        DB_FILE
    )

    conn.row_factory = sqlite3.Row

    return conn


def setup_database():

    conn = get_db()

    cur = conn.cursor()

    # --------------------------------------------------------
    # Personal item subscriptions
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            item TEXT NOT NULL,
            PRIMARY KEY (
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_subscriptions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            PRIMARY KEY (
                guild_id,
                user_id,
                event_type
            )
        )
    """)

    # --------------------------------------------------------
    # Stock cache
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_cache (
            guild_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            stock_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (
                guild_id,
                game
            )
        )
    """)

    # --------------------------------------------------------
    # Event cache
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_cache (
            guild_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            last_value TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (
                guild_id,
                event_type
            )
        )
    """)

    # --------------------------------------------------------
    # Shop channels
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS shop_channels (
            guild_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (
                guild_id,
                game
            )
        )
    """)

    # --------------------------------------------------------
    # Standard notification roles
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_roles (
            guild_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (
                guild_id,
                notification_type
            )
        )
    """)

    # --------------------------------------------------------
    # Notification panels
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)

    # --------------------------------------------------------
    # Notification members
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_members (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            PRIMARY KEY (
                guild_id,
                user_id,
                notification_type
            )
        )
    """)

    # --------------------------------------------------------
    # GAG item/fruit roles
    #
    # One role per GAG item:
    # 🔔 Apple
    # 🔔 Strawberry
    # etc.
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS gag_item_roles (
            guild_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (
                guild_id,
                item_name
            )
        )
    """)

    # --------------------------------------------------------
    # GAG item/fruit subscriptions
    #
    # Stores which member wants which item.
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS gag_item_subscriptions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            PRIMARY KEY (
                guild_id,
                user_id,
                item_name
            )
        )
    """)

    conn.commit()

    conn.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def set_shop_channel(
    guild_id,
    game,
    channel_id
):

    conn = get_db()

    conn.execute("""
        INSERT INTO shop_channels (
            guild_id,
            game,
            channel_id
        )
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, game)
        DO UPDATE SET
            channel_id = excluded.channel_id
    """, (
        guild_id,
        game,
        channel_id
    ))

    conn.commit()

    conn.close()


def remove_shop_channel(
    guild_id,
    game
):

    conn = get_db()

    conn.execute("""
        DELETE FROM shop_channels
        WHERE guild_id = ?
        AND game = ?
    """, (
        guild_id,
        game
    ))

    conn.commit()

    conn.close()


def get_shop_channels(
    guild_id
):

    conn = get_db()

    rows = conn.execute("""
        SELECT game, channel_id
        FROM shop_channels
        WHERE guild_id = ?
    """, (
        guild_id,
    )).fetchall()

    conn.close()

    return {
        row["game"]: row["channel_id"]
        for row in rows
    }


def get_shop_channel(
    guild_id,
    game
):

    conn = get_db()

    row = conn.execute("""
        SELECT channel_id
        FROM shop_channels
        WHERE guild_id = ?
        AND game = ?
    """, (
        guild_id,
        game
    )).fetchone()

    conn.close()

    if row:
        return row["channel_id"]

    return None


def get_cached_stock(
    guild_id,
    game
):

    conn = get_db()

    row = conn.execute("""
        SELECT stock_json
        FROM stock_cache
        WHERE guild_id = ?
        AND game = ?
    """, (
        guild_id,
        game
    )).fetchone()

    conn.close()

    if not row:
        return None

    return row["stock_json"]


def save_cached_stock(
    guild_id,
    game,
    stock_json
):

    conn = get_db()

    conn.execute("""
        INSERT INTO stock_cache (
            guild_id,
            game,
            stock_json,
            updated_at
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, game)
        DO UPDATE SET
            stock_json = excluded.stock_json,
            updated_at = excluded.updated_at
    """, (
        guild_id,
        game,
        stock_json,
        datetime.now(
            timezone.utc
        ).isoformat()
    ))

    conn.commit()

    conn.close()


def get_notification_role(
    guild_id,
    notification_type
):

    conn = get_db()

    row = conn.execute("""
        SELECT role_id
        FROM notification_roles
        WHERE guild_id = ?
        AND notification_type = ?
    """, (
        guild_id,
        notification_type
    )).fetchone()

    conn.close()

    if row:
        return row["role_id"]

    return None


def save_notification_role(
    guild_id,
    notification_type,
    role_id
):

    conn = get_db()

    conn.execute("""
        INSERT INTO notification_roles (
            guild_id,
            notification_type,
            role_id
        )
        VALUES (?, ?, ?)
        ON CONFLICT(
            guild_id,
            notification_type
        )
        DO UPDATE SET
            role_id = excluded.role_id
    """, (
        guild_id,
        notification_type,
        role_id
    ))

    conn.commit()

    conn.close()


def save_notification_panel(
    guild_id,
    channel_id,
    message_id
):

    conn = get_db()

    conn.execute("""
        INSERT INTO notification_panels (
            guild_id,
            channel_id,
            message_id
        )
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id)
        DO UPDATE SET
            channel_id = excluded.channel_id,
            message_id = excluded.message_id
    """, (
        guild_id,
        channel_id,
        message_id
    ))

    conn.commit()

    conn.close()


def get_notification_panel(
    guild_id
):

    conn = get_db()

    row = conn.execute("""
        SELECT channel_id, message_id
        FROM notification_panels
        WHERE guild_id = ?
    """, (
        guild_id,
    )).fetchone()

    conn.close()

    if not row:
        return None

    return (
        row["channel_id"],
        row["message_id"]
    )


def add_notification_member(
    guild_id,
    user_id,
    notification_type
):

    conn = get_db()

    conn.execute("""
        INSERT OR IGNORE INTO notification_members (
            guild_id,
            user_id,
            notification_type
        )
        VALUES (?, ?, ?)
    """, (
        guild_id,
        user_id,
        notification_type
    ))

    conn.commit()

    conn.close()


def remove_notification_member(
    guild_id,
    user_id,
    notification_type
):

    conn = get_db()

    conn.execute("""
        DELETE FROM notification_members
        WHERE guild_id = ?
        AND user_id = ?
        AND notification_type = ?
    """, (
        guild_id,
        user_id,
        notification_type
    ))

    conn.commit()

    conn.close()


# ============================================================
# GAG ITEM ROLE DATABASE
# ============================================================

def normalize_item_name(
    name
):

    return str(
        name or ""
    ).strip()


def get_gag_item_role(
    guild_id,
    item_name
):

    item_name = normalize_item_name(
        item_name
    )

    conn = get_db()

    row = conn.execute("""
        SELECT role_id
        FROM gag_item_roles
        WHERE guild_id = ?
        AND item_name = ?
    """, (
        guild_id,
        item_name
    )).fetchone()

    conn.close()

    if row:
        return row["role_id"]

    return None


def save_gag_item_role(
    guild_id,
    item_name,
    role_id
):

    item_name = normalize_item_name(
        item_name
    )

    conn = get_db()

    conn.execute("""
        INSERT INTO gag_item_roles (
            guild_id,
            item_name,
            role_id
        )
        VALUES (?, ?, ?)
        ON CONFLICT(
            guild_id,
            item_name
        )
        DO UPDATE SET
            role_id = excluded.role_id
    """, (
        guild_id,
        item_name,
        role_id
    ))

    conn.commit()

    conn.close()


def add_gag_item_subscription(
    guild_id,
    user_id,
    item_name
):

    item_name = normalize_item_name(
        item_name
    )

    conn = get_db()

    conn.execute("""
        INSERT OR IGNORE INTO gag_item_subscriptions (
            guild_id,
            user_id,
            item_name
        )
        VALUES (?, ?, ?)
    """, (
        guild_id,
        user_id,
        item_name
    ))

    conn.commit()

    conn.close()


def remove_gag_item_subscription(
    guild_id,
    user_id,
    item_name
):

    item_name = normalize_item_name(
        item_name
    )

    conn = get_db()

    conn.execute("""
        DELETE FROM gag_item_subscriptions
        WHERE guild_id = ?
        AND user_id = ?
        AND item_name = ?
    """, (
        guild_id,
        user_id,
        item_name
    ))

    conn.commit()

    conn.close()


def get_gag_item_subscribers(
    guild_id,
    item_name
):

    item_name = normalize_item_name(
        item_name
    )

    conn = get_db()

    rows = conn.execute("""
        SELECT user_id
        FROM gag_item_subscriptions
        WHERE guild_id = ?
        AND item_name = ?
    """, (
        guild_id,
        item_name
    )).fetchall()

    conn.close()

    return [
        row["user_id"]
        for row in rows
    ]


def get_gag_user_items(
    guild_id,
    user_id
):

    conn = get_db()

    rows = conn.execute("""
        SELECT item_name
        FROM gag_item_subscriptions
        WHERE guild_id = ?
        AND user_id = ?
        ORDER BY item_name COLLATE NOCASE
    """, (
        guild_id,
        user_id
    )).fetchall()

    conn.close()

    return [
        row["item_name"]
        for row in rows
    ]


# ============================================================
# API
# ============================================================

async def fetch_json(
    session,
    url
):

    if not url:
        return None

    try:

        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=15
            )
        ) as response:

            if response.status != 200:

                print(
                    f"⚠️ Stock API HTTP "
                    f"{response.status}: {url}"
                )

                return None

            try:

                return await response.json(
                    content_type=None
                )

            except Exception:

                print(
                    f"⚠️ Stock API returned "
                    f"invalid JSON: {url}"
                )

                return None

    except asyncio.TimeoutError:

        print(
            f"⚠️ Stock API timeout: {url}"
        )

        return None

    except Exception as error:

        print(
            f"⚠️ Stock API error: {error}"
        )

        return None


# ============================================================
# API DATA EXTRACTION
# ============================================================

def extract_list(
    data
):

    if isinstance(
        data,
        list
    ):
        return data

    if not isinstance(
        data,
        dict
    ):
        return []

    possible_keys = [
        "stock",
        "stocks",
        "items",
        "data",
        "shop",
        "inventory",
        "goods",
        "seeds",
        "seedStock",
        "gear",
        "gearStock",
        "eggs",
        "eggStock",
        "eventShop",
        "eventStock",
        "cosmetics",
        "cosmeticStock",
    ]

    for key in possible_keys:

        value = data.get(
            key
        )

        if isinstance(
            value,
            list
        ):
            return value

        if isinstance(
            value,
            dict
        ):

            result = []

            for name, item in value.items():

                if isinstance(
                    item,
                    dict
                ):

                    copied = dict(
                        item
                    )

                    copied.setdefault(
                        "name",
                        name
                    )

                    result.append(
                        copied
                    )

                else:

                    result.append({
                        "name": name,
                        "stock": item
                    })

            return result

    return []


def normalize_item(
    item
):

    if isinstance(
        item,
        str
    ):

        return {
            "name": item,
            "stock": 0,
            "rarity": "",
        }

    if not isinstance(
        item,
        dict
    ):
        return None

    name = (
        item.get("name")
        or item.get("item")
        or item.get("title")
        or item.get("displayName")
        or item.get("display_name")
        or item.get("seed")
        or item.get("fruit")
        or item.get("egg")
        or item.get("gear")
    )

    if not name:
        return None

    stock = (
        item.get("stock")
        if item.get("stock") is not None
        else item.get("quantity")
    )

    if stock is None:
        stock = item.get(
            "amount"
        )

    if stock is None:
        stock = item.get(
            "count"
        )

    if stock is None:
        stock = 0

    rarity = (
        item.get("rarity")
        or item.get("tier")
        or item.get("type")
        or ""
    )

    return {
        "name": str(name).strip(),
        "stock": stock,
        "rarity": str(rarity).strip(),
    }


def normalize_stock(
    data
):

    raw = extract_list(
        data
    )

    result = []

    for item in raw:

        normalized = normalize_item(
            item
        )

        if normalized:
            result.append(
                normalized
            )

    return clean_stock(
        result
    )


# ============================================================
# STOCK FETCHERS
# ============================================================

async def fetch_gag_stock(
    session
):

    if not GAG_API_URL:

        print(
            "⚠️ GAG_API_URL is not configured."
        )

        return []

    data = await fetch_json(
        session,
        GAG_API_URL
    )

    if data is None:
        return []

    stock = normalize_stock(
        data
    )

    if not stock:

        print(
            "⚠️ GAG API responded, "
            "but no recognizable stock "
            "items were found."
        )

    return stock


async def fetch_blox_stock(
    session
):

    if not BLOX_API_URL:
        return []

    data = await fetch_json(
        session,
        BLOX_API_URL
    )

    if data is None:
        return []

    return normalize_stock(
        data
    )


# ============================================================
# STOCK CLEANING
# ============================================================

def clean_stock(
    stock
):

    cleaned = []

    seen = set()

    for item in stock:

        if not isinstance(
            item,
            dict
        ):
            continue

        name = str(
            item.get("name")
            or "Unknown"
        ).strip()

        stock_count = item.get(
            "stock",
            0
        )

        rarity = str(
            item.get("rarity")
            or ""
        ).strip()

        key = (
            name.lower(),
            str(stock_count),
            rarity.lower()
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        cleaned.append({
            "name": name,
            "stock": stock_count,
            "rarity": rarity,
        })

    cleaned.sort(
        key=lambda item: (
            item["name"].lower(),
            str(item["stock"])
        )
    )

    return cleaned


def serialize_stock(
    stock
):

    return json.dumps(
        clean_stock(stock),
        ensure_ascii=False,
        sort_keys=True
    )


# ============================================================
# RARE DETECTION
# ============================================================

def is_rare_item(
    item
):

    rarity = str(
        item.get("rarity")
        or ""
    ).lower()

    name = str(
        item.get("name")
        or ""
    ).lower()

    rare_words = [
        "rare",
        "legendary",
        "mythic",
        "mythical",
        "divine",
        "secret",
        "godly",
        "limited",
        "event",
        "prismatic",
    ]

    return any(
        word in rarity
        or word in name
        for word in rare_words
    )


# ============================================================
# SHOP EMBEDS
# ============================================================

def build_shop_embeds(
    game,
    stock
):

    stock = clean_stock(
        stock
    )

    game_name = GAME_NAMES.get(
        game,
        game
    )

    if not stock:

        return [
            discord.Embed(
                title=f"{game_name} | Stock",
                description=(
                    "لا يوجد ستوك متاح حاليًا."
                ),
                color=discord.Color.dark_grey()
            )
        ]

    chunks = []

    current = ""

    for item in stock:

        name = item["name"]

        amount = item["stock"]

        rarity = item.get(
            "rarity",
            ""
        )

        line = f"**{name}**"

        if amount not in (
            None,
            "",
            0,
            "0"
        ):
            line += (
                f" × `{amount}`"
            )

        if rarity:
            line += (
                f" — `{rarity}`"
            )

        line += "\n"

        if (
            len(current)
            + len(line)
            > 3800
        ):

            if current:
                chunks.append(
                    current
                )

            current = line

        else:

            current += line

    if current:
        chunks.append(
            current
        )

    embeds = []

    for index, chunk in enumerate(
        chunks
    ):

        title = (
            f"{game_name} | Shop"
        )

        if len(chunks) > 1:

            title += (
                f" "
                f"({index + 1}/{len(chunks)})"
            )

        embed = discord.Embed(
            title=title,
            description=chunk,
            color=discord.Color.blurple(),
            timestamp=datetime.now(
                timezone.utc
            )
        )

        if index == 0:

            embed.set_footer(
                text=(
                    "Team Fime • "
                    "Stock System"
                )
            )

        embeds.append(
            embed
        )

    return embeds


# ============================================================
# STANDARD NOTIFICATION PANEL
# ============================================================

def build_notification_panel_embed():

    embed = discord.Embed(
        title="🔔 إشعارات الستوك",
        description=(
            "اختار الإشعارات اللي تبي توصلك.\n\n"
            "اضغط على القائمة بالأسفل واختر النوع "
            "المناسب لك.\n\n"
            "عند اختيار الإشعار، البوت يعطيك "
            "**رتبة الإشعار تلقائيًا**.\n\n"
            "تقدر تضغط على نفس الاختيار مرة ثانية "
            "لإلغاءه."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🌱 Grow a Garden",
        value=(
            "• تجديد الستوك\n"
            "• الستوك النادر\n"
            "• إشعارات الفواكه"
        ),
        inline=True
    )

    embed.add_field(
        name="🍎 Blox Fruits",
        value=(
            "• تجديد الستوك"
        ),
        inline=True
    )

    embed.add_field(
        name="🥚 Steal An Egg",
        value=(
            "• Reset\n"
            "• Rift"
        ),
        inline=True
    )

    embed.add_field(
        name="🔔 عام",
        value=(
            "• جميع إشعارات الستوك"
        ),
        inline=False
    )

    embed.set_footer(
        text=(
            "Team Fime • "
            "Notification System"
        )
    )

    return embed


# ============================================================
# STANDARD NOTIFICATION SELECT
# ============================================================

class NotificationSelect(
    discord.ui.Select
):

    def __init__(self):

        options = []

        for (
            notification_type,
            info
        ) in NOTIFICATION_INFO.items():

            options.append(
                discord.SelectOption(
                    label=info["short"][:100],
                    description=info["description"][:100],
                    value=notification_type
                )
            )

        super().__init__(
            placeholder=(
                "🔔 اختر إشعارًا..."
            ),
            min_values=1,
            max_values=1,
            options=options,
            custom_id=(
                "fime_stock_notifications"
            )
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا النظام داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        cog = interaction.client.get_cog(
            "FimeStock"
        )

        if not cog:

            await interaction.response.send_message(
                "❌ نظام الستوك غير متاح.",
                ephemeral=True
            )

            return

        notification_type = self.values[0]

        await interaction.response.defer(
            ephemeral=True
        )

        role = (
            await cog.get_or_create_notification_role(
                interaction.guild,
                notification_type
            )
        )

        if not role:

            await interaction.followup.send(
                (
                    "❌ ما قدرت أجهز رتبة الإشعار.\n"
                    "تأكد أن البوت عنده Manage Roles "
                    "وأن رتبته أعلى من رتب الإشعارات."
                ),
                ephemeral=True
            )

            return

        try:

            if role in interaction.user.roles:

                await interaction.user.remove_roles(
                    role,
                    reason=(
                        "Fime Stock "
                        "Notification Toggle"
                    )
                )

                remove_notification_member(
                    interaction.guild.id,
                    interaction.user.id,
                    notification_type
                )

                await interaction.followup.send(
                    (
                        f"➖ تم إلغاء "
                        f"**{role.name}**."
                    ),
                    ephemeral=True
                )

            else:

                await interaction.user.add_roles(
                    role,
                    reason=(
                        "Fime Stock "
                        "Notification Selection"
                    )
                )

                add_notification_member(
                    interaction.guild.id,
                    interaction.user.id,
                    notification_type
                )

                await interaction.followup.send(
                    (
                        f"✅ تم تفعيل "
                        f"**{role.name}**."
                    ),
                    ephemeral=True
                )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ Discord رفض تعديل الرتبة.\n"
                    "تأكد أن رتبة البوت أعلى من رتبة "
                    "الإشعار."
                ),
                ephemeral=True
            )

        except Exception as error:

            print(
                "❌ Notification role error:",
                error
            )

            await interaction.followup.send(
                "❌ حدث خطأ أثناء تعديل الإشعار.",
                ephemeral=True
            )


class NotificationView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            NotificationSelect()
        )


# ============================================================
# GAG FRUIT / ITEM SELECT
# ============================================================

def build_gag_item_select_options(
    stock
):

    options = []

    seen = set()

    for item in clean_stock(stock):

        name = normalize_item_name(
            item.get("name")
        )

        if not name:
            continue

        key = name.lower()

        if key in seen:
            continue

        seen.add(key)

        amount = item.get(
            "stock",
            0
        )

        rarity = item.get(
            "rarity",
            ""
        )

        description_parts = []

        if amount not in (
            None,
            "",
            0,
            "0"
        ):
            description_parts.append(
                f"× {amount}"
            )

        if rarity:
            description_parts.append(
                str(rarity)
            )

        description = (
            " • ".join(
                description_parts
            )
            if description_parts
            else "متوفر في الستوك"
        )

        options.append(
            discord.SelectOption(
                label=name[:100],
                description=description[:100],
                value=name[:100]
            )
        )

        if len(options) >= MAX_SELECT_OPTIONS:
            break

    return options


class GAGFruitSelect(
    discord.ui.Select
):

    def __init__(
        self,
        stock
    ):

        options = build_gag_item_select_options(
            stock
        )

        # Discord requires at least one option.
        if not options:

            options = [
                discord.SelectOption(
                    label="لا يوجد عناصر",
                    description="لا توجد عناصر متاحة حاليًا.",
                    value="__none__"
                )
            ]

        self.stock_names = {
            option.value.lower()
            for option in options
        }

        max_values = min(
            len(options),
            MAX_SELECT_OPTIONS
        )

        super().__init__(
            placeholder=(
                "🍎 اختر الفواكه اللي تبي إشعار عنها..."
            ),
            min_values=1,
            max_values=max_values,
            options=options,
            custom_id=(
                "fime_gag_fruit_select"
            )
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا النظام داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        if (
            "__none__"
            in self.values
        ):

            await interaction.response.send_message(
                "❌ ما فيه عناصر متاحة حاليًا.",
                ephemeral=True
            )

            return

        cog = interaction.client.get_cog(
            "FimeStock"
        )

        if not cog:

            await interaction.response.send_message(
                "❌ نظام الستوك غير متاح.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        added_names = []

        failed_names = []

        for item_name in self.values:

            item_name = normalize_item_name(
                item_name
            )

            if not item_name:
                continue

            role = (
                await cog.get_or_create_gag_item_role(
                    interaction.guild,
                    item_name
                )
            )

            if not role:

                failed_names.append(
                    item_name
                )

                continue

            try:

                if role not in interaction.user.roles:

                    await interaction.user.add_roles(
                        role,
                        reason=(
                            "Fime GAG "
                            "Fruit Notification"
                        )
                    )

                add_gag_item_subscription(
                    interaction.guild.id,
                    interaction.user.id,
                    item_name
                )

                added_names.append(
                    item_name
                )

            except discord.Forbidden:

                failed_names.append(
                    item_name
                )

            except Exception as error:

                print(
                    "❌ GAG fruit role error:",
                    error
                )

                failed_names.append(
                    item_name
                )

        if added_names:

            text = "\n".join(
                f"🍎 **{name}**"
                for name in added_names
            )

            message = (
                "✅ **تم تفعيل إشعاراتك!**\n\n"
                f"{text}\n\n"
                "إذا ظهرت أي وحدة منها في ستوك جديد، "
                "بمنشنك البوت تلقائيًا."
            )

        else:

            message = (
                "❌ ما قدرت أفعّل أي إشعار.\n"
                "تأكد أن البوت يملك **Manage Roles** "
                "وأن رتبته أعلى من رتب الإشعارات."
            )

        if failed_names:

            failed_text = "\n".join(
                f"• {name}"
                for name in failed_names
            )

            message += (
                "\n\n⚠️ تعذر تفعيل:\n"
                f"{failed_text}"
            )

        await interaction.followup.send(
            message,
            ephemeral=True
        )


class GAGFruitView(
    discord.ui.View
):

    def __init__(
        self,
        stock
    ):

        super().__init__(
            timeout=None
        )

        options = build_gag_item_select_options(
            stock
        )

        if not options:
            return

        self.add_item(
            GAGFruitSelect(stock)
        )


# ============================================================
# COG
# ============================================================

class FimeStock(
    commands.Cog
):

    # ========================================================
    # ONE TOP-LEVEL COMMAND GROUP
    #
    # This reduces bot6 from 12 top-level commands
    # to ONE top-level command: /stock
    # ========================================================

    stock_group = app_commands.Group(
        name="stock",
        description="إدارة وعرض نظام الستوك"
    )

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        setup_database()

        self.session = None

        self.steal_reset_counter = 0

        self.steal_rift_counter = 0

        self.stock_loop.start()

        self.steal_event_loop.start()

    # ========================================================
    # LOAD
    # ========================================================

    async def cog_load(
        self
    ):

        await self.ensure_session()

        try:

            self.bot.add_view(
                NotificationView()
            )

            print(
                "✅ Stock notification "
                "persistent view loaded."
            )

        except Exception as error:

            print(
                "⚠️ Notification view error:",
                error
            )

    # ========================================================
    # UNLOAD
    # ========================================================

    def cog_unload(
        self
    ):

        self.stock_loop.cancel()

        self.steal_event_loop.cancel()

        if self.session:

            asyncio.create_task(
                self.session.close()
            )

    # ========================================================
    # SESSION
    # ========================================================

    async def ensure_session(
        self
    ):

        if (
            self.session is None
            or self.session.closed
        ):

            self.session = (
                aiohttp.ClientSession()
            )

    # ========================================================
    # CHANNEL
    # ========================================================

    async def resolve_channel(
        self,
        channel_id
    ):

        channel = self.bot.get_channel(
            channel_id
        )

        if channel:
            return channel

        try:

            return await self.bot.fetch_channel(
                channel_id
            )

        except Exception:

            return None

    # ========================================================
    # STANDARD NOTIFICATION ROLE
    # ========================================================

    async def get_or_create_notification_role(
        self,
        guild,
        notification_type
    ):

        info = NOTIFICATION_INFO.get(
            notification_type
        )

        if not info:
            return None

        existing_id = (
            get_notification_role(
                guild.id,
                notification_type
            )
        )

        if existing_id:

            role = guild.get_role(
                existing_id
            )

            if role:
                return role

        role_name = (
            f"🔔 {info['role']}"
        )

        existing_role = discord.utils.get(
            guild.roles,
            name=role_name
        )

        if existing_role:

            save_notification_role(
                guild.id,
                notification_type,
                existing_role.id
            )

            return existing_role

        try:

            role = await guild.create_role(
                name=role_name,
                color=info["color"],
                mentionable=True,
                reason=(
                    "Fime Stock "
                    "Notification Role"
                )
            )

            save_notification_role(
                guild.id,
                notification_type,
                role.id
            )

            return role

        except discord.Forbidden:

            print(
                "❌ Cannot create "
                "notification role."
            )

            return None

        except Exception as error:

            print(
                "❌ Role creation error:",
                error
            )

            return None

    # ========================================================
    # GAG ITEM / FRUIT ROLE
    # ========================================================

    async def get_or_create_gag_item_role(
        self,
        guild,
        item_name
    ):

        item_name = normalize_item_name(
            item_name
        )

        if not item_name:
            return None

        existing_id = get_gag_item_role(
            guild.id,
            item_name
        )

        if existing_id:

            role = guild.get_role(
                existing_id
            )

            if role:
                return role

        # Keep role names short and clean.
        role_name = (
            f"🍎 {item_name}"
        )

        if len(role_name) > 100:

            role_name = (
                role_name[:100]
            )

        existing_role = discord.utils.get(
            guild.roles,
            name=role_name
        )

        if existing_role:

            save_gag_item_role(
                guild.id,
                item_name,
                existing_role.id
            )

            return existing_role

        try:

            role = await guild.create_role(
                name=role_name,
                color=discord.Color.green(),
                mentionable=True,
                reason=(
                    "Fime GAG "
                    "Fruit Notification Role"
                )
            )

            save_gag_item_role(
                guild.id,
                item_name,
                role.id
            )

            return role

        except discord.Forbidden:

            print(
                "❌ Cannot create GAG "
                f"item role for {item_name}."
            )

            return None

        except Exception as error:

            print(
                "❌ GAG item role "
                f"creation error: {error}"
            )

            return None

    # ========================================================
    # SEND GAG FRUIT SELECT PANEL
    # ========================================================

    async def send_gag_fruit_panel(
        self,
        channel,
        stock
    ):

        options = build_gag_item_select_options(
            stock
        )

        if not options:
            return

        embed = discord.Embed(
            title="🍎 اختر إشعارات الفواكه",
            description=(
                "تبي البوت ينبهك إذا ظهرت فاكهة معينة؟\n\n"
                "اختار **أكثر من فاكهة** من القائمة "
                "بالأسفل.\n\n"
                "إذا ظهرت وحدة من اختياراتك في ستوك جديد، "
                "البوت بمنشنك تلقائيًا."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.add_field(
            name="💡 طريقة الاستخدام",
            value=(
                "تقدر تختار أكثر من عنصر بنفس المرة.\n"
                "كل اختيار يتم حفظه تلقائيًا."
            ),
            inline=False
        )

        embed.set_footer(
            text=(
                "Team Fime • "
                "Grow a Garden Notifications"
            )
        )

        try:

            await channel.send(
                embed=embed,
                view=GAGFruitView(stock)
            )

        except discord.Forbidden:

            print(
                "❌ Cannot send GAG "
                "fruit selector."
            )

        except Exception as error:

            print(
                "⚠️ GAG fruit selector error:",
                error
            )

    # ========================================================
    # SEND SHOP UPDATE
    # ========================================================

    async def send_shop_update(
        self,
        guild,
        game,
        stock
    ):

        channel_id = get_shop_channel(
            guild.id,
            game
        )

        if not channel_id:
            return

        channel = await self.resolve_channel(
            channel_id
        )

        if not channel:
            return

        mention = None

        if game == GAME_GAG:

            role_id = get_notification_role(
                guild.id,
                NOTIF_GAG_STOCK
            )

            all_role_id = get_notification_role(
                guild.id,
                NOTIF_ALL_STOCK
            )

            mentions = []

            if role_id:
                mentions.append(
                    f"<@&{role_id}>"
                )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
                )

            if mentions:
                mention = " ".join(
                    mentions
                )

        elif game == GAME_BLOX:

            role_id = get_notification_role(
                guild.id,
                NOTIF_BLOX_STOCK
            )

            all_role_id = get_notification_role(
                guild.id,
                NOTIF_ALL_STOCK
            )

            mentions = []

            if role_id:
                mentions.append(
                    f"<@&{role_id}>"
                )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
                )

            if mentions:
                mention = " ".join(
                    mentions
                )

        embeds = build_shop_embeds(
            game,
            stock
        )

        for index, embed in enumerate(
            embeds
        ):

            content = None

            if (
                index == 0
                and mention
            ):
                content = mention

            try:

                await channel.send(
                    content=content,
                    embed=embed
                )

            except discord.Forbidden:

                print(
                    f"❌ Cannot send in "
                    f"#{getattr(channel, 'name', 'unknown')}"
                )

                break

            except Exception as error:

                print(
                    "⚠️ Shop send error:",
                    error
                )

                break

        # ----------------------------------------------------
        # Every NEW GAG stock update gets the fruit selector.
        # ----------------------------------------------------

        if game == GAME_GAG:

            await self.send_gag_fruit_panel(
                channel,
                stock
            )

    # ========================================================
    # PERSONAL ALERTS
    # ========================================================

    async def send_personal_alerts(
        self,
        guild,
        game,
        added
    ):

        if not added:
            return

        conn = get_db()

        rows = conn.execute("""
            SELECT user_id, item
            FROM subscriptions
            WHERE guild_id = ?
            AND game = ?
        """, (
            guild.id,
            game
        )).fetchall()

        conn.close()

        for row in rows:

            member = guild.get_member(
                row["user_id"]
            )

            if not member:
                continue

            target = row["item"].lower()

            matches = [
                item
                for item in added
                if target
                in item["name"].lower()
            ]

            if not matches:
                continue

            text = "\n".join(
                (
                    f"• **{item['name']}** "
                    f"× `{item['stock']}`"
                )
                for item in matches
            )

            embed = discord.Embed(
                title="🔔 Stock Alert",
                description=(
                    "ظهر العنصر اللي طلبت "
                    "تنبيه عنه:\n\n"
                    f"{text}"
                ),
                color=discord.Color.green()
            )

            embed.set_footer(
                text=(
                    "Team Fime • "
                    "Personal Stock Alert"
                )
            )

            try:

                await member.send(
                    embed=embed
                )

            except Exception:
                pass

    # ========================================================
    # GAG ITEM ROLE ALERTS
    # ========================================================

    async def send_gag_item_role_alerts(
        self,
        guild,
        added
    ):

        if not added:
            return

        # ----------------------------------------------------
        # Collect subscribers for all newly added items.
        # ----------------------------------------------------

        for item in added:

            item_name = normalize_item_name(
                item.get("name")
            )

            if not item_name:
                continue

            subscribers = (
                get_gag_item_subscribers(
                    guild.id,
                    item_name
                )
            )

            if not subscribers:
                continue

            role_id = get_gag_item_role(
                guild.id,
                item_name
            )

            if not role_id:
                continue

            role = guild.get_role(
                role_id
            )

            if not role:
                continue

            # ------------------------------------------------
            # Mention everyone subscribed to this item
            # through the item role.
            # ------------------------------------------------

            content = role.mention

            embed = discord.Embed(
                title="🍎 فاكهة مطلوبة وصلت!",
                description=(
                    f"ظهرت **{item_name}** في "
                    f"الستوك الجديد.\n\n"
                    f"📦 الكمية: `{item.get('stock', 0)}`"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(
                    timezone.utc
                )
            )

            rarity = item.get(
                "rarity",
                ""
            )

            if rarity:

                embed.add_field(
                    name="✨ النوع",
                    value=f"`{rarity}`",
                    inline=True
                )

            embed.set_footer(
                text=(
                    "Team Fime • "
                    "GAG Fruit Alerts"
                )
            )

            channel_id = get_shop_channel(
                guild.id,
                GAME_GAG
            )

            if not channel_id:
                continue

            channel = await self.resolve_channel(
                channel_id
            )

            if not channel:
                continue

            try:

                await channel.send(
                    content=content,
                    embed=embed
                )

            except discord.Forbidden:

                print(
                    "❌ Cannot send GAG "
                    f"fruit alert for {item_name}."
                )

            except Exception as error:

                print(
                    "⚠️ GAG fruit alert error:",
                    error
                )

    # ========================================================
    # PROCESS STOCK
    # ========================================================

    async def process_stock(
        self,
        guild,
        game,
        stock
    ):

        stock = clean_stock(
            stock
        )

        if not stock:
            return

        current_json = (
            serialize_stock(stock)
        )

        old_json = get_cached_stock(
            guild.id,
            game
        )

        # First successful poll:
        # cache only, don't spam.
        if old_json is None:

            save_cached_stock(
                guild.id,
                game,
                current_json
            )

            return

        if old_json == current_json:
            return

        try:

            old_stock = json.loads(
                old_json
            )

        except Exception:

            old_stock = []

        old_stock = clean_stock(
            old_stock
        )

        old_keys = {
            (
                item["name"].lower(),
                str(item["stock"]),
                item.get(
                    "rarity",
                    ""
                ).lower()
            )
            for item in old_stock
        }

        new_keys = {
            (
                item["name"].lower(),
                str(item["stock"]),
                item.get(
                    "rarity",
                    ""
                ).lower()
            )
            for item in stock
        }

        added = [
            item
            for item in stock
            if (
                item["name"].lower(),
                str(item["stock"]),
                item.get(
                    "rarity",
                    ""
                ).lower()
            ) not in old_keys
        ]

        removed = [
            item
            for item in old_stock
            if (
                item["name"].lower(),
                str(item["stock"]),
                item.get(
                    "rarity",
                    ""
                ).lower()
            ) not in new_keys
        ]

        # Save immediately
        save_cached_stock(
            guild.id,
            game,
            current_json
        )

        # ----------------------------------------------------
        # Send full stock
        # ----------------------------------------------------

        await self.send_shop_update(
            guild,
            game,
            stock
        )

        # ----------------------------------------------------
        # Personal alerts
        # ----------------------------------------------------

        await self.send_personal_alerts(
            guild,
            game,
            added
        )

        # ----------------------------------------------------
        # GAG fruit/item role alerts
        # ----------------------------------------------------

        if game == GAME_GAG:

            await self.send_gag_item_role_alerts(
                guild,
                added
            )

        # ----------------------------------------------------
        # Rare stock
        # ----------------------------------------------------

        if game == GAME_GAG:

            rare_added = [
                item
                for item in added
                if is_rare_item(item)
            ]

            if rare_added:

                role_id = (
                    get_notification_role(
                        guild.id,
                        NOTIF_GAG_RARE
                    )
                )

                channel_id = (
                    get_shop_channel(
                        guild.id,
                        GAME_GAG
                    )
                )

                if (
                    role_id
                    and channel_id
                ):

                    channel = (
                        await self.resolve_channel(
                            channel_id
                        )
                    )

                    if channel:

                        text = "\n".join(
                            (
                                f"💎 **{item['name']}** "
                                f"× `{item['stock']}`"
                            )
                            for item
                            in rare_added
                        )

                        embed = discord.Embed(
                            title=(
                                "💎 Rare Stock!"
                            ),
                            description=text,
                            color=discord.Color.gold()
                        )

                        try:

                            await channel.send(
                                content=(
                                    f"<@&{role_id}>"
                                ),
                                embed=embed
                            )

                        except Exception:
                            pass

    # ========================================================
    # STOCK LOOP
    # ========================================================

    @tasks.loop(
        seconds=STOCK_CHECK_SECONDS
    )
    async def stock_loop(
        self
    ):

        await self.bot.wait_until_ready()

        await self.ensure_session()

        if not self.bot.guilds:
            return

        # ----------------------------------------------------
        # Grow a Garden
        # ----------------------------------------------------

        gag_stock = (
            await fetch_gag_stock(
                self.session
            )
        )

        # ----------------------------------------------------
        # Blox Fruits
        # ----------------------------------------------------

        blox_stock = []

        if BLOX_API_URL:

            blox_stock = (
                await fetch_blox_stock(
                    self.session
                )
            )

        # ----------------------------------------------------
        # Process every guild
        # ----------------------------------------------------

        for guild in list(
            self.bot.guilds
        ):

            try:

                if gag_stock:

                    await self.process_stock(
                        guild,
                        GAME_GAG,
                        gag_stock
                    )

                if blox_stock:

                    await self.process_stock(
                        guild,
                        GAME_BLOX,
                        blox_stock
                    )

            except Exception as error:

                print(
                    f"⚠️ Stock processing "
                    f"error for "
                    f"{guild.name}: "
                    f"{error}"
                )

    @stock_loop.before_loop
    async def before_stock_loop(
        self
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # STEAL AN EGG LOOP
    # ========================================================

    @tasks.loop(
        minutes=1
    )
    async def steal_event_loop(
        self
    ):

        await self.bot.wait_until_ready()

        self.steal_reset_counter += 1

        self.steal_rift_counter += 1

        if (
            self.steal_reset_counter
            >= STEAL_EGG_RESET_MINUTES
        ):

            self.steal_reset_counter = 0

            await self.send_event_notification(
                NOTIF_STEAL_RESET,
                "🥚 Steal An Egg — Reset",
                "بدأت دورة Reset جديدة."
            )

        if (
            self.steal_rift_counter
            >= STEAL_EGG_RIFT_MINUTES
        ):

            self.steal_rift_counter = 0

            await self.send_event_notification(
                NOTIF_STEAL_RIFT,
                "🌀 Steal An Egg — Rift",
                "حان وقت Rift."
            )

    @steal_event_loop.before_loop
    async def before_steal_loop(
        self
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # EVENT NOTIFICATION
    # ========================================================

    async def send_event_notification(
        self,
        notification_type,
        title,
        description
    ):

        for guild in list(
            self.bot.guilds
        ):

            role_id = (
                get_notification_role(
                    guild.id,
                    notification_type
                )
            )

            all_role_id = (
                get_notification_role(
                    guild.id,
                    NOTIF_ALL_STOCK
                )
            )

            channel_id = (
                get_shop_channel(
                    guild.id,
                    GAME_STEAL
                )
            )

            if not channel_id:
                continue

            channel = (
                await self.resolve_channel(
                    channel_id
                )
            )

            if not channel:
                continue

            mentions = []

            if role_id:
                mentions.append(
                    f"<@&{role_id}>"
                )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
                )

            content = (
                " ".join(mentions)
                if mentions
                else None
            )

            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.orange(),
                timestamp=datetime.now(
                    timezone.utc
                )
            )

            embed.set_footer(
                text=(
                    "Team Fime • "
                    "Stock Alerts"
                )
            )

            try:

                await channel.send(
                    content=content,
                    embed=embed
                )

            except Exception:
                pass

    # ========================================================
    # /STOCK VIEW
    # ========================================================

    @stock_group.command(
        name="view",
        description="عرض الستوك الحالي"
    )
    @app_commands.describe(
        game="اللعبة"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX
            ),
        ]
    )
    async def stock_command(
        self,
        interaction,
        game: app_commands.Choice[str]
    ):

        await interaction.response.defer()

        await self.ensure_session()

        if game.value == GAME_GAG:

            stock = (
                await fetch_gag_stock(
                    self.session
                )
            )

        else:

            stock = (
                await fetch_blox_stock(
                    self.session
                )
            )

        if not stock:

            await interaction.followup.send(
                (
                    "❌ ما قدرت أجيب الستوك حاليًا.\n"
                    "قد يكون مصدر البيانات غير متاح."
                )
            )

            return

        embeds = build_shop_embeds(
            game.value,
            stock
        )

        for embed in embeds:

            await interaction.followup.send(
                embed=embed
            )

        # When manually viewing GAG stock,
        # also provide the fruit selector.
        if game.value == GAME_GAG:

            await interaction.followup.send(
                embed=discord.Embed(
                    title="🍎 إشعارات الفواكه",
                    description=(
                        "اختار الفواكه اللي تبي البوت "
                        "ينبهك عنها."
                    ),
                    color=discord.Color.green()
                ),
                view=GAGFruitView(stock)
            )

    # ========================================================
    # /STOCK CHANNEL
    # ========================================================

    @stock_group.command(
        name="channel",
        description="تحديد روم إرسال تحديثات الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        game="اللعبة",
        channel="الروم"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL
            ),
        ]
    )
    async def stock_channel_command(
        self,
        interaction,
        game: app_commands.Choice[str],
        channel: discord.TextChannel
    ):

        set_shop_channel(
            interaction.guild.id,
            game.value,
            channel.id
        )

        await interaction.response.send_message(
            (
                f"✅ تم تحديد {channel.mention}\n"
                f"للعبة **{GAME_NAMES[game.value]}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK CHANNEL-REMOVE
    # ========================================================

    @stock_group.command(
        name="channel-remove",
        description="إزالة روم الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        game="اللعبة"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL
            ),
        ]
    )
    async def stock_channel_remove(
        self,
        interaction,
        game: app_commands.Choice[str]
    ):

        remove_shop_channel(
            interaction.guild.id,
            game.value
        )

        await interaction.response.send_message(
            (
                f"✅ تم حذف روم "
                f"**{GAME_NAMES[game.value]}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK CHANNEL-STATUS
    # ========================================================

    @stock_group.command(
        name="channel-status",
        description="عرض رومات الستوك المحددة"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_channel_status(
        self,
        interaction
    ):

        channels = get_shop_channels(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="📡 Stock Channels",
            color=discord.Color.blurple()
        )

        for game in [
            GAME_GAG,
            GAME_BLOX,
            GAME_STEAL
        ]:

            channel_id = channels.get(
                game
            )

            channel = (
                interaction.guild.get_channel(
                    channel_id
                )
                if channel_id
                else None
            )

            embed.add_field(
                name=GAME_NAMES[game],
                value=(
                    channel.mention
                    if channel
                    else "❌ غير محدد"
                ),
                inline=False
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # /STOCK NOTIFICATIONS-SETUP
    # ========================================================

    @stock_group.command(
        name="notifications-setup",
        description="إنشاء لوحة إشعارات الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        channel="الروم"
    )
    async def stock_notifications_setup(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        embed = (
            build_notification_panel_embed()
        )

        try:

            message = await channel.send(
                embed=embed,
                view=NotificationView()
            )

            save_notification_panel(
                interaction.guild.id,
                channel.id,
                message.id
            )

            await interaction.followup.send(
                (
                    f"✅ تم إنشاء لوحة "
                    f"الإشعارات في {channel.mention}."
                ),
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ البوت لا يملك الصلاحيات "
                    "الكافية في هذا الروم."
                ),
                ephemeral=True
            )

        except Exception as error:

            print(
                "❌ Notification setup error:",
                error
            )

            await interaction.followup.send(
                "❌ حدث خطأ أثناء إنشاء اللوحة.",
                ephemeral=True
            )

    # ========================================================
    # /STOCK NOTIFICATIONS-RESET
    # ========================================================

    @stock_group.command(
        name="notifications-reset",
        description="تحديث لوحة الإشعارات"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_notifications_reset(
        self,
        interaction
    ):

        panel = get_notification_panel(
            interaction.guild.id
        )

        if not panel:

            await interaction.response.send_message(
                "❌ لا توجد لوحة محفوظة.",
                ephemeral=True
            )

            return

        channel_id, message_id = panel

        channel = (
            await self.resolve_channel(
                channel_id
            )
        )

        if not channel:

            await interaction.response.send_message(
                "❌ لا أستطيع الوصول للروم.",
                ephemeral=True
            )

            return

        try:

            message = (
                await channel.fetch_message(
                    message_id
                )
            )

            await message.edit(
                embed=(
                    build_notification_panel_embed()
                ),
                view=NotificationView()
            )

            await interaction.response.send_message(
                "✅ تم تحديث لوحة الإشعارات.",
                ephemeral=True
            )

        except discord.NotFound:

            try:

                new_message = (
                    await channel.send(
                        embed=(
                            build_notification_panel_embed()
                        ),
                        view=NotificationView()
                    )
                )

                save_notification_panel(
                    interaction.guild.id,
                    channel.id,
                    new_message.id
                )

                await interaction.response.send_message(
                    "✅ تم إنشاء لوحة جديدة.",
                    ephemeral=True
                )

            except Exception:

                await interaction.response.send_message(
                    "❌ تعذر إنشاء اللوحة.",
                    ephemeral=True
                )

        except Exception as error:

            print(
                "❌ Notification reset error:",
                error
            )

            await interaction.response.send_message(
                "❌ حدث خطأ أثناء تحديث اللوحة.",
                ephemeral=True
            )

    # ========================================================
    # /STOCK ALERT
    # ========================================================

    @stock_group.command(
        name="alert",
        description="إضافة تنبيه شخصي لعنصر"
    )
    @app_commands.describe(
        game="اللعبة",
        item="اسم العنصر"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX
            ),
        ]
    )
    async def stock_alert(
        self,
        interaction,
        game: app_commands.Choice[str],
        item: str
    ):

        conn = get_db()

        conn.execute("""
            INSERT OR IGNORE INTO subscriptions (
                guild_id,
                user_id,
                game,
                item
            )
            VALUES (?, ?, ?, ?)
        """, (
            interaction.guild.id,
            interaction.user.id,
            game.value,
            item.strip()
        ))

        conn.commit()

        conn.close()

        await interaction.response.send_message(
            (
                f"🔔 تم تفعيل التنبيه عن "
                f"**{item}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK ALERT-REMOVE
    # ========================================================

    @stock_group.command(
        name="alert-remove",
        description="إزالة تنبيه شخصي"
    )
    @app_commands.describe(
        game="اللعبة",
        item="اسم العنصر"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX
            ),
        ]
    )
    async def stock_alert_remove(
        self,
        interaction,
        game: app_commands.Choice[str],
        item: str
    ):

        conn = get_db()

        conn.execute("""
            DELETE FROM subscriptions
            WHERE guild_id = ?
            AND user_id = ?
            AND game = ?
            AND item = ?
        """, (
            interaction.guild.id,
            interaction.user.id,
            game.value,
            item.strip()
        ))

        conn.commit()

        conn.close()

        await interaction.response.send_message(
            (
                f"✅ تم إزالة تنبيه "
                f"**{item}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK ALERTS
    # ========================================================

    @stock_group.command(
        name="alerts",
        description="عرض تنبيهاتك الشخصية"
    )
    async def stock_alerts(
        self,
        interaction
    ):

        conn = get_db()

        rows = conn.execute("""
            SELECT game, item
            FROM subscriptions
            WHERE guild_id = ?
            AND user_id = ?
            ORDER BY game, item
        """, (
            interaction.guild.id,
            interaction.user.id
        )).fetchall()

        conn.close()

        gag_items = get_gag_user_items(
            interaction.guild.id,
            interaction.user.id
        )

        if not rows and not gag_items:

            await interaction.response.send_message(
                (
                    "📭 ما عندك أي تنبيهات "
                    "شخصية حاليًا."
                ),
                ephemeral=True
            )

            return

        lines = []

        for row in rows:

            lines.append(
                (
                    f"• "
                    f"{GAME_NAMES.get(row['game'], row['game'])}"
                    f" — **{row['item']}**"
                )
            )

        if gag_items:

            lines.append(
                ""
            )

            lines.append(
                "🍎 **فواكه Grow a Garden:**"
            )

            for item_name in gag_items:

                lines.append(
                    f"• **{item_name}**"
                )

        embed = discord.Embed(
            title="🔔 تنبيهاتك الشخصية",
            description="\n".join(
                lines
            ),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # /STOCK STEAL-ALERT
    # ========================================================

    @stock_group.command(
        name="steal-alert",
        description="تفعيل إشعار Steal An Egg"
    )
    @app_commands.describe(
        alert="نوع الإشعار"
    )
    @app_commands.choices(
        alert=[
            app_commands.Choice(
                name="🥚 Reset",
                value=NOTIF_STEAL_RESET
            ),
            app_commands.Choice(
                name="🌀 Rift",
                value=NOTIF_STEAL_RIFT
            ),
        ]
    )
    async def steal_alert(
        self,
        interaction,
        alert: app_commands.Choice[str]
    ):

        role = (
            await self.get_or_create_notification_role(
                interaction.guild,
                alert.value
            )
        )

        if not role:

            await interaction.response.send_message(
                (
                    "❌ ما قدرت أجهز رتبة الإشعار."
                ),
                ephemeral=True
            )

            return

        try:

            await interaction.user.add_roles(
                role,
                reason=(
                    "Fime Stock Notification"
                )
            )

            add_notification_member(
                interaction.guild.id,
                interaction.user.id,
                alert.value
            )

            await interaction.response.send_message(
                (
                    f"🔔 تم تفعيل "
                    f"**{role.name}**."
                ),
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                (
                    "❌ البوت لا يستطيع إعطاء "
                    "هذه الرتبة."
                ),
                ephemeral=True
            )

    # ========================================================
    # /STOCK STEAL-ALERT-REMOVE
    # ========================================================

    @stock_group.command(
        name="steal-alert-remove",
        description="إزالة إشعار Steal An Egg"
    )
    @app_commands.describe(
        alert="نوع الإشعار"
    )
    @app_commands.choices(
        alert=[
            app_commands.Choice(
                name="🥚 Reset",
                value=NOTIF_STEAL_RESET
            ),
            app_commands.Choice(
                name="🌀 Rift",
                value=NOTIF_STEAL_RIFT
            ),
        ]
    )
    async def steal_alert_remove(
        self,
        interaction,
        alert: app_commands.Choice[str]
    ):

        role_id = (
            get_notification_role(
                interaction.guild.id,
                alert.value
            )
        )

        if role_id:

            role = interaction.guild.get_role(
                role_id
            )

            if (
                role
                and role in interaction.user.roles
            ):

                try:

                    await interaction.user.remove_roles(
                        role,
                        reason=(
                            "Fime Stock "
                            "Notification Removal"
                        )
                    )

                except Exception:
                    pass

        remove_notification_member(
            interaction.guild.id,
            interaction.user.id,
            alert.value
        )

        await interaction.response.send_message(
            "✅ تم إلغاء الإشعار.",
            ephemeral=True
        )

    # ========================================================
    # /STOCK STATUS
    # ========================================================

    @stock_group.command(
        name="status",
        description="عرض حالة نظام الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_status(
        self,
        interaction
    ):

        channels = get_shop_channels(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="📊 Team Fime Stock System",
            color=discord.Color.blurple(),
            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.add_field(
            name="🌱 GAG API",
            value=(
                "🟢 Configured"
                if GAG_API_URL
                else "🔴 Not configured"
            ),
            inline=True
        )

        embed.add_field(
            name="🍎 Blox API",
            value=(
                "🟢 Configured"
                if BLOX_API_URL
                else "⚪ Not configured"
            ),
            inline=True
        )

        embed.add_field(
            name="⏱️ Polling",
            value=(
                f"`{STOCK_CHECK_SECONDS}s`"
            ),
            inline=True
        )

        embed.add_field(
            name="🔔 Notification Panel",
            value=(
                "🟢 Configured"
                if get_notification_panel(
                    interaction.guild.id
                )
                else "🔴 Not configured"
            ),
            inline=True
        )

        for game in [
            GAME_GAG,
            GAME_BLOX,
            GAME_STEAL
        ]:

            channel_id = channels.get(
                game
            )

            channel = (
                interaction.guild.get_channel(
                    channel_id
                )
                if channel_id
                else None
            )

            embed.add_field(
                name=GAME_NAMES[game],
                value=(
                    channel.mention
                    if channel
                    else "❌ غير محدد"
                ),
                inline=True
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # ERROR HANDLER
    # ========================================================

    async def cog_app_command_error(
        self,
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

        elif isinstance(
            error,
            app_commands.errors.CommandOnCooldown
        ):

            message = (
                "⏳ انتظر قليلًا ثم حاول."
            )

        else:

            print(
                "❌ bot6 command error:",
                error
            )

            message = (
                "❌ حدث خطأ أثناء تنفيذ الأمر."
            )

        try:

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

        except Exception:
            pass


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