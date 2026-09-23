# ============================================================
# Team Fime — bot4.py
# Game Search System
# ============================================================

# Last Updated: 2026-02-10
# Version: 2.6

import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
import asyncio
import json
import difflib
import re
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import validators
import urllib.parse

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
FALLBACK_IMAGE = "https://c.tenor.com/jnINmQlMNbsAAAAC/tenor.gif"
intents = discord.Intents.default()
intents.message_content = True


# ============================================================
# AUTO SEARCH SETTINGS
# ============================================================

SEARCH_ROOMS_FILE = "bot4_search_rooms.json"

AUTO_SEARCH_COOLDOWN = 8

_search_cooldowns = {}


def load_search_rooms():
    try:
        if not os.path.exists(SEARCH_ROOMS_FILE):
            return {}

        with open(
            SEARCH_ROOMS_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


def save_search_rooms(data):
    try:
        with open(
            SEARCH_ROOMS_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4
            )

    except Exception as e:
        print(
            f"❌ Failed to save search rooms: {e}"
        )


search_rooms = load_search_rooms()


# ============================================================
# GAME ALIASES
# ============================================================

GAME_ALIASES = {

    "doors": [
        "doors",
        "door",
        "doors roblox",
        "دورز",
        "دور",
        "دورز روبلوكس",
        "دورز ماب",
        "الابواب",
        "الباب"
    ],

    "murder mystery 2": [
        "mm2",
        "mm 2",
        "murder mystery 2",
        "murder mystery",
        "murdermystery2",
        "murder mystery ii",
        "م م 2",
        "ام ام 2",
        "ام ام تو",
        "مردر مستري 2",
        "مردر ميستري 2",
        "مردر",
        "مرڈر",
        "ام ام"
    ],

    "blox fruits": [
        "blox fruits",
        "bloxfruit",
        "blox fruit",
        "bf",
        "بلوك فروت",
        "بلوك فروتس",
        "بلوكس فروت",
        "بلوكس فروتس",
        "بلوك فروتس روبلوكس"
    ],

    "grow a garden": [
        "grow a garden",
        "growagarden",
        "grow a garden roblox",
        "gag",
        "جرو جاردن",
        "قرو جاردن",
        "جرو اي قاردن",
        "جرو اغاردن",
        "جرو ا جاردن",
        "جرو جاردن روبلوكس"
    ],

    "steal a brainrot": [
        "steal a brainrot",
        "stealabrainrot",
        "brainrot",
        "steal brainrot",
        "ستيل برينروت",
        "ستيل اي برينروت",
        "ستيل برين روت",
        "برينروت"
    ],

    "arsenal": [
        "arsenal",
        "ارسنال",
        "ارسنل",
        "ارسنال روبلوكس"
    ],

    "adopt me": [
        "adopt me",
        "adoptme",
        "adopt",
        "ادوبت مي",
        "ادوبت",
        "ادوبت مي روبلوكس"
    ],

    "brookhaven": [
        "brookhaven",
        "brook haven",
        "بروك هافن",
        "بروكهافن",
        "بروك"
    ],

    "pet simulator 99": [
        "pet simulator 99",
        "pet sim 99",
        "petsim99",
        "ps99",
        "pet sim",
        "بت سيم 99",
        "بت سيم",
        "بيت سيم 99",
        "بتسيم"
    ],

    "the strongest battlegrounds": [
        "the strongest battlegrounds",
        "strongest battlegrounds",
        "tsb",
        "strongest",
        "ذا سترونقست باتل قراوند",
        "ذا سترونقست",
        "سترونقست",
        "سترونجست",
        "سترونقست باتل قراوند"
    ],

    "blade ball": [
        "blade ball",
        "bladeball",
        "blade",
        "بليد بول",
        "بليدبال",
        "بليد"
    ],

    "natural disaster survival": [
        "natural disaster survival",
        "natural disaster",
        "nds",
        "ناتشورال ديزاستر",
        "ناتشرال ديزاستر",
        "الكوارث الطبيعية"
    ],

    "tower of hell": [
        "tower of hell",
        "towerofhell",
        "toh",
        "تاور اوف هيل",
        "تاور اوف هل",
        "تاور"
    ],

    "piggy": [
        "piggy",
        "بيقي",
        "بيجي",
        "بقي"
    ],

    "rainbow friends": [
        "rainbow friends",
        "rainbowfriend",
        "راينبو فريندز",
        "رينبو فريندز",
        "راينبو"
    ],

    "evade": [
        "evade",
        "ايفيد",
        "إيفيد",
        "ايفيد روبلوكس"
    ],

    "bedwars": [
        "bedwars",
        "bed wars",
        "bedwar",
        "بد وورز",
        "بيد وورز",
        "بدورز"
    ],

    "pet simulator x": [
        "pet simulator x",
        "pet sim x",
        "petsimx",
        "psx",
        "بت سيم اكس",
        "بت سيم x"
    ],

    "jailbreak": [
        "jailbreak",
        "جايليبريك",
        "جيلبريك",
        "جلبريك"
    ],

    "shindo life": [
        "shindo life",
        "shindolife",
        "شيندو لايف",
        "شندو لايف",
        "شيندو"
    ],

    "anime defenders": [
        "anime defenders",
        "animedefenders",
        "anime defender",
        "انمي ديفندرز",
        "انمي دفندرز",
        "انمي ديفندرز"
    ],

    "anime adventures": [
        "anime adventures",
        "animeadventures",
        "انمي ادفنتشرز",
        "انمي ادفنشرز",
        "انمي ادفنشر"
    ],

    "fisch": [
        "fisch",
        "fish",
        "فيش",
        "فش",
        "فيش روبلوكس"
    ],

    "pet simulator": [
        "pet simulator",
        "pet sim",
        "بت سيم",
        "بيت سيم"
    ],

    "murder mystery": [
        "murder mystery",
        "murder mystery game",
        "مردر مستري",
        "مردر ميستري",
        "مردر"
    ]
}


def normalize_game_name(text):
    if not text:
        return ""

    text = str(text).lower().strip()

    text = re.sub(
        r"[\u064B-\u065F\u0670]",
        "",
        text
    )

    text = text.replace(
        "أ",
        "ا"
    ).replace(
        "إ",
        "ا"
    ).replace(
        "آ",
        "ا"
    )

    text = text.replace(
        "ة",
        "ه"
    )

    text = text.replace(
        "ى",
        "ي"
    )

    text = text.replace(
        "ؤ",
        "و"
    )

    text = text.replace(
        "ئ",
        "ي"
    )

    text = re.sub(
        r"[^a-z0-9\u0600-\u06FF]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


NORMALIZED_GAME_ALIASES = {}

for game_name, aliases in GAME_ALIASES.items():

    normalized_aliases = []

    for alias in aliases:
        normalized = normalize_game_name(
            alias
        )

        if normalized:
            normalized_aliases.append(
                normalized
            )

    normalized_game = normalize_game_name(
        game_name
    )

    normalized_aliases.append(
        normalized_game
    )

    NORMALIZED_GAME_ALIASES[
        normalized_game
    ] = list(
        set(normalized_aliases)
    )


def resolve_game_query(query):
    normalized_query = normalize_game_name(
        query
    )

    if not normalized_query:
        return query

    # تطابق مباشر
    for game_name, aliases in NORMALIZED_GAME_ALIASES.items():

        if normalized_query in aliases:
            return game_name

    # إذا كانت عبارة طويلة تحتوي اسم اللعبة
    for game_name, aliases in NORMALIZED_GAME_ALIASES.items():

        for alias in aliases:

            if len(alias) >= 4:

                if (
                    alias in normalized_query
                    or normalized_query in alias
                ):
                    return game_name

    # تصحيح الأخطاء الإملائية البسيطة
    all_aliases = []

    for aliases in NORMALIZED_GAME_ALIASES.values():
        all_aliases.extend(
            aliases
        )

    matches = difflib.get_close_matches(
        normalized_query,
        all_aliases,
        n=1,
        cutoff=0.72
    )

    if matches:

        matched_alias = matches[0]

        for game_name, aliases in NORMALIZED_GAME_ALIASES.items():

            if matched_alias in aliases:
                return game_name

    # البحث العادي إذا لم تكن اللعبة من القائمة
    return query


async def automatic_game_search(
    message,
    query
):
    resolved_query = resolve_game_query(
        query
    )

    # نستخدم ScriptBlox مباشرة في البحث التلقائي
    scripts, total_pages, error = fetch_scripts(
        "scriptblox",
        resolved_query,
        "free",
        1
    )

    if error:
        await message.channel.send(
            f"❌ ما لقيت نتائج لـ **{query}**."
        )
        return

    if not scripts:
        await message.channel.send(
            f"❌ ما لقيت نتائج لـ **{query}**."
        )
        return

    script = scripts[0]

    display_total = (
        total_pages
        if total_pages is not None
        else "Unknown"
    )

    embed = create_embed(
        script,
        1,
        display_total,
        "scriptblox"
    )

    post_url = (
        f"https://scriptblox.com/script/"
        f"{script.get('slug','')}"
    )

    raw_url = (
        f"https://rawscripts.net/raw/"
        f"{script.get('slug','')}"
    )

    download_url = (
        f"https://scriptblox.com/download/"
        f"{script.get('_id','')}"
    )

    view = discord.ui.View(
        timeout=60
    )

    view.add_item(
        discord.ui.Button(
            label="View",
            url=post_url,
            style=discord.ButtonStyle.link,
            row=1
        )
    )

    view.add_item(
        discord.ui.Button(
            label="Raw",
            url=raw_url,
            style=discord.ButtonStyle.link,
            row=1
        )
    )

    view.add_item(
        discord.ui.Button(
            label="Download",
            url=download_url,
            style=discord.ButtonStyle.link,
            row=1
        )
    )

    copy_button = discord.ui.Button(
        label="Copy",
        style=discord.ButtonStyle.primary,
        row=1
    )

    async def auto_copy_callback(
        btn_interaction
    ):
        content = script.get(
            "script",
            ""
        )

        await btn_interaction.response.send_message(
            f"```\n{content}\n```",
            ephemeral=True
        )

    copy_button.callback = (
        auto_copy_callback
    )

    view.add_item(
        copy_button
    )

    await message.channel.send(
        embed=embed,
        view=view
    )


class MyBot(commands.Bot):

    def __init__(
        self,
        *args,
        **kwargs
    ):
        super().__init__(
            *args,
            **kwargs
        )

        self.active_searches = {}

    async def setup_hook(self):
        await self.tree.sync()


bot = MyBot(
    command_prefix='!',
    intents=intents
)


@bot.event
async def on_ready():

    activity = discord.Game(
        name="Script Searcher | v3.0"
    )

    await bot.change_presence(
        activity=activity
    )

    print(
        f"Bot is ready 🤖 | "
        f"Serving in {len(bot.guilds)} servers"
    )

    print(
        "Commands: /search, /fetch, "
        "/trending, /script, /executors, "
        "/rscripts_*"
    )


# ============================================================
# AUTO SEARCH MESSAGE LISTENER
# ============================================================

async def automatic_search_listener(
    message
):

    if message.author.bot:
        return

    if not message.guild:
        return

    guild_id = str(
        message.guild.id
    )

    configured_channel = search_rooms.get(
        guild_id
    )

    if not configured_channel:
        return

    if str(message.channel.id) != str(
        configured_channel
    ):
        return

    query = message.content.strip()

    if not query:
        return

    # تجاهل الرسائل الطويلة
    if len(query) > 80:
        return

    # تجاهل الأوامر
    if query.startswith(
        "!"
    ) or query.startswith(
        "/"
    ):
        return

    cooldown_key = (
        f"{message.guild.id}:"
        f"{message.author.id}"
    )

    now = datetime.now(
        timezone.utc
    ).timestamp()

    last_search = _search_cooldowns.get(
        cooldown_key,
        0
    )

    if (
        now - last_search
        < AUTO_SEARCH_COOLDOWN
    ):
        return

    _search_cooldowns[
        cooldown_key
    ] = now

    async with message.channel.typing():

        try:
            await automatic_game_search(
                message,
                query
            )

        except Exception as e:

            print(
                "❌ Automatic search error: "
                f"{e}"
            )

            await message.channel.send(
                "❌ صار خطأ أثناء البحث، "
                "حاول مرة ثانية."
            )


# ============================================================
# GAME SEARCH FUNCTIONS
# ============================================================

def fetch_scripts(
    api,
    query,
    mode,
    page,
    **filters
):

    try:

        if api == "scriptblox":

            params = {
                "q": query,
                "mode": mode,
                "page": page
            }

            if filters.get(
                "verified"
            ) is not None:

                params["verified"] = (
                    1
                    if filters["verified"]
                    else 0
                )

            if filters.get(
                "patched"
            ) is not None:

                params["patched"] = (
                    1
                    if filters["patched"]
                    else 0
                )

            if filters.get(
                "key"
            ) is not None:

                params["key"] = (
                    1
                    if filters["key"]
                    else 0
                )

            if filters.get(
                "universal"
            ) is not None:

                params["universal"] = (
                    1
                    if filters["universal"]
                    else 0
                )

            if filters.get(
                "sortBy"
            ):

                params["sortBy"] = (
                    filters["sortBy"]
                )

            if filters.get(
                "order"
            ):

                params["order"] = (
                    filters["order"]
                )

            if filters.get(
                "strict"
            ) is not None:

                params["strict"] = (
                    "true"
                    if filters["strict"]
                    else "false"
                )

            if filters.get(
                "owner"
            ):

                params["owner"] = (
                    filters["owner"]
                )

            if filters.get(
                "placeId"
            ):

                params["placeId"] = (
                    filters["placeId"]
                )

            query_string = (
                urllib.parse.urlencode(
                    params
                )
            )

            url = (
                "https://scriptblox.com/"
                "api/script/search?"
                f"{query_string}"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if (
                "result" in data
                and "scripts" in data["result"]
            ):

                scripts = (
                    data["result"]["scripts"]
                )

                total_pages = (
                    data["result"].get(
                        "totalPages",
                        None
                    )
                )

                return (
                    scripts,
                    total_pages,
                    None
                )

            else:

                return (
                    None,
                    None,
                    f"Couldn't find any scripts "
                    f"matching '{query}'"
                )

        elif api == "rscripts":

            not_paid = (
                False
                if mode.lower() == "paid"
                else True
            )

            params = {
                "q": query,
                "page": page,
                "notPaid": not_paid
            }

            if filters.get(
                "noKeySystem"
            ) is not None:

                params["noKeySystem"] = (
                    filters["noKeySystem"]
                )

            if filters.get(
                "mobileOnly"
            ) is not None:

                params["mobileOnly"] = (
                    filters["mobileOnly"]
                )

            if filters.get(
                "verifiedOnly"
            ) is not None:

                params["verifiedOnly"] = (
                    filters["verifiedOnly"]
                )

            if filters.get(
                "unpatched"
            ) is not None:

                params["unpatched"] = (
                    filters["unpatched"]
                )

            if filters.get(
                "orderBy"
            ):

                params["orderBy"] = (
                    filters["orderBy"]
                )

            if filters.get(
                "sort"
            ):

                params["sort"] = (
                    filters["sort"]
                )

            query_string = (
                urllib.parse.urlencode(
                    params
                )
            )

            url = (
                "https://rscripts.net/"
                "api/v2/scripts?"
                f"{query_string}"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if "scripts" in data:

                scripts = data["scripts"]

                return (
                    scripts,
                    None,
                    None
                )

            else:

                return (
                    None,
                    None,
                    f"Couldn't find any scripts "
                    f"matching '{query}'"
                )

    except requests.RequestException as e:

        return (
            None,
            None,
            f"Something went wrong: {e}"
        )

    except KeyError as ke:

        return (
            None,
            None,
            f"Unexpected response format: {ke}"
        )


def fetch_scripts_from_api(
    api,
    endpoint,
    page=1,
    **params
):

    try:

        if api == "scriptblox":

            if page and page > 1:
                params["page"] = page

            query_string = (
                urllib.parse.urlencode(
                    params
                )
                if params
                else ""
            )

            url = (
                "https://scriptblox.com/"
                f"api/script/{endpoint}"
            )

            if query_string:
                url += (
                    f"?{query_string}"
                )

        elif api == "rscripts":

            if page and page > 1:
                params["page"] = page

            query_string = (
                urllib.parse.urlencode(
                    params
                )
                if params
                else ""
            )

            url = (
                "https://rscripts.net/"
                f"api/v2/{endpoint}"
            )

            if query_string:
                url += (
                    f"?{query_string}"
                )

        r = requests.get(
            url
        )

        r.raise_for_status()

        data = r.json()

        return (
            data,
            None
        )

    except requests.RequestException as e:

        return (
            None,
            f"Something went wrong: {e}"
        )

    except Exception as e:

        return (
            None,
            f"Unexpected response format: {e}"
        )


# ugly code right here yes
def fetch_trending(api):

    try:

        if api == "scriptblox":

            url = (
                "https://scriptblox.com/"
                "api/script/trending"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if (
                "result" in data
                and "scripts" in data["result"]
            ):

                trending_scripts = (
                    data["result"]["scripts"]
                )

                full_scripts = []

                for script_meta in trending_scripts:

                    slug = script_meta.get(
                        "slug"
                    )

                    if slug:

                        try:

                            script_url = (
                                "https://scriptblox.com/"
                                f"api/script/{slug}"
                            )

                            script_r = requests.get(
                                script_url
                            )

                            script_r.raise_for_status()

                            script_data = (
                                script_r.json()
                            )

                            if "script" in script_data:

                                full_scripts.append(
                                    script_data["script"]
                                )

                        except:
                            continue

                return (
                    full_scripts,
                    None
                )

            return (
                None,
                "Nothing trending right now"
            )

        elif api == "rscripts":

            url = (
                "https://rscripts.net/"
                "api/v2/trending"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if "success" in data:

                scripts = []

                for item in data["success"]:

                    script_data = item.get(
                        "script",
                        {}
                    )

                    if script_data:

                        script_data["views"] = (
                            item.get(
                                "views",
                                0
                            )
                        )

                        user_data = item.get(
                            "user",
                            {}
                        )

                        if user_data:

                            script_data["user"] = (
                                user_data
                            )

                        scripts.append(
                            script_data
                        )

                return (
                    scripts,
                    None
                )

            return (
                None,
                "Nothing is trending right now"
            )

    except requests.RequestException as e:

        return (
            None,
            f"bad: something went wrong: {e}"
        )

    except Exception as e:

        return (
            None,
            f"bad response = format broke "
            f"or something: {e}"
        )


def fetch_script_by_id(
    api,
    script_id
):

    try:

        if api == "scriptblox":

            url = (
                "https://scriptblox.com/"
                f"api/script/{script_id}"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if "script" in data:

                return (
                    data["script"],
                    None
                )

            return (
                None,
                f"Couldn't find script "
                f"'{script_id}'"
            )

        elif api == "rscripts":

            url = (
                "https://rscripts.net/"
                f"api/v2/script?id={script_id}"
            )

            r = requests.get(
                url
            )

            r.raise_for_status()

            data = r.json()

            if (
                "script" in data
                and len(data["script"]) > 0
            ):

                return (
                    data["script"][0],
                    None
                )

            return (
                None,
                f"Couldn't find script "
                f"'{script_id}'"
            )

    except requests.RequestException as e:

        return (
            None,
            f"Something went wrong: {e}"
        )

    except Exception as e:

        return (
            None,
            f"Unexpected response format: {e}"
        )


def fetch_executors():

    try:

        url = (
            "https://scriptblox.com/"
            "api/executor/list"
        )

        r = requests.get(
            url
        )

        r.raise_for_status()

        data = r.json()

        return (
            data,
            None
        )

    except requests.RequestException as e:

        return (
            None,
            f"bad = went wrong: {e}"
        )

    except Exception as e:

        return (
            None,
            f"something went wrong: "
            f"response format: {e}"
        )


def format_datetime(
    dt_str
):

    try:

        dt = datetime.strptime(
            dt_str,
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ).replace(
            tzinfo=timezone.utc
        )

    except ValueError:

        try:

            dt = datetime.strptime(
                dt_str,
                "%Y-%m-%dT%H:%M:%SZ"
            ).replace(
                tzinfo=timezone.utc
            )

        except ValueError:

            return "Unknown"

    now = datetime.now(
        timezone.utc
    )

    delta = relativedelta(
        now,
        dt
    )

    if delta.years > 0:

        ago = (
            f"{delta.years} years ago"
        )

    elif delta.months > 0:

        ago = (
            f"{delta.months} months ago"
        )

    elif delta.days > 0:

        ago = (
            f"{delta.days} days ago"
        )

    elif delta.hours > 0:

        ago = (
            f"{delta.hours} hours ago"
        )

    elif delta.minutes > 0:

        ago = (
            f"{delta.minutes} minutes ago"
        )

    else:

        ago = "just now"

    formatted = dt.strftime(
        "%m/%d/%Y | %I:%M:%S %p"
    )

    return (
        f"{ago} | {formatted}"
    )


def format_timestamps(
    script
):

    created = format_datetime(
        script.get(
            "createdAt",
            ""
        )
    )

    updated = format_datetime(
        script.get(
            "updatedAt",
            ""
        )
    )

    return (
        f"**Created At:** {created}\n"
        f"**Updated At:** {updated}"
    )


def create_embed(
    script,
    page,
    total_items,
    api
):

    embed = discord.Embed(
        color=0x206694
    )

    if api == "scriptblox":

        embed.title = (
            f"[SB] "
            f"{script.get('title', 'No Title')}"
        )

        game = script.get(
            "game",
            {}
        )

        game_name = game.get(
            "name",
            "Unknown Game"
        )

        game_id = game.get(
            "gameId",
            ""
        )

        if game_id:

            game_link = (
                f"https://www.roblox.com/"
                f"games/{game_id}"
            )

        else:

            game_link = (
                "https://www.roblox.com"
            )

        script_image = script.get(
            "image",
            FALLBACK_IMAGE
        )

        views = script.get(
            "views",
            0
        )

        script_type = (
            "Free"
            if script.get(
                "scriptType",
                "free"
            ).lower() == "free"
            else "Paid"
        )

        verified_status = (
            "✅ Verified"
            if script.get(
                "verified",
                False
            )
            else "❌ Not Verified"
        )

        key_status = (
            f"[Key Link]"
            f"({script.get('keyLink', '')})"
            if script.get(
                "key",
                False
            )
            else "✅ No Key"
        )

        patched_status = (
            "❌ Patched"
            if script.get(
                "isPatched",
                False
            )
            else "✅ Not Patched"
        )

        universal_status = (
            "🌐 Universal"
            if script.get(
                "isUniversal",
                False
            )
            else "Not Universal"
        )

        truncated_script = script.get(
            "script",
            "No Script"
        )

        if len(
            truncated_script
        ) > 400:

            truncated_script = (
                truncated_script[:397]
                + "..."
            )

        embed.add_field(
            name="Game",
            value=(
                f"[{game_name}]"
                f"({game_link})"
            ),
            inline=True
        )

        embed.add_field(
            name="Verified",
            value=verified_status,
            inline=True
        )

        embed.add_field(
            name="Type",
            value=script_type,
            inline=True
        )

        embed.add_field(
            name="Universal",
            value=universal_status,
            inline=True
        )

        embed.add_field(
            name="Views",
            value=f"👁️ {views}",
            inline=True
        )

        embed.add_field(
            name="Key",
            value=key_status,
            inline=True
        )

        embed.add_field(
            name="Patched",
            value=patched_status,
            inline=True
        )

        embed.add_field(
            name="Links",
            value=(
                f"[Raw Script]"
                f"(https://rawscripts.net/raw/"
                f"{script.get('slug','')}) - "
                f"[Script Page]"
                f"(https://scriptblox.com/script/"
                f"{script.get('slug','')})"
            ),
            inline=False
        )

        embed.add_field(
            name="Script",
            value=(
                f"```\n"
                f"{truncated_script}"
                f"\n```"
            ),
            inline=False
        )

        embed.add_field(
            name="Timestamps",
            value=format_timestamps(
                script
            ),
            inline=False
        )

        if validators.url(
            script_image
        ):

            embed.set_image(
                url=script_image
            )

        else:

            embed.set_image(
                url=FALLBACK_IMAGE
            )

    elif api == "rscripts":

        embed.title = (
            f"[RS] "
            f"{script.get('title', 'No Title')}"
        )

        views = script.get(
            "views",
            0
        )

        likes = script.get(
            "likes",
            0
        )

        dislikes = script.get(
            "dislikes",
            0
        )

        date_str = (
            script.get("lastUpdated")
            or script.get(
                "createdAt",
                ""
            )
        )

        date = format_datetime(
            date_str
        )

        mobile_ready = (
            "📱 Mobile Ready"
            if script.get(
                "mobileReady",
                False
            )
            else "🚫 Not Mobile Ready"
        )

        user = script.get(
            "user",
            {}
        )

        verified_status = (
            "✅ Verified"
            if user.get(
                "verified",
                False
            )
            else "❌ Not Verified"
        )

        paid_status = (
            "💲 Paid"
            if script.get(
                "paid",
                False
            )
            else "🆓 Free"
        )

        raw_script = script.get(
            "rawScript",
            ""
        )

        script_text = (
            f"```\n"
            f"loadstring(game:HttpGet(\""
            f"{raw_script}\"))()"
            f"\n```"
            if raw_script
            else "⚠️ No script content."
        )

        user_name = user.get(
            "username",
            "Unknown"
        )

        user_avatar_url = user.get(
            "image",
            FALLBACK_IMAGE
        )

        embed.add_field(
            name="Views",
            value=f"👁️ {views}",
            inline=True
        )

        embed.add_field(
            name="Likes",
            value=f"👍 {likes}",
            inline=True
        )

        embed.add_field(
            name="Dislikes",
            value=f"👎 {dislikes}",
            inline=True
        )

        embed.add_field(
            name="Mobile",
            value=mobile_ready,
            inline=True
        )

        embed.add_field(
            name="Verified",
            value=verified_status,
            inline=True
        )

        embed.add_field(
            name="Cost",
            value=paid_status,
            inline=True
        )

        embed.add_field(
            name="Script",
            value=script_text,
            inline=False
        )

        embed.add_field(
            name="Links",
            value=(
                f"[Script Page]"
                f"(https://rscripts.net/script/"
                f"{script.get('slug','')})"
            ),
            inline=False
        )

        embed.add_field(
            name="Date",
            value=date,
            inline=True
        )

        embed.set_author(
            name=user_name,
            icon_url=user_avatar_url
        )

        image_url = script.get(
            "image"
        )

        if validators.url(
            image_url
        ):

            embed.set_image(
                url=image_url
            )

        else:

            embed.set_image(
                url=FALLBACK_IMAGE
            )

    embed.set_footer(
        text=(
            f"Made by AdvanceFalling Team | "
            f"Powered by "
            f"{'ScriptBlox' if api == 'scriptblox' else 'RScripts'} | "
            f"Page {page}/{total_items}"
        )
    )

    return embed


async def display_scripts_dynamic(
    interaction,
    message,
    query,
    mode,
    api,
    **filters
):

    current_page = 1

    while True:

        scripts, total_pages, error = (
            fetch_scripts(
                api,
                query,
                mode,
                current_page,
                **filters
            )
        )

        if error:

            await interaction.followup.send(
                error
            )

            break

        if not scripts:

            await interaction.followup.send(
                "No scripts found."
            )

            break

        script = scripts[0]

        display_total = (
            total_pages
            if total_pages is not None
            else "Unknown"
        )

        embed = create_embed(
            script,
            current_page,
            display_total,
            api
        )

        view = discord.ui.View(
            timeout=60
        )

        if total_pages is None:

            if current_page > 1:

                view.add_item(
                    discord.ui.Button(
                        label="◀️",
                        style=discord.ButtonStyle.primary,
                        custom_id="previous",
                        row=0
                    )
                )

            view.add_item(
                discord.ui.Button(
                    label=(
                        f"Page "
                        f"{current_page}/?"
                    ),
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0
                )
            )

            view.add_item(
                discord.ui.Button(
                    label="▶️",
                    style=discord.ButtonStyle.primary,
                    custom_id="next",
                    row=0
                )
            )

        else:

            if current_page > 1:

                view.add_item(
                    discord.ui.Button(
                        label="⏪",
                        style=discord.ButtonStyle.primary,
                        custom_id="first",
                        row=0
                    )
                )

                view.add_item(
                    discord.ui.Button(
                        label="◀️",
                        style=discord.ButtonStyle.primary,
                        custom_id="previous",
                        row=0
                    )
                )

            view.add_item(
                discord.ui.Button(
                    label=(
                        f"Page "
                        f"{current_page}/"
                        f"{display_total}"
                    ),
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0
                )
            )

            if current_page < total_pages:

                view.add_item(
                    discord.ui.Button(
                        label="▶️",
                        style=discord.ButtonStyle.primary,
                        custom_id="next",
                        row=0
                    )
                )

                view.add_item(
                    discord.ui.Button(
                        label="⏩",
                        style=discord.ButtonStyle.primary,
                        custom_id="last",
                        row=0
                    )
                )

        if api == "scriptblox":

            post_url = (
                f"https://scriptblox.com/script/"
                f"{script.get('slug','')}"
            )

            raw_url = (
                f"https://rawscripts.net/raw/"
                f"{script.get('slug','')}"
            )

            download_url = (
                f"https://scriptblox.com/download/"
                f"{script.get('_id','')}"
            )

        else:

            post_url = (
                f"https://rscripts.net/script/"
                f"{script.get('slug','')}"
            )

            raw_url = script.get(
                "rawScript",
                ""
            )

            download_url = raw_url

        view.add_item(
            discord.ui.Button(
                label="View",
                url=post_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        view.add_item(
            discord.ui.Button(
                label="Raw",
                url=raw_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        view.add_item(
            discord.ui.Button(
                label="Download",
                url=download_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        copy_button = discord.ui.Button(
            label="Copy",
            style=discord.ButtonStyle.primary,
            row=1
        )

        async def copy_callback(
            btn_interaction
        ):

            if api == "scriptblox":

                content = script.get(
                    "script",
                    ""
                )

            else:

                raw_url_local = script.get(
                    "rawScript",
                    ""
                )

                content = (
                    f'loadstring(game:HttpGet('
                    f'"{raw_url_local}"))()'
                )

            await btn_interaction.response.send_message(
                f"```\n"
                f"{content}"
                f"\n```",
                ephemeral=True
            )

        copy_button.callback = (
            copy_callback
        )

        view.add_item(
            copy_button
        )

        await message.edit(
            embed=embed,
            view=view
        )

        def check(
            i: discord.Interaction
        ):

            return (
                i.user == interaction.user
                and i.message.id == message.id
            )

        try:

            i: discord.Interaction = (
                await bot.wait_for(
                    "interaction",
                    check=check,
                    timeout=30.0
                )
            )

            cid = i.data.get(
                "custom_id"
            )

            if (
                cid == "previous"
                and current_page > 1
            ):

                current_page -= 1

            elif (
                cid == "next"
                and (
                    total_pages is None
                    or current_page < total_pages
                )
            ):

                current_page += 1

            elif (
                cid == "last"
                and total_pages is not None
            ):

                current_page = total_pages

            elif cid == "first":

                current_page = 1

            await i.response.defer()

        except asyncio.TimeoutError:

            await message.edit(
                content="Interaction timed out.",
                view=None
            )

            break


async def display_scripts_local(
    interaction,
    message,
    scripts,
    api
):

    if not scripts:

        await interaction.followup.send(
            "No scripts found."
        )

        return

    scripts_per_page = 5
    page = 0

    total_pages = (
        (len(scripts) - 1)
        // scripts_per_page
        + 1
    )

    def create_multi_script_embed(
        page_num
    ):

        embed = discord.Embed(
            title=(
                f"{'📊 ScriptBlox' if api == 'scriptblox' else '📜 RScripts'} Scripts"
            ),
            description=(
                f"Showing {len(scripts)} "
                f"script"
                f"{'s' if len(scripts) != 1 else ''}"
            ),
            color=0x206694
        )

        start = (
            page_num
            * scripts_per_page
        )

        end = min(
            start + scripts_per_page,
            len(scripts)
        )

        for idx, script in enumerate(
            scripts[start:end],
            start=start + 1
        ):

            if api == "scriptblox":

                title = script.get(
                    "title",
                    "No Title"
                )

                game = script.get(
                    "game",
                    {}
                ).get(
                    "name",
                    "Unknown Game"
                )

                verified = (
                    "✅"
                    if script.get(
                        "verified",
                        False
                    )
                    else "❌"
                )

                patched = (
                    "❌"
                    if script.get(
                        "isPatched",
                        False
                    )
                    else "✅"
                )

                views = script.get(
                    "views",
                    0
                )

                slug = script.get(
                    "slug",
                    ""
                )

                value = (
                    f"**Game:** {game}\n"
                )

                value += (
                    f"**Verified:** "
                    f"{verified} | "
                    f"**Patched:** "
                    f"{patched}\n"
                )

                value += (
                    f"**Views:** 👁️ {views}\n"
                )

                value += (
                    f"[View]"
                    f"(https://scriptblox.com/"
                    f"script/{slug}) | "
                    f"[Raw]"
                    f"(https://rawscripts.net/"
                    f"raw/{slug})"
                )

                embed.add_field(
                    name=f"{idx}. {title}",
                    value=value,
                    inline=False
                )

            else:

                title = script.get(
                    "title",
                    "No Title"
                )

                views = script.get(
                    "views",
                    0
                )

                likes = script.get(
                    "likes",
                    0
                )

                verified = (
                    "✅"
                    if script.get(
                        "user",
                        {}
                    ).get(
                        "verified",
                        False
                    )
                    else "❌"
                )

                slug = script.get(
                    "slug",
                    ""
                )

                value = (
                    f"**Views:** 👁️ {views} | "
                    f"**Likes:** 👍 {likes}\n"
                )

                value += (
                    f"**Verified:** "
                    f"{verified}\n"
                )

                value += (
                    f"[View]"
                    f"(https://rscripts.net/"
                    f"script/{slug})"
                )

                embed.add_field(
                    name=f"{idx}. {title}",
                    value=value,
                    inline=False
                )

        embed.set_footer(
            text=(
                f"Made by AdvanceFalling Team | "
                f"Page {page_num + 1}/"
                f"{total_pages}"
            )
        )

        return embed

    while True:

        embed = create_multi_script_embed(
            page
        )

        view = discord.ui.View(
            timeout=60
        )

        if total_pages > 1:

            if page > 0:

                view.add_item(
                    discord.ui.Button(
                        label="⏪",
                        style=discord.ButtonStyle.primary,
                        custom_id="first",
                        row=0
                    )
                )

                view.add_item(
                    discord.ui.Button(
                        label="◀️",
                        style=discord.ButtonStyle.primary,
                        custom_id="previous",
                        row=0
                    )
                )

            view.add_item(
                discord.ui.Button(
                    label=(
                        f"Page "
                        f"{page + 1}/"
                        f"{total_pages}"
                    ),
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    row=0
                )
            )

            if page < total_pages - 1:

                view.add_item(
                    discord.ui.Button(
                        label="▶️",
                        style=discord.ButtonStyle.primary,
                        custom_id="next",
                        row=0
                    )
                )

                view.add_item(
                    discord.ui.Button(
                        label="⏩",
                        style=discord.ButtonStyle.primary,
                        custom_id="last",
                        row=0
                    )
                )

        await message.edit(
            embed=embed,
            view=view
        )

        def check(i):

            return (
                i.user == interaction.user
                and i.message.id == message.id
            )

        try:

            i = await bot.wait_for(
                "interaction",
                check=check,
                timeout=30.0
            )

            cid = i.data.get(
                "custom_id"
            )

            if (
                cid == "previous"
                and page > 0
            ):

                page -= 1

            elif (
                cid == "next"
                and page < total_pages - 1
            ):

                page += 1

            elif cid == "last":

                page = (
                    total_pages - 1
                )

            elif cid == "first":

                page = 0

            await i.response.defer()

        except asyncio.TimeoutError:

            await message.edit(
                content="Interaction timed out.",
                view=None
            )

            break


async def send_help(
    destination
):

    embed = discord.Embed(
        title="🔍 Script Searcher Bot",
        description=(
            "Search and browse scripts from "
            "ScriptBlox and RScripts"
        ),
        color=0x3498db
    )

    search_commands = (
        "**`/search <query>`** - "
        "Search scripts across both APIs\n"
        "├ `mode` - Free or paid scripts\n"
        "├ `verified` - Only verified scripts\n"
        "├ `patched` - Filter by patch status\n"
        "├ `key_system` - Filter key requirements\n"
        "├ `universal` - Universal scripts only\n"
        "├ `mobile_only` - Mobile compatible\n"
        "├ `sort_by` - Sort by views, likes, date\n"
        "└ `sort_order` - Ascending or descending\n\n"
        "**`/fetch`** - "
        "Browse ScriptBlox scripts\n"
        "├ All search filters plus:\n"
        "├ `owner` - Filter by creator\n"
        "├ `place_id` - Specific game ID\n"
        "└ `max_results` - Limit results (1-20)\n"
    )

    embed.add_field(
        name="Search & Browse",
        value=search_commands,
        inline=False
    )

    rscripts_commands = (
        "**`/rscripts_fetch`** - "
        "Browse RScripts library\n"
        "├ `verified_only` - Verified scripts\n"
        "├ `no_key_system` - "
        "No keys required\n"
        "├ `mobile_only` - "
        "Mobile ready\n"
        "├ `unpatched` - "
        "Unpatched scripts\n"
        "└ `order_by` - Sort options\n\n"
        "**`/rscripts_by_user <username>`** - "
        "Creator's scripts\n"
    )

    embed.add_field(
        name="RScripts Commands",
        value=rscripts_commands,
        inline=False
    )

    other_commands = (
        "**`/trending`** - Hot scripts right now\n"
        "**`/script <id>`** - Get specific script\n"
        "**`/executors`** - List all executors\n"
        "**`!search <query>`** - Legacy search\n"
    )

    embed.add_field(
        name="Other Commands",
        value=other_commands,
        inline=False
    )

    examples = (
        "• `/search arsenal verified:True`\n"
        "• `/rscripts_fetch no_key_system:True`\n"
        "• `/rscripts_by_user pcallskeleton`\n"
        "• `/trending api:scriptblox`\n"
    )

    embed.add_field(
        name="💡 Examples",
        value=examples,
        inline=False
    )

    embed.set_thumbnail(
        url=(
            "https://media1.tenor.com/m/"
            "j9Jhn5M1Xw0AAAAd/neuro-sama-ai.gif"
        )
    )

    embed.set_footer(
        text=(
            "Made by AdvanceFalling Team | v2.6"
        )
    )

    if isinstance(
        destination,
        discord.Interaction
    ):

        await destination.response.send_message(
            embed=embed,
            ephemeral=True
        )

    else:

        await destination.send(
            embed=embed
        )


@bot.command(
    name='bothelp'
)
async def prefix_help(
    ctx
):

    await send_help(
        ctx
    )


@bot.tree.command(
    name="bothelp",
    description="Display help information"
)
async def slash_help(
    interaction: discord.Interaction
):

    await send_help(
        interaction
    )


@bot.command(
    name='search'
)
async def prefix_search(
    ctx,
    query: str = None,
    mode: str = 'free'
):

    if query:

        await send_api_selection(
            ctx,
            query,
            mode
        )

    else:

        await send_help(
            ctx
        )


# ============================================================
# ARABIC SEARCH ROOM COMMANDS
# ============================================================

@bot.command(
    name="تحديد_روم"
)
@commands.has_permissions(
    manage_guild=True
)
async def set_search_room_arabic(
    ctx
):

    search_rooms[
        str(ctx.guild.id)
    ] = str(
        ctx.channel.id
    )

    save_search_rooms(
        search_rooms
    )

    await ctx.send(
        "✅ تم تحديد هذا الروم كروم البحث التلقائي.\n"
        "من الآن أي عضو يكتب اسم ماب هنا، "
        "البوت يبحث عنه تلقائيًا."
    )


@bot.command(
    name="روم_البحث"
)
async def show_search_room_arabic(
    ctx
):

    channel_id = search_rooms.get(
        str(ctx.guild.id)
    )

    if not channel_id:

        await ctx.send(
            "❌ ما تم تحديد روم للبحث التلقائي "
            "في هذا السيرفر."
        )

        return

    channel = ctx.guild.get_channel(
        int(channel_id)
    )

    if not channel:

        await ctx.send(
            "⚠️ روم البحث المحفوظ لم يعد موجودًا."
        )

        return

    await ctx.send(
        f"🔎 روم البحث التلقائي الحالي: "
        f"{channel.mention}"
    )


@bot.command(
    name="الغاء_روم_البحث"
)
@commands.has_permissions(
    manage_guild=True
)
async def remove_search_room_arabic(
    ctx
):

    guild_id = str(
        ctx.guild.id
    )

    if guild_id in search_rooms:

        del search_rooms[
            guild_id
        ]

        save_search_rooms(
            search_rooms
        )

        await ctx.send(
            "✅ تم إلغاء روم البحث التلقائي."
        )

    else:

        await ctx.send(
            "ℹ️ ما فيه روم بحث محدد أصلًا."
        )


# ============================================================
# SLASH SEARCH ROOM COMMAND
# ============================================================

@bot.tree.command(
    name="setscriptroom",
    description="تحديد روم البحث التلقائي"
)
@app_commands.describe(
    channel="الروم الذي سيتم فيه البحث التلقائي"
)
@app_commands.checks.has_permissions(
    manage_guild=True
)
async def slash_set_search_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    search_rooms[
        str(interaction.guild.id)
    ] = str(
        channel.id
    )

    save_search_rooms(
        search_rooms
    )

    await interaction.response.send_message(
        f"✅ تم تحديد {channel.mention} "
        f"كروم البحث التلقائي.\n"
        f"اكتب اسم الماب فيه بالعربي أو الإنجليزي "
        f"والبوت يبحث عنه تلقائيًا."
    )


@bot.tree.command(
    name="searchroom",
    description="عرض روم البحث التلقائي"
)
async def slash_show_search_room(
    interaction: discord.Interaction
):

    channel_id = search_rooms.get(
        str(interaction.guild.id)
    )

    if not channel_id:

        await interaction.response.send_message(
            "❌ ما تم تحديد روم للبحث التلقائي."
        )

        return

    channel = interaction.guild.get_channel(
        int(channel_id)
    )

    if not channel:

        await interaction.response.send_message(
            "⚠️ روم البحث المحفوظ لم يعد موجودًا."
        )

        return

    await interaction.response.send_message(
        f"🔎 روم البحث التلقائي الحالي: "
        f"{channel.mention}"
    )


class APISelect(
    discord.ui.Select
):

    def __init__(
        self,
        query,
        mode,
        filters=None
    ):

        self.query = query
        self.mode = mode
        self.filters = filters or {}

        options = [

            discord.SelectOption(
                label="ScriptBlox",
                value="scriptblox",
                description=(
                    "Search scripts from "
                    "ScriptBlox API"
                )
            ),

            discord.SelectOption(
                label="Rscripts",
                value="rscripts",
                description=(
                    "Search scripts from "
                    "RScripts API"
                )
            ),
        ]

        super().__init__(
            placeholder=(
                "Choose the API to search scripts..."
            ),
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        if self.values[0] == "scriptblox":

            await interaction.followup.send(
                "Searching ScriptBlox API..."
            )

            temp_msg = (
                await interaction.followup.send(
                    "Fetching data...",
                    ephemeral=True
                )
            )

            await display_scripts_dynamic(
                interaction,
                temp_msg,
                self.query,
                self.mode,
                api="scriptblox",
                **self.filters
            )

        elif self.values[0] == "rscripts":

            await interaction.followup.send(
                "Searching RScripts API..."
            )

            temp_msg = (
                await interaction.followup.send(
                    "Fetching data...",
                    ephemeral=True
                )
            )

            scripts, _, error = fetch_scripts(
                "rscripts",
                self.query,
                self.mode,
                1,
                **self.filters
            )

            if error:

                await interaction.followup.send(
                    error
                )

                return

            await display_scripts_local(
                interaction,
                temp_msg,
                scripts,
                api="rscripts"
            )


class APISearchView(
    discord.ui.View
):

    def __init__(
        self,
        query,
        mode,
        filters=None
    ):

        super().__init__(
            timeout=60
        )

        self.add_item(
            APISelect(
                query,
                mode,
                filters
            )
        )


async def send_api_selection(
    destination,
    query,
    mode
):

    if isinstance(
        destination,
        discord.Interaction
    ):

        await destination.response.send_message(
            "Select the API to search scripts from:",
            view=APISearchView(
                query,
                mode
            )
        )

    else:

        await destination.send(
            "Select the API to search scripts from:",
            view=APISearchView(
                query,
                mode
            )
        )


@bot.tree.command(
    name="search",
    description="Search for scripts with advanced filters"
)
@app_commands.describe(
    query="The search query",
    mode="Search mode (free or paid)",
    verified="Filter by verified status",
    patched="Filter by patched status (ScriptBlox only)",
    key_system="Filter by key system requirement",
    universal="Filter by universal scripts (ScriptBlox only)",
    mobile_only="Mobile ready scripts only (RScripts only)",
    sort_by="Sort by field (views, likes, date, etc.)",
    sort_order="Sort order (asc or desc)"
)
async def slash_search(
    interaction: discord.Interaction,
    query: str,
    mode: str = 'free',
    verified: bool = None,
    patched: bool = None,
    key_system: bool = None,
    universal: bool = None,
    mobile_only: bool = None,
    sort_by: str = None,
    sort_order: str = None
):

    filters = {}

    if verified is not None:

        filters["verified"] = verified
        filters["verifiedOnly"] = verified

    if patched is not None:

        filters["patched"] = patched

    if key_system is not None:

        filters["key"] = key_system
        filters["noKeySystem"] = (
            not key_system
        )

    if universal is not None:

        filters["universal"] = universal

    if mobile_only is not None:

        filters["mobileOnly"] = mobile_only

    if sort_by:

        filters["sortBy"] = sort_by
        filters["orderBy"] = sort_by

    if sort_order:

        filters["order"] = sort_order
        filters["sort"] = sort_order

    await interaction.response.send_message(
        "Select the API to search scripts from:",
        view=APISearchView(
            query,
            mode,
            filters
        )
    )


@bot.tree.command(
    name="fetch",
    description="Fetch scripts from ScriptBlox with advanced filters"
)
@app_commands.describe(
    mode="Script mode (free or paid)",
    verified="Filter by verified status",
    patched="Filter by patched status",
    key_system="Filter by key system",
    universal="Filter universal scripts",
    sort_by="Sort by (views, likeCount, createdAt, updatedAt, dislikeCount)",
    sort_order="Sort order (asc or desc)",
    owner="Filter by owner username",
    place_id="Filter by game place ID",
    max_results="Maximum results per page (1-20)"
)
async def slash_fetch(
    interaction: discord.Interaction,
    mode: str = 'free',
    verified: bool = None,
    patched: bool = None,
    key_system: bool = None,
    universal: bool = None,
    sort_by: str = None,
    sort_order: str = None,
    owner: str = None,
    place_id: str = None,
    max_results: int = 20
):

    await interaction.response.defer()

    params = {
        "mode": mode,
        "max": max_results
    }

    if verified is not None:

        params["verified"] = (
            1
            if verified
            else 0
        )

    if patched is not None:

        params["patched"] = (
            1
            if patched
            else 0
        )

    if key_system is not None:

        params["key"] = (
            1
            if key_system
            else 0
        )

    if universal is not None:

        params["universal"] = (
            1
            if universal
            else 0
        )

    if sort_by:

        params["sortBy"] = sort_by

    if sort_order:

        params["order"] = sort_order

    if owner:

        params["owner"] = owner

    if place_id:

        params["placeId"] = place_id

    data, error = fetch_scripts_from_api(
        "scriptblox",
        "fetch",
        **params
    )

    if error:

        await interaction.followup.send(
            f"❌ {error}"
        )

        return

    if (
        "result" in data
        and "scripts" in data["result"]
    ):

        scripts = (
            data["result"]["scripts"]
        )

        if not scripts:

            await interaction.followup.send(
                "No scripts found with "
                "the specified filters."
            )

            return

        temp_msg = (
            await interaction.followup.send(
                "Fetching data..."
            )
        )

        await display_scripts_local(
            interaction,
            temp_msg,
            scripts,
            api="scriptblox"
        )

    else:

        await interaction.followup.send(
            "No scripts found."
        )


@bot.tree.command(
    name="trending",
    description="View trending scripts"
)
@app_commands.describe(
    api="Choose API (scriptblox or rscripts)"
)
async def slash_trending(
    interaction: discord.Interaction,
    api: str = "scriptblox"
):

    await interaction.response.defer()

    if api.lower() not in [
        "scriptblox",
        "rscripts"
    ]:

        await interaction.followup.send(
            "❌ Invalid API. "
            "Choose 'scriptblox' or 'rscripts'."
        )

        return

    scripts, error = fetch_trending(
        api.lower()
    )

    if error:

        await interaction.followup.send(
            f"❌ {error}"
        )

        return

    if not scripts:

        await interaction.followup.send(
            "No trending scripts found."
        )

        return

    temp_msg = (
        await interaction.followup.send(
            "Fetching trending scripts..."
        )
    )

    await display_scripts_local(
        interaction,
        temp_msg,
        scripts,
        api=api.lower()
    )


@bot.tree.command(
    name="script",
    description="Fetch a specific script by ID or slug"
)
@app_commands.describe(
    script_id="The script ID or slug",
    api="Choose API (scriptblox or rscripts)"
)
async def slash_script(
    interaction: discord.Interaction,
    script_id: str,
    api: str = "scriptblox"
):

    await interaction.response.defer()

    if api.lower() not in [
        "scriptblox",
        "rscripts"
    ]:

        await interaction.followup.send(
            "❌ Invalid API. "
            "Choose 'scriptblox' or 'rscripts'."
        )

        return

    script, error = fetch_script_by_id(
        api.lower(),
        script_id
    )

    if error:

        await interaction.followup.send(
            f"❌ {error}"
        )

        return

    if not script:

        await interaction.followup.send(
            "Script not found."
        )

        return

    temp_msg = (
        await interaction.followup.send(
            "Fetching script..."
        )
    )

    await display_scripts_local(
        interaction,
        temp_msg,
        [script],
        api=api.lower()
    )


@bot.tree.command(
    name="executors",
    description="View list of available executors"
)
async def slash_executors(
    interaction: discord.Interaction
):

    await interaction.response.defer()

    executors, error = fetch_executors()

    if error:

        await interaction.followup.send(
            f"❌ {error}"
        )

        return

    if (
        not executors
        or not isinstance(
            executors,
            list
        )
    ):

        await interaction.followup.send(
            "No executors found."
        )

        return

    page = 0
    per_page = 5

    total_pages = (
        (len(executors) - 1)
        // per_page
        + 1
    )

    def create_executor_embed(
        page_num
    ):

        embed = discord.Embed(
            title="🎮 Available Executors",
            description=(
                f"List of executors from "
                f"ScriptBlox "
                f"(Page "
                f"{page_num + 1}/"
                f"{total_pages})"
            ),
            color=0x206694
        )

        start = (
            page_num
            * per_page
        )

        end = min(
            start + per_page,
            len(executors)
        )

        for executor in executors[start:end]:

            name = executor.get(
                "name",
                "Unknown"
            )

            platform = executor.get(
                "platform",
                "Unknown"
            )

            exe_type = executor.get(
                "type",
                "Unknown"
            )

            patched = (
                "❌ Patched"
                if executor.get(
                    "patched",
                    False
                )
                else "✅ Active"
            )

            version = executor.get(
                "version",
                "N/A"
            )

            value = (
                f"**Platform:** {platform}\n"
                f"**Type:** {exe_type}\n"
                f"**Status:** {patched}\n"
                f"**Version:** {version}"
            )

            if executor.get(
                "website"
            ):

                value += (
                    f"\n[Website]"
                    f"({executor['website']})"
                )

            if executor.get(
                "discord"
            ):

                value += (
                    f" | [Discord]"
                    f"({executor['discord']})"
                )

            embed.add_field(
                name=name,
                value=value,
                inline=False
            )

        embed.set_footer(
            text=(
                "Made by AdvanceFalling Team | "
                "Powered by ScriptBlox"
            )
        )

        return embed

    embed = create_executor_embed(
        page
    )

    view = discord.ui.View(
        timeout=60
    )

    if total_pages > 1:

        if page > 0:

            view.add_item(
                discord.ui.Button(
                    label="⏪",
                    style=discord.ButtonStyle.primary,
                    custom_id="first"
                )
            )

            view.add_item(
                discord.ui.Button(
                    label="◀️",
                    style=discord.ButtonStyle.primary,
                    custom_id="previous"
                )
            )

        view.add_item(
            discord.ui.Button(
                label=(
                    f"Page "
                    f"{page + 1}/"
                    f"{total_pages}"
                ),
                style=discord.ButtonStyle.secondary,
                disabled=True
            )
        )

        if page < total_pages - 1:

            view.add_item(
                discord.ui.Button(
                    label="▶️",
                    style=discord.ButtonStyle.primary,
                    custom_id="next"
                )
            )

            view.add_item(
                discord.ui.Button(
                    label="⏩",
                    style=discord.ButtonStyle.primary,
                    custom_id="last"
                )
            )

    message = (
        await interaction.followup.send(
            embed=embed,
            view=view
        )
    )

    while True:

        def check(i):

            return (
                i.user == interaction.user
                and i.message.id == message.id
            )

        try:

            i = await bot.wait_for(
                "interaction",
                check=check,
                timeout=30.0
            )

            cid = i.data.get(
                "custom_id"
            )

            if (
                cid == "previous"
                and page > 0
            ):

                page -= 1

            elif (
                cid == "next"
                and page < total_pages - 1
            ):

                page += 1

            elif cid == "last":

                page = (
                    total_pages - 1
                )

            elif cid == "first":

                page = 0

            embed = create_executor_embed(
                page
            )

            view = discord.ui.View(
                timeout=60
            )

            if total_pages > 1:

                if page > 0:

                    view.add_item(
                        discord.ui.Button(
                            label="⏪",
                            style=discord.ButtonStyle.primary,
                            custom_id="first"
                        )
                    )

                    view.add_item(
                        discord.ui.Button(
                            label="◀️",
                            style=discord.ButtonStyle.primary,
                            custom_id="previous"
                        )
                    )

                view.add_item(
                    discord.ui.Button(
                        label=(
                            f"Page "
                            f"{page + 1}/"
                            f"{total_pages}"
                        ),
                        style=discord.ButtonStyle.secondary,
                        disabled=True
                    )
                )

                if page < total_pages - 1:

                    view.add_item(
                        discord.ui.Button(
                            label="▶️",
                            style=discord.ButtonStyle.primary,
                            custom_id="next"
                        )
                    )

                    view.add_item(
                        discord.ui.Button(
                            label="⏩",
                            style=discord.ButtonStyle.primary,
                            custom_id="last"
                        )
                    )

            await i.response.edit_message(
                embed=embed,
                view=view
            )

        except asyncio.TimeoutError:

            await message.edit(
                content="Interaction timed out.",
                view=None
            )

            break


def fetch_rscripts_by_username(
    username,
    page=1
):

    try:

        url = (
            f"https://rscripts.net/"
            f"api/v2/scripts"
            f"?page={page}"
            f"&orderBy=date"
            f"&sort=desc"
        )

        headers = {
            "Username": username
        }

        r = requests.get(
            url,
            headers=headers
        )

        r.raise_for_status()

        data = r.json()

        if "scripts" in data:

            return (
                data["scripts"],
                None
            )

        return (
            None,
            f"No scripts found for "
            f"'{username}'"
        )

    except requests.RequestException as e:

        return (
            None,
            f"Something went wrong: {e}"
        )

    except Exception as e:

        return (
            None,
            f"Unexpected response format: {e}"
        )


@bot.tree.command(
    name="rscripts_fetch",
    description="Browse RScripts with advanced filters"
)
@app_commands.describe(
    verified_only="Show only verified scripts",
    no_key_system="Show only scripts without key systems",
    mobile_only="Show only mobile-ready scripts",
    unpatched="Show only unpatched scripts",
    order_by="Sort by field (createdAt, updatedAt, views, name)",
    sort="Sort direction (asc or desc)",
    max_results="Maximum results per page (1-20)"
)
async def slash_rscripts_fetch(
    interaction: discord.Interaction,
    verified_only: bool = None,
    no_key_system: bool = None,
    mobile_only: bool = None,
    unpatched: bool = None,
    order_by: str = None,
    sort: str = None,
    max_results: int = 20
):

    await interaction.response.defer()

    params = {
        "q": "",
        "page": 1,
        "notPaid": True
    }

    if verified_only is not None:

        params["verifiedOnly"] = (
            verified_only
        )

    if no_key_system is not None:

        params["noKeySystem"] = (
            no_key_system
        )

    if mobile_only is not None:

        params["mobileOnly"] = (
            mobile_only
        )

    if unpatched is not None:

        params["unpatched"] = (
            unpatched
        )

    if order_by:

        params["orderBy"] = (
            order_by
        )

    if sort:

        params["sort"] = sort

    query_string = (
        urllib.parse.urlencode(
            params
        )
    )

    url = (
        f"https://rscripts.net/"
        f"api/v2/scripts?"
        f"{query_string}"
    )

    try:

        r = requests.get(
            url
        )

        r.raise_for_status()

        data = r.json()

        if "scripts" in data:

            scripts = (
                data["scripts"][
                    :max_results
                ]
            )

            if not scripts:

                await interaction.followup.send(
                    "No scripts found with "
                    "those filters"
                )

                return

            temp_msg = (
                await interaction.followup.send(
                    "Loading scripts..."
                )
            )

            await display_scripts_local(
                interaction,
                temp_msg,
                scripts,
                api="rscripts"
            )

        else:

            await interaction.followup.send(
                "No scripts found"
            )

    except Exception as e:

        await interaction.followup.send(
            f"❌ Something went wrong: {e}"
        )


@bot.tree.command(
    name="rscripts_by_user",
    description=(
        "Find all scripts by a "
        "specific RScripts creator"
    )
)
@app_commands.describe(
    username="The creator's username"
)
async def slash_rscripts_by_user(
    interaction: discord.Interaction,
    username: str
):

    await interaction.response.defer()

    scripts, error = (
        fetch_rscripts_by_username(
            username
        )
    )

    if error:

        await interaction.followup.send(
            f"❌ {error}"
        )

        return

    if not scripts:

        await interaction.followup.send(
            f"No scripts found for "
            f"'{username}'"
        )

        return

    temp_msg = (
        await interaction.followup.send(
            f"Loading scripts by "
            f"{username}..."
        )
    )

    await display_scripts_local(
        interaction,
        temp_msg,
        scripts,
        api="rscripts"
    )


# ============================================================
# EXTENSION SETUP
# ============================================================

# ============================================================
# EXTENSION SETUP
# ============================================================

_extension_bot = bot


async def setup(main_bot):

    global bot

    # استخدام البوت الرئيسي الموجود في bot.py
    bot = main_bot

    # --------------------------------------------------------
    # نقل أوامر Prefix إلى البوت الرئيسي
    # --------------------------------------------------------

        # --------------------------------------------------------
    # نقل أوامر Prefix إلى البوت الرئيسي
    # --------------------------------------------------------

    extension_commands = list(
        _extension_bot.commands
    )

    for command in extension_commands:

        # إذا كان نفس الأمر موجودًا في البوت الرئيسي،
        # نتأكد من عدم وجود تعارض قبل تسجيله.
        existing = main_bot.get_command(
            command.name
        )

        if existing is not None:

            print(
                f"⚠️ Prefix command already exists: "
                f"!{command.name} — skipped."
            )

            continue

        try:

            main_bot.add_command(
                command
            )

            print(
                f"✅ Registered prefix command: "
                f"!{command.name}"
            )

        except commands.CommandRegistrationError as e:

            print(
                f"⚠️ Prefix command conflict "
                f"!{command.name}: {e}"
            )

        except Exception as e:

            print(
                f"❌ Failed to register prefix command "
                f"!{command.name}: {e}"
            )

    # --------------------------------------------------------
    # نقل أوامر Slash
    # --------------------------------------------------------

    extension_slash_commands = list(
        _extension_bot.tree.get_commands()
    )

    for command in extension_slash_commands:

        try:

            existing = (
                main_bot.tree.get_command(
                    command.name
                )
            )

            if existing is not None:

                main_bot.tree.remove_command(
                    command.name
                )

            main_bot.tree.add_command(
                command
            )

            print(
                f"✅ Registered slash command: "
                f"/{command.name}"
            )

        except Exception as e:

            print(
                f"❌ Failed to register slash command "
                f"/{command.name}: {e}"
            )

    # --------------------------------------------------------
    # Listener: on_ready
    # --------------------------------------------------------

    main_bot.add_listener(
        on_ready,
        "on_ready"
    )

    # --------------------------------------------------------
    # Listener: automatic search
    # --------------------------------------------------------

    main_bot.add_listener(
        automatic_search_listener,
        "on_message"
    )

    # --------------------------------------------------------
    # مزامنة Slash Commands
    # --------------------------------------------------------

    try:

        synced = await main_bot.tree.sync()

        print(
            f"✅ bot4.py synced "
            f"{len(synced)} slash commands."
        )

    except Exception as e:

        print(
            f"❌ bot4.py slash command sync failed: "
            f"{e}"
        )

    # --------------------------------------------------------
    # تأكيد أوامر الغرف العربية
    # --------------------------------------------------------

    arabic_commands = [
        "تحديد_روم",
        "روم_البحث",
        "الغاء_روم_البحث"
    ]

    for command_name in arabic_commands:

        if main_bot.get_command(
            command_name
        ) is not None:

            print(
                f"🇸🇦 Arabic command ready: "
                f"!{command_name}"
            )

        else:

            print(
                f"❌ Arabic command missing: "
                f"!{command_name}"
            )