# ============================================================
# Team Fime
# bot6.py
# Advanced Stock System
#
# Games:
#   🌱 Grow a Garden
#   🍎 Blox Fruits
#   🥚 Steal An Egg
#
# Features:
#   - Live stock polling
#   - Separate shop channel per game
#   - Notification setup
#   - Automatic notification roles
#   - Stock change notifications
#   - Rare stock notifications
#   - Personal stock alerts
#   - GAG item/fruit role alerts
#   - GAG item/fruit subscriptions
#   - Blox Normal + Mirage stock
#   - Blox reset countdown information
#   - Steal An Egg Reset / Rift events
#   - Optional Steal An Egg API
#   - SQLite persistence
#   - Safer API parsing
#   - Quantity changes no longer count as "new item"
#   - Multiple GAG stock sections are preserved
#   - API failures do not overwrite good cached stock
#   - Automatic cleanup of aiohttp session
#
# ============================================================

from __future__ import annotations

import os
import io
import json
import time
import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

OWNER_ID = 1388514481444880549

DB_FILE = os.getenv(
    "STOCK_DB_FILE",
    "fime_stock.db"
)

STOCK_CHECK_SECONDS = max(
    20,
    int(os.getenv("STOCK_CHECK_SECONDS", "60"))
)

API_TIMEOUT_SECONDS = max(
    5,
    int(os.getenv("API_TIMEOUT_SECONDS", "15"))
)

MAX_SELECT_OPTIONS = 25

# ------------------------------------------------------------
# Grow a Garden
# ------------------------------------------------------------

# Community stock endpoint discovered for Grow a Garden.
# Can be replaced from Render Environment Variables.
DEFAULT_GAG_API_URL = (
    "https://www.gamersberg.com/api/grow-a-garden/stock"
)

GAG_API_URL = os.getenv(
    "GAG_API_URL",
    DEFAULT_GAG_API_URL
).strip()

# ------------------------------------------------------------
# Blox Fruits
# ------------------------------------------------------------

# Parse managed Fandom API.
# Requires PARSE_API_KEY.
DEFAULT_BLOX_API_URL = (
    "https://api.parse.bot/scraper/"
    "78cf8155-3819-45d0-b799-92f840a94827/get_stock"
)

BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    DEFAULT_BLOX_API_URL
).strip()

PARSE_API_KEY = os.getenv(
    "PARSE_API_KEY",
    ""
).strip()

# ------------------------------------------------------------
# Steal An Egg
# ------------------------------------------------------------

# Optional.
# If you find/use another live JSON API later, only put its
# endpoint in STEAL_EGG_API_URL.
STEAL_EGG_API_URL = os.getenv(
    "STEAL_EGG_API_URL",
    ""
).strip()

STEAL_EGG_RESET_MINUTES = 5
STEAL_EGG_RIFT_MINUTES = 30


# ============================================================
# GAME CONSTANTS
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


# ============================================================
# DATABASE
# ============================================================

def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    connection = db_connect()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                item_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, game, item_name)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS event_subscriptions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, event_type)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_cache (
                guild_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                stock_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (guild_id, game)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS event_cache (
                guild_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                last_sent INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, event_type)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_channels (
                guild_id INTEGER NOT NULL,
                game TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, game)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_roles (
                guild_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, notification_type)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_panels (
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_members (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, notification_type)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gag_item_roles (
                guild_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, item_name)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gag_item_subscriptions (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                item_name TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id, item_name)
            )
            """
        )

        connection.commit()

    finally:
        connection.close()


# ============================================================
# DATABASE HELPERS
# ============================================================

def db_execute(
    query: str,
    parameters: tuple = (),
) -> None:
    connection = db_connect()

    try:
        connection.execute(query, parameters)
        connection.commit()
    finally:
        connection.close()


def db_fetchone(
    query: str,
    parameters: tuple = (),
):
    connection = db_connect()

    try:
        return connection.execute(
            query,
            parameters
        ).fetchone()
    finally:
        connection.close()


def db_fetchall(
    query: str,
    parameters: tuple = (),
):
    connection = db_connect()

    try:
        return connection.execute(
            query,
            parameters
        ).fetchall()
    finally:
        connection.close()


# ============================================================
# JSON HELPERS
# ============================================================

def json_dumps(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


# ============================================================
# API HELPERS
# ============================================================

async def fetch_json(
    session: aiohttp.ClientSession,
    url: str,
    headers: Optional[dict[str, str]] = None,
) -> Optional[Any]:

    if not url:
        return None

    try:
        timeout = aiohttp.ClientTimeout(
            total=API_TIMEOUT_SECONDS
        )

        async with session.get(
            url,
            headers=headers or {},
            timeout=timeout,
        ) as response:

            if response.status != 200:
                print(
                    f"⚠️ Stock API returned HTTP "
                    f"{response.status}: {url}"
                )
                return None

            text = await response.text()

            if not text.strip():
                return None

            try:
                return json.loads(text)

            except json.JSONDecodeError:
                print(
                    f"⚠️ API returned invalid JSON: {url}"
                )
                return None

    except asyncio.TimeoutError:
        print(
            f"⚠️ Stock API timeout: {url}"
        )

    except aiohttp.ClientError as error:
        print(
            f"⚠️ Stock API connection error: {error}"
        )

    except Exception as error:
        print(
            f"⚠️ Unexpected API error: {error}"
        )

    return None


# ============================================================
# GENERIC DATA EXTRACTION
# ============================================================

LIST_KEYS = (
    "stock",
    "stocks",
    "items",
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
)


def find_lists_recursive(
    data: Any,
    prefix: str = "",
) -> list[tuple[str, list]]:

    found: list[tuple[str, list]] = []

    if isinstance(data, dict):

        for key, value in data.items():

            current_path = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )

            if isinstance(value, list):

                lower_key = str(key).lower()

                if (
                    lower_key in {
                        item.lower()
                        for item in LIST_KEYS
                    }
                    or value
                ):
                    found.append(
                        (current_path, value)
                    )

            elif isinstance(value, dict):
                found.extend(
                    find_lists_recursive(
                        value,
                        current_path
                    )
                )

    elif isinstance(data, list):

        found.append(
            (prefix or "root", data)
        )

    return found


def extract_all_lists(
    data: Any,
) -> list[tuple[str, list]]:

    found = find_lists_recursive(data)

    result = []

    seen_ids = set()

    for path, values in found:

        if id(values) in seen_ids:
            continue

        seen_ids.add(id(values))

        if values:
            result.append(
                (path, values)
            )

    return result


# ============================================================
# ITEM NORMALIZATION
# ============================================================

def normalize_item(
    item: Any,
    section: str = "",
) -> Optional[dict]:

    if isinstance(item, str):

        name = item.strip()

        if not name:
            return None

        return {
            "name": name,
            "stock": 1,
            "rarity": "",
            "section": section,
        }

    if not isinstance(item, dict):
        return None

    name = (
        item.get("name")
        or item.get("item")
        or item.get("title")
        or item.get("displayName")
        or item.get("fruit")
        or item.get("fruit_name")
        or item.get("seed")
    )

    if name is None:
        return None

    name = str(name).strip()

    if not name:
        return None

    stock = (
        item.get("stock")
        if "stock" in item
        else item.get("quantity")
    )

    if stock is None:
        stock = item.get("amount")

    if stock is None:
        stock = item.get("count")

    if stock is None:
        stock = item.get("qty")

    if stock is None:
        stock = 1

    rarity = (
        item.get("rarity")
        or item.get("tier")
        or item.get("type")
        or ""
    )

    normalized = {
        "name": name,
        "stock": stock,
        "rarity": str(rarity),
        "section": section,
    }

    # Preserve useful Blox information.
    for source_key, target_key in (
        ("price_beli", "price_beli"),
        ("money_price", "price_beli"),
        ("beli", "price_beli"),
        ("price_robux", "price_robux"),
        ("robux_price", "price_robux"),
        ("image_url", "image_url"),
        ("wiki_url", "wiki_url"),
        ("type", "type"),
    ):
        if source_key in item:
            normalized[target_key] = item[source_key]

    return normalized


def clean_stock(
    items: list[dict],
) -> list[dict]:

    result = []
    seen = set()

    for item in items:

        name = str(
            item.get("name", "")
        ).strip()

        if not name:
            continue

        section = str(
            item.get("section", "")
        )

        key = (
            section.lower(),
            name.lower(),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(item)

    result.sort(
        key=lambda x: (
            str(x.get("section", "")).lower(),
            str(x.get("name", "")).lower(),
        )
    )

    return result


# ============================================================
# GAG PARSER
# ============================================================

def parse_gag_stock(
    data: Any,
) -> list[dict]:

    if not data:
        return []

    # Gamersberg-style response:
    #
    # {
    #   "data": [
    #       {
    #           "seeds": {...},
    #           "gear": {...},
    #           "eggs": [...],
    #           "cosmetic": {...}
    #       }
    #   ]
    # }

    payload = data

    if isinstance(data, dict):

        if isinstance(
            data.get("data"),
            list
        ) and data["data"]:

            payload = data["data"][0]

        elif isinstance(
            data.get("data"),
            dict
        ):

            payload = data["data"]

    if isinstance(payload, list):

        if payload and isinstance(
            payload[0],
            dict
        ):
            payload = payload[0]

    items: list[dict] = []

    if isinstance(payload, dict):

        # ----------------------------
        # Seeds
        # ----------------------------

        seeds = payload.get("seeds")

        if isinstance(seeds, dict):

            for name, quantity in seeds.items():

                items.append({
                    "name": str(name),
                    "stock": quantity,
                    "rarity": "",
                    "section": "Seeds",
                })

        elif isinstance(seeds, list):

            for raw in seeds:

                normalized = normalize_item(
                    raw,
                    "Seeds"
                )

                if normalized:
                    items.append(normalized)

        # ----------------------------
        # Gear
        # ----------------------------

        gear = payload.get("gear")

        if isinstance(gear, dict):

            for name, quantity in gear.items():

                items.append({
                    "name": str(name),
                    "stock": quantity,
                    "rarity": "",
                    "section": "Gear",
                })

        elif isinstance(gear, list):

            for raw in gear:

                normalized = normalize_item(
                    raw,
                    "Gear"
                )

                if normalized:
                    items.append(normalized)

        # ----------------------------
        # Eggs
        # ----------------------------

        eggs = payload.get("eggs")

        if isinstance(eggs, list):

            for raw in eggs:

                normalized = normalize_item(
                    raw,
                    "Eggs"
                )

                if normalized:
                    items.append(normalized)

        elif isinstance(eggs, dict):

            for name, quantity in eggs.items():

                items.append({
                    "name": str(name),
                    "stock": quantity,
                    "rarity": "",
                    "section": "Eggs",
                })

        # ----------------------------
        # Cosmetics
        # ----------------------------

        cosmetics = (
            payload.get("cosmetic")
            or payload.get("cosmetics")
        )

        if isinstance(cosmetics, dict):

            for name, quantity in cosmetics.items():

                items.append({
                    "name": str(name),
                    "stock": quantity,
                    "rarity": "",
                    "section": "Cosmetics",
                })

        elif isinstance(cosmetics, list):

            for raw in cosmetics:

                normalized = normalize_item(
                    raw,
                    "Cosmetics"
                )

                if normalized:
                    items.append(normalized)

    # Fallback generic parser.
    if not items:

        for path, values in extract_all_lists(data):

            section = (
                path.split(".")[-1]
                .replace("_", " ")
                .title()
            )

            for raw in values:

                normalized = normalize_item(
                    raw,
                    section
                )

                if normalized:
                    items.append(normalized)

    return clean_stock(items)


# ============================================================
# BLOX PARSER
# ============================================================

def parse_blox_stock(
    data: Any,
) -> list[dict]:

    if not data:
        return []

    payload = data

    if isinstance(data, dict):

        if isinstance(
            data.get("data"),
            dict
        ):
            payload = data["data"]

        elif isinstance(
            data.get("data"),
            list
        ) and data["data"]:

            payload = data["data"][0]

    if not isinstance(payload, dict):
        return []

    result: list[dict] = []

    # --------------------------------------------------------
    # Normal dealer
    # --------------------------------------------------------

    normal = (
        payload.get("normal")
        or payload.get("normal_stock")
        or payload.get("normalStock")
        or []
    )

    if isinstance(normal, list):

        for raw in normal:

            normalized = normalize_item(
                raw,
                "Normal Dealer"
            )

            if normalized:
                result.append(normalized)

    # --------------------------------------------------------
    # Mirage dealer
    # --------------------------------------------------------

    mirage = (
        payload.get("mirage")
        or payload.get("mirage_stock")
        or payload.get("mirageStock")
        or []
    )

    if isinstance(mirage, list):

        for raw in mirage:

            normalized = normalize_item(
                raw,
                "Mirage Dealer"
            )

            if normalized:
                result.append(normalized)

    return clean_stock(result)


# ============================================================
# STEAL AN EGG PARSER
# ============================================================

def parse_steal_stock(
    data: Any,
) -> list[dict]:

    if not data:
        return []

    items: list[dict] = []

    for path, values in extract_all_lists(data):

        section = (
            path.split(".")[-1]
            .replace("_", " ")
            .title()
        )

        for raw in values:

            normalized = normalize_item(
                raw,
                section
            )

            if normalized:
                items.append(normalized)

    return clean_stock(items)


# ============================================================
# RARITY
# ============================================================

def is_rare_item(
    item: dict,
) -> bool:

    text = (
        f"{item.get('name', '')} "
        f"{item.get('rarity', '')}"
    ).lower()

    rare_words = (
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
    )

    return any(
        word in text
        for word in rare_words
    )


# ============================================================
# DISPLAY HELPERS
# ============================================================

def stock_value_text(
    item: dict,
) -> str:

    stock = item.get("stock")

    if stock is None:
        return "متوفر"

    if isinstance(stock, float):
        if stock.is_integer():
            stock = int(stock)

    return str(stock)


def format_item_line(
    item: dict,
) -> str:

    name = str(
        item.get("name", "Unknown")
    )

    stock = stock_value_text(item)

    line = f"**{name}** × `{stock}`"

    price_beli = item.get("price_beli")
    price_robux = item.get("price_robux")

    if price_beli is not None:

        try:
            line += (
                f" — `{int(price_beli):,} Beli`"
            )
        except Exception:
            line += (
                f" — `{price_beli} Beli`"
            )

    if price_robux is not None:

        try:
            line += (
                f" / `{int(price_robux)} Robux`"
            )
        except Exception:
            line += (
                f" / `{price_robux} Robux`"
            )

    return line


# ============================================================
# EMBEDS
# ============================================================

def build_shop_embeds(
    game: str,
    stock: list[dict],
) -> list[discord.Embed]:

    title = GAME_NAMES.get(
        game,
        game
    )

    if not stock:

        return [
            discord.Embed(
                title=title,
                description=(
                    "لا يوجد Stock متاح حاليًا."
                ),
                color=discord.Color.dark_grey(),
                timestamp=datetime.now(
                    timezone.utc
                ),
            )
        ]

    groups: dict[str, list[dict]] = {}

    for item in stock:

        section = (
            item.get("section")
            or "Stock"
        )

        groups.setdefault(
            section,
            []
        ).append(item)

    embeds: list[discord.Embed] = []

    current_embed = discord.Embed(
        title=title,
        description=(
            "📦 **الـStock الحالي**"
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(
            timezone.utc
        ),
    )

    field_count = 0

    for section, items in groups.items():

        lines = []

        for item in items:
            lines.append(
                format_item_line(item)
            )

        text = "\n".join(lines)

        chunks = []

        while text:

            if len(text) <= 1024:
                chunks.append(text)
                break

            cut = text.rfind(
                "\n",
                0,
                1024
            )

            if cut <= 0:
                cut = 1024

            chunks.append(
                text[:cut]
            )

            text = text[cut:].lstrip("\n")

        for index, chunk in enumerate(chunks):

            field_name = section

            if len(chunks) > 1:
                field_name += (
                    f" ({index + 1}/{len(chunks)})"
                )

            if (
                field_count >= 25
                or len(
                    current_embed.fields
                ) >= 25
            ):

                embeds.append(
                    current_embed
                )

                current_embed = discord.Embed(
                    title=title,
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(
                        timezone.utc
                    ),
                )

                field_count = 0

            current_embed.add_field(
                name=field_name,
                value=chunk,
                inline=False,
            )

            field_count += 1

    if current_embed.fields:
        embeds.append(current_embed)

    return embeds[:10]


# ============================================================
# SELECT OPTION HELPERS
# ============================================================

def safe_select_label(
    text: str,
    maximum: int = 100,
) -> str:

    text = str(text)

    if len(text) > maximum:
        return text[:maximum - 3] + "..."

    return text


# ============================================================
# GAG FRUIT VIEW
# ============================================================

class GAGFruitSelect(
    discord.ui.Select
):

    def __init__(
        self,
        cog: "FimeStock",
        guild_id: int,
        stock: list[dict],
    ):

        self.cog = cog
        self.guild_id = guild_id

        unique: dict[str, dict] = {}

        for item in stock:

            name = str(
                item.get("name", "")
            ).strip()

            if not name:
                continue

            unique.setdefault(
                name.lower(),
                item
            )

        options = []

        for item in list(
            unique.values()
        )[:MAX_SELECT_OPTIONS]:

            name = str(
                item["name"]
            )

            options.append(
                discord.SelectOption(
                    label=safe_select_label(
                        name
                    ),
                    value=name,
                    description=(
                        "اضغط للاشتراك في تنبيه هذا العنصر."
                    )[:100],
                )
            )

        if not options:

            options = [
                discord.SelectOption(
                    label="لا يوجد Stock",
                    value="__none__",
                )
            ]

        super().__init__(
            placeholder=(
                "🌱 اختر فاكهة / عنصر..."
            ),
            min_values=1,
            max_values=1,
            options=options,
            custom_id=(
                f"fime:gag-select:"
                f"{guild_id}"
            ),
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        value = self.values[0]

        if value == "__none__":

            await interaction.response.send_message(
                "❌ لا يوجد عناصر متاحة حاليًا.",
                ephemeral=True,
            )
            return

        guild_id = interaction.guild_id

        if guild_id is None:
            return

        existing = db_fetchone(
            """
            SELECT 1
            FROM gag_item_subscriptions
            WHERE guild_id = ?
              AND user_id = ?
              AND item_name = ?
            """,
            (
                guild_id,
                interaction.user.id,
                value,
            )
        )

        if existing:

            db_execute(
                """
                DELETE FROM gag_item_subscriptions
                WHERE guild_id = ?
                  AND user_id = ?
                  AND item_name = ?
                """,
                (
                    guild_id,
                    interaction.user.id,
                    value,
                )
            )

            await interaction.response.send_message(
                f"🔕 تم إلغاء تنبيه **{value}**.",
                ephemeral=True,
            )

        else:

            db_execute(
                """
                INSERT OR IGNORE INTO
                gag_item_subscriptions
                (guild_id, user_id, item_name)
                VALUES (?, ?, ?)
                """,
                (
                    guild_id,
                    interaction.user.id,
                    value,
                )
            )

            await interaction.response.send_message(
                f"🔔 تم تفعيل تنبيه **{value}**.",
                ephemeral=True,
            )


class GAGFruitView(
    discord.ui.View
):

    def __init__(
        self,
        cog: "FimeStock",
        guild_id: int,
        stock: list[dict],
    ):

        super().__init__(
            timeout=900
        )

        self.add_item(
            GAGFruitSelect(
                cog,
                guild_id,
                stock
            )
        )


# ============================================================
# NOTIFICATION VIEW
# ============================================================

class NotificationSelect(
    discord.ui.Select
):

    def __init__(
        self,
        cog: "FimeStock",
    ):

        self.cog = cog

        options = [
            discord.SelectOption(
                label="GAG Stock",
                value=NOTIF_GAG_STOCK,
                emoji="🌱",
            ),
            discord.SelectOption(
                label="GAG Rare",
                value=NOTIF_GAG_RARE,
                emoji="✨",
            ),
            discord.SelectOption(
                label="Blox Fruits Stock",
                value=NOTIF_BLOX_STOCK,
                emoji="🍎",
            ),
            discord.SelectOption(
                label="Steal An Egg Reset",
                value=NOTIF_STEAL_RESET,
                emoji="🥚",
            ),
            discord.SelectOption(
                label="Steal An Egg Rift",
                value=NOTIF_STEAL_RIFT,
                emoji="🌀",
            ),
            discord.SelectOption(
                label="All Stock",
                value=NOTIF_ALL_STOCK,
                emoji="📦",
            ),
        ]

        super().__init__(
            placeholder=(
                "🔔 اختر نوع التنبيه..."
            ),
            min_values=1,
            max_values=1,
            options=options,
            custom_id="fime:stock-notification",
        )

    async def callback(
        self,
        interaction: discord.Interaction,
    ):

        guild = interaction.guild

        if guild is None:
            return

        notif_type = self.values[0]

        role = self.cog.get_notification_role(
            guild.id,
            notif_type
        )

        if role is None:

            role = await self.cog.create_notification_role(
                guild,
                notif_type
            )

        if role is None:

            await interaction.response.send_message(
                "❌ ما قدرت أنشئ رتبة التنبيه.",
                ephemeral=True,
            )
            return

        member = guild.get_member(
            interaction.user.id
        )

        if member is None:
            return

        try:

            if role in member.roles:

                await member.remove_roles(
                    role,
                    reason="Stock notification toggle"
                )

                db_execute(
                    """
                    DELETE FROM notification_members
                    WHERE guild_id = ?
                      AND user_id = ?
                      AND notification_type = ?
                    """,
                    (
                        guild.id,
                        member.id,
                        notif_type,
                    )
                )

                message = (
                    f"🔕 تم إلغاء **{role.name}**."
                )

            else:

                await member.add_roles(
                    role,
                    reason="Stock notification toggle"
                )

                db_execute(
                    """
                    INSERT OR IGNORE INTO
                    notification_members
                    (guild_id, user_id, notification_type)
                    VALUES (?, ?, ?)
                    """,
                    (
                        guild.id,
                        member.id,
                        notif_type,
                    )
                )

                message = (
                    f"🔔 تم تفعيل **{role.name}**."
                )

            await interaction.response.send_message(
                message,
                ephemeral=True,
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ البوت ما عنده صلاحية إدارة الرتب.",
                ephemeral=True,
            )


class NotificationView(
    discord.ui.View
):

    def __init__(
        self,
        cog: "FimeStock",
    ):

        super().__init__(
            timeout=None
        )

        self.add_item(
            NotificationSelect(cog)
        )


# ============================================================
# MAIN COG
# ============================================================

class FimeStock(
    commands.Cog
):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot
        self.session: Optional[
            aiohttp.ClientSession
        ] = None

        self.ready_for_loops = False

        init_database()

        self.stock_loop.start()
        self.steal_event_loop.start()

    # ========================================================
    # LIFECYCLE
    # ========================================================

    async def cog_load(
        self,
    ):

        if self.session is None:

            timeout = aiohttp.ClientTimeout(
                total=API_TIMEOUT_SECONDS
            )

            self.session = aiohttp.ClientSession(
                timeout=timeout
            )

        self.ready_for_loops = True

    def cog_unload(
        self,
    ):

        self.stock_loop.cancel()
        self.steal_event_loop.cancel()

        if self.session:
            asyncio.create_task(
                self.session.close()
            )

    async def ensure_session(
        self,
    ):

        if self.session is None:

            timeout = aiohttp.ClientTimeout(
                total=API_TIMEOUT_SECONDS
            )

            self.session = aiohttp.ClientSession(
                timeout=timeout
            )

    # ========================================================
    # OWNER CHECK
    # ========================================================

    async def owner_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:

        if interaction.user.id != OWNER_ID:

            await interaction.response.send_message(
                "❌ هذا الأمر للمالك فقط.",
                ephemeral=True,
            )

            return False

        return True

    # ========================================================
    # API FETCHERS
    # ========================================================

    async def fetch_gag_stock(
        self,
    ) -> list[dict]:

        await self.ensure_session()

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; TeamFimeStock/1.0)"
            ),
            "Accept": "application/json",
        }

        data = await fetch_json(
            self.session,
            GAG_API_URL,
            headers,
        )

        if data is None:
            return []

        return parse_gag_stock(data)

    async def fetch_blox_stock(
        self,
    ) -> tuple[
        list[dict],
        Optional[Any],
        Optional[Any],
    ]:

        await self.ensure_session()

        headers = {
            "Accept": "application/json",
        }

        if PARSE_API_KEY:

            headers["X-API-Key"] = (
                PARSE_API_KEY
            )

        data = await fetch_json(
            self.session,
            BLOX_API_URL,
            headers,
        )

        if data is None:
            return [], None, None

        stock = parse_blox_stock(data)

        payload = data

        if isinstance(data, dict):

            if isinstance(
                data.get("data"),
                dict
            ):
                payload = data["data"]

        normal_reset = None
        mirage_reset = None

        if isinstance(payload, dict):

            normal_reset = (
                payload.get(
                    "normal_resets_at"
                )
                or payload.get(
                    "normal_reset"
                )
                or payload.get(
                    "normal_resets_at_epoch"
                )
            )

            mirage_reset = (
                payload.get(
                    "mirage_resets_at"
                )
                or payload.get(
                    "mirage_reset"
                )
                or payload.get(
                    "mirage_resets_at_epoch"
                )
            )

        return (
            stock,
            normal_reset,
            mirage_reset,
        )

    async def fetch_steal_stock(
        self,
    ) -> list[dict]:

        if not STEAL_EGG_API_URL:
            return []

        await self.ensure_session()

        data = await fetch_json(
            self.session,
            STEAL_EGG_API_URL,
            {
                "Accept": "application/json",
                "User-Agent": (
                    "TeamFimeStock/1.0"
                ),
            }
        )

        if data is None:
            return []

        return parse_steal_stock(data)

    # ========================================================
    # CACHE
    # ========================================================

    def get_cached_stock(
        self,
        guild_id: int,
        game: str,
    ) -> Optional[list[dict]]:

        row = db_fetchone(
            """
            SELECT stock_json
            FROM stock_cache
            WHERE guild_id = ?
              AND game = ?
            """,
            (
                guild_id,
                game,
            )
        )

        if row is None:
            return None

        try:

            return json.loads(
                row["stock_json"]
            )

        except Exception:
            return None

    def save_cached_stock(
        self,
        guild_id: int,
        game: str,
        stock: list[dict],
    ):

        db_execute(
            """
            INSERT INTO stock_cache
            (guild_id, game, stock_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, game)
            DO UPDATE SET
                stock_json = excluded.stock_json,
                updated_at = excluded.updated_at
            """,
            (
                guild_id,
                game,
                json_dumps(stock),
                time.time(),
            )
        )

    # ========================================================
    # STOCK COMPARISON
    # ========================================================

    @staticmethod
    def stock_identity(
        item: dict,
    ) -> tuple[str, str]:

        return (
            str(
                item.get("section", "")
            ).lower(),
            str(
                item.get("name", "")
            ).lower(),
        )

    def get_added_items(
        self,
        old_stock: list[dict],
        new_stock: list[dict],
    ) -> list[dict]:

        old_names = {
            self.stock_identity(item)
            for item in old_stock
        }

        return [
            item
            for item in new_stock
            if self.stock_identity(item)
            not in old_names
        ]

    def get_removed_items(
        self,
        old_stock: list[dict],
        new_stock: list[dict],
    ) -> list[dict]:

        new_names = {
            self.stock_identity(item)
            for item in new_stock
        }

        return [
            item
            for item in old_stock
            if self.stock_identity(item)
            not in new_names
        ]

    # ========================================================
    # SHOP CHANNEL
    # ========================================================

    def get_shop_channel_id(
        self,
        guild_id: int,
        game: str,
    ) -> Optional[int]:

        row = db_fetchone(
            """
            SELECT channel_id
            FROM shop_channels
            WHERE guild_id = ?
              AND game = ?
            """,
            (
                guild_id,
                game,
            )
        )

        if row is None:
            return None

        return int(
            row["channel_id"]
        )

    def set_shop_channel(
        self,
        guild_id: int,
        game: str,
        channel_id: int,
    ):

        db_execute(
            """
            INSERT INTO shop_channels
            (guild_id, game, channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, game)
            DO UPDATE SET
                channel_id = excluded.channel_id
            """,
            (
                guild_id,
                game,
                channel_id,
            )
        )

    def remove_shop_channel(
        self,
        guild_id: int,
        game: str,
    ):

        db_execute(
            """
            DELETE FROM shop_channels
            WHERE guild_id = ?
              AND game = ?
            """,
            (
                guild_id,
                game,
            )
        )

    # ========================================================
    # NOTIFICATION ROLES
    # ========================================================

    def notification_role_name(
        self,
        notification_type: str,
    ) -> str:

        names = {
            NOTIF_GAG_STOCK:
                "🌱 GAG Stock",
            NOTIF_GAG_RARE:
                "✨ GAG Rare",
            NOTIF_BLOX_STOCK:
                "🍎 Blox Stock",
            NOTIF_STEAL_RESET:
                "🥚 Egg Reset",
            NOTIF_STEAL_RIFT:
                "🌀 Egg Rift",
            NOTIF_ALL_STOCK:
                "📦 All Stock",
        }

        return names.get(
            notification_type,
            "Stock Alerts"
        )

    def get_notification_role(
        self,
        guild_id: int,
        notification_type: str,
    ) -> Optional[discord.Role]:

        row = db_fetchone(
            """
            SELECT role_id
            FROM notification_roles
            WHERE guild_id = ?
              AND notification_type = ?
            """,
            (
                guild_id,
                notification_type,
            )
        )

        if row is None:
            return None

        guild = self.bot.get_guild(
            guild_id
        )

        if guild is None:
            return None

        return guild.get_role(
            int(row["role_id"])
        )

    async def create_notification_role(
        self,
        guild: discord.Guild,
        notification_type: str,
    ) -> Optional[discord.Role]:

        existing = self.get_notification_role(
            guild.id,
            notification_type
        )

        if existing:
            return existing

        try:

            role = await guild.create_role(
                name=self.notification_role_name(
                    notification_type
                ),
                mentionable=True,
                reason="Team Fime stock notification role",
            )

            db_execute(
                """
                INSERT OR REPLACE INTO
                notification_roles
                (guild_id, notification_type, role_id)
                VALUES (?, ?, ?)
                """,
                (
                    guild.id,
                    notification_type,
                    role.id,
                )
            )

            return role

        except discord.Forbidden:
            return None

    # ========================================================
    # SEND SHOP UPDATE
    # ========================================================

    async def send_shop_update(
        self,
        guild: discord.Guild,
        game: str,
        stock: list[dict],
    ):

        channel_id = self.get_shop_channel_id(
            guild.id,
            game
        )

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if channel is None:
            return

        embeds = build_shop_embeds(
            game,
            stock
        )

        for embed in embeds:

            try:

                await channel.send(
                    embed=embed
                )

            except discord.Forbidden:
                print(
                    f"⚠️ Missing permission "
                    f"for {channel.name}"
                )
                return

            except discord.HTTPException as error:
                print(
                    f"⚠️ Could not send stock: {error}"
                )

        # Only show selector for GAG.
        if game == GAME_GAG and stock:

            try:

                await channel.send(
                    content=(
                        "🔔 **تنبيهات Grow a Garden**\n"
                        "اختر عنصرًا من القائمة لتفعيل "
                        "أو إلغاء تنبيهه."
                    ),
                    view=GAGFruitView(
                        self,
                        guild.id,
                        stock
                    ),
                )

            except discord.HTTPException:
                pass

    # ========================================================
    # PERSONAL ALERTS
    # ========================================================

    async def send_personal_alerts(
        self,
        guild: discord.Guild,
        game: str,
        added: list[dict],
    ):

        if not added:
            return

        subscriptions = db_fetchall(
            """
            SELECT user_id, item_name
            FROM subscriptions
            WHERE guild_id = ?
              AND game = ?
            """,
            (
                guild.id,
                game,
            )
        )

        if not subscriptions:
            return

        for subscription in subscriptions:

            user_id = int(
                subscription["user_id"]
            )

            wanted = str(
                subscription["item_name"]
            ).lower()

            matches = []

            for item in added:

                name = str(
                    item.get("name", "")
                ).lower()

                if wanted in name:
                    matches.append(item)

            if not matches:
                continue

            user = guild.get_member(
                user_id
            )

            if user is None:
                continue

            lines = "\n".join(
                format_item_line(item)
                for item in matches
            )

            try:

                await user.send(
                    f"🔔 **Stock Alert — "
                    f"{GAME_NAMES.get(game, game)}**\n\n"
                    f"{lines}"
                )

            except discord.Forbidden:
                pass

            except discord.HTTPException:
                pass

    # ========================================================
    # GAG ITEM ROLE ALERTS
    # ========================================================

    async def send_gag_item_role_alerts(
        self,
        guild: discord.Guild,
        added: list[dict],
    ):

        if not added:
            return

        channel_id = self.get_shop_channel_id(
            guild.id,
            GAME_GAG
        )

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if channel is None:
            return

        for item in added:

            item_name = str(
                item.get("name", "")
            ).strip()

            if not item_name:
                continue

            rows = db_fetchall(
                """
                SELECT user_id
                FROM gag_item_subscriptions
                WHERE guild_id = ?
                  AND lower(item_name) = lower(?)
                """,
                (
                    guild.id,
                    item_name,
                )
            )

            role_row = db_fetchone(
                """
                SELECT role_id
                FROM gag_item_roles
                WHERE guild_id = ?
                  AND lower(item_name) = lower(?)
                """,
                (
                    guild.id,
                    item_name,
                )
            )

            if not rows:
                continue

            role = None

            if role_row:

                role = guild.get_role(
                    int(role_row["role_id"])
                )

            if role is None:

                try:

                    role = await guild.create_role(
                        name=(
                            f"🌱 {item_name}"
                        )[:100],
                        mentionable=True,
                        reason=(
                            "GAG item notification role"
                        ),
                    )

                    db_execute(
                        """
                        INSERT OR REPLACE INTO
                        gag_item_roles
                        (guild_id, item_name, role_id)
                        VALUES (?, ?, ?)
                        """,
                        (
                            guild.id,
                            item_name,
                            role.id,
                        )
                    )

                except discord.Forbidden:
                    continue

            if role is None:
                continue

            mentions = []

            for row in rows:

                member = guild.get_member(
                    int(row["user_id"])
                )

                if member is not None:
                    mentions.append(
                        member.mention
                    )

            if not mentions:
                continue

            try:

                await channel.send(
                    f"🔔 {role.mention} "
                    f"**{item_name}** ظهر في الـStock!\n"
                    + " ".join(mentions),
                    allowed_mentions=discord.AllowedMentions(
                        roles=True,
                        users=True,
                    ),
                )

            except discord.HTTPException:
                pass

    # ========================================================
    # RARE ALERTS
    # ========================================================

    async def send_rare_alert(
        self,
        guild: discord.Guild,
        added: list[dict],
    ):

        rare = [
            item
            for item in added
            if is_rare_item(item)
        ]

        if not rare:
            return

        role = self.get_notification_role(
            guild.id,
            NOTIF_GAG_RARE
        )

        if role is None:
            return

        channel_id = self.get_shop_channel_id(
            guild.id,
            GAME_GAG
        )

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if channel is None:
            return

        lines = "\n".join(
            format_item_line(item)
            for item in rare
        )

        try:

            await channel.send(
                f"✨ {role.mention} "
                f"**Rare Stock ظهر!**\n\n"
                f"{lines}",
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                ),
            )

        except discord.HTTPException:
            pass

    # ========================================================
    # PROCESS STOCK
    # ========================================================

    async def process_stock(
        self,
        guild: discord.Guild,
        game: str,
        stock: list[dict],
    ):

        if not stock:
            return

        old_stock = self.get_cached_stock(
            guild.id,
            game
        )

        # First successful sync.
        if old_stock is None:

            self.save_cached_stock(
                guild.id,
                game,
                stock
            )

            return

        old_serialized = json_dumps(
            old_stock
        )

        new_serialized = json_dumps(
            stock
        )

        if old_serialized == new_serialized:
            return

        added = self.get_added_items(
            old_stock,
            stock
        )

        removed = self.get_removed_items(
            old_stock,
            stock
        )

        self.save_cached_stock(
            guild.id,
            game,
            stock
        )

        # Always post updated stock.
        await self.send_shop_update(
            guild,
            game,
            stock
        )

        # Important:
        # quantity changes are NOT "new items".
        # Only names/sections that were absent before
        # trigger alerts.
        if added:

            await self.send_personal_alerts(
                guild,
                game,
                added
            )

            if game == GAME_GAG:

                await self.send_gag_item_role_alerts(
                    guild,
                    added
                )

                await self.send_rare_alert(
                    guild,
                    added
                )

    # ========================================================
    # STOCK LOOP
    # ========================================================

    @tasks.loop(
        seconds=STOCK_CHECK_SECONDS
    )
    async def stock_loop(self):

        if not self.bot.is_ready():
            return

        try:

            gag_stock = await self.fetch_gag_stock()

            (
                blox_stock,
                normal_reset,
                mirage_reset,
            ) = await self.fetch_blox_stock()

            steal_stock = (
                await self.fetch_steal_stock()
            )

            for guild in self.bot.guilds:

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

                if steal_stock:

                    await self.process_stock(
                        guild,
                        GAME_STEAL,
                        steal_stock
                    )

        except Exception as error:

            print(
                f"❌ Stock loop error: {error}"
            )

    @stock_loop.before_loop
    async def before_stock_loop(
        self,
    ):

        await self.bot.wait_until_ready()

        await self.ensure_session()

    # ========================================================
    # STEAL AN EGG EVENTS
    # ========================================================

    def event_bucket(
        self,
        minutes: int,
    ) -> int:

        return int(
            time.time() // (
                minutes * 60
            )
        )

    async def send_event(
        self,
        guild: discord.Guild,
        event_type: str,
    ):

        role = self.get_notification_role(
            guild.id,
            event_type
        )

        channel_id = self.get_shop_channel_id(
            guild.id,
            GAME_STEAL
        )

        if not channel_id:
            return

        channel = guild.get_channel(
            channel_id
        )

        if channel is None:
            return

        if event_type == NOTIF_STEAL_RESET:

            title = (
                "🥚 Steal An Egg — Reset"
            )

            text = (
                "🔄 وقت إعادة دورة الـEggs."
            )

        else:

            title = (
                "🌀 Steal An Egg — Rift"
            )

            text = (
                "🌀 دخل وقت الـRift."
            )

        mention = (
            role.mention
            if role
            else ""
        )

        embed = discord.Embed(
            title=title,
            description=text,
            color=discord.Color.blurple(),
            timestamp=datetime.now(
                timezone.utc
            ),
        )

        try:

            await channel.send(
                content=mention or None,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(
                    roles=True
                ),
            )

        except discord.HTTPException:
            pass

    @tasks.loop(
        minutes=1
    )
    async def steal_event_loop(
        self,
    ):

        if not self.bot.is_ready():
            return

        current_minute = int(
            time.time() // 60
        )

        if (
            current_minute
            % STEAL_EGG_RESET_MINUTES
            == 0
        ):

            bucket = (
                current_minute
                // STEAL_EGG_RESET_MINUTES
            )

            for guild in self.bot.guilds:

                row = db_fetchone(
                    """
                    SELECT last_sent
                    FROM event_cache
                    WHERE guild_id = ?
                      AND event_type = ?
                    """,
                    (
                        guild.id,
                        NOTIF_STEAL_RESET,
                    )
                )

                if (
                    row
                    and int(row["last_sent"]) == bucket
                ):
                    continue

                await self.send_event(
                    guild,
                    NOTIF_STEAL_RESET
                )

                db_execute(
                    """
                    INSERT OR REPLACE INTO
                    event_cache
                    (guild_id, event_type, last_sent)
                    VALUES (?, ?, ?)
                    """,
                    (
                        guild.id,
                        NOTIF_STEAL_RESET,
                        bucket,
                    )
                )

        if (
            current_minute
            % STEAL_EGG_RIFT_MINUTES
            == 0
        ):

            bucket = (
                current_minute
                // STEAL_EGG_RIFT_MINUTES
            )

            for guild in self.bot.guilds:

                row = db_fetchone(
                    """
                    SELECT last_sent
                    FROM event_cache
                    WHERE guild_id = ?
                      AND event_type = ?
                    """,
                    (
                        guild.id,
                        NOTIF_STEAL_RIFT,
                    )
                )

                if (
                    row
                    and int(row["last_sent"]) == bucket
                ):
                    continue

                await self.send_event(
                    guild,
                    NOTIF_STEAL_RIFT
                )

                db_execute(
                    """
                    INSERT OR REPLACE INTO
                    event_cache
                    (guild_id, event_type, last_sent)
                    VALUES (?, ?, ?)
                    """,
                    (
                        guild.id,
                        NOTIF_STEAL_RIFT,
                        bucket,
                    )
                )

    @steal_event_loop.before_loop
    async def before_steal_event_loop(
        self,
    ):

        await self.bot.wait_until_ready()

    # ========================================================
    # STOCK GROUP
    # ========================================================

    stock_group = app_commands.Group(
        name="stock",
        description="Team Fime Stock System"
    )

    # ========================================================
    # /stock view
    # ========================================================

    @stock_group.command(
        name="view",
        description="عرض الـStock الحالي"
    )
    @app_commands.describe(
        game="اختر اللعبة"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG,
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX,
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL,
            ),
        ]
    )
    async def stock_view(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
    ):

        game_id = game.value

        await interaction.response.defer(
            ephemeral=True
        )

        stock = []

        if game_id == GAME_GAG:
            stock = await self.fetch_gag_stock()

        elif game_id == GAME_BLOX:
            (
                stock,
                normal_reset,
                mirage_reset,
            ) = await self.fetch_blox_stock()

        elif game_id == GAME_STEAL:
            stock = await self.fetch_steal_stock()

        if not stock:

            await interaction.followup.send(
                "❌ ما قدرت أجيب الـStock حاليًا.",
                ephemeral=True,
            )
            return

        embeds = build_shop_embeds(
            game_id,
            stock
        )

        for embed in embeds:

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )

    # ========================================================
    # /stock channel
    # ========================================================

    @stock_group.command(
        name="channel",
        description="تحديد روم Stock للعبة"
    )
    @app_commands.describe(
        game="اللعبة",
        channel="الروم"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG,
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX,
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL,
            ),
        ]
    )
    async def stock_channel(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        channel: discord.TextChannel,
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        self.set_shop_channel(
            interaction.guild_id,
            game.value,
            channel.id
        )

        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} "
            f"كروم لـ{GAME_NAMES[game.value]}.",
            ephemeral=True,
        )

    # ========================================================
    # /stock channel-remove
    # ========================================================

    @stock_group.command(
        name="channel-remove",
        description="إلغاء روم Stock"
    )
    @app_commands.describe(
        game="اللعبة"
    )
    @app_commands.choices(
        game=[
            app_commands.Choice(
                name="🌱 Grow a Garden",
                value=GAME_GAG,
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX,
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL,
            ),
        ]
    )
    async def stock_channel_remove(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        self.remove_shop_channel(
            interaction.guild_id,
            game.value
        )

        await interaction.response.send_message(
            f"✅ تم إلغاء روم "
            f"{GAME_NAMES[game.value]}.",
            ephemeral=True,
        )

    # ========================================================
    # /stock channel-status
    # ========================================================

    @stock_group.command(
        name="channel-status",
        description="عرض رومات الـStock"
    )
    async def stock_channel_status(
        self,
        interaction: discord.Interaction,
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        lines = []

        for game_id, game_name in GAME_NAMES.items():

            channel_id = self.get_shop_channel_id(
                interaction.guild_id,
                game_id
            )

            if channel_id:

                channel = interaction.guild.get_channel(
                    channel_id
                )

                if channel:
                    value = channel.mention
                else:
                    value = (
                        f"`{channel_id}`"
                    )

            else:
                value = "غير محدد"

            lines.append(
                f"{game_name}: {value}"
            )

        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
        )

    # ========================================================
    # /stock notifications-setup
    # ========================================================

    @stock_group.command(
        name="notifications-setup",
        description="إنشاء لوحة تنبيهات الـStock"
    )
    @app_commands.describe(
        channel="الروم الذي ستوضع فيه اللوحة"
    )
    async def notifications_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        embed = discord.Embed(
            title="🔔 Stock Notifications",
            description=(
                "اختر نوع التنبيه الذي تريده.\n\n"
                "تقدر تضغط مرة ثانية لإلغاء التنبيه."
            ),
            color=discord.Color.blurple(),
        )

        message = await channel.send(
            embed=embed,
            view=NotificationView(self),
        )

        db_execute(
            """
            INSERT OR REPLACE INTO
            notification_panels
            (guild_id, channel_id, message_id)
            VALUES (?, ?, ?)
            """,
            (
                interaction.guild_id,
                channel.id,
                message.id,
            )
        )

        await interaction.response.send_message(
            f"✅ تم إنشاء لوحة التنبيهات في "
            f"{channel.mention}.",
            ephemeral=True,
        )

    # ========================================================
    # /stock notifications-reset
    # ========================================================

    @stock_group.command(
        name="notifications-reset",
        description="حذف بيانات تنبيهات الأعضاء"
    )
    async def notifications_reset(
        self,
        interaction: discord.Interaction,
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        db_execute(
            """
            DELETE FROM notification_members
            WHERE guild_id = ?
            """,
            (
                interaction.guild_id,
            )
        )

        await interaction.response.send_message(
            "✅ تم تصفير اشتراكات تنبيهات الأعضاء.",
            ephemeral=True,
        )

    # ========================================================
    # /stock alert
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
                value=GAME_GAG,
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX,
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL,
            ),
        ]
    )
    async def stock_alert(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        item: str,
    ):

        item = item.strip()

        if not item:
            await interaction.response.send_message(
                "❌ اكتب اسم العنصر.",
                ephemeral=True,
            )
            return

        db_execute(
            """
            INSERT OR IGNORE INTO
            subscriptions
            (guild_id, user_id, game, item_name)
            VALUES (?, ?, ?, ?)
            """,
            (
                interaction.guild_id,
                interaction.user.id,
                game.value,
                item,
            )
        )

        await interaction.response.send_message(
            f"🔔 تم تفعيل تنبيه **{item}** "
            f"في {GAME_NAMES[game.value]}.",
            ephemeral=True,
        )

    # ========================================================
    # /stock alert-remove
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
                value=GAME_GAG,
            ),
            app_commands.Choice(
                name="🍎 Blox Fruits",
                value=GAME_BLOX,
            ),
            app_commands.Choice(
                name="🥚 Steal An Egg",
                value=GAME_STEAL,
            ),
        ]
    )
    async def stock_alert_remove(
        self,
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        item: str,
    ):

        db_execute(
            """
            DELETE FROM subscriptions
            WHERE guild_id = ?
              AND user_id = ?
              AND game = ?
              AND lower(item_name) = lower(?)
            """,
            (
                interaction.guild_id,
                interaction.user.id,
                game.value,
                item.strip(),
            )
        )

        await interaction.response.send_message(
            f"🔕 تم إلغاء تنبيه **{item}**.",
            ephemeral=True,
        )

    # ========================================================
    # /stock alerts
    # ========================================================

    @stock_group.command(
        name="alerts",
        description="عرض تنبيهاتك"
    )
    async def stock_alerts(
        self,
        interaction: discord.Interaction,
    ):

        rows = db_fetchall(
            """
            SELECT game, item_name
            FROM subscriptions
            WHERE guild_id = ?
              AND user_id = ?
            ORDER BY game, item_name
            """,
            (
                interaction.guild_id,
                interaction.user.id,
            )
        )

        if not rows:

            await interaction.response.send_message(
                "📭 ما عندك أي تنبيهات حاليًا.",
                ephemeral=True,
            )
            return

        lines = []

        for row in rows:

            lines.append(
                f"• {GAME_NAMES.get(row['game'], row['game'])}"
                f" — **{row['item_name']}**"
            )

        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
        )

    # ========================================================
    # /stock steal-alert
    # ========================================================

    @stock_group.command(
        name="steal-alert",
        description="تفعيل تنبيه Steal An Egg"
    )
    @app_commands.describe(
        event="نوع التنبيه"
    )
    @app_commands.choices(
        event=[
            app_commands.Choice(
                name="🥚 Reset",
                value=NOTIF_STEAL_RESET,
            ),
            app_commands.Choice(
                name="🌀 Rift",
                value=NOTIF_STEAL_RIFT,
            ),
        ]
    )
    async def steal_alert(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
    ):

        role = self.get_notification_role(
            interaction.guild_id,
            event.value
        )

        if role is None:

            role = await self.create_notification_role(
                interaction.guild,
                event.value
            )

        if role is None:

            await interaction.response.send_message(
                "❌ ما قدرت أنشئ الرتبة.",
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(
            interaction.user.id
        )

        try:

            await member.add_roles(
                role,
                reason="Steal An Egg notification"
            )

            await interaction.response.send_message(
                f"🔔 تم تفعيل {role.mention}.",
                ephemeral=True,
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ ما عندي صلاحية إدارة الرتب.",
                ephemeral=True,
            )

    # ========================================================
    # /stock steal-alert-remove
    # ========================================================

    @stock_group.command(
        name="steal-alert-remove",
        description="إلغاء تنبيه Steal An Egg"
    )
    @app_commands.describe(
        event="نوع التنبيه"
    )
    @app_commands.choices(
        event=[
            app_commands.Choice(
                name="🥚 Reset",
                value=NOTIF_STEAL_RESET,
            ),
            app_commands.Choice(
                name="🌀 Rift",
                value=NOTIF_STEAL_RIFT,
            ),
        ]
    )
    async def steal_alert_remove(
        self,
        interaction: discord.Interaction,
        event: app_commands.Choice[str],
    ):

        role = self.get_notification_role(
            interaction.guild_id,
            event.value
        )

        if role is None:

            await interaction.response.send_message(
                "❌ ما فيه رتبة لهذا التنبيه.",
                ephemeral=True,
            )
            return

        member = interaction.guild.get_member(
            interaction.user.id
        )

        try:

            await member.remove_roles(
                role,
                reason="Steal An Egg notification removed"
            )

            await interaction.response.send_message(
                f"🔕 تم إلغاء {role.name}.",
                ephemeral=True,
            )

        except discord.Forbidden:

            await interaction.response.send_message(
                "❌ ما عندي صلاحية إدارة الرتب.",
                ephemeral=True,
            )

    # ========================================================
    # /stock status
    # ========================================================

    @stock_group.command(
        name="status",
        description="حالة نظام الـStock"
    )
    async def stock_status(
        self,
        interaction: discord.Interaction,
    ):

        if not await self.owner_check(
            interaction
        ):
            return

        gag_status = (
            "🟢 متصل"
            if GAG_API_URL
            else "🔴 غير مضبوط"
        )

        blox_status = (
            "🟢 متصل"
            if BLOX_API_URL
            else "🔴 غير مضبوط"
        )

        blox_key = (
            "🟢 موجود"
            if PARSE_API_KEY
            else "🟡 غير موجود"
        )

        steal_status = (
            "🟢 API مخصص"
            if STEAL_EGG_API_URL
            else "🟡 بدون API Stock"
        )

        embed = discord.Embed(
            title="📊 Team Fime Stock Status",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="🌱 Grow a Garden",
            value=gag_status,
            inline=False,
        )

        embed.add_field(
            name="🍎 Blox Fruits",
            value=(
                f"{blox_status}\n"
                f"API Key: {blox_key}"
            ),
            inline=False,
        )

        embed.add_field(
            name="🥚 Steal An Egg",
            value=steal_status,
            inline=False,
        )

        embed.add_field(
            name="⏱️ Polling",
            value=(
                f"`{STOCK_CHECK_SECONDS}` ثانية"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        FimeStock(bot)
    )

    print(
        "✅ bot6.py loaded successfully."
    )