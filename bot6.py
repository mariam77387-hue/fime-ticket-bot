# ============================================================
# Team Fime - Stock System
# bot6.py
#
# Stock:
#   🌱 Grow a Garden
#   🍎 Blox Fruits
#   🥚 Steal An Egg
#
# Features:
#   - Live stock polling
#   - Automatic shop posting
#   - Custom shop channel per guild/game
#   - Notification setup panel
#   - Automatic notification roles
#   - Stock refresh notification
#   - Rare stock notification
#   - Steal An Egg reset notification
#   - Steal An Egg rift notification
#   - SQLite persistence
#   - Personal stock alerts
#   - Admin status commands
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

GAG_API_URL = os.getenv(
    "GAG_API_URL",
    "https://gagapi-production.up.railway.app/stock"
)

BLOX_API_URL = os.getenv(
    "BLOX_API_URL",
    ""
)

try:
    STOCK_CHECK_SECONDS = max(
        10,
        int(os.getenv("STOCK_CHECK_SECONDS", "30"))
    )
except Exception:
    STOCK_CHECK_SECONDS = 30

STEAL_EGG_RESET_MINUTES = 5
STEAL_EGG_RIFT_MINUTES = 30


# ============================================================
# GAME DEFINITIONS
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
# NOTIFICATION DEFINITIONS
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
        "description": "إشعار عند ظهور عناصر نادرة في الستوك.",
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
        "description": "إشعار عند بداية دورة Reset الجديدة.",
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
        "description": "إشعار لجميع تحديثات الستوك الرئيسية.",
        "color": discord.Color.purple(),
    },
}


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def setup_database():
    conn = get_db()
    cur = conn.cursor()

    # Personal item subscriptions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            item TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, game, item)
        )
    """)

    # Event subscriptions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_subscriptions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, event_type)
        )
    """)

    # Stock cache
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_cache (
            guild_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            stock_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, game)
        )
    """)

    # Event cache
    cur.execute("""
        CREATE TABLE IF NOT EXISTS event_cache (
            guild_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            last_value TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, event_type)
        )
    """)

    # Shop channels
    cur.execute("""
        CREATE TABLE IF NOT EXISTS shop_channels (
            guild_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            channel_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, game)
        )
    """)

    # Notification roles
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_roles (
            guild_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, notification_type)
        )
    """)

    # Notification panel
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    """)

    # User notification choices
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_members (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, notification_type)
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
        INSERT INTO shop_channels
        (guild_id, game, channel_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, game)
        DO UPDATE SET channel_id = excluded.channel_id
    """, (guild_id, game, channel_id))
    conn.commit()
    conn.close()


def remove_shop_channel(guild_id, game):
    conn = get_db()
    conn.execute("""
        DELETE FROM shop_channels
        WHERE guild_id = ? AND game = ?
    """, (guild_id, game))
    conn.commit()
    conn.close()


def get_shop_channels(guild_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT game, channel_id
        FROM shop_channels
        WHERE guild_id = ?
    """, (guild_id,)).fetchall()
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
        WHERE guild_id = ? AND game = ?
    """, (guild_id, game)).fetchone()
    conn.close()

    return row["channel_id"] if row else None


def get_cached_stock(guild_id, game):
    conn = get_db()
    row = conn.execute("""
        SELECT stock_json
        FROM stock_cache
        WHERE guild_id = ? AND game = ?
    """, (guild_id, game)).fetchone()
    conn.close()

    if not row:
        return None

    return row["stock_json"]


def save_cached_stock(guild_id, game, stock_json):
    conn = get_db()

    conn.execute("""
        INSERT INTO stock_cache
        (guild_id, game, stock_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, game)
        DO UPDATE SET
            stock_json = excluded.stock_json,
            updated_at = excluded.updated_at
    """, (
        guild_id,
        game,
        stock_json,
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()


def get_notification_role(guild_id, notification_type):
    conn = get_db()

    row = conn.execute("""
        SELECT role_id
        FROM notification_roles
        WHERE guild_id = ? AND notification_type = ?
    """, (guild_id, notification_type)).fetchone()

    conn.close()

    return row["role_id"] if row else None


def save_notification_role(
    guild_id,
    notification_type,
    role_id
):
    conn = get_db()

    conn.execute("""
        INSERT INTO notification_roles
        (guild_id, notification_type, role_id)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, notification_type)
        DO UPDATE SET role_id = excluded.role_id
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
        INSERT INTO notification_panels
        (guild_id, channel_id, message_id)
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
    """, (guild_id,)).fetchone()

    conn.close()

    return (
        (row["channel_id"], row["message_id"])
        if row
        else None
    )


def add_notification_member(
    guild_id,
    user_id,
    notification_type
):
    conn = get_db()

    conn.execute("""
        INSERT OR IGNORE INTO notification_members
        (guild_id, user_id, notification_type)
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


def get_member_notification_choices(
    guild_id,
    user_id
):
    conn = get_db()

    rows = conn.execute("""
        SELECT notification_type
        FROM notification_members
        WHERE guild_id = ?
        AND user_id = ?
    """, (
        guild_id,
        user_id
    )).fetchall()

    conn.close()

    return {
        row["notification_type"]
        for row in rows
    }


# ============================================================
# JSON / API
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
            timeout=aiohttp.ClientTimeout(total=15)
        ) as response:

            if response.status != 200:
                print(
                    f"⚠️ Stock API HTTP {response.status}: {url}"
                )
                return None

            try:
                return await response.json(
                    content_type=None
                )
            except Exception:
                print(
                    f"⚠️ Stock API returned invalid JSON: {url}"
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
# NORMALIZATION
# ============================================================

def normalize_item(
    item,
    default_stock=0
):
    if isinstance(item, str):
        return {
            "name": item,
            "stock": default_stock,
            "rarity": "",
        }

    if not isinstance(item, dict):
        return None

    name = (
        item.get("name")
        or item.get("item")
        or item.get("title")
        or item.get("displayName")
        or item.get("display_name")
        or item.get("fruit")
        or item.get("egg")
        or "Unknown"
    )

    stock = (
        item.get("stock")
        if item.get("stock") is not None
        else item.get("quantity")
    )

    if stock is None:
        stock = item.get("amount")

    if stock is None:
        stock = default_stock

    rarity = (
        item.get("rarity")
        or item.get("tier")
        or item.get("type")
        or ""
    )

    return {
        "name": str(name),
        "stock": stock,
        "rarity": str(rarity),
    }


def extract_list(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    possible_keys = [
        "stock",
        "stocks",
        "items",
        "data",
        "shop",
        "inventory",
        "goods",
        "fruits",
    ]

    for key in possible_keys:
        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            result = []

            for name, item in value.items():

                if isinstance(item, dict):
                    copied = dict(item)
                    copied.setdefault("name", name)
                    result.append(copied)

                else:
                    result.append({
                        "name": name,
                        "stock": item
                    })

            return result

    return []


def normalize_gag(data):
    raw = extract_list(data)

    result = []

    for item in raw:
        normalized = normalize_item(item)

        if normalized:
            result.append(normalized)

    return result


def normalize_blox(data):
    raw = extract_list(data)

    result = []

    for item in raw:
        normalized = normalize_item(item)

        if normalized:
            result.append(normalized)

    return result


# ============================================================
# STOCK FETCHERS
# ============================================================

async def fetch_gag_stock(session):
    data = await fetch_json(
        session,
        GAG_API_URL
    )

    if data is None:
        return []

    return normalize_gag(data)


async def fetch_blox_stock(session):
    if not BLOX_API_URL:
        return []

    data = await fetch_json(
        session,
        BLOX_API_URL
    )

    if data is None:
        return []

    return normalize_blox(data)


# ============================================================
# STOCK SERIALIZATION
# ============================================================

def clean_stock(stock):
    cleaned = []

    seen = set()

    for item in stock:

        if not isinstance(item, dict):
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

        seen.add(key)

        cleaned.append({
            "name": name,
            "stock": stock_count,
            "rarity": rarity,
        })

    cleaned.sort(
        key=lambda x: (
            x["name"].lower(),
            str(x["stock"])
        )
    )

    return cleaned


def serialize_stock(stock):
    import json

    return json.dumps(
        clean_stock(stock),
        ensure_ascii=False,
        sort_keys=True
    )


# ============================================================
# RARE DETECTION
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
        word in rarity or word in name
        for word in rare_words
    )


def has_rare_stock(stock):
    return any(
        is_rare_item(item)
        for item in stock
    )


# ============================================================
# EMBEDS
# ============================================================

def build_shop_embeds(
    game,
    stock,
    mention=None
):
    stock = clean_stock(stock)

    game_name = GAME_NAMES.get(
        game,
        game
    )

    if not stock:
        embed = discord.Embed(
            title=f"{game_name} | Stock",
            description="لا يوجد ستوك متاح حاليًا.",
            color=discord.Color.dark_grey()
        )

        return [embed]

    chunks = []
    current = ""

    for item in stock:

        name = item["name"]
        amount = item["stock"]
        rarity = item.get("rarity", "")

        line = f"**{name}**"

        if amount not in (
            None,
            "",
            0,
            "0"
        ):
            line += f" × `{amount}`"

        if rarity:
            line += f" — `{rarity}`"

        line += "\n"

        if len(current) + len(line) > 3800:

            if current:
                chunks.append(current)

            current = line

        else:
            current += line

    if current:
        chunks.append(current)

    embeds = []

    for index, chunk in enumerate(chunks):

        title = f"{game_name} | Shop"

        if len(chunks) > 1:
            title += f" ({index + 1}/{len(chunks)})"

        embed = discord.Embed(
            title=title,
            description=chunk,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        if index == 0:
            embed.set_footer(
                text="Team Fime • Stock System"
            )

        embeds.append(embed)

    return embeds


# ============================================================
# NOTIFICATION EMBED
# ============================================================

def build_notification_panel_embed():
    embed = discord.Embed(
        title="🔔 إشعارات الستوك",
        description=(
            "اختار الإشعارات اللي تبي توصلك.\n\n"
            "اضغط على القائمة بالأسفل ثم اختر النوع المناسب لك.\n"
            "عند اختيار إشعار، البوت يعطيك **رتبة الإشعار تلقائيًا**.\n\n"
            "**يمكنك تغيير اختياراتك بأي وقت.**"
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🌱 Grow a Garden",
        value=(
            "• تجديد الستوك\n"
            "• الستوك النادر"
        ),
        inline=True
    )

    embed.add_field(
        name="🍎 Blox Fruits",
        value="• تجديد الستوك",
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
        value="• جميع إشعارات الستوك",
        inline=False
    )

    embed.set_footer(
        text="Team Fime • Notification System"
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

        for notification_type, info in NOTIFICATION_INFO.items():

            options.append(
                discord.SelectOption(
                    label=info["short"][:100],
                    description=info["description"][:100],
                    value=notification_type
                )
            )

        super().__init__(
            placeholder="🔔 اختر إشعاراتك...",
            min_values=1,
            max_values=min(
                len(options),
                6
            ),
            options=options,
            custom_id="fime_stock_notifications"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ هذا النظام يعمل داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        cog = interaction.client.get_cog(
            "FimeStock"
        )

        if not cog:
            await interaction.response.send_message(
                "❌ نظام الستوك غير متاح حاليًا.",
                ephemeral=True
            )
            return

        selected = set(self.values)

        await interaction.response.defer(
            ephemeral=True
        )

        results = []

        for notification_type in selected:

            role = await cog.get_or_create_notification_role(
                interaction.guild,
                notification_type
            )

            if not role:
                results.append(
                    f"❌ تعذر إنشاء رتبة "
                    f"{NOTIFICATION_INFO[notification_type]['short']}"
                )
                continue

            try:

                if role not in interaction.user.roles:

                    await interaction.user.add_roles(
                        role,
                        reason="Fime Stock Notification"
                    )

                    add_notification_member(
                        interaction.guild.id,
                        interaction.user.id,
                        notification_type
                    )

                    results.append(
                        f"✅ تمت إضافة **{role.name}**"
                    )

                else:

                    await interaction.user.remove_roles(
                        role,
                        reason="Fime Stock Notification Toggle"
                    )

                    remove_notification_member(
                        interaction.guild.id,
                        interaction.user.id,
                        notification_type
                    )

                    results.append(
                        f"➖ تمت إزالة **{role.name}**"
                    )

            except discord.Forbidden:
                results.append(
                    f"❌ البوت لا يستطيع تعديل رتبة **{role.name}**"
                )

            except Exception as error:
                print(
                    f"Notification role error: {error}"
                )

                results.append(
                    "❌ حدث خطأ أثناء تعديل الإشعار."
                )

        await interaction.followup.send(
            "\n".join(results),
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
# FIME STOCK COG
# ============================================================

class FimeStock(commands.Cog):

    def __init__(
        self,
        bot
    ):
        self.bot = bot

        setup_database()

        self.session = None

        self.gag_last_stock = None
        self.blox_last_stock = None

        self.steal_reset_counter = 0
        self.steal_rift_counter = 0

        self.stock_loop.start()
        self.steal_event_loop.start()

    # ========================================================
    # LIFECYCLE
    # ========================================================

    def cog_unload(self):

        self.stock_loop.cancel()
        self.steal_event_loop.cancel()

        if self.session:
            asyncio.create_task(
                self.session.close()
            )

    async def cog_load(self):

        if self.session is None:
            self.session = aiohttp.ClientSession()

        try:
            self.bot.add_view(
                NotificationView()
            )
        except Exception as error:
            print(
                f"⚠️ Notification persistent view: {error}"
            )

    async def ensure_session(self):

        if (
            self.session is None
            or self.session.closed
        ):
            self.session = aiohttp.ClientSession()

    # ========================================================
    # CHANNEL RESOLUTION
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
    # NOTIFICATION ROLES
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

        role_name = f"🔔 {info['role']}"

        # Search existing role by exact name
        role = discord.utils.get(
            guild.roles,
            name=role_name
        )

        if role:

            save_notification_role(
                guild.id,
                notification_type,
                role.id
            )

            return role

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
            return None

        except Exception as error:
            print(
                f"❌ Could not create notification role: {error}"
            )
            return None

    # ========================================================
    # SEND STOCK UPDATE
    # ========================================================

    async def send_shop_update(
        self,
        guild,
        game,
        stock,
        changed_added=None,
        changed_removed=None
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

            if role_id:
                mention = f"<@&{role_id}>"

        elif game == GAME_BLOX:

            role_id = get_notification_role(
                guild.id,
                NOTIF_BLOX_STOCK
            )

            if role_id:
                mention = f"<@&{role_id}>"

        embeds = build_shop_embeds(
            game,
            stock,
            mention=mention
        )

        for index, embed in enumerate(embeds):

            content = None

            if index == 0 and mention:
                content = mention

            try:

                await channel.send(
                    content=content,
                    embed=embed
                )

            except discord.Forbidden:
                print(
                    f"❌ No permission to send in #{channel.name}"
                )
                break

            except Exception as error:
                print(
                    f"⚠️ Shop send error: {error}"
                )
                break

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

            user = guild.get_member(
                row["user_id"]
            )

            if not user:
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
                f"• **{item['name']}** × `{item['stock']}`"
                for item in matches
            )

            try:

                embed = discord.Embed(
                    title="🔔 Stock Alert",
                    description=(
                        f"ظهر العنصر اللي طلبت تنبيه عنه:\n\n"
                        f"{text}"
                    ),
                    color=discord.Color.green()
                )

                embed.set_footer(
                    text="Team Fime • Personal Stock Alert"
                )

                await user.send(
                    embed=embed
                )

            except Exception:
                pass

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

        import json

        current_json = serialize_stock(
            stock
        )

        old_json = get_cached_stock(
            guild.id,
            game
        )

        # First run:
        # Cache only, don't spam the channel.
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
                item.get("rarity", "").lower()
            )
            for item in old_stock
        }

        new_keys = {
            (
                item["name"].lower(),
                str(item["stock"]),
                item.get("rarity", "").lower()
            )
            for item in stock
        }

        added = [
            item
            for item in stock
            if (
                item["name"].lower(),
                str(item["stock"]),
                item.get("rarity", "").lower()
            ) not in old_keys
        ]

        removed = [
            item
            for item in old_stock
            if (
                item["name"].lower(),
                str(item["stock"]),
                item.get("rarity", "").lower()
            ) not in new_keys
        ]

        # Save immediately after detecting change
        save_cached_stock(
            guild.id,
            game,
            current_json
        )

        # Main shop message
        await self.send_shop_update(
            guild,
            game,
            stock,
            added,
            removed
        )

        # Personal alerts
        await self.send_personal_alerts(
            guild,
            game,
            added
        )

        # Rare alert
        if game == GAME_GAG:

            rare_added = [
                item
                for item in added
                if is_rare_item(item)
            ]

            if rare_added:

                role_id = get_notification_role(
                    guild.id,
                    NOTIF_GAG_RARE
                )

                channel_id = get_shop_channel(
                    guild.id,
                    game
                )

                if role_id and channel_id:

                    channel = await self.resolve_channel(
                        channel_id
                    )

                    if channel:

                        text = "\n".join(
                            f"💎 **{item['name']}** × `{item['stock']}`"
                            for item in rare_added
                        )

                        embed = discord.Embed(
                            title="💎 Rare Stock!",
                            description=text,
                            color=discord.Color.gold()
                        )

                        try:

                            await channel.send(
                                content=f"<@&{role_id}>",
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
    async def stock_loop(self):

        await self.bot.wait_until_ready()

        await self.ensure_session()

        guilds = list(
            self.bot.guilds
        )

        if not guilds:
            return

        gag_stock = await fetch_gag_stock(
            self.session
        )

        blox_stock = []

        if BLOX_API_URL:
            blox_stock = await fetch_blox_stock(
                self.session
            )

        for guild in guilds:

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
                    f"⚠️ Stock processing error "
                    f"for {guild.name}: {error}"
                )

    @stock_loop.before_loop
    async def before_stock_loop(
        self
    ):
        await self.bot.wait_until_ready()

    # ========================================================
    # STEAL AN EGG EVENTS
    # ========================================================

    @tasks.loop(minutes=1)
    async def steal_event_loop(self):

        await self.bot.wait_until_ready()

        self.steal_reset_counter += 1
        self.steal_rift_counter += 1

        # Reset
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

        # Rift
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

        for guild in self.bot.guilds:

            role_id = get_notification_role(
                guild.id,
                notification_type
            )

            if not role_id:
                continue

            # Use Steal An Egg shop channel
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

            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )

            embed.set_footer(
                text="Team Fime • Stock Alerts"
            )

            try:

                await channel.send(
                    content=f"<@&{role_id}>",
                    embed=embed
                )

            except Exception:
                pass

    # ========================================================
    # /STOCK
    # ========================================================

    @app_commands.command(
        name="stock",
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
        interaction: discord.Interaction,
        game: app_commands.Choice[str]
    ):

        await interaction.response.defer()

        await self.ensure_session()

        if game.value == GAME_GAG:

            stock = await fetch_gag_stock(
                self.session
            )

        else:

            stock = await fetch_blox_stock(
                self.session
            )

        if not stock:

            await interaction.followup.send(
                "❌ لا يوجد ستوك متاح حاليًا أو أن مصدر البيانات غير متاح."
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

    # ========================================================
    # /STOCK-CHANNEL
    # ========================================================

    @app_commands.command(
        name="stock-channel",
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
        interaction: discord.Interaction,
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
                f"✅ تم تحديد روم {channel.mention}\n"
                f"للعبة **{GAME_NAMES[game.value]}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK-CHANNEL-REMOVE
    # ========================================================

    @app_commands.command(
        name="stock-channel-remove",
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
        interaction: discord.Interaction,
        game: app_commands.Choice[str]
    ):

        remove_shop_channel(
            interaction.guild.id,
            game.value
        )

        await interaction.response.send_message(
            f"✅ تم حذف روم **{GAME_NAMES[game.value]}**.",
            ephemeral=True
        )

    # ========================================================
    # /STOCK-CHANNEL-STATUS
    # ========================================================

    @app_commands.command(
        name="stock-channel-status",
        description="عرض رومات الستوك المحددة"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_channel_status(
        self,
        interaction: discord.Interaction
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
    # /STOCK-NOTIFICATIONS-SETUP
    # ========================================================

    @app_commands.command(
        name="stock-notifications-setup",
        description="إنشاء لوحة اختيار إشعارات الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    @app_commands.describe(
        channel="الروم الذي تريد وضع لوحة الإشعارات فيه"
    )
    async def stock_notifications_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        embed = build_notification_panel_embed()

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
                    f"✅ تم إنشاء لوحة الإشعارات في "
                    f"{channel.mention}\n\n"
                    "العضو الآن يختار الإشعار من القائمة "
                    "والبوت يعطيه الرتبة تلقائيًا."
                ),
                ephemeral=True
            )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    "❌ البوت لا يملك صلاحية إرسال الرسائل "
                    "أو إدارة الرسائل في هذا الروم."
                ),
                ephemeral=True
            )

        except Exception as error:

            print(
                f"Notification setup error: {error}"
            )

            await interaction.followup.send(
                "❌ حدث خطأ أثناء إنشاء لوحة الإشعارات.",
                ephemeral=True
            )

    # ========================================================
    # /STOCK-NOTIFICATIONS-RESET
    # ========================================================

    @app_commands.command(
        name="stock-notifications-reset",
        description="إعادة إنشاء لوحة الإشعارات"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_notifications_reset(
        self,
        interaction: discord.Interaction
    ):

        panel = get_notification_panel(
            interaction.guild.id
        )

        if not panel:

            await interaction.response.send_message(
                "❌ لا توجد لوحة محفوظة لهذا السيرفر.",
                ephemeral=True
            )

            return

        channel_id, message_id = panel

        channel = await self.resolve_channel(
            channel_id
        )

        if not channel:

            await interaction.response.send_message(
                "❌ لم أستطع الوصول للروم القديم.",
                ephemeral=True
            )

            return

        try:

            old_message = await channel.fetch_message(
                message_id
            )

            await old_message.edit(
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
                    "❌ تعذر إنشاء اللوحة الجديدة.",
                    ephemeral=True
                )

        except Exception as error:

            print(
                f"Notification reset error: {error}"
            )

            await interaction.response.send_message(
                "❌ حدث خطأ أثناء تحديث اللوحة.",
                ephemeral=True
            )

    # ========================================================
    # /STOCK-ALERT
    # ========================================================

    @app_commands.command(
        name="stock-alert",
        description="إضافة تنبيه شخصي لعنصر معين"
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
        interaction: discord.Interaction,
        game: app_commands.Choice[str],
        item: str
    ):

        conn = get_db()

        conn.execute("""
            INSERT OR IGNORE INTO subscriptions
            (guild_id, user_id, game, item)
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
                f"🔔 تم تفعيل التنبيه عن **{item}** "
                f"في {GAME_NAMES[game.value]}."
            ),
            ephemeral=True
        )

    # ========================================================
    # /STOCK-ALERT-REMOVE
    # ========================================================

    @app_commands.command(
        name="stock-alert-remove",
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
        interaction: discord.Interaction,
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
    # /STOCK-ALERTS
    # ========================================================

    @app_commands.command(
        name="stock-alerts",
        description="عرض تنبيهاتك الشخصية"
    )
    async def stock_alerts(
        self,
        interaction: discord.Interaction
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

        if not rows:

            await interaction.response.send_message(
                "📭 ما عندك أي تنبيهات شخصية حاليًا.",
                ephemeral=True
            )

            return

        lines = []

        for row in rows:

            lines.append(
                f"• {GAME_NAMES.get(row['game'], row['game'])} — "
                f"**{row['item']}**"
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
    # /STEAL-ALERT
    # ========================================================

    @app_commands.command(
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
        interaction: discord.Interaction,
        alert: app_commands.Choice[str]
    ):

        role = await self.get_or_create_notification_role(
            interaction.guild,
            alert.value
        )

        if not role:

            await interaction.response.send_message(
                "❌ ما قدرت أنشئ رتبة الإشعار.",
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
                "❌ البوت لا يستطيع إعطاء هذه الرتبة.",
                ephemeral=True
            )

    # ========================================================
    # /STEAL-ALERT-REMOVE
    # ========================================================

    @app_commands.command(
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
        interaction: discord.Interaction,
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

            if role and role in interaction.user.roles:

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
    # /STOCK-STATUS
    # ========================================================

    @app_commands.command(
        name="stock-status",
        description="عرض حالة نظام الستوك"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def stock_status(
        self,
        interaction: discord.Interaction
    ):

        channels = get_shop_channels(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="📊 Team Fime Stock System",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="🌱 Grow a Garden API",
            value=(
                "🟢 Enabled"
                if GAG_API_URL
                else "🔴 Disabled"
            ),
            inline=True
        )

        embed.add_field(
            name="🍎 Blox Fruits API",
            value=(
                "🟢 Enabled"
                if BLOX_API_URL
                else "🔴 Not configured"
            ),
            inline=True
        )

        embed.add_field(
            name="⏱️ Check Interval",
            value=f"`{STOCK_CHECK_SECONDS}` seconds",
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
                    else "❌ No channel"
                ),
                inline=True
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # COMMAND ERROR HANDLER
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
                "❌ تحتاج صلاحية **Manage Server** "
                "لاستخدام هذا الأمر."
            )

        elif isinstance(
            error,
            app_commands.errors.CommandOnCooldown
        ):

            message = (
                "⏳ انتظر قليلًا ثم حاول مرة أخرى."
            )

        else:

            print(
                f"❌ bot6 command error: {error}"
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

async def setup(bot):

    await bot.add_cog(
        FimeStock(bot)
    )

    print(
        "✅ bot6.py loaded successfully."
    )