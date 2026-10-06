# ============================================================
# Team Fime — bot4.py (REFACTORED)
# Game Search System — Clean, Fast, Safe
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
import asyncio
import json
import difflib
import re
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import validators
import urllib.parse
import time
import aiohttp
import ipaddress

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
FALLBACK_IMAGE = None

intents = discord.Intents.default()
intents.message_content = True

# ============================================================
# CONFIGURATION
# ============================================================

SEARCH_ROOMS_FILE = "bot4_search_rooms.json"
SEARCH_HELP_ROOMS_FILE = "bot4_search_help_rooms.json"

AUTO_SEARCH_COOLDOWN = 2
AUTO_SEARCH_CACHE_TTL = 180
AUTO_SEARCH_MAX_RESULTS = 250
AUTO_SEARCH_PAGES_PER_SOURCE = 3
AUTO_SEARCH_PAGE_SIZE = 20

AUTO_SEARCH_TOTAL_TIMEOUT = 15.0
AUTO_SEARCH_CONNECT_TIMEOUT = 3.0
AUTO_SEARCH_READ_TIMEOUT = 10.0

AUTO_SEARCH_DIRECT = True

SEARCH_SOURCE_NAMES = {
    "scriptblox": "ScriptBlox",
    "robloxscripts": "RobloxScripts",
    "rscripts": "RScripts",
    "haxhell": "HaxHell",
    "roscripts": "RoScripts",
    "rbxscripts": "RBXScripts",
}

RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()
SEARCH_MAX_QUERIES_PER_SOURCE = 8
SEARCH_PAGES = tuple(range(1, AUTO_SEARCH_PAGES_PER_SOURCE + 1))

# ============================================================
# GLOBAL STATE (with locks for safety)
# ============================================================

_direct_search_tasks = set()
_search_cooldowns = {}
_auto_search_cache = {}
_auto_search_inflight = {}

_cache_lock = asyncio.Lock()
_cooldown_lock = asyncio.Lock()

search_rooms = {}
search_help_rooms = {}

# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def validate_channel_id(channel_id):
    """Safely validate channel ID."""
    try:
        cid = int(str(channel_id).strip())
        return cid if cid > 0 else None
    except (ValueError, TypeError):
        return None


def validate_username(username, max_len=100):
    """Safely validate username input."""
    if not isinstance(username, str):
        return None
    clean = username.strip()[:max_len]
    if not clean or len(clean) < 1:
        return None
    if not re.match(r'^[\w\-._@]+$', clean):
        return None
    return clean


def validate_game_name(game_name, max_len=200):
    """Safely validate game name input."""
    if not isinstance(game_name, str):
        return None
    clean = game_name.strip()[:max_len]
    if not clean or len(clean) < 1:
        return None
    return clean


def compact_game_name(query):
    """Normalize game name for cache key."""
    if not query:
        return ""
    text = str(query).lower().strip()
    text = re.sub(r'[^\w\s\-]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text[:150]


def _auto_cache_key(query, key_mode):
    """Generate cache key."""
    return f"{compact_game_name(query)}|{key_mode}"


def _copy_cached_scripts(scripts):
    """Deep copy scripts from cache to prevent modification."""
    if not scripts or not isinstance(scripts, list):
        return []
    return [dict(item) for item in scripts if isinstance(item, dict)]


# ============================================================
# FILE OPERATIONS (unified, safe)
# ============================================================

def load_json_file(filename, default=None):
    """
    Safely load JSON file with proper error handling.
    
    Args:
        filename: Path to JSON file
        default: Default value if file missing or invalid
    
    Returns:
        Loaded dict or default value
    """
    if default is None:
        default = {}
    
    try:
        if not os.path.exists(filename):
            return default
        
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if not isinstance(data, dict):
            return default
        
        return data
    
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error in {filename}: {e}")
        return default
    except IOError as e:
        print(f"❌ IO error reading {filename}: {e}")
        return default
    except Exception as e:
        print(f"❌ Unexpected error loading {filename}: {e}")
        return default


def save_json_file(filename, data, indent=2):
    """
    Safely save data to JSON file.
    
    Args:
        filename: Path to JSON file
        data: Dict to save
        indent: Indent level (2 or 4)
    
    Returns:
        True on success, False on failure
    """
    try:
        if not isinstance(data, dict):
            print(f"❌ Cannot save non-dict to {filename}")
            return False
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
        
        return True
    
    except IOError as e:
        print(f"❌ IO error writing {filename}: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error saving {filename}: {e}")
        return False


def init_files():
    """Load all JSON files on startup."""
    global search_rooms, search_help_rooms
    search_rooms = load_json_file(SEARCH_ROOMS_FILE, {})
    search_help_rooms = load_json_file(SEARCH_HELP_ROOMS_FILE, {})
    print(f"✅ Loaded {len(search_rooms)} search rooms")
    print(f"✅ Loaded {len(search_help_rooms)} help room configs")


# ============================================================
# CACHE FUNCTIONS (thread-safe)
# ============================================================

async def get_auto_cache(query, key_mode):
    """Retrieve scripts from cache if not expired."""
    async with _cache_lock:
        cache_key = _auto_cache_key(query, key_mode)
        item = _auto_search_cache.get(cache_key)
        
        if not item:
            return None
        
        if time.monotonic() - item.get("timestamp", 0) > AUTO_SEARCH_CACHE_TTL:
            _auto_search_cache.pop(cache_key, None)
            return None
        
        return _copy_cached_scripts(item.get("scripts", []))


async def set_auto_cache(query, key_mode, scripts):
    """Store scripts in cache with timestamp."""
    async with _cache_lock:
        cache_key = _auto_cache_key(query, key_mode)
        _auto_search_cache[cache_key] = {
            "timestamp": time.monotonic(),
            "scripts": _copy_cached_scripts(scripts),
        }
        
        # Cleanup expired entries
        now = time.monotonic()
        expired = [k for k, v in _auto_search_cache.items()
                   if now - v.get("timestamp", 0) > AUTO_SEARCH_CACHE_TTL * 2]
        
        for key in expired:
            _auto_search_cache.pop(key, None)
        
        # Hard cap to prevent memory leak
        if len(_auto_search_cache) > 500:
            _auto_search_cache.clear()


async def clear_auto_cache():
    """Force cache cleanup (for maintenance)."""
    async with _cache_lock:
        _auto_search_cache.clear()


# ============================================================
# NETWORK FUNCTIONS (async/aiohttp)
# ============================================================

async def fetch_json(url, timeout_secs=5, params=None):
    """
    Safely fetch JSON from URL using aiohttp.
    
    Args:
        url: Full URL or base URL
        timeout_secs: Request timeout
        params: Query parameters dict
    
    Returns:
        (data_dict, error_str) tuple
    """
    if not url:
        return None, "Empty URL"
    
    # Validate URL
    if not validators.url(url):
        return None, "Invalid URL format"
    
    timeout = aiohttp.ClientTimeout(
        total=timeout_secs,
        connect=AUTO_SEARCH_CONNECT_TIMEOUT,
        sock_read=AUTO_SEARCH_READ_TIMEOUT
    )
    
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params, ssl=False) as resp:
                if resp.status == 200:
                    return await resp.json(), None
                else:
                    return None, f"HTTP {resp.status}"
    
    except asyncio.TimeoutError:
        return None, "Request timeout"
    except aiohttp.ClientError as e:
        return None, f"Network error: {str(e)[:100]}"
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON response: {str(e)[:100]}"
    except Exception as e:
        return None, f"Unexpected error: {str(e)[:100]}"


# ============================================================
# SEARCH ROOM FUNCTIONS
# ============================================================

def get_configured_help_channel_ids(guild_id):
    """Get list of help channel IDs for guild."""
    value = search_help_rooms.get(str(guild_id), [])
    
    if isinstance(value, str):
        value = [value]
    
    if not isinstance(value, list):
        return []
    
    return [str(cid) for cid in value if validate_channel_id(cid)]


def set_search_room(guild_id, channel_id):
    """Set search room for guild."""
    guild_id = str(guild_id)
    channel_id = validate_channel_id(channel_id)
    
    if not channel_id:
        return False
    
    search_rooms[guild_id] = str(channel_id)
    return save_json_file(SEARCH_ROOMS_FILE, search_rooms)


def remove_search_room(guild_id):
    """Remove search room config for guild."""
    guild_id = str(guild_id)
    
    if guild_id in search_rooms:
        del search_rooms[guild_id]
        return save_json_file(SEARCH_ROOMS_FILE, search_rooms)
    
    return True


def get_search_room(guild_id):
    """Get search room channel ID for guild."""
    guild_id = str(guild_id)
    channel_id = search_rooms.get(guild_id)
    
    if not channel_id:
        return None
    
    validated = validate_channel_id(channel_id)
    return str(validated) if validated else None


def add_help_room(guild_id, channel_id):
    """Add help channel to guild config."""
    guild_id = str(guild_id)
    channel_id = validate_channel_id(channel_id)
    
    if not channel_id:
        return False
    
    if guild_id not in search_help_rooms:
        search_help_rooms[guild_id] = []
    
    channel_str = str(channel_id)
    
    if channel_str not in search_help_rooms[guild_id]:
        search_help_rooms[guild_id].append(channel_str)
    
    return save_json_file(SEARCH_HELP_ROOMS_FILE, search_help_rooms)


def remove_help_room(guild_id, channel_id):
    """Remove help channel from guild config."""
    guild_id = str(guild_id)
    channel_id = validate_channel_id(channel_id)
    
    if not channel_id or guild_id not in search_help_rooms:
        return False
    
    channel_str = str(channel_id)
    
    if channel_str in search_help_rooms[guild_id]:
        search_help_rooms[guild_id].remove(channel_str)
    
    return save_json_file(SEARCH_HELP_ROOMS_FILE, search_help_rooms)


# ============================================================
# DISCORD UI COMPONENTS
# ============================================================

class SearchHelpRoomSelect(discord.ui.Select):
    """Dropdown to select help room."""
    
    def __init__(self, guild, channel_ids):
        options = []
        
        for channel_id_str in channel_ids[:25]:
            channel_id = validate_channel_id(channel_id_str)
            
            if not channel_id:
                continue
            
            channel = guild.get_channel(channel_id)
            
            if channel and isinstance(channel, discord.TextChannel):
                options.append(
                    discord.SelectOption(
                        label=channel.name[:100],
                        value=str(channel.id),
                        emoji="📌",
                    )
                )
        
        super().__init__(
            placeholder="اختر الروم الذي تبي تتوجه له...",
            min_values=1,
            max_values=1,
            options=options[:25],
            disabled=len(options) == 0,
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            channel_id = validate_channel_id(self.values[0])
            channel = interaction.guild.get_channel(channel_id) if channel_id else None
        except Exception as e:
            print(f"❌ Error in SearchHelpRoomSelect callback: {e}")
            channel = None
        
        if not channel or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "❌ الروم المحفوظ لم يعد موجودًا.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            f"📍 توجه إلى {channel.mention}",
            ephemeral=True,
        )


class SearchHelpRoomsView(discord.ui.View):
    """View with help room selector."""
    
    def __init__(self, guild, channel_ids):
        super().__init__(timeout=120)
        
        valid_ids = []
        for channel_id_str in channel_ids[:25]:
            channel_id = validate_channel_id(channel_id_str)
            
            if not channel_id:
                continue
            
            channel = guild.get_channel(channel_id)
            
            if channel and isinstance(channel, discord.TextChannel):
                valid_ids.append(str(channel.id))
        
        if valid_ids:
            self.add_item(SearchHelpRoomSelect(guild, valid_ids))


class SearchHelpButtonView(discord.ui.View):
    """Button to open help room selector."""
    
    def __init__(self, guild, requester_id):
        super().__init__(timeout=120)
        self.guild_id = guild.id
        self.requester_id = requester_id
        
        button = discord.ui.Button(
            label="توجه إلى الرومات",
            emoji="📚",
            style=discord.ButtonStyle.primary,
        )
        button.callback = self.open_rooms
        self.add_item(button)
    
    async def open_rooms(self, interaction: discord.Interaction):
        ids = get_configured_help_channel_ids(self.guild_id)
        
        if not ids:
            await interaction.response.send_message(
                "ℹ️ المالك ما حدد رومات للتوجه لها حتى الآن.",
                ephemeral=True,
            )
            return
        
        view = SearchHelpRoomsView(interaction.guild, ids)
        
        if not view.children:
            await interaction.response.send_message(
                "⚠️ الرومات المحددة لم تعد موجودة.",
                ephemeral=True
            )
            return
        
        await interaction.response.send_message(
            "📚 **اختر الروم المناسب:**",
            view=view,
            ephemeral=True,
        )


# ============================================================
# BOT INSTANCE & SETUP
# ============================================================

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    """Bot startup event."""
    print(f"✅ Bot is ready as {bot.user}")
    print(f"📊 Latency: {bot.latency * 1000:.2f}ms")
    init_files()


# ============================================================
# EXAMPLE SLASH COMMANDS (minimal for demo)
# ============================================================

@bot.tree.command(name="ping", description="Bot latency")
async def slash_ping(interaction: discord.Interaction):
    """Simple ping command."""
    await interaction.response.defer()
    latency = bot.latency * 1000
    await interaction.followup.send(f"🏓 Pong! {latency:.2f}ms")


@bot.tree.command(name="set_search_room", description="Set search room for this guild")
@app_commands.describe(channel="The text channel for search")
async def slash_set_search_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    """Set search room configuration."""
    await interaction.response.defer(ephemeral=True)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ Need admin perms", ephemeral=True)
        return
    
    success = set_search_room(interaction.guild_id, channel.id)
    
    if success:
        await interaction.followup.send(
            f"✅ Search room set to {channel.mention}",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ Failed to save configuration",
            ephemeral=True
        )


@bot.tree.command(name="add_help_room", description="Add help room")
@app_commands.describe(channel="The help channel")
async def slash_add_help_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    """Add help channel to guild."""
    await interaction.response.defer(ephemeral=True)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ Need admin perms", ephemeral=True)
        return
    
    success = add_help_room(interaction.guild_id, channel.id)
    
    if success:
        await interaction.followup.send(
            f"✅ Help room added: {channel.mention}",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ Failed to save configuration",
            ephemeral=True
        )


@bot.tree.command(name="remove_help_room", description="Remove help room")
@app_commands.describe(channel="The help channel to remove")
async def slash_remove_help_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    """Remove help channel from guild."""
    await interaction.response.defer(ephemeral=True)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ Need admin perms", ephemeral=True)
        return
    
    success = remove_help_room(interaction.guild_id, channel.id)
    
    if success:
        await interaction.followup.send(
            f"✅ Help room removed: {channel.mention}",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ Failed to save configuration",
            ephemeral=True
        )


# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    if not TOKEN:
        print("❌ BOT_TOKEN not found in .env")
        sys.exit(1)
    
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"❌ Bot failed to start: {e}")
        sys.exit(1)