# ============================================================
# Team Fime - Stock System
# bot6.py
#
# 🌱 Grow a Garden
# 🍎 Blox Fruits
# 🥚 Steal An Egg
#
# FULL STABLE EDITION
# ============================================================

import os
import json
import sqlite3
import asyncio
import html
import re
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus

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

# ------------------------------------------------------------
# Grow a Garden
# ------------------------------------------------------------

GAG_API_URL = os.getenv(
    "GAG_API_URL",
    ""
).strip()

GAG_API_FALLBACK_URL = os.getenv(
    "GAG_API_FALLBACK_URL",
    ""
).strip()

GAG_API_FALLBACK_URLS = [
    url.strip()
    for url in os.getenv(
        "GAG_API_FALLBACK_URLS",
        ""
    ).split(",")
    if url.strip()
]

# ------------------------------------------------------------
# Blox Fruits
# ------------------------------------------------------------

# Parse get_stock endpoint.
BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    "https://api.parse.bot/scraper/78cf8155-3819-45d0-b799-92f840a94827/get_stock"
).strip()

BLOX_API_KEY = os.getenv(
    "BLOX_API_KEY",
    ""
).strip()

BLOX_API_FALLBACK_URL = os.getenv(
    "BLOX_API_FALLBACK_URL",
    ""
).strip()

# ------------------------------------------------------------
# Steal An Egg
# ------------------------------------------------------------

# Optional API.
#
# If you have an API:
# STEAL_EGG_API_URL=https://...
#
# If empty, the system remains alive and can use
# the general-search fallback manually.
STEAL_EGG_API_URL = os.getenv(
    "STEAL_EGG_API_URL",
    ""
).strip()

STEAL_EGG_FALLBACK_URLS = [
    url.strip()
    for url in os.getenv(
        "STEAL_EGG_API_FALLBACK_URLS",
        ""
    ).split(",")
    if url.strip()
]

# ------------------------------------------------------------
# General web search fallback
# ------------------------------------------------------------

WEB_SEARCH_ENABLED = os.getenv(
    "STOCK_WEB_SEARCH_ENABLED",
    "true"
).lower() not in (
    "false",
    "0",
    "no",
    "off"
)

WEB_SEARCH_URL = os.getenv(
    "STOCK_WEB_SEARCH_URL",
    "https://api.duckduckgo.com/"
).strip()

# ------------------------------------------------------------
# Polling
# ------------------------------------------------------------

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

MAX_SELECT_OPTIONS = 25

# ============================================================
# GENERAL ROBLOX / EVENT SEARCH
# ============================================================

GENERAL_SEARCH_LIMIT = 8
EVENT_CHECK_MINUTES = 5

ROBLOX_GAME_SEARCH_URL = (
    "https://games.roblox.com/v1/games/list"
)
ROBLOX_GAME_DETAILS_URL = (
    "https://games.roblox.com/v1/games"
)
GOOGLE_NEWS_RSS_URL = (
    "https://news.google.com/rss/search"
)



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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_watchers (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            game_name TEXT NOT NULL,
            query TEXT NOT NULL,
            last_fingerprint TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, channel_id, game_name)
        )
    """)

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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)

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

def set_shop_channel(guild_id, game, channel_id):

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


def remove_shop_channel(guild_id, game):

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


def get_shop_channels(guild_id):

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


def get_shop_channel(guild_id, game):

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


def get_cached_stock(guild_id, game):

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


def get_notification_panel(guild_id):

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
# GAG ITEM DATABASE
# ============================================================

def normalize_item_name(name):

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
# HTTP
# ============================================================

async def fetch_json(
    session,
    url,
    headers=None
):

    if not url:
        return None

    try:

        timeout = aiohttp.ClientTimeout(
            total=15
        )

        async with session.get(
            url,
            headers=headers or {},
            timeout=timeout
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

                text = await response.text()

                if text:
                    print(
                        "⚠️ API returned non-JSON "
                        f"response: {url}"
                    )

                return None

    except asyncio.TimeoutError:

        print(
            f"⚠️ Stock API timeout: {url}"
        )

        return None

    except aiohttp.ClientError as error:

        print(
            f"⚠️ Stock API connection error: "
            f"{error}"
        )

        return None

    except Exception as error:

        print(
            f"⚠️ Stock API error: {error}"
        )

        return None


# ============================================================
# HELPERS
# ============================================================

def key_normalize(value):

    return (
        str(value or "")
        .strip()
        .lower()
        .replace("_", "")
        .replace("-", "")
        .replace(" ", "")
    )


def first_value(
    data,
    keys
):

    if not isinstance(data, dict):
        return None

    normalized = {
        key_normalize(k): v
        for k, v in data.items()
    }

    for key in keys:

        value = normalized.get(
            key_normalize(key)
        )

        if value is not None:
            return value

    return None


def to_number_if_possible(value):

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):

        value = value.strip()

        if not value:
            return value

        try:

            if "." in value:
                return float(value)

            return int(value)

        except Exception:
            return value

    return value


# ============================================================
# STOCK NORMALIZER
# ============================================================

def normalize_item(
    item,
    default_stock=None,
    forced_category="",
    forced_dealer=""
):

    if isinstance(item, str):

        return {
            "name": item.strip(),
            "stock": default_stock,
            "rarity": "",
            "type": "",
            "category": forced_category,
            "dealer": forced_dealer,
            "money_price": None,
            "robux_price": None,
            "price": None,
        }

    if not isinstance(item, dict):
        return None

    name = first_value(
        item,
        [
            "name",
            "item",
            "title",
            "displayName",
            "display_name",
            "seed",
            "fruit",
            "gear",
            "egg",
        ]
    )

    if not name:
        return None

    stock = first_value(
        item,
        [
            "quantity",
            "stock",
            "amount",
            "count",
            "qty",
            "available",
            "available_stock",
            "stock_amount",
        ]
    )

    if stock is None:
        stock = default_stock

    stock = to_number_if_possible(
        stock
    )

    rarity = first_value(
        item,
        [
            "rarity",
            "tier",
        ]
    )

    item_type = first_value(
        item,
        [
            "type",
            "item_type",
            "kind",
        ]
    )

    category = first_value(
        item,
        [
            "category",
            "section",
            "group",
        ]
    )

    dealer = first_value(
        item,
        [
            "dealer",
            "shop",
            "source",
        ]
    )

    money_price = first_value(
        item,
        [
            "money_price",
            "moneyPrice",
            "price_beli",
            "priceBeli",
            "beli_price",
            "beliPrice",
            "beli",
        ]
    )

    robux_price = first_value(
        item,
        [
            "robux_price",
            "robuxPrice",
            "price_robux",
            "priceRobux",
            "robux",
        ]
    )

    price = first_value(
        item,
        [
            "price",
        ]
    )

    return {
        "name": str(name).strip(),
        "stock": stock,
        "rarity": str(
            rarity or ""
        ).strip(),
        "type": str(
            item_type or ""
        ).strip(),
        "category": str(
            category or forced_category or ""
        ).strip(),
        "dealer": str(
            dealer or forced_dealer or ""
        ).strip(),
        "money_price": to_number_if_possible(
            money_price
        ),
        "robux_price": to_number_if_possible(
            robux_price
        ),
        "price": to_number_if_possible(
            price
        ),
    }


# ============================================================
# RECURSIVE STOCK EXTRACTION
# ============================================================

STOCK_CONTAINER_KEYS = {
    "stock",
    "stocks",
    "items",
    "shop",
    "inventory",
    "goods",
    "data",

    "seeds",
    "seedstock",
    "seed_stock",

    "gear",
    "gearstock",
    "gear_stock",

    "eggs",
    "eggstock",
    "egg_stock",

    "cosmetics",
    "cosmeticstock",
    "cosmetic_stock",

    "eventshop",
    "eventstock",
    "event_shop",
    "event_stock",
}


def dict_looks_like_item(data):

    if not isinstance(data, dict):
        return False

    keys = {
        key_normalize(key)
        for key in data.keys()
    }

    item_keys = {
        "name",
        "item",
        "title",
        "displayname",
        "display_name",
        "seed",
        "fruit",
        "egg",
        "gear",
    }

    return bool(
        keys.intersection(item_keys)
    )


def extract_items_recursive(
    data,
    category="",
    output=None,
    visited=None
):

    if output is None:
        output = []

    if visited is None:
        visited = set()

    if isinstance(data, (dict, list)):

        marker = id(data)

        if marker in visited:
            return output

        visited.add(marker)

    if isinstance(data, list):

        for item in data:

            if isinstance(item, dict):

                if dict_looks_like_item(item):

                    normalized = normalize_item(
                        item,
                        forced_category=category
                    )

                    if normalized:
                        output.append(
                            normalized
                        )

                else:

                    extract_items_recursive(
                        item,
                        category=category,
                        output=output,
                        visited=visited
                    )

            elif isinstance(item, str):

                normalized = normalize_item(
                    item,
                    forced_category=category
                )

                if normalized:
                    output.append(
                        normalized
                    )

        return output

    if not isinstance(data, dict):
        return output

    if dict_looks_like_item(data):

        normalized = normalize_item(
            data,
            forced_category=category
        )

        if normalized:
            output.append(
                normalized
            )

        return output

    for raw_key, value in data.items():

        normalized_key = key_normalize(
            raw_key
        )

        current_category = category

        if normalized_key in {
            "seedstock",
            "seeds",
            "seed_stock",
        }:
            current_category = "Seeds"

        elif normalized_key in {
            "gearstock",
            "gear",
            "gear_stock",
        }:
            current_category = "Gear"

        elif normalized_key in {
            "eggstock",
            "eggs",
            "egg_stock",
        }:
            current_category = "Eggs"

        elif normalized_key in {
            "cosmeticstock",
            "cosmetics",
            "cosmetic_stock",
        }:
            current_category = "Cosmetics"

        elif normalized_key in {
            "eventshop",
            "eventstock",
            "event_shop",
            "event_stock",
        }:
            current_category = "Event"

        if isinstance(value, dict):

            # Example:
            # {
            #   "Apple": 4,
            #   "Carrot": 7
            # }
            if not dict_looks_like_item(value):

                looks_like_mapping = True

                for child_value in value.values():

                    if isinstance(
                        child_value,
                        (dict, list)
                    ):
                        looks_like_mapping = False
                        break

                if looks_like_mapping:

                    for item_name, amount in value.items():

                        # Ignore obvious metadata fields.
                        if key_normalize(item_name) in {
                            "status",
                            "message",
                            "timestamp",
                            "updatedat",
                            "reset",
                            "resettimes",
                        }:
                            continue

                        if isinstance(
                            amount,
                            (int, float, str)
                        ):

                            normalized = normalize_item(
                                {
                                    "name": item_name,
                                    "stock": amount,
                                },
                                forced_category=current_category
                            )

                            if normalized:
                                output.append(
                                    normalized
                                )

                            continue

            extract_items_recursive(
                value,
                category=current_category,
                output=output,
                visited=visited
            )

        elif isinstance(value, list):

            extract_items_recursive(
                value,
                category=current_category,
                output=output,
                visited=visited
            )

    return output


def normalize_stock(
    data,
    default_stock=None
):

    result = []

    raw_items = extract_items_recursive(
        data
    )

    # If recursive extraction found nothing and the
    # response itself is a list, process it directly.
    if not raw_items and isinstance(
        data,
        list
    ):

        for item in data:

            normalized = normalize_item(
                item,
                default_stock=default_stock
            )

            if normalized:
                raw_items.append(
                    normalized
                )

    # Apply default stock to items that didn't have one.
    for item in raw_items:

        if (
            item.get("stock") is None
            and default_stock is not None
        ):
            item["stock"] = default_stock

        result.append(
            item
        )

    return clean_stock(
        result
    )


# ============================================================
# BLOX SPECIFIC EXTRACTION
# ============================================================

def find_blox_sections(data):

    sections = []

    if isinstance(data, dict):

        normal = first_value(
            data,
            [
                "normal",
            ]
        )

        mirage = first_value(
            data,
            [
                "mirage",
            ]
        )

        if normal is not None:
            sections.append(
                (
                    "Normal",
                    normal
                )
            )

        if mirage is not None:
            sections.append(
                (
                    "Mirage",
                    mirage
                )
            )

        # Common wrapper.
        nested_data = first_value(
            data,
            [
                "data",
                "result",
                "response",
            ]
        )

        if (
            nested_data is not None
            and nested_data is not data
        ):

            sections.extend(
                find_blox_sections(
                    nested_data
                )
            )

    return sections


def normalize_blox_section(
    section,
    dealer
):

    result = []

    if isinstance(section, list):

        for item in section:

            normalized = normalize_item(
                item,
                default_stock=1,
                forced_dealer=dealer
            )

            if normalized:

                normalized["dealer"] = dealer

                result.append(
                    normalized
                )

    elif isinstance(section, dict):

        if dict_looks_like_item(section):

            normalized = normalize_item(
                section,
                default_stock=1,
                forced_dealer=dealer
            )

            if normalized:

                normalized["dealer"] = dealer

                result.append(
                    normalized
                )

        else:

            for name, value in section.items():

                if isinstance(
                    value,
                    dict
                ):

                    copied = dict(value)

                    copied.setdefault(
                        "name",
                        name
                    )

                    normalized = normalize_item(
                        copied,
                        default_stock=1,
                        forced_dealer=dealer
                    )

                else:

                    normalized = normalize_item(
                        {
                            "name": name,
                            "stock": 1,
                            "price": value,
                        },
                        default_stock=1,
                        forced_dealer=dealer
                    )

                if normalized:

                    normalized["dealer"] = dealer

                    result.append(
                        normalized
                    )

    return result


async def fetch_blox_stock(
    session
):

    if not BLOX_API_KEY:

        print(
            "⚠️ BLOX_API_KEY is not configured."
        )

        return []

    urls = []

    if BLOX_API_URL:
        urls.append(
            BLOX_API_URL
        )

    if (
        BLOX_API_FALLBACK_URL
        and BLOX_API_FALLBACK_URL
        not in urls
    ):
        urls.append(
            BLOX_API_FALLBACK_URL
        )

    headers = {
        "X-API-Key": BLOX_API_KEY,
        "Accept": "application/json",
        "User-Agent": "Team-Fime-Stock/1.0",
    }

    for url in urls:

        data = await fetch_json(
            session,
            url,
            headers=headers
        )

        if data is None:
            continue

        sections = find_blox_sections(
            data
        )

        result = []

        for dealer, section in sections:

            result.extend(
                normalize_blox_section(
                    section,
                    dealer
                )
            )

        if result:

            return clean_stock(
                result
            )

        # Some APIs might return a direct list.
        direct = normalize_stock(
            data,
            default_stock=1
        )

        if direct:

            for item in direct:

                if not item.get("dealer"):
                    item["dealer"] = "Normal"

            return clean_stock(
                direct
            )

        print(
            "⚠️ Blox API responded but "
            "no stock format was recognized."
        )

    return []


# ============================================================
# GAG FETCHER
# ============================================================

async def fetch_gag_stock(
    session
):

    urls = []

    if GAG_API_URL:
        urls.append(
            GAG_API_URL
        )

    if (
        GAG_API_FALLBACK_URL
        and GAG_API_FALLBACK_URL
        not in urls
    ):
        urls.append(
            GAG_API_FALLBACK_URL
        )

    for url in GAG_API_FALLBACK_URLS:

        if url not in urls:
            urls.append(
                url
            )

    if not urls:

        print(
            "⚠️ GAG_API_URL is not configured."
        )

        return []

    # Primary first.
    # Fallbacks only when the previous source
    # gives no recognizable stock.
    for index, url in enumerate(urls):

        data = await fetch_json(
            session,
            url
        )

        if data is None:
            print(
                f"⚠️ GAG source {index + 1} failed."
            )
            continue

        stock = normalize_stock(
            data
        )

        if stock:

            print(
                f"✅ GAG stock loaded from "
                f"source {index + 1}: "
                f"{len(stock)} items."
            )

            return stock

        print(
            f"⚠️ GAG source {index + 1} "
            "returned no recognizable items."
        )

    return []


# ============================================================
# STEAL AN EGG FETCHER
# ============================================================

async def fetch_steal_stock(
    session
):

    urls = []

    if STEAL_EGG_API_URL:
        urls.append(
            STEAL_EGG_API_URL
        )

    for url in STEAL_EGG_FALLBACK_URLS:

        if url not in urls:
            urls.append(
                url
            )

    if not urls:
        return []

    for index, url in enumerate(urls):

        data = await fetch_json(
            session,
            url
        )

        if data is None:
            continue

        stock = normalize_stock(
            data
        )

        if stock:

            print(
                f"✅ Steal An Egg stock "
                f"loaded from source {index + 1}."
            )

            return stock

    return []


# ============================================================
# GENERAL WEB SEARCH
# ============================================================


async def roblox_game_search(session, query, limit=GENERAL_SEARCH_LIMIT):

    query = str(query or "").strip()
    if not query:
        return []

    params = {
        "model.keyword": query,
        "model.maxRows": min(max(int(limit), 1), 25),
        "model.startRows": 0,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=12)
        async with session.get(
            ROBLOX_GAME_SEARCH_URL,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "Team-Fime/1.0"},
        ) as response:
            if response.status != 200:
                return []
            data = await response.json(content_type=None)

        rows = data.get("games", []) if isinstance(data, dict) else []
        results = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            universe_id = row.get("universeId") or row.get("id")
            if not universe_id:
                continue
            results.append({
                "universe_id": int(universe_id),
                "name": str(row.get("name") or "Roblox Game").strip(),
                "description": str(row.get("description") or "").strip(),
                "creator": str(row.get("creatorName") or row.get("creator") or "Unknown").strip(),
                "place_id": row.get("placeId"),
            })
        return results[:limit]
    except Exception as error:
        print("⚠️ Roblox game search error:", error)
        return []


async def roblox_game_details(session, universe_ids):

    ids = []
    for value in universe_ids:
        try:
            ids.append(int(value))
        except Exception:
            pass

    if not ids:
        return []

    try:
        params = {"universeIds": ",".join(map(str, ids[:50]))}
        timeout = aiohttp.ClientTimeout(total=12)
        async with session.get(
            ROBLOX_GAME_DETAILS_URL,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "Team-Fime/1.0"},
        ) as response:
            if response.status != 200:
                return []
            data = await response.json(content_type=None)

        return data.get("data", []) if isinstance(data, dict) else []
    except Exception as error:
        print("⚠️ Roblox game details error:", error)
        return []


async def general_roblox_search(session, query, limit=GENERAL_SEARCH_LIMIT):

    """General Roblox search: games + live player counts + basic metadata."""

    games = await roblox_game_search(session, query, limit)
    if not games:
        return {"games": [], "news": []}

    details = await roblox_game_details(
        session,
        [game["universe_id"] for game in games]
    )
    by_id = {int(row.get("id")): row for row in details if row.get("id")}

    for game in games:
        row = by_id.get(game["universe_id"], {})
        game["playing"] = int(row.get("playing") or 0)
        game["visits"] = int(row.get("visits") or 0)
        game["favorites"] = int(row.get("favoritedCount") or 0)
        game["updated"] = row.get("updated") or row.get("created") or ""
        game["root_place_id"] = row.get("rootPlaceId") or game.get("place_id")

    return {"games": games, "news": []}


async def general_news_search(session, query, limit=8):

    """Public RSS search used for events, updates, pets, eggs, rarity, etc."""

    query = str(query or "").strip()
    if not query:
        return []

    try:
        params = {
            "q": query,
            "hl": "ar",
            "gl": "SA",
            "ceid": "SA:ar",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(
            GOOGLE_NEWS_RSS_URL,
            params=params,
            timeout=timeout,
            headers={"User-Agent": "Team-Fime/1.0"},
        ) as response:
            if response.status != 200:
                return []
            raw = await response.text()

        root = ET.fromstring(raw)
        results = []
        for item in root.findall("./channel/item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source = item.find("source")
            source_name = (source.text or "").strip() if source is not None else ""
            if title:
                results.append({
                    "title": html.unescape(title),
                    "link": link,
                    "published": pub,
                    "source": source_name,
                })
        return results
    except Exception as error:
        print("⚠️ General event/news search error:", error)
        return []


async def general_game_intelligence(session, query):

    """Search anything related to a Roblox map/game without pretending data is live."""

    query = str(query or "").strip()
    if not query:
        return None

    roblox = await general_roblox_search(session, query, GENERAL_SEARCH_LIMIT)
    news_queries = [
        f'Roblox "{query}" update event',
        f'Roblox "{query}" new update pets eggs rarity',
    ]

    news = []
    seen = set()
    for news_query in news_queries:
        for item in await general_news_search(session, news_query, 6):
            key = item.get("title", "").lower()
            if key and key not in seen:
                seen.add(key)
                news.append(item)
            if len(news) >= 10:
                break
        if len(news) >= 10:
            break

    roblox["news"] = news
    roblox["query"] = query
    return roblox


def event_fingerprint(items):
    return "|".join(
        str(item.get("title", "")).strip().lower()
        for item in items[:8]
    )


def set_event_watcher(guild_id, channel_id, game_name, query):
    conn = get_db()
    conn.execute("""
        INSERT INTO event_watchers
        (guild_id, channel_id, game_name, query, last_fingerprint, updated_at)
        VALUES (?, ?, ?, ?, '', ?)
        ON CONFLICT(guild_id, channel_id, game_name)
        DO UPDATE SET query=excluded.query, updated_at=excluded.updated_at
    """, (
        guild_id, channel_id, game_name, query,
        datetime.now(timezone.utc).isoformat(),
    ))
    conn.commit()
    conn.close()


def remove_event_watcher(guild_id, channel_id, game_name):
    conn = get_db()
    conn.execute("""
        DELETE FROM event_watchers
        WHERE guild_id=? AND channel_id=? AND game_name=?
    """, (guild_id, channel_id, game_name))
    conn.commit()
    conn.close()


def get_event_watchers():
    conn = get_db()
    rows = conn.execute("""
        SELECT guild_id, channel_id, game_name, query, last_fingerprint
        FROM event_watchers
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_event_fingerprint(guild_id, channel_id, game_name, fingerprint):
    conn = get_db()
    conn.execute("""
        UPDATE event_watchers
        SET last_fingerprint=?, updated_at=?
        WHERE guild_id=? AND channel_id=? AND game_name=?
    """, (
        fingerprint,
        datetime.now(timezone.utc).isoformat(),
        guild_id,
        channel_id,
        game_name,
    ))
    conn.commit()
    conn.close()


def build_game_intelligence_embed(query, data):

    embed = discord.Embed(
        title=f"🎮 {query}",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )

    games = data.get("games", [])
    news = data.get("news", [])

    if games:
        lines = []
        for index, game in enumerate(games[:8], 1):
            playing = f"{game.get('playing', 0):,}"
            creator = game.get("creator") or "غير معروف"
            lines.append(
                f"**{index}. {game['name'][:70]}**\n"
                f"👥 يلعبون الآن: **{playing}** • 👤 {creator[:40]}"
            )
        embed.add_field(
            name="🕹️ ألعاب وخرائط Roblox",
            value="\n\n".join(lines)[:1024],
            inline=False,
        )
    else:
        embed.add_field(
            name="🕹️ Roblox",
            value="ما لقيت لعبة مطابقة مباشرة في بحث Roblox.",
            inline=False,
        )

    if news:
        lines = []
        for item in news[:6]:
            title = item.get("title", "خبر جديد")[:160]
            link = item.get("link") or ""
            if link:
                lines.append(f"• [{title}]({link})")
            else:
                lines.append(f"• {title}")
        embed.add_field(
            name="📰 أحداث وتحديثات وأخبار",
            value="\n".join(lines)[:1024],
            inline=False,
        )

    embed.add_field(
        name="ℹ️ وش يقدر يبحث عنه؟",
        value=(
            "أحداث، تحديثات، حيوانات، بيض، ندرة، لاعبين، "
            "معلومات الماب وأي شيء تكتبه مرتبط بروبلوكس."
        ),
        inline=False,
    )
    embed.set_footer(text="حقوق Fime • بحث عام")
    return embed


def build_event_embed(game_name, news):

    embed = discord.Embed(
        title=f"🚨 حدث / تحديث جديد — {game_name}",
        color=discord.Color.orange(),
        timestamp=datetime.now(timezone.utc),
    )

    lines = []
    for item in news[:8]:
        title = item.get("title", "تحديث جديد")[:180]
        link = item.get("link") or ""
        if link:
            lines.append(f"• [{title}]({link})")
        else:
            lines.append(f"• {title}")

    embed.description = "\n".join(lines)[:4096] if lines else "تم رصد تحديث جديد، لكن تفاصيله غير متاحة حاليًا."
    embed.set_footer(text="حقوق Fime • تنبيهات الأحداث")
    return embed


async def general_stock_search(
    session,
    game
):

    if not WEB_SEARCH_ENABLED:
        return None

    queries = {
        GAME_GAG: (
            "Grow a Garden stock today Roblox"
        ),
        GAME_BLOX: (
            "Blox Fruits stock today Roblox"
        ),
        GAME_STEAL: (
            "Steal An Egg stock today Roblox"
        ),
    }

    query = queries.get(
        game,
        f"{game} stock today"
    )

    try:

        url = (
            f"{WEB_SEARCH_URL}"
            f"?q={quote_plus(query)}"
            f"&format=json"
            f"&no_html=1"
            f"&no_redirect=1"
        )

        data = await fetch_json(
            session,
            url
        )

        if not isinstance(
            data,
            dict
        ):
            return None

        abstract = str(
            data.get(
                "AbstractText"
            )
            or ""
        ).strip()

        abstract_url = str(
            data.get(
                "AbstractURL"
            )
            or ""
        ).strip()

        heading = str(
            data.get(
                "Heading"
            )
            or ""
        ).strip()

        topics = []

        related = data.get(
            "RelatedTopics"
        )

        if isinstance(
            related,
            list
        ):

            for topic in related[:5]:

                if not isinstance(
                    topic,
                    dict
                ):
                    continue

                text_value = str(
                    topic.get(
                        "Text"
                    )
                    or ""
                ).strip()

                if text_value:
                    topics.append(
                        text_value
                    )

        if not abstract and not topics:
            return None

        return {
            "query": query,
            "heading": heading,
            "abstract": abstract,
            "url": abstract_url,
            "topics": topics,
        }

    except Exception as error:

        print(
            "⚠️ General stock search error:",
            error
        )

        return None


def build_search_embed(
    game,
    result
):

    embed = discord.Embed(
        title=(
            f"🔎 {GAME_NAMES.get(game, game)}"
            " | بحث عام"
        ),
        description=(
            "ما لقيت مصدر ستوك مباشر متاح حاليًا، "
            "فتم إجراء بحث عام بدل اختراع بيانات ستوك."
        ),
        color=discord.Color.orange(),
        timestamp=datetime.now(
            timezone.utc
        )
    )

    if result.get("heading"):

        embed.add_field(
            name="📌 النتيجة",
            value=result["heading"][:1024],
            inline=False
        )

    if result.get("abstract"):

        embed.add_field(
            name="🔎 ملخص البحث",
            value=result["abstract"][:1024],
            inline=False
        )

    topics = result.get(
        "topics",
        []
    )

    if topics:

        text = "\n".join(
            f"• {html.unescape(topic)[:250]}"
            for topic in topics[:5]
        )

        embed.add_field(
            name="📚 نتائج إضافية",
            value=text[:1024],
            inline=False
        )

    embed.add_field(
        name="🔍 البحث",
        value=f"`{result.get('query', '')}`",
        inline=False
    )

    if result.get("url"):

        embed.add_field(
            name="🌐 المصدر",
            value=result["url"][:1024],
            inline=False
        )

    embed.set_footer(
        text=(
            "Team Fime • General Search Fallback"
        )
    )

    return embed


# ============================================================
# STOCK CLEANING
# ============================================================

def clean_stock(stock):

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

        if not name:
            continue

        stock_count = item.get(
            "stock"
        )

        rarity = str(
            item.get("rarity")
            or ""
        ).strip()

        item_type = str(
            item.get("type")
            or ""
        ).strip()

        category = str(
            item.get("category")
            or ""
        ).strip()

        dealer = str(
            item.get("dealer")
            or ""
        ).strip()

        money_price = item.get(
            "money_price"
        )

        robux_price = item.get(
            "robux_price"
        )

        price = item.get(
            "price"
        )

        key = (
            name.lower(),
            str(stock_count),
            rarity.lower(),
            item_type.lower(),
            category.lower(),
            dealer.lower(),
            str(money_price),
            str(robux_price),
            str(price),
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
            "type": item_type,
            "category": category,
            "dealer": dealer,
            "money_price": money_price,
            "robux_price": robux_price,
            "price": price,
        })

    cleaned.sort(
        key=lambda item: (
            item["category"].lower(),
            item["dealer"].lower(),
            item["name"].lower(),
            str(item["stock"])
        )
    )

    return cleaned


def serialize_stock(stock):

    return json.dumps(
        clean_stock(stock),
        ensure_ascii=False,
        sort_keys=True
    )


# ============================================================
# RARE
# ============================================================

def is_rare_item(item):

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
# DISPLAY HELPERS
# ============================================================

def format_price(
    item
):

    money = item.get(
        "money_price"
    )

    robux = item.get(
        "robux_price"
    )

    price = item.get(
        "price"
    )

    parts = []

    if money not in (
        None,
        "",
        0,
        "0"
    ):
        parts.append(
            f"💰 `{money}`"
        )

    if robux not in (
        None,
        "",
        0,
        "0"
    ):
        parts.append(
            f"💎 `{robux} Robux`"
        )

    if not parts and price not in (
        None,
        "",
        0,
        "0"
    ):
        parts.append(
            f"💰 `{price}`"
        )

    return " • ".join(
        parts
    )


def format_stock_line(
    item
):

    line = f"**{item['name']}**"

    amount = item.get(
        "stock"
    )

    if amount not in (
        None,
        "",
        0,
        "0"
    ):
        line += (
            f" × `{amount}`"
        )

    dealer = item.get(
        "dealer"
    )

    if dealer:
        line += (
            f" — `{dealer}`"
        )

    item_type = item.get(
        "type"
    )

    if item_type:
        line += (
            f" — `{item_type}`"
        )

    rarity = item.get(
        "rarity"
    )

    if rarity:
        line += (
            f" — `{rarity}`"
        )

    price = format_price(
        item
    )

    if price:
        line += (
            f"\n{price}"
        )

    return line + "\n"


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

    current_category = None

    for item in stock:

        category = (
            item.get("category")
            or item.get("dealer")
            or ""
        )

        heading = ""

        if (
            category
            and category != current_category
        ):

            heading = (
                f"\n**━━ {category} ━━**\n"
            )

            current_category = category

        line = (
            heading
            + format_stock_line(item)
        )

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
                f" ({index + 1}/{len(chunks)})"
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
                    "Team Fime • Stock System"
                )
            )

        embeds.append(
            embed
        )

    return embeds


# ============================================================
# NOTIFICATION PANEL
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
            "Team Fime • Notification System"
        )
    )

    return embed


# ============================================================
# NOTIFICATION SELECT
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
            placeholder="🔔 اختر إشعارًا...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="fime_stock_notifications"
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
                    reason="Fime Stock Notification Toggle"
                )

                remove_notification_member(
                    interaction.guild.id,
                    interaction.user.id,
                    notification_type
                )

                await interaction.followup.send(
                    f"➖ تم إلغاء **{role.name}**.",
                    ephemeral=True
                )

            else:

                await interaction.user.add_roles(
                    role,
                    reason="Fime Stock Notification Selection"
                )

                add_notification_member(
                    interaction.guild.id,
                    interaction.user.id,
                    notification_type
                )

                await interaction.followup.send(
                    f"✅ تم تفعيل **{role.name}**.",
                    ephemeral=True
                )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ Discord رفض تعديل الرتبة.\n"
                    "تأكد أن رتبة البوت أعلى من رتبة الإشعار."
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
# GAG SELECT
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
            "stock"
        )

        rarity = item.get(
            "rarity"
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

        if not options:

            options = [
                discord.SelectOption(
                    label="لا يوجد عناصر",
                    description="لا توجد عناصر متاحة حاليًا.",
                    value="__none__"
                )
            ]

        max_values = min(
            len(options),
            MAX_SELECT_OPTIONS
        )

        super().__init__(
            placeholder="🍎 اختر الفواكه اللي تبي إشعار عنها...",
            min_values=1,
            max_values=max_values,
            options=options,
            custom_id="fime_gag_fruit_select"
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

        if "__none__" in self.values:

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
                        reason="Fime GAG Fruit Notification"
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

        if options:

            self.add_item(
                GAGFruitSelect(stock)
            )


# ============================================================
# COG
# ============================================================

class FimeStock(
    commands.Cog
):

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

        # Old stock polling is intentionally disabled.
        # bot6 is now focused on general Roblox information/events.
        self.game_event_loop.start()

    # ========================================================
    # LOAD
    # ========================================================

    async def cog_load(
        self
    ):

        await self.ensure_session()

        try:

            # This makes the old notification panel
            # continue working after restart.
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

        # Old stock notification panels are no longer restored.
        # bot6 now focuses on general game information and events.

    # ========================================================
    # RESTORE NOTIFICATION PANELS
    # ========================================================

    async def restore_notification_panels(
        self
    ):

        try:

            await self.bot.wait_until_ready()

            conn = get_db()

            rows = conn.execute("""
                SELECT guild_id, channel_id, message_id
                FROM notification_panels
            """).fetchall()

            conn.close()

            restored = 0

            for row in rows:

                try:

                    channel = await self.resolve_channel(
                        row["channel_id"]
                    )

                    if not channel:
                        continue

                    message = await channel.fetch_message(
                        row["message_id"]
                    )

                    await message.edit(
                        embed=build_notification_panel_embed(),
                        view=NotificationView()
                    )

                    restored += 1

                except discord.NotFound:

                    # Do not delete the database entry.
                    # The reset command can create a new panel.
                    continue

                except discord.Forbidden:

                    continue

                except Exception as error:

                    print(
                        "⚠️ Could not restore "
                        f"notification panel: {error}"
                    )

            print(
                f"✅ Restored {restored} notification panel(s)."
            )

        except Exception as error:

            print(
                "⚠️ Notification panel restore error:",
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

        if not channel_id:
            return None

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
    # NOTIFICATION ROLE
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

        existing_id = get_notification_role(
            guild.id,
            notification_type
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
                reason="Fime Stock Notification Role"
            )

            save_notification_role(
                guild.id,
                notification_type,
                role.id
            )

            return role

        except discord.Forbidden:

            print(
                "❌ Cannot create notification role."
            )

            return None

        except Exception as error:

            print(
                "❌ Role creation error:",
                error
            )

            return None

    # ========================================================
    # GAG ITEM ROLE
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

        role_name = (
            f"🍎 {item_name}"
        )

        if len(role_name) > 100:

            role_name = role_name[:100]

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
                reason="Fime GAG Fruit Notification Role"
            )

            save_gag_item_role(
                guild.id,
                item_name,
                role.id
            )

            return role

        except discord.Forbidden:

            print(
                f"❌ Cannot create GAG role for {item_name}."
            )

            return None

        except Exception as error:

            print(
                f"❌ GAG role creation error: {error}"
            )

            return None

    # ========================================================
    # GAG FRUIT PANEL
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
                "اختار **أكثر من فاكهة** من القائمة بالأسفل.\n\n"
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
                "❌ Cannot send GAG fruit selector."
            )

        except Exception as error:

            print(
                "⚠️ GAG fruit selector error:",
                error
            )

    # ========================================================
    # SHOP UPDATE
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

        mentions = []

        if game == GAME_GAG:

            role_id = get_notification_role(
                guild.id,
                NOTIF_GAG_STOCK
            )

            all_role_id = get_notification_role(
                guild.id,
                NOTIF_ALL_STOCK
            )

            if role_id:
                mentions.append(
                    f"<@&{role_id}>"
                )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
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

            if role_id:
                mentions.append(
                    f"<@&{role_id}>"
                )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
                )

        elif game == GAME_STEAL:

            all_role_id = get_notification_role(
                guild.id,
                NOTIF_ALL_STOCK
            )

            if all_role_id:
                mentions.append(
                    f"<@&{all_role_id}>"
                )

        mention = (
            " ".join(mentions)
            if mentions
            else None
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
                    f"❌ Cannot send stock "
                    f"in #{getattr(channel, 'name', 'unknown')}"
                )

                break

            except Exception as error:

                print(
                    "⚠️ Shop send error:",
                    error
                )

                break

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
                if target in item["name"].lower()
            ]

            if not matches:
                continue

            text = "\n".join(
                format_stock_line(item)
                for item in matches
            )

            embed = discord.Embed(
                title="🔔 Stock Alert",
                description=(
                    "ظهر العنصر اللي طلبت تنبيه عنه:\n\n"
                    f"{text}"
                ),
                color=discord.Color.green()
            )

            embed.set_footer(
                text=(
                    "Team Fime • Personal Stock Alert"
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

        channel_id = get_shop_channel(
            guild.id,
            GAME_GAG
        )

        if not channel_id:
            return

        channel = await self.resolve_channel(
            channel_id
        )

        if not channel:
            return

        for item in added:

            item_name = normalize_item_name(
                item.get("name")
            )

            if not item_name:
                continue

            subscribers = get_gag_item_subscribers(
                guild.id,
                item_name
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

            embed = discord.Embed(
                title="🍎 فاكهة مطلوبة وصلت!",
                description=(
                    f"ظهرت **{item_name}** في الستوك الجديد."
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(
                    timezone.utc
                )
            )

            amount = item.get(
                "stock"
            )

            if amount not in (
                None,
                "",
                0,
                "0"
            ):

                embed.add_field(
                    name="📦 الكمية",
                    value=f"`{amount}`",
                    inline=True
                )

            rarity = item.get(
                "rarity"
            )

            if rarity:

                embed.add_field(
                    name="✨ النوع",
                    value=f"`{rarity}`",
                    inline=True
                )

            price = format_price(
                item
            )

            if price:

                embed.add_field(
                    name="💰 السعر",
                    value=price,
                    inline=True
                )

            embed.set_footer(
                text=(
                    "Team Fime • GAG Fruit Alerts"
                )
            )

            try:

                await channel.send(
                    content=role.mention,
                    embed=embed
                )

            except discord.Forbidden:

                print(
                    f"❌ Cannot send GAG alert "
                    f"for {item_name}."
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

        current_json = serialize_stock(
            stock
        )

        old_json = get_cached_stock(
            guild.id,
            game
        )

        # First successful poll:
        # cache only.
        if old_json is None:

            save_cached_stock(
                guild.id,
                game,
                current_json
            )

            print(
                f"📦 Initial {game} cache "
                f"saved for {guild.name}."
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

        def item_key(item):

            return (
                item["name"].lower(),
                str(item.get("stock")),
                item.get(
                    "rarity",
                    ""
                ).lower(),
                item.get(
                    "type",
                    ""
                ).lower(),
                item.get(
                    "category",
                    ""
                ).lower(),
                item.get(
                    "dealer",
                    ""
                ).lower(),
                str(item.get("money_price")),
                str(item.get("robux_price")),
                str(item.get("price")),
            )

        old_keys = {
            item_key(item)
            for item in old_stock
        }

        new_keys = {
            item_key(item)
            for item in stock
        }

        added = [
            item
            for item in stock
            if item_key(item) not in old_keys
        ]

        removed = [
            item
            for item in old_stock
            if item_key(item) not in new_keys
        ]

        # Save first so a Discord error can never
        # make the same stock repeat forever.
        save_cached_stock(
            guild.id,
            game,
            current_json
        )

        # ----------------------------------------------------
        # SHOP
        # ----------------------------------------------------

        try:

            await self.send_shop_update(
                guild,
                game,
                stock
            )

        except Exception as error:

            print(
                f"⚠️ Shop update error "
                f"{guild.name}/{game}: {error}"
            )

        # ----------------------------------------------------
        # PERSONAL ALERTS
        # ----------------------------------------------------

        try:

            await self.send_personal_alerts(
                guild,
                game,
                added
            )

        except Exception as error:

            print(
                f"⚠️ Personal alert error "
                f"{guild.name}/{game}: {error}"
            )

        # ----------------------------------------------------
        # GAG ITEM ROLE ALERTS
        # ----------------------------------------------------

        if game == GAME_GAG:

            try:

                await self.send_gag_item_role_alerts(
                    guild,
                    added
                )

            except Exception as error:

                print(
                    f"⚠️ GAG item role alert error "
                    f"{guild.name}: {error}"
                )

        # ----------------------------------------------------
        # RARE
        # ----------------------------------------------------

        if game == GAME_GAG:

            rare_added = [
                item
                for item in added
                if is_rare_item(item)
            ]

            if rare_added:

                try:

                    role_id = get_notification_role(
                        guild.id,
                        NOTIF_GAG_RARE
                    )

                    channel_id = get_shop_channel(
                        guild.id,
                        GAME_GAG
                    )

                    if (
                        role_id
                        and channel_id
                    ):

                        channel = await self.resolve_channel(
                            channel_id
                        )

                        if channel:

                            text = "\n".join(
                                format_stock_line(item)
                                for item in rare_added
                            )

                            embed = discord.Embed(
                                title="💎 Rare Stock!",
                                description=text,
                                color=discord.Color.gold(),
                                timestamp=datetime.now(
                                    timezone.utc
                                )
                            )

                            await channel.send(
                                content=f"<@&{role_id}>",
                                embed=embed
                            )

                except Exception as error:

                    print(
                        f"⚠️ Rare stock error "
                        f"{guild.name}: {error}"
                    )

        print(
            f"🔄 {game.upper()} stock changed "
            f"in {guild.name} | "
            f"+{len(added)} / -{len(removed)}"
        )

    # ========================================================
    # SAFE FETCHERS
    # ========================================================

    async def safe_fetch_gag(self):

        try:

            return await fetch_gag_stock(
                self.session
            )

        except Exception as error:

            print(
                "❌ GAG fetch crashed:",
                error
            )

            return []

    async def safe_fetch_blox(self):

        try:

            return await fetch_blox_stock(
                self.session
            )

        except Exception as error:

            print(
                "❌ Blox fetch crashed:",
                error
            )

            return []

    async def safe_fetch_steal(self):

        try:

            return await fetch_steal_stock(
                self.session
            )

        except Exception as error:

            print(
                "❌ Steal fetch crashed:",
                error
            )

            return []

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
        # IMPORTANT:
        # Every game is fetched independently.
        # One API cannot kill another.
        # ----------------------------------------------------

        gag_stock = []
        blox_stock = []
        steal_stock = []

        try:

            gag_stock = await self.safe_fetch_gag()

        except Exception as error:

            print(
                "❌ GAG isolated loop error:",
                error
            )

        try:

            blox_stock = await self.safe_fetch_blox()

        except Exception as error:

            print(
                "❌ Blox isolated loop error:",
                error
            )

        try:

            steal_stock = await self.safe_fetch_steal()

        except Exception as error:

            print(
                "❌ Steal isolated loop error:",
                error
            )

        # ----------------------------------------------------
        # Process GAG independently.
        # ----------------------------------------------------

        if gag_stock:

            for guild in list(
                self.bot.guilds
            ):

                try:

                    await self.process_stock(
                        guild,
                        GAME_GAG,
                        gag_stock
                    )

                except Exception as error:

                    print(
                        f"⚠️ GAG processing error "
                        f"for {guild.name}: {error}"
                    )

        # ----------------------------------------------------
        # Process Blox independently.
        # ----------------------------------------------------

        if blox_stock:

            for guild in list(
                self.bot.guilds
            ):

                try:

                    await self.process_stock(
                        guild,
                        GAME_BLOX,
                        blox_stock
                    )

                except Exception as error:

                    print(
                        f"⚠️ Blox processing error "
                        f"for {guild.name}: {error}"
                    )

        # ----------------------------------------------------
        # Process Steal independently.
        # ----------------------------------------------------

        if steal_stock:

            for guild in list(
                self.bot.guilds
            ):

                try:

                    await self.process_stock(
                        guild,
                        GAME_STEAL,
                        steal_stock
                    )

                except Exception as error:

                    print(
                        f"⚠️ Steal processing error "
                        f"for {guild.name}: {error}"
                    )

    @stock_loop.before_loop
    async def before_stock_loop(
        self
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # STEAL EVENT LOOP
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

            try:

                await self.send_event_notification(
                    NOTIF_STEAL_RESET,
                    "🥚 Steal An Egg — Reset",
                    "بدأت دورة Reset جديدة."
                )

            except Exception as error:

                print(
                    "⚠️ Steal Reset error:",
                    error
                )

        if (
            self.steal_rift_counter
            >= STEAL_EGG_RIFT_MINUTES
        ):

            self.steal_rift_counter = 0

            try:

                await self.send_event_notification(
                    NOTIF_STEAL_RIFT,
                    "🌀 Steal An Egg — Rift",
                    "حان وقت Rift."
                )

            except Exception as error:

                print(
                    "⚠️ Steal Rift error:",
                    error
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

            try:

                role_id = get_notification_role(
                    guild.id,
                    notification_type
                )

                all_role_id = get_notification_role(
                    guild.id,
                    NOTIF_ALL_STOCK
                )

                channel_id = get_shop_channel(
                    guild.id,
                    GAME_STEAL
                )

                if not channel_id:
                    continue

                channel = await self.resolve_channel(
                    channel_id
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
                    text="Team Fime • Stock Alerts"
                )

                await channel.send(
                    content=content,
                    embed=embed
                )

            except Exception as error:

                print(
                    f"⚠️ Event notification error "
                    f"for {guild.name}: {error}"
                )

    # ========================================================
    # GENERAL GAME EVENT LOOP
    # ========================================================

    @tasks.loop(minutes=EVENT_CHECK_MINUTES)
    async def game_event_loop(self):

        await self.bot.wait_until_ready()
        await self.ensure_session()

        for watcher in get_event_watchers():
            try:
                channel = self.bot.get_channel(watcher["channel_id"])
                if channel is None:
                    continue

                data = await general_game_intelligence(
                    self.session,
                    watcher["query"]
                )
                news = data.get("news", []) if data else []
                if not news:
                    continue

                fingerprint = event_fingerprint(news)
                old = watcher.get("last_fingerprint") or ""
                update_event_fingerprint(
                    watcher["guild_id"],
                    watcher["channel_id"],
                    watcher["game_name"],
                    fingerprint,
                )

                if old and old == fingerprint:
                    continue

                await channel.send(
                    embed=build_event_embed(
                        watcher["game_name"],
                        news,
                    )
                )

            except Exception as error:
                print("⚠️ General game event watcher error:", error)

    @game_event_loop.before_loop
    async def before_game_event_loop(self):
        await self.bot.wait_until_ready()

    # ========================================================
    # /STOCK SEARCH — GENERAL ROBLOX SEARCH
    # ========================================================

    @stock_group.command(
        name="search",
        description="بحث عام عن أي ماب أو حدث أو تحديث في Roblox"
    )
    @app_commands.describe(
        query="اكتب اسم الماب أو الحيوان أو البيضة أو الحدث أو أي شيء تبيه"
    )
    async def general_search_command(self, interaction, query: str):

        await interaction.response.defer()
        await self.ensure_session()

        data = await general_game_intelligence(
            self.session,
            query
        )

        if not data or (not data.get("games") and not data.get("news")):
            await interaction.followup.send(
                f"🔎 ما لقيت نتيجة واضحة عن **{query}** حاليًا. جرّب اسم الماب بشكل أوضح."
            )
            return

        await interaction.followup.send(
            embed=build_game_intelligence_embed(query, data)
        )

    # ========================================================
    # /STOCK WATCH — WATCH ANY ROBLOX GAME
    # ========================================================

    @stock_group.command(
        name="watch",
        description="تحديد ماب لمراقبة أحداثه وتحديثاته في روم معين"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        game="اسم الماب / اللعبة",
        channel="الروم الذي تصله فيه الأحداث والتحديثات"
    )
    async def watch_game_command(self, interaction, game: str, channel: discord.TextChannel):

        game = game.strip()
        if len(game) < 2:
            await interaction.response.send_message(
                "❌ اكتب اسم ماب صحيح.", ephemeral=True
            )
            return

        set_event_watcher(
            interaction.guild.id,
            channel.id,
            game,
            game,
        )

        await interaction.response.send_message(
            f"✅ تم تفعيل مراقبة **{game}** في {channel.mention}.\n"
            "البوت بيبحث عن الأحداث والتحديثات والأشياء الجديدة ويرسلها هناك.",
            ephemeral=True,
        )

    # ========================================================
    # /STOCK UNWATCH
    # ========================================================

    @stock_group.command(
        name="unwatch",
        description="إيقاف مراقبة ماب"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        game="اسم الماب",
        channel="الروم"
    )
    async def unwatch_game_command(self, interaction, game: str, channel: discord.TextChannel):

        remove_event_watcher(
            interaction.guild.id,
            channel.id,
            game.strip(),
        )

        await interaction.response.send_message(
            f"✅ تم إيقاف مراقبة **{game.strip()}** في {channel.mention}.",
            ephemeral=True,
        )

    # ========================================================
    # /STOCK RANDOM — RANDOM ROBLOX MAP
    # ========================================================

    @stock_group.command(
        name="random",
        description="عرض ماب Roblox عشوائي مع معلوماته واللاعبين"
    )
    async def random_game_command(self, interaction):

        await interaction.response.defer()
        await self.ensure_session()

        # Different search buckets make the result genuinely varied
        # without inventing a game or its player count.
        buckets = [
            "Roblox", "anime", "horror", "simulator", "tycoon",
            "roleplay", "obby", "battlegrounds", "survival", "adventure"
        ]
        query = random.choice(buckets)
        data = await general_roblox_search(
            self.session,
            query,
            GENERAL_SEARCH_LIMIT
        )

        games = data.get("games", []) if data else []
        if not games:
            await interaction.followup.send(
                "🎲 ما قدرت أجيب ماب عشوائي حاليًا، جرّب مرة ثانية."
            )
            return

        game = random.choice(games)
        embed = discord.Embed(
            title=f"🎲 ماب عشوائي: {game['name'][:200]}",
            description=(
                game.get("description") or
                "ما فيه وصف متاح حاليًا من Roblox."
            )[:4096],
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="👥 اللاعبين الآن",
            value=f"**{game.get('playing', 0):,}**",
            inline=True,
        )
        embed.add_field(
            name="👤 المطور",
            value=(game.get("creator") or "غير معروف")[:100],
            inline=True,
        )
        embed.add_field(
            name="⭐ الزيارات",
            value=f"**{game.get('visits', 0):,}**",
            inline=True,
        )
        embed.set_footer(text="حقوق Fime • معلومات Roblox عامة")
        await interaction.followup.send(embed=embed)

    # ========================================================
    # /STOCK WATCHES
    # ========================================================

    @stock_group.command(
        name="watches",
        description="عرض المابات التي تتم مراقبة أحداثها"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def watches_command(self, interaction):

        rows = [
            row for row in get_event_watchers()
            if row["guild_id"] == interaction.guild.id
        ]

        if not rows:
            await interaction.response.send_message(
                "📭 ما فيه أي ماب تتم مراقبة أحداثه حاليًا.",
                ephemeral=True,
            )
            return

        lines = []
        for row in rows:
            channel = interaction.guild.get_channel(row["channel_id"])
            mention = channel.mention if channel else f"`{row['channel_id']}`"
            lines.append(f"• **{row['game_name']}** → {mention}")

        embed = discord.Embed(
            title="📡 مراقبة أحداث المابات",
            description="\n".join(lines)[:4000],
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="حقوق Fime")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ========================================================
    # /STOCK VIEW
    # ========================================================

    @stock_group.command(
        name="legacy-view",
        description="نظام الستوك القديم (متوافقية فقط)"
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
    async def stock_command(
        self,
        interaction,
        game: app_commands.Choice[str]
    ):

        await interaction.response.defer()

        await self.ensure_session()

        stock = []

        if game.value == GAME_GAG:

            try:

                stock = await fetch_gag_stock(
                    self.session
                )

            except Exception as error:

                print(
                    "❌ Manual GAG fetch error:",
                    error
                )

        elif game.value == GAME_BLOX:

            try:

                stock = await fetch_blox_stock(
                    self.session
                )

            except Exception as error:

                print(
                    "❌ Manual Blox fetch error:",
                    error
                )

        elif game.value == GAME_STEAL:

            try:

                stock = await fetch_steal_stock(
                    self.session
                )

            except Exception as error:

                print(
                    "❌ Manual Steal fetch error:",
                    error
                )

        if not stock:

            # ------------------------------------------------
            # General search fallback.
            # It NEVER fabricates stock.
            # ------------------------------------------------

            search_result = None

            try:

                search_result = await general_stock_search(
                    self.session,
                    game.value
                )

            except Exception as error:

                print(
                    "⚠️ Search fallback error:",
                    error
                )

            if search_result:

                await interaction.followup.send(
                    embed=build_search_embed(
                        game.value,
                        search_result
                    )
                )

            else:

                await interaction.followup.send(
                    (
                        "❌ ما قدرت أجيب الستوك حاليًا، "
                        "ولا لقيت نتيجة بحث عامة مفيدة."
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

        try:

            message = await channel.send(
                embed=build_notification_panel_embed(),
                view=NotificationView()
            )

            save_notification_panel(
                interaction.guild.id,
                channel.id,
                message.id
            )

            await interaction.followup.send(
                (
                    f"✅ تم إنشاء لوحة الإشعارات "
                    f"في {channel.mention}."
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

        channel = await self.resolve_channel(
            channel_id
        )

        if not channel:

            await interaction.response.send_message(
                "❌ لا أستطيع الوصول للروم.",
                ephemeral=True
            )

            return

        try:

            message = await channel.fetch_message(
                message_id
            )

            await message.edit(
                embed=build_notification_panel_embed(),
                view=NotificationView()
            )

            await interaction.response.send_message(
                "✅ تم تحديث لوحة الإشعارات.",
                ephemeral=True
            )

        except discord.NotFound:

            try:

                new_message = await channel.send(
                    embed=build_notification_panel_embed(),
                    view=NotificationView()
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
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL
            ),
        ]
    )
    async def stock_alert(
        self,
        interaction,
        game: app_commands.Choice[str],
        item: str
    ):

        item = item.strip()

        if not item:

            await interaction.response.send_message(
                "❌ اكتب اسم العنصر.",
                ephemeral=True
            )

            return

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
            item
        ))

        conn.commit()
        conn.close()

        await interaction.response.send_message(
            f"🔔 تم تفعيل التنبيه عن **{item}**.",
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
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL
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
            f"✅ تم إزالة تنبيه **{item}**.",
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

            lines.append("")
            lines.append(
                "🍎 **فواكه Grow a Garden:**"
            )

            for item_name in gag_items:

                lines.append(
                    f"• **{item_name}**"
                )

        embed = discord.Embed(
            title="🔔 تنبيهاتك الشخصية",
            description="\n".join(lines),
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
                "❌ ما قدرت أجهز رتبة الإشعار.",
                ephemeral=True
            )

            return

        try:

            await interaction.user.add_roles(
                role,
                reason="Fime Stock Notification"
            )

            add_notification_member(
                interaction.guild.id,
                interaction.user.id,
                alert.value
            )

            await interaction.response.send_message(
                f"🔔 تم تفعيل **{role.name}**.",
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

        role_id = get_notification_role(
            interaction.guild.id,
            alert.value
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
                        reason="Fime Stock Notification Removal"
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
        description="عرض حالة نظام البحث والأحداث"
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
            name="🔁 GAG Fallback",
            value=(
                "🟢 Available"
                if (
                    GAG_API_FALLBACK_URL
                    or GAG_API_FALLBACK_URLS
                )
                else "⚪ None"
            ),
            inline=True
        )

        embed.add_field(
            name="🍎 Blox API",
            value=(
                "🟢 Configured"
                if BLOX_API_URL
                else "🔴 Not configured"
            ),
            inline=True
        )

        embed.add_field(
            name="🔑 Blox API Key",
            value=(
                "🟢 Configured"
                if BLOX_API_KEY
                else "🔴 Missing"
            ),
            inline=True
        )

        embed.add_field(
            name="🥚 Steal API",
            value=(
                "🟢 Configured"
                if STEAL_EGG_API_URL
                else "⚪ Optional"
            ),
            inline=True
        )

        embed.add_field(
            name="🔎 Search Fallback",
            value=(
                "🟢 Enabled"
                if WEB_SEARCH_ENABLED
                else "🔴 Disabled"
            ),
            inline=True
        )

        embed.add_field(
            name="⏱️ Polling",
            value=f"`{STOCK_CHECK_SECONDS}s`",
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
                "❌ تحتاج صلاحية **Manage Server**."
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