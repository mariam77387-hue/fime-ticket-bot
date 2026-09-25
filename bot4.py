# ============================================================
# Team Fime — bot4.py
# Game Search System
# ============================================================

# Last Updated: 2026-09-25
# Version: 3.0

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

# وقت الانتظار بين بحثين لنفس العضو
AUTO_SEARCH_COOLDOWN = 8

# مدة حفظ نتائج البحث في الذاكرة
AUTO_SEARCH_CACHE_TTL = 45

# الحد الأقصى للنتائج التي نحتفظ بها للبحث التلقائي
AUTO_SEARCH_MAX_RESULTS = 30

# مهلة طلب API
AUTO_SEARCH_REQUEST_TIMEOUT = 12

_search_cooldowns = {}

# ============================================================
# AUTO SEARCH CACHE
# ============================================================

_auto_search_cache = {}

_auto_search_inflight = {}

_auto_search_cache_lock = asyncio.Lock()


def _auto_cache_key(
    query,
    key_mode
):

    normalized = compact_game_name(
        query
    )

    return (
        f"{normalized}|{key_mode}"
    )


async def get_auto_cache(
    query,
    key_mode
):

    cache_key = _auto_cache_key(
        query,
        key_mode
    )

    async with _auto_search_cache_lock:

        item = _auto_search_cache.get(
            cache_key
        )

        if not item:
            return None

        timestamp = item.get(
            "timestamp",
            0
        )

        now = datetime.now(
            timezone.utc
        ).timestamp()

        if (
            now - timestamp
            > AUTO_SEARCH_CACHE_TTL
        ):

            _auto_search_cache.pop(
                cache_key,
                None
            )

            return None

        return list(
            item.get(
                "scripts",
                []
            )
        )


async def set_auto_cache(
    query,
    key_mode,
    scripts
):

    cache_key = _auto_cache_key(
        query,
        key_mode
    )

    async with _auto_search_cache_lock:

        _auto_search_cache[
            cache_key
        ] = {
            "timestamp": (
                datetime.now(
                    timezone.utc
                ).timestamp()
            ),
            "scripts": list(
                scripts
            )
        }

        # تنظيف الكاش القديم
        if len(
            _auto_search_cache
        ) > 150:

            now = datetime.now(
                timezone.utc
            ).timestamp()

            old_keys = []

            for key, item in (
                _auto_search_cache.items()
            ):

                if (
                    now
                    - item.get(
                        "timestamp",
                        0
                    )
                    > AUTO_SEARCH_CACHE_TTL
                ):

                    old_keys.append(
                        key
                    )

            for key in old_keys:

                _auto_search_cache.pop(
                    key,
                    None
                )


# ============================================================
# SEARCH ROOMS
# ============================================================

def load_search_rooms():

    try:

        if not os.path.exists(
            SEARCH_ROOMS_FILE
        ):

            return {}

        with open(
            SEARCH_ROOMS_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(
                f
            )

        return (
            data
            if isinstance(
                data,
                dict
            )
            else {}
        )

    except Exception:

        return {}


def save_search_rooms(
    data
):

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


# ============================================================
# SMART GAME NAME NORMALIZATION
# ============================================================

def normalize_game_name(
    text
):

    if not text:
        return ""

    text = str(
        text
    ).lower().strip()

    text = re.sub(
        r"[\u064B-\u065F\u0670]",
        "",
        text
    )

    text = (
        text
        .replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ـ", "")
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

    stripped_words = []

    for word in text.split():

        if (
            len(word) > 4
            and word.startswith("ال")
        ):

            stripped_words.append(
                word[2:]
            )

        else:

            stripped_words.append(
                word
            )

    return " ".join(
        stripped_words
    )


def compact_game_name(
    text
):

    normalized = normalize_game_name(
        text
    )

    normalized = re.sub(
        r"(.)\1{1,}",
        r"\1",
        normalized
    )

    return normalized.replace(
        " ",
        ""
    )


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
        dict.fromkeys(
            normalized_aliases
        )
    )


def get_close_game_suggestions(
    query,
    limit=3
):

    compact_query = compact_game_name(
        query
    )

    if len(
        compact_query
    ) < 3:

        return []

    matches = []

    for game_name, aliases in (
        NORMALIZED_GAME_ALIASES.items()
    ):

        best_score = 0.0

        for alias in aliases:

            compact_alias = compact_game_name(
                alias
            )

            if len(
                compact_alias
            ) < 3:

                continue

            score = difflib.SequenceMatcher(
                None,
                compact_query,
                compact_alias
            ).ratio()

            if (
                compact_query[:3]
                == compact_alias[:3]
            ):

                score += 0.08

            best_score = max(
                best_score,
                score
            )

        if best_score >= 0.48:

            matches.append(
                (
                    best_score,
                    game_name
                )
            )

    matches.sort(
        reverse=True
    )

    output = []

    for _, game_name in matches:

        if game_name not in output:

            output.append(
                game_name
            )

        if len(
            output
        ) >= limit:

            break

    return output


def resolve_game_query(
    query
):

    normalized_query = normalize_game_name(
        query
    )

    if not normalized_query:

        return query

    compact_query = compact_game_name(
        query
    )

    # ========================================================
    # 1. تطابق مباشر
    # ========================================================

    for game_name, aliases in (
        NORMALIZED_GAME_ALIASES.items()
    ):

        if normalized_query in aliases:

            return game_name

    # ========================================================
    # 2. تطابق بدون مسافات
    # ========================================================

    for game_name, aliases in (
        NORMALIZED_GAME_ALIASES.items()
    ):

        for alias in aliases:

            compact_alias = compact_game_name(
                alias
            )

            if (
                compact_query
                == compact_alias
            ):

                return game_name

    # ========================================================
    # 3. احتواء الاسم
    # ========================================================

    for game_name, aliases in (
        NORMALIZED_GAME_ALIASES.items()
    ):

        for alias in aliases:

            if len(alias) < 4:

                continue

            compact_alias = compact_game_name(
                alias
            )

            if (
                alias in normalized_query
                or normalized_query in alias
                or compact_alias in compact_query
                or compact_query in compact_alias
            ):

                return game_name

    # ========================================================
    # 4. البحث الذكي بالأخطاء الإملائية
    # ========================================================

    if len(
        compact_query
    ) >= 3:

        best_match = None
        best_score = 0.0

        for game_name, aliases in (
            NORMALIZED_GAME_ALIASES.items()
        ):

            for alias in aliases:

                compact_alias = compact_game_name(
                    alias
                )

                if len(
                    compact_alias
                ) < 3:

                    continue

                score = difflib.SequenceMatcher(
                    None,
                    compact_query,
                    compact_alias
                ).ratio()

                if (
                    len(compact_query) >= 4
                    and len(compact_alias) >= 4
                    and compact_query[:3]
                    == compact_alias[:3]
                ):

                    score += 0.08

                length_difference = abs(
                    len(compact_query)
                    - len(compact_alias)
                )

                if length_difference <= 2:

                    score += 0.03

                if score > best_score:

                    best_score = score
                    best_match = game_name

        if len(
            compact_query
        ) <= 4:

            threshold = 0.82

        elif len(
            compact_query
        ) <= 6:

            threshold = 0.68

        else:

            threshold = 0.58

        if (
            best_match
            and best_score >= threshold
        ):

            return best_match

    # ========================================================
    # 5. مطابقة الكلمات
    # ========================================================

    query_words = set(
        normalized_query.split()
    )

    if query_words:

        best_game = None
        best_score = 0.0

        for game_name, aliases in (
            NORMALIZED_GAME_ALIASES.items()
        ):

            for alias in aliases:

                alias_words = set(
                    alias.split()
                )

                if not alias_words:

                    continue

                overlap = (
                    len(
                        query_words
                        & alias_words
                    )
                    / max(
                        len(
                            query_words
                            | alias_words
                        ),
                        1
                    )
                )

                partial = 0.0

                for word in query_words:

                    for alias_word in alias_words:

                        if (
                            len(word) >= 3
                            and len(alias_word) >= 3
                        ):

                            partial = max(
                                partial,
                                difflib.SequenceMatcher(
                                    None,
                                    word,
                                    alias_word
                                ).ratio()
                            )

                score = (
                    overlap * 0.55
                ) + (
                    partial * 0.45
                )

                if score > best_score:

                    best_score = score
                    best_game = game_name

        if (
            best_game
            and best_score >= 0.55
        ):

            return best_game

    return query


def get_game_search_queries(
    query
):

    resolved = resolve_game_query(
        query
    )

    queries = []

    def add_query(
        value
    ):

        if not value:

            return

        normalized = normalize_game_name(
            value
        )

        if not normalized:

            return

        for existing in queries:

            if (
                normalize_game_name(
                    existing
                )
                == normalized
            ):

                return

        queries.append(
            value
        )

    add_query(
        resolved
    )

    add_query(
        query
    )

    # ========================================================
    # إضافة صيغ بحث إضافية عند الحاجة
    # ========================================================

    if len(
        queries
    ) < 3:

        suggestions = (
            get_close_game_suggestions(
                query,
                limit=3
            )
        )

        for suggestion in suggestions:

            add_query(
                suggestion
            )

            if len(
                queries
            ) >= 3:

                break

    return queries[:3]


# ============================================================
# AUTO SEARCH API WORKER
# ============================================================

async def fetch_auto_search_mode(
    search_query,
    key_mode
):

    """
    key_mode:
        no_key
        with_key
    """

    cache = await get_auto_cache(
        search_query,
        key_mode
    )

    if cache is not None:

        return (
            cache,
            False,
            True
        )

    cache_key = _auto_cache_key(
        search_query,
        key_mode
    )

    # ========================================================
    # منع تكرار نفس الطلب إذا مستخدمان بحثوا بنفس اللحظة
    # ========================================================

    existing_task = (
        _auto_search_inflight.get(
            cache_key
        )
    )

    if existing_task:

        try:

            result = await existing_task

            return (
                list(result),
                False,
                True
            )

        except Exception:

            pass

    async def worker():

        collected = []
        seen = set()

        had_network_error = False

        search_queries = [
            search_query
        ]

        # نستخدم صيغ إضافية فقط عند الحاجة
        extra_queries = (
            get_game_search_queries(
                search_query
            )
        )

        for item in extra_queries:

            if normalize_game_name(
                item
            ) not in [
                normalize_game_name(
                    existing
                )
                for existing in search_queries
            ]:

                search_queries.append(
                    item
                )

        # ====================================================
        # نبحث في أول صيغتين بالتوازي
        # ====================================================

        async def search_one_query(
            current_query
        ):

            local_results = []
            local_error = False

            async def fetch_page(
                page
            ):

                return await asyncio.to_thread(
                    fetch_scripts,
                    "scriptblox",
                    current_query,
                    "free",
                    page,
                    key=(
                        0
                        if key_mode == "no_key"
                        else 1
                    )
                )

            tasks = [
                asyncio.create_task(
                    fetch_page(
                        1
                    )
                ),
                asyncio.create_task(
                    fetch_page(
                        2
                    )
                )
            ]

            results = await asyncio.gather(
                *tasks,
                return_exceptions=True
            )

            for result in results:

                if isinstance(
                    result,
                    Exception
                ):

                    local_error = True
                    continue

                scripts, _, error = result

                if error:

                    error_text = str(
                        error
                    ).lower()

                    if (
                        "something went wrong"
                        in error_text
                        or "unexpected response"
                        in error_text
                        or "timeout"
                        in error_text
                        or "connection"
                        in error_text
                        or "http"
                        in error_text
                    ):

                        local_error = True

                    continue

                if not scripts:

                    continue

                local_results.extend(
                    scripts
                )

            return (
                local_results,
                local_error
            )

        query_tasks = []

        for current_query in (
            search_queries[:2]
        ):

            query_tasks.append(
                asyncio.create_task(
                    search_one_query(
                        current_query
                    )
                )
            )

        query_results = await asyncio.gather(
            *query_tasks,
            return_exceptions=True
        )

        for result in query_results:

            if isinstance(
                result,
                Exception
            ):

                had_network_error = True
                continue

            scripts, network_error = result

            if network_error:

                had_network_error = True

            for script in scripts:

                script_key = (
                    script.get("_id")
                    or script.get("slug")
                    or script.get("title")
                )

                if not script_key:

                    script_key = (
                        str(
                            script
                        )
                    )

                if script_key in seen:

                    continue

                seen.add(
                    script_key
                )

                collected.append(
                    script
                )

                if len(
                    collected
                ) >= AUTO_SEARCH_MAX_RESULTS:

                    break

            if len(
                collected
            ) >= AUTO_SEARCH_MAX_RESULTS:

                break

        # ====================================================
        # ترتيب النتائج
        # ====================================================

        def result_score(
            script
        ):

            score = 0.0

            title = normalize_game_name(
                script.get(
                    "title",
                    ""
                )
            )

            game = script.get(
                "game",
                {}
            )

            if isinstance(
                game,
                dict
            ):

                game_name = normalize_game_name(
                    game.get(
                        "name",
                        ""
                    )
                )

            else:

                game_name = ""

            target = normalize_game_name(
                search_query
            )

            if target:

                if title == target:

                    score += 100

                elif game_name == target:

                    score += 95

                elif target in title:

                    score += 70

                elif target in game_name:

                    score += 65

                else:

                    title_score = (
                        difflib.SequenceMatcher(
                            None,
                            compact_game_name(
                                target
                            ),
                            compact_game_name(
                                title
                            )
                        ).ratio()
                    )

                    game_score = (
                        difflib.SequenceMatcher(
                            None,
                            compact_game_name(
                                target
                            ),
                            compact_game_name(
                                game_name
                            )
                        ).ratio()
                    )

                    score += max(
                        title_score,
                        game_score
                    ) * 40

            try:

                score += min(
                    float(
                        script.get(
                            "views",
                            0
                        ) or 0
                    ) / 10000,
                    15
                )

            except Exception:

                pass

            if script.get(
                "verified",
                False
            ):

                score += 5

            return score

        collected.sort(
            key=result_score,
            reverse=True
        )

        await set_auto_cache(
            search_query,
            key_mode,
            collected
        )

        return (
            collected,
            had_network_error
        )

    task = asyncio.create_task(
        worker()
    )

    _auto_search_inflight[
        cache_key
    ] = task

    try:

        scripts, network_error = (
            await task
        )

        return (
            scripts,
            network_error,
            False
        )

    finally:

        if (
            _auto_search_inflight.get(
                cache_key
            )
            is task
        ):

            _auto_search_inflight.pop(
                cache_key,
                None
            )


# ============================================================
# AUTO SEARCH KEY SELECT
# ============================================================

class AutoSearchKeySelect(
    discord.ui.Select
):

    def __init__(
        self,
        requester_id,
        query,
        resolved_query
    ):

        self.requester_id = requester_id
        self.query = query
        self.resolved_query = resolved_query

        options = [

            discord.SelectOption(
                label="بدون مفتاح",
                value="no_key",
                description=(
                    "سكربتات لا تحتاج مفتاح تفعيل"
                ),
                emoji="🔓"
            ),

            discord.SelectOption(
                label="بمفتاح",
                value="with_key",
                description=(
                    "سكربتات تحتاج مفتاح تفعيل"
                ),
                emoji="🔑"
            ),

            discord.SelectOption(
                label="جميعهم",
                value="all",
                description=(
                    "البحث عن السكربتات بدون مفتاح وبمفتاح"
                ),
                emoji="🌐"
            )
        ]

        super().__init__(
            placeholder=(
                "🔐 اختر نوع السكربت..."
            ),
            min_values=1,
            max_values=2,
            options=options,
            row=0
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        selected = list(
            self.values
        )

        # ====================================================
        # جميعهم = النوعين
        # ====================================================

        if "all" in selected:

            selected_modes = [
                "no_key",
                "with_key"
            ]

        else:

            selected_modes = [
                value
                for value in selected
                if value in [
                    "no_key",
                    "with_key"
                ]
            ]

        if not selected_modes:

            selected_modes = [
                "no_key",
                "with_key"
            ]

        labels = []

        if "no_key" in selected_modes:

            labels.append(
                "🔓 بدون مفتاح"
            )

        if "with_key" in selected_modes:

            labels.append(
                "🔑 بمفتاح"
            )

        label = " + ".join(
            labels
        )

        self.disabled = True

        self.placeholder = (
            f"🔐 {label}"
        )

        searching_content = (
            f"⏳ **جاري البحث الآن...**\n"
            f"🎮 الماب: **{self.query}**\n"
            f"🔐 النوع: **{label}**\n\n"
            f"جاري البحث بشكل متزامن عن أفضل النتائج..."
        )

        try:

            await interaction.response.edit_message(
                content=searching_content,
                embed=None,
                view=self.view
            )

        except Exception as e:

            print(
                f"❌ Key select immediate edit error: {e}"
            )

            try:

                await interaction.response.defer()

                await interaction.edit_original_response(
                    content=searching_content,
                    embed=None,
                    view=self.view
                )

            except Exception as fallback_error:

                print(
                    "❌ Key select fallback error: "
                    f"{fallback_error}"
                )

                return

        # ====================================================
        # تشغيل النوعين بشكل متزامن
        # ====================================================

        tasks = [
            asyncio.create_task(
                fetch_auto_search_mode(
                    self.resolved_query,
                    mode
                )
            )
            for mode in selected_modes
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

        collected = []
        seen = set()
        had_network_error = False
        had_successful_result = False

        for result in results:

            if isinstance(
                result,
                Exception
            ):

                print(
                    f"❌ Auto search task error: {result}"
                )

                had_network_error = True
                continue

            scripts, network_error, _ = result

            if network_error:

                had_network_error = True

            if scripts:

                had_successful_result = True

            for script in scripts:

                script_key = (
                    script.get("_id")
                    or script.get("slug")
                    or script.get("title")
                )

                if not script_key:

                    script_key = str(
                        script
                    )

                if script_key in seen:

                    continue

                seen.add(
                    script_key
                )

                # نحفظ نوع المفتاح داخل النتيجة
                if (
                    "no_key" in selected_modes
                    and "with_key" in selected_modes
                ):

                    script["_fime_key_source"] = (
                        "بمفتاح"
                        if script.get(
                            "key",
                            False
                        )
                        else "بدون مفتاح"
                    )

                elif "no_key" in selected_modes:

                    script["_fime_key_source"] = (
                        "بدون مفتاح"
                    )

                else:

                    script["_fime_key_source"] = (
                        "بمفتاح"
                    )

                collected.append(
                    script
                )

        # ====================================================
        # إذا لم نجد نتيجة، محاولة بحث أوسع
        # ====================================================

        if not collected:

            fallback_queries = (
                get_game_search_queries(
                    self.query
                )
            )

            fallback_tasks = []

            for fallback_query in fallback_queries:

                if normalize_game_name(
                    fallback_query
                ) == normalize_game_name(
                    self.resolved_query
                ):

                    continue

                for mode in selected_modes:

                    fallback_tasks.append(
                        asyncio.create_task(
                            fetch_auto_search_mode(
                                fallback_query,
                                mode
                            )
                        )
                    )

            if fallback_tasks:

                fallback_results = (
                    await asyncio.gather(
                        *fallback_tasks,
                        return_exceptions=True
                    )
                )

                for result in fallback_results:

                    if isinstance(
                        result,
                        Exception
                    ):

                        had_network_error = True
                        continue

                    scripts, network_error, _ = result

                    if network_error:

                        had_network_error = True

                    if scripts:

                        had_successful_result = True

                    for script in scripts:

                        script_key = (
                            script.get("_id")
                            or script.get("slug")
                            or script.get("title")
                        )

                        if not script_key:

                            script_key = str(
                                script
                            )

                        if script_key in seen:

                            continue

                        seen.add(
                            script_key
                        )

                        if (
                            "no_key"
                            in selected_modes
                            and
                            "with_key"
                            in selected_modes
                        ):

                            script[
                                "_fime_key_source"
                            ] = (
                                "بمفتاح"
                                if script.get(
                                    "key",
                                    False
                                )
                                else "بدون مفتاح"
                            )

                        elif "no_key" in selected_modes:

                            script[
                                "_fime_key_source"
                            ] = "بدون مفتاح"

                        else:

                            script[
                                "_fime_key_source"
                            ] = "بمفتاح"

                        collected.append(
                            script
                        )

        # ====================================================
        # عرض النتيجة
        # ====================================================

        try:

            if not collected:

                suggestions = (
                    get_close_game_suggestions(
                        self.query,
                        limit=3
                    )
                )

                if (
                    had_network_error
                    and not had_successful_result
                ):

                    await interaction.edit_original_response(
                        content=(
                            "⚠️ **تعذر الوصول لمصدر البحث حاليًا.**\n"
                            "جرّب مرة ثانية بعد قليل."
                        ),
                        embed=None,
                        view=None
                    )

                else:

                    suggestion_text = ""

                    if suggestions:

                        suggestion_text = (
                            "\n\n💡 **هل تقصد:** "
                            + " • ".join(
                                f"`{item}`"
                                for item in suggestions
                            )
                        )

                    await interaction.edit_original_response(
                        content=(
                            f"❌ **ما لقيت أي سكربت** "
                            f"للماب **{self.query}**.\n"
                            f"🔐 البحث: **{label}**"
                            f"{suggestion_text}"
                        ),
                        embed=None,
                        view=None
                    )

                return

            result_view = (
                AutoSearchResultBrowseView(
                    self.requester_id,
                    collected,
                    self.query,
                    selected_modes
                )
            )

            embed = (
                result_view.build_embed()
            )

            await interaction.edit_original_response(
                content=(
                    f"✅ لقيت **{len(collected)}** نتيجة "
                    f"لـ **{self.query}**\n"
                    f"🔐 النوع: **{label}**"
                ),
                embed=embed,
                view=result_view
            )

        except Exception as e:

            import traceback

            print(
                f"❌ Key select result-edit error: {e}"
            )

            traceback.print_exc()

            try:

                await interaction.followup.send(
                    "❌ صار خطأ أثناء عرض النتيجة، حاول تبحث مرة ثانية.",
                    ephemeral=True
                )

            except Exception:
                pass


# ============================================================
# AUTO SEARCH KEY VIEW
# ============================================================

class AutoSearchKeyView(
    discord.ui.View
):

    def __init__(
        self,
        requester,
        query,
        resolved_query
    ):

        super().__init__(
            timeout=60
        )

        self.requester_id = requester.id

        self.add_item(
            AutoSearchKeySelect(
                requester.id,
                query,
                resolved_query
            )
        )

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):

        if (
            interaction.user.id
            != self.requester_id
        ):

            await interaction.response.send_message(
                "⚠️ هذي الخيارات للشخص اللي طلب البحث فقط.",
                ephemeral=True
            )

            return False

        return True

    async def on_timeout(
        self
    ):

        for item in self.children:

            item.disabled = True


# ============================================================
# AUTO SEARCH RESULT BROWSER
# ============================================================

class AutoSearchResultBrowseView(
    discord.ui.View
):

    def __init__(
        self,
        requester_id,
        scripts,
        query,
        selected_modes
    ):

        super().__init__(
            timeout=180
        )

        self.requester_id = requester_id
        self.scripts = scripts
        self.query = query
        self.selected_modes = selected_modes
        self.index = 0

        self.refresh_buttons()

    async def interaction_check(
        self,
        interaction: discord.Interaction
    ):

        if (
            interaction.user.id
            != self.requester_id
        ):

            await interaction.response.send_message(
                "⚠️ أزرار النتائج للشخص اللي طلب البحث فقط.",
                ephemeral=True
            )

            return False

        return True

    def refresh_buttons(
        self
    ):

        self.clear_items()

        previous = discord.ui.Button(
            label="◀️",
            style=discord.ButtonStyle.primary,
            disabled=(
                self.index <= 0
            ),
            row=0
        )

        previous.callback = (
            self.previous_callback
        )

        self.add_item(
            previous
        )

        position = discord.ui.Button(
            label=(
                f"{self.index + 1}/"
                f"{len(self.scripts)}"
            ),
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0
        )

        self.add_item(
            position
        )

        nxt = discord.ui.Button(
            label="▶️",
            style=discord.ButtonStyle.primary,
            disabled=(
                self.index
                >= len(self.scripts) - 1
            ),
            row=0
        )

        nxt.callback = (
            self.next_callback
        )

        self.add_item(
            nxt
        )

        script = self.scripts[
            self.index
        ]

        post_url = (
            "https://scriptblox.com/script/"
            f"{script.get('slug','')}"
        )

        raw_url = (
            "https://rawscripts.net/raw/"
            f"{script.get('slug','')}"
        )

        download_url = (
            "https://scriptblox.com/download/"
            f"{script.get('_id','')}"
        )

        self.add_item(
            discord.ui.Button(
                label="View",
                url=post_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Raw",
                url=raw_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        self.add_item(
            discord.ui.Button(
                label="Download",
                url=download_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        copy_button = discord.ui.Button(
            label="Copy",
            style=discord.ButtonStyle.success,
            row=1
        )

        copy_button.callback = (
            self.copy_callback
        )

        self.add_item(
            copy_button
        )

    def build_embed(
        self
    ):

        script = self.scripts[
            self.index
        ]

        return create_embed(
            script,
            self.index + 1,
            len(self.scripts),
            "scriptblox"
        )

    async def previous_callback(
        self,
        interaction: discord.Interaction
    ):

        if self.index <= 0:

            return await interaction.response.defer()

        self.index -= 1

        self.refresh_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    async def next_callback(
        self,
        interaction: discord.Interaction
    ):

        if (
            self.index
            >= len(self.scripts) - 1
        ):

            return await interaction.response.defer()

        self.index += 1

        self.refresh_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self
        )

    async def copy_callback(
        self,
        interaction: discord.Interaction
    ):

        script = self.scripts[
            self.index
        ]

        content = str(
            script.get(
                "script",
                ""
            )
            or ""
        ).strip()

        if not content:

            await interaction.response.send_message(
                "❌ ما فيه كود لهذا السكربت.",
                ephemeral=True
            )

            return

        if len(
            content
        ) <= 1990:

            await interaction.response.send_message(
                content,
                ephemeral=True,
                allowed_mentions=(
                    discord.AllowedMentions.none()
                )
            )

        else:

            import io

            file = discord.File(
                io.BytesIO(
                    content.encode(
                        "utf-8"
                    )
                ),
                filename="script.lua"
            )

            await interaction.response.send_message(
                "📜 الكود طويل، هذا ملف السكربت:",
                file=file,
                ephemeral=True
            )

    async def on_timeout(
        self
    ):

        self.clear_items()


# ============================================================
# AUTOMATIC GAME SEARCH
# ============================================================

async def automatic_game_search(
    message,
    query
):

    resolved_query = (
        resolve_game_query(
            query
        )
    )

    view = AutoSearchKeyView(
        message.author,
        query,
        resolved_query
    )

    recognized_text = ""

    normalized_original = (
        normalize_game_name(
            query
        )
    )

    normalized_resolved = (
        normalize_game_name(
            resolved_query
        )
    )

    if (
        normalized_resolved
        and normalized_original
        and normalized_resolved
        != normalized_original
    ):

        recognized_text = (
            f"\n🎯 فهمت أنك تقصد: "
            f"**{resolved_query}**"
        )

    await message.channel.send(
        content=(
            f"🔎 **تم استلام طلب البحث عن {query}**"
            f"{recognized_text}\n"
            "🔐 اختر نوع السكربت اللي تبيه من القائمة:"
        ),
        view=view
    )


# ============================================================
# BOT
# ============================================================

class MyBot(
    commands.Bot
):

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

    async def setup_hook(
        self
    ):

        pass


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

    configured_channel = (
        search_rooms.get(
            guild_id
        )
    )

    if not configured_channel:

        return

    if (
        str(message.channel.id)
        != str(configured_channel)
    ):

        return

    query = message.content.strip()

    if not query:

        return

    if len(query) > 80:

        return

    if (
        query.startswith("!")
        or query.startswith("/")
    ):

        return

    cooldown_key = (
        f"{message.guild.id}:"
        f"{message.author.id}"
    )

    now = datetime.now(
        timezone.utc
    ).timestamp()

    last_search = (
        _search_cooldowns.get(
            cooldown_key,
            0
        )
    )

    if (
        now - last_search
        < AUTO_SEARCH_COOLDOWN
    ):

        return

    _search_cooldowns[
        cooldown_key
    ] = now

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
                    if filters["key"] == 1
                    or filters["key"] is True
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
                url,
                timeout=AUTO_SEARCH_REQUEST_TIMEOUT
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
                url,
                timeout=AUTO_SEARCH_REQUEST_TIMEOUT
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


# ============================================================
# باقي نظام البحث الأساسي كما هو
# ============================================================

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


def fetch_trending(
    api
):

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

        source_type = script.get(
            "_fime_key_source"
        )

        if source_type:

            embed.add_field(
                name="🔐 البحث",
                value=source_type,
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
                    f"**Verified:** "
                    f"{verified} | "
                    f"**Patched:** "
                    f"{patched}\n"
                    f"**Views:** 👁️ {views}\n"
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
                    f"**Verified:** "
                    f"{verified}\n"
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
            "Made by AdvanceFalling Team | v3.0"
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

    guild_id = str(
        interaction.guild.id
    )

    search_rooms[
        guild_id
    ] = str(
        channel.id
    )

    save_search_rooms(
        search_rooms
    )

    await interaction.response.send_message(
        f"✅ تم تحديد {channel.mention} كروم البحث التلقائي.\n"
        "🔎 العضو يكتب اسم الماب، وبعدها يختار **بدون مفتاح** أو **بمفتاح** أو **جميعهم**."
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


# ============================================================
# API SELECT
# ============================================================

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

_extension_bot = bot


async def setup(
    main_bot
):

    global bot

    bot = main_bot

    # --------------------------------------------------------
    # نقل أوامر Prefix إلى البوت الرئيسي
    # --------------------------------------------------------

    extension_commands = list(
        _extension_bot.commands
    )

    for command in extension_commands:

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

            existing = main_bot.tree.get_command(
                command.name
            )

            if existing is not None:

                print(
                    f"⚠️ Slash command already exists: "
                    f"/{command.name} — skipped."
                )

                continue

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