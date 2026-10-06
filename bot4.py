# ============================================================
# Team Fime — bot4.py
# Game Search System
# ============================================================

# Last Updated: 2026-10-06
# Version: 7.1

import discord
from discord.ext import commands
from discord import app_commands
import requests
import os
import sys
import shutil
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
from functools import lru_cache
import ipaddress
import hashlib

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
FALLBACK_IMAGE = None  # لا تستخدم GIF كصورة احتياطية

intents = discord.Intents.default()
intents.message_content = True

# ============================================================
# AUTO SEARCH SETTINGS — HIGH RECALL / FAST MULTI-SOURCE
# ============================================================

SEARCH_ROOMS_FILE = "bot4_search_rooms.json"
AUTO_SEARCH_COOLDOWN = 2
AUTO_SEARCH_CACHE_TTL = 180

# عدد النتائج التي يمكن تصفحها. لا يعني أن كل مصدر يعيد هذا العدد.
AUTO_SEARCH_MAX_RESULTS = 250
AUTO_SEARCH_PAGES_PER_SOURCE = 6
AUTO_SEARCH_PAGE_SIZE = 20

# بحث متوازٍ: نرفع المهلة بما يكفي للـ pagination بدون جعل البوت يختنق.
AUTO_SEARCH_TOTAL_TIMEOUT = 9.0
AUTO_SEARCH_CONNECT_TIMEOUT = 2.0
AUTO_SEARCH_READ_TIMEOUT = 7.0

# البحث المباشر: العضو يكتب الاسم فقط، بدون خطوة اختيار أولية.
AUTO_SEARCH_DIRECT = True

_direct_search_tasks = set()
_search_cooldowns = {}
_auto_search_cache = {}
_auto_search_inflight = {}

SEARCH_SOURCE_NAMES = {
    "scriptblox": "ScriptBlox",
    "robloxscripts": "RobloxScripts",
    "rscripts": "RScripts",
    "haxhell": "HaxHell",
    "roscripts": "RoScripts",
    "rbxscripts": "RBXScripts",
}

# RScripts API v1 يحتاج API key. إذا لم يوجد، يتم تجاهله فقط.
RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()
SEARCH_MAX_QUERIES_PER_SOURCE = 8

# عدد الصفحات العامة التي نسحبها بالتوازي من كل مصدر.
SEARCH_PAGES = tuple(range(1, AUTO_SEARCH_PAGES_PER_SOURCE + 1))




def _auto_cache_key(query, key_mode):
    return f"{compact_game_name(query)}|{key_mode}"


def _copy_cached_scripts(scripts):
    # نعيد list جديدة حتى لا تتغير نسخة الكاش بسبب إضافة metadata.
    return [dict(item) for item in (scripts or []) if isinstance(item, dict)]


async def get_auto_cache(query, key_mode):
    cache_key = _auto_cache_key(query, key_mode)
    item = _auto_search_cache.get(cache_key)

    if not item:
        return None

    if time.monotonic() - item["timestamp"] > AUTO_SEARCH_CACHE_TTL:
        _auto_search_cache.pop(cache_key, None)
        return None

    return _copy_cached_scripts(item["scripts"])


async def set_auto_cache(query, key_mode, scripts):
    cache_key = _auto_cache_key(query, key_mode)
    _auto_search_cache[cache_key] = {
        "timestamp": time.monotonic(),
        "scripts": _copy_cached_scripts(scripts),
    }

    if len(_auto_search_cache) > 200:
        now = time.monotonic()
        expired = [
            key for key, item in _auto_search_cache.items()
            if now - item.get("timestamp", 0) > AUTO_SEARCH_CACHE_TTL
        ]
        for key in expired:
            _auto_search_cache.pop(key, None)


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

SEARCH_HELP_ROOMS_FILE = "bot4_search_help_rooms.json"


def load_search_help_rooms():
    try:
        path = SEARCH_HELP_ROOMS_FILE
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"❌ Failed to load search help rooms: {e}")
        return {}


def save_search_help_rooms(data):
    try:
        with open(SEARCH_HELP_ROOMS_FILE, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ Failed to save search help rooms: {e}")
        return False


search_help_rooms = load_search_help_rooms()


def get_configured_help_channel_ids(guild_id):
    value = search_help_rooms.get(str(guild_id), [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).isdigit()]


class SearchHelpRoomSelect(discord.ui.Select):
    def __init__(self, guild, channel_ids):
        options = []
        for channel_id in channel_ids[:25]:
            channel = guild.get_channel(int(channel_id))
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
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            channel = interaction.guild.get_channel(int(self.values[0]))
        except Exception:
            channel = None

        if not channel:
            await interaction.response.send_message(
                "❌ الروم المحفوظ لم يعد موجودًا.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"📍 توجه إلى {channel.mention}",
            ephemeral=True,
        )


class SearchHelpRoomsView(discord.ui.View):
    def __init__(self, guild, channel_ids):
        super().__init__(timeout=120)
        valid_ids = []
        for channel_id in channel_ids[:25]:
            channel = guild.get_channel(int(channel_id))
            if channel and isinstance(channel, discord.TextChannel):
                valid_ids.append(str(channel.id))
        if valid_ids:
            self.add_item(SearchHelpRoomSelect(guild, valid_ids))


class SearchHelpButtonView(discord.ui.View):
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
        # أي عضو في روم البحث يقدر يستخدم الزر.
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
                "⚠️ الرومات المحددة لم تعد موجودة.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            "📚 **اختر الروم المناسب:**",
            view=view,
            ephemeral=True,
        )




# ============================================================
# GAME RESOLUTION
# ============================================================
# لا توجد قائمة مابات ثابتة هنا.
# البحث يعتمد على الاسم الذي كتبه العضو + التحويل العربي/الإنجليزي،
# ثم يقرر API وترتيب النتائج بناءً على اسم اللعبة الحقيقي.
GAME_ALIASES = {}


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


# لا توجد aliases ثابتة: هذا متعمد حتى لا يتحول بحث مثل
# "Timebomb" أو "Steal an Egg" إلى لعبة أخرى مسجلة داخل البوت.
NORMALIZED_GAME_ALIASES = {}


def get_close_game_suggestions(query, limit=3):
    # الاقتراحات الثابتة كانت أحد مصادر الخلط، لذلك لا نقترح ألعابًا
    # من قائمة داخلية لمجرد تشابه الاسم.
    return []


def resolve_game_query(query):
    # لا نعيد كتابة اسم اللعبة إلى اسم مسجل.
    # نترك API يستلم استعلام العضو كما هو.
    return str(query or "").strip()


# ============================================================
# SMART ARABIC / ENGLISH QUERY SYSTEM
# ============================================================


# يقبل العربي والإنجليزي: العربي يتحول لصيغ إنجليزية للبحث
# + مطابقة صوتية لترتيب النتائج (بدون مكتبات إضافية وبدون رام).
# ============================================================

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def has_arabic(text):
    return bool(_ARABIC_CHAR_RE.search(str(text or "")))


# كلمات شائعة في أسماء الماب. الكلمات الفارغة = كلمات زائدة تُحذف من البحث.
_AR_WORD_SOURCE = {
    "ماب": "", "روبلوكس": "", "سكربت": "", "سكريبت": "", "اسكربت": "",
    "سكربتات": "", "لعبة": "", "هاك": "",
    "سيمولاتور": "simulator", "سيميولاتور": "simulator", "سيميوليتر": "simulator",
    "سمولاتور": "simulator", "سيم": "sim", "تايكون": "tycoon", "تايكن": "tycoon",
    "اوبي": "obby", "تاور": "tower", "وورز": "wars", "وور": "war",
    "باتل": "battle", "قراوند": "ground", "قراوندز": "grounds", "جراوند": "ground",
    "فروت": "fruit", "فروتس": "fruits", "سرفايفل": "survival", "ديفنس": "defense",
    "ديفندرز": "defenders", "ادفنتشرز": "adventures", "ستوري": "story",
    "لايف": "life", "ورلد": "world", "وورلد": "world", "زيرو": "zero",
    "كينق": "king", "كينج": "king", "جاردن": "garden", "جرو": "grow",
    "برينروت": "brainrot", "ستيل": "steal", "هيرو": "hero", "هيروز": "heroes",
    "ايلاند": "island", "ايلاندز": "islands", "فارم": "farm", "كليكر": "clicker",
    "كلكر": "clicker", "فايتنق": "fighting", "فايتنج": "fighting", "قيم": "game",
    "قيمز": "games", "ماستر": "master", "ليجند": "legend", "ليقند": "legend",
    "سيرفر": "server", "ريسنق": "racing", "ريسينق": "racing", "درايف": "drive",
    "كار": "car", "كارز": "cars", "زومبي": "zombie", "زومبيز": "zombies",
    "نينجا": "ninja", "انمي": "anime", "ماينكرافت": "minecraft", "هيل": "hell",
    "اوف": "of", "اي": "a", "ان": "an", "ذا": "the", "ذي": "the",
    "فيش": "fish", "بول": "ball", "بليد": "blade", "هاوس": "house",
    "سيتي": "city", "ستريت": "street", "كوينز": "queens", "ديث": "death",
    "ريفت": "rift", "ريسيل": "rival", "رايفلز": "rivals", "ريفالز": "rivals",
}

_AR_WORD_MAP = {}
for _word, _english in _AR_WORD_SOURCE.items():
    _normalized_word = normalize_game_name(_word)
    if _normalized_word:
        _AR_WORD_MAP[_normalized_word] = _english

# نسختان صوتيتان لأن الحروف العربية تحتمل أكثر من نطق (ق = g أو q، ج = j أو g ...).
_AR_LETTERS = (
    {
        "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
        "د": "d", "ذ": "th", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
        "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "g", "ف": "f", "ق": "g",
        "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "o", "ي": "i",
        "ء": "", "پ": "p", "ڤ": "v", "چ": "ch", "گ": "g", "ک": "k", "ی": "i",
    },
    {
        "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "g", "ح": "h", "خ": "k",
        "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
        "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "g", "ف": "f", "ق": "q",
        "ك": "c", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "u", "ي": "e",
        "ء": "", "پ": "p", "ڤ": "v", "چ": "ch", "گ": "g", "ک": "c", "ی": "e",
    },
)


def _translit_word(word, variant):
    table = _AR_LETTERS[variant]
    last = len(word) - 1
    out = []

    for index, char in enumerate(word):
        if not _ARABIC_CHAR_RE.match(char):
            out.append(char)
        elif char == "و" and index == 0:
            out.append("w")
        elif char == "ي" and index == 0:
            out.append("y")
        elif char == "ه" and index == last and variant == 1 and last >= 2:
            continue
        else:
            out.append(table.get(char, ""))

    text = re.sub(r"(.)\1{2,}", r"\1\1", "".join(out))

    if variant == 0:
        text = re.sub(r"ks$", "x", text)

    return text


def arabic_to_latin_queries(text, limit=2):
    """يحول نص عربي (أو مختلط) إلى صيغ إنجليزية محتملة للبحث."""

    normalized = normalize_game_name(text)

    if not normalized or not has_arabic(normalized):
        return []

    results = []

    for variant in range(2):
        words = []

        for token in normalized.split():
            if token in _AR_WORD_MAP:
                mapped = _AR_WORD_MAP[token]
            elif has_arabic(token):
                mapped = _translit_word(token, variant)
            else:
                mapped = token

            if mapped:
                words.append(mapped)

        candidate = " ".join(words).strip()

        if candidate and candidate not in results:
            results.append(candidate)

    return results[:limit]


def latin_skeleton(text):
    """هيكل صوتي (حروف ساكنة فقط) لمقارنة النطق العربي بالاسم الإنجليزي."""

    value = re.sub(r"[^a-z0-9]", "", str(text or "").lower())

    for old, new in (
        ("x", "ks"), ("ph", "f"), ("ck", "k"), ("sh", "s"),
        ("th", "t"), ("kh", "k"), ("ch", "s"),
    ):
        value = value.replace(old, new)

    value = value.translate(
        str.maketrans({"q": "k", "c": "k", "v": "f", "p": "b", "z": "s", "j": "g"})
    )
    value = re.sub(r"[aeiouyw]", "", value)

    return re.sub(r"(.)\1+", r"\1", value)


def phonetic_similarity(query, text):
    skeleton_text = latin_skeleton(text)

    if len(skeleton_text) < 2:
        return 0.0

    sources = arabic_to_latin_queries(query) if has_arabic(query) else [query]
    best = 0.0

    for source in sources:
        skeleton_query = latin_skeleton(source)

        if len(skeleton_query) < 2:
            continue

        if len(skeleton_query) >= 3 and skeleton_query in skeleton_text:
            ratio = 0.9
        elif len(skeleton_text) >= 3 and skeleton_text in skeleton_query:
            ratio = 0.8
        else:
            ratio = difflib.SequenceMatcher(
                None, skeleton_query, skeleton_text
            ).ratio()

        best = max(best, ratio)

    return best


@lru_cache(maxsize=512)
def search_query_candidates(query):
    """يبني صيغ بحث متعددة من كلام العضو، حتى لو أضاف كلامًا لا علاقة له باسم الماب."""
    query = str(query or "").strip()
    if not query:
        return ()

    output, seen = [], set()

    def add(value):
        value = str(value or "").strip()
        key = normalize_game_name(value)
        if not value or not key or key in seen:
            return
        seen.add(key)
        output.append(value)

    # الأصل أولًا للحفاظ على دقة الاسم إذا كان العضو كتبه وحده.
    add(query)

    normalized = normalize_game_name(query)
    tokens = normalized.split()
    noise = {
        "ماب", "الماب", "سكربت", "سكريبت", "سكربتات", "اسكربت", "لعبه", "لعبة",
        "بوت", "ابحث", "بحث", "عن", "ابي", "ابغى", "ابغا", "اريد", "ابيكم", "ابيها",
        "هات", "جيب", "اعطني", "عطني", "تكفى", "تكفون", "لو", "ممكن", "احتاج", "احتاجه",
        "please", "pls", "script", "scripts", "map", "game", "find", "search", "get", "give", "me",
        "for", "the", "a", "an", "roblox", "روبلوكس",
    }
    useful = [t for t in tokens if t not in noise and len(t) >= 2]

    if useful:
        add(" ".join(useful))

        # نبحث أيضًا بأزواج وثلاثيات الكلمات، لأن اسم اللعبة قد يكون وسط جملة طويلة.
        for n in (3, 2):
            for i in range(max(0, len(useful) - n + 1)):
                add(" ".join(useful[i:i+n]))

        # كلمة مميزة وحدها كحل أخير للأسماء المكتوبة بخلط عربي/إنجليزي.
        for token in useful:
            if len(token) >= 4:
                add(token)

    if has_arabic(query):
        # الترجمة الصوتية لا تستبدل الأصل، بل تضيفه كصيغة بحث ثانية.
        for item in arabic_to_latin_queries(query, limit=4):
            add(item)
        if useful:
            useful_text = " ".join(useful)
            for item in arabic_to_latin_queries(useful_text, limit=4):
                add(item)

    return tuple(output[:10])


def prepare_search_query(query):
    """يبقي الإنجليزي كما كتبه العضو، ويحوّل العربي فقط عند الحاجة."""
    query = str(query or "").strip()
    if not query or not has_arabic(query):
        return query

    candidates = search_query_candidates(query)
    return candidates[0] if candidates else query


def get_game_search_queries(
    query
):

    return list(
        search_query_candidates(
            query
        )
    )[:4]


def _script_key(script):
    """يعطي كل نتيجة بحث مفتاحًا ثابتًا لإزالة التكرار بدون الحاجة لأي API key."""
    if not isinstance(script, dict):
        return hashlib.sha1(str(script).encode("utf-8", "ignore")).hexdigest()

    # نفضّل المعرفات التي ترسلها المصادر نفسها.
    for field in (
        "_id", "id", "scriptId", "script_id", "uuid", "_fime_id",
        "url", "scriptUrl", "webUrl", "pageUrl", "rawScriptUrl", "rawUrl",
    ):
        value = script.get(field)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()

    # إذا لم يوجد ID، نكوّن مفتاحًا من المصدر + اسم الماب + العنوان + الكود.
    parts = [
        str(script.get("_fime_api") or ""),
        str(script.get("gameName") or script.get("game") or ""),
        str(script.get("title") or script.get("name") or ""),
        str(script.get("script") or script.get("rawScript") or ""),
    ]
    raw = "|".join(parts).strip()
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


def _game_name_from_script(script):
    """يستخرج اسم اللعبة بأمان من اختلاف بنية نتائج المصادر المختلفة."""
    if not isinstance(script, dict):
        return ""

    # الاسم الموحد الذي تضيفه طبقات API الجديدة.
    for field in (
        "gameName", "game_name", "gameTitle", "game_title",
        "placeName", "place_name", "experienceName", "experience_name",
    ):
        value = script.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # بعض المصادر ترسل game ككائن، وبعضها كنص أو ID فقط.
    game = script.get("game")
    if isinstance(game, dict):
        for field in ("name", "title", "displayName", "gameName", "experienceName"):
            value = game.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(game, str) and game.strip():
        return game.strip()

    # صيغ إضافية قد تظهر في المصادر الخارجية.
    nested = script.get("experience") or script.get("place")
    if isinstance(nested, dict):
        for field in ("name", "title", "displayName"):
            value = nested.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def _game_relevance_score(game_name, query):
    """درجة تطابق اسم اللعبة مع الاستعلام، مع دعم العربي والإنجليزي."""
    game = str(game_name or "").strip()
    q = str(query or "").strip()
    if not game or not q:
        return 0.0

    game_norm = normalize_game_name(game)
    q_norm = normalize_game_name(q)
    if not game_norm or not q_norm:
        return 0.0

    game_compact = compact_game_name(game_norm)
    q_compact = compact_game_name(q_norm)

    if game_norm == q_norm or game_compact == q_compact:
        return 1.0
    if q_norm in game_norm or q_compact in game_compact:
        return 0.90
    if game_norm in q_norm:
        return 0.86

    best = difflib.SequenceMatcher(None, q_norm, game_norm).ratio()

    # الاستعلام العربي قد يكون مجرد نطق عربي للاسم الإنجليزي.
    best = max(best, phonetic_similarity(q_norm, game_norm))
    for candidate in search_query_candidates(q):
        cand_norm = normalize_game_name(candidate)
        if not cand_norm:
            continue
        cand_compact = compact_game_name(cand_norm)
        if cand_norm == game_norm or cand_compact == game_compact:
            best = max(best, 1.0)
        elif cand_norm in game_norm or cand_compact in game_compact:
            best = max(best, 0.90)
        else:
            best = max(best, difflib.SequenceMatcher(None, cand_norm, game_norm).ratio())
            best = max(best, phonetic_similarity(cand_norm, game_norm))

    return min(1.0, best)


def _script_needs_key(script):
    """يحدد وجود نظام مفتاح من عدة أسماء حقول مستخدمة لدى المصادر."""
    if not isinstance(script, dict):
        return False

    truthy_fields = (
        "keySystem", "key_system", "requiresKey", "requires_key",
        "keyRequired", "key_required", "hasKeySystem", "has_key_system",
        "isKey", "key",
    )
    for field in truthy_fields:
        value = script.get(field)
        if isinstance(value, bool):
            if value:
                return True
        elif isinstance(value, (int, float)) and value == 1:
            return True
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "yes", "1", "required", "key", "withkey", "with_key", "keysystem"}:
                return True

    # بعض النتائج تضع بيانات المفتاح داخل كائن.
    for field in ("key", "keySystem", "key_system", "access"):
        value = script.get(field)
        if isinstance(value, dict) and value:
            for nested_field in ("required", "enabled", "active", "hasKey", "has_key"):
                nested = value.get(nested_field)
                if nested is True or nested == 1 or (isinstance(nested, str) and nested.strip().lower() in {"true", "yes", "1"}):
                    return True

    # إذا كان المصدر يصف نظام المفتاح نصيًا، نلتقطه بحذر.
    for field in ("description", "desc", "notes", "status"):
        value = script.get(field)
        if isinstance(value, str) and value.strip():
            text = normalize_game_name(value)
            if re.search(r"\b(key system|key required|requires key|keys?ystem)\b", text):
                return True
            if any(token in text for token in ("مفتاح", "كي سيستم", "keysystem", "key required", "requires key")):
                return True

    return False


def _score_auto_result(script, query):
    """ترتيب النتائج: اسم الماب أولًا ثم تطابق العنوان وبعض مؤشرات الجودة."""
    if not isinstance(script, dict):
        return 0.0

    game_score = _game_relevance_score(_game_name_from_script(script), query)

    title = str(script.get("title") or script.get("name") or "")
    title_score = _game_relevance_score(title, query) if title else 0.0

    views = script.get("views", script.get("viewCount", 0)) or 0
    likes = script.get("likes", script.get("likeCount", 0)) or 0
    try:
        views_score = min(1.0, max(0.0, float(views)) / 100000.0)
    except (TypeError, ValueError):
        views_score = 0.0
    try:
        likes_score = min(1.0, max(0.0, float(likes)) / 10000.0)
    except (TypeError, ValueError):
        likes_score = 0.0

    source_bonus = {
        "scriptblox": 0.05,
        "robloxscripts": 0.045,
        "rscripts": 0.04,
        "haxhell": 0.01,
        "roscripts": 0.01,
        "rbxscripts": 0.01,
    }.get(str(script.get("_fime_api") or ""), 0.0)

    return (game_score * 0.72) + (title_score * 0.18) + (views_score * 0.06) + (likes_score * 0.03) + source_bonus


def _filter_relevant_results(results, query, key_mode=None):
    """فلترة آمنة للنتائج مع عدم إسقاط النتائج التي لا تملك اسم لعبة صريحًا."""
    output = []
    for item in results or []:
        if not isinstance(item, dict):
            continue

        game_name = _game_name_from_script(item)
        # النتائج التي لا تملك اسم لعبة صريحًا تُترك لأنها قد تكون fallback من موقع خارجي.
        if game_name:
            score = _game_relevance_score(game_name, query)
            if score < 0.42:
                continue

        if key_mode == "no_key" and _script_needs_key(item):
            continue
        if key_mode == "with_key" and not _script_needs_key(item):
            continue

        output.append(item)

    return output


# ============================================================
# AUTO SEARCH API WORKER — HIGH RECALL MULTI-SOURCE
# ============================================================

async def _http_json(session, url, *, params=None, headers=None):
    try:
        async with session.get(url, params=params, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                return None, response.status
            return await response.json(content_type=None), 200
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return None, -1
    except Exception as exc:
        print(f"⚠️ Search source error: {exc}")
        return None, -2


async def _scriptblox_page(session, query, page):
    params = {
        "q": query,
        "page": page,
        "max": min(AUTO_SEARCH_PAGE_SIZE, 20),
        "mode": "free",
        "sortBy": "accuracy",
        "order": "desc",
        "strict": "false",
    }
    data, status = await _http_json(
        session,
        "https://scriptblox.com/api/script/search",
        params=params,
        headers={"User-Agent": "Team-Fime-Search/7.1", "Accept": "application/json"},
    )
    if not isinstance(data, dict):
        return [], status == -1
    result = data.get("result") or {}
    rows = result.get("scripts") or []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            item = dict(row)
            item["_fime_api"] = "scriptblox"
            item["_fime_page"] = page
            out.append(item)
    return out, False


async def _robloxscripts_page(session, query, page):
    params = {
        "q": query,
        "page": page,
        "limit": min(AUTO_SEARCH_PAGE_SIZE, 50),
        "sort": "most-liked",
    }
    data, status = await _http_json(
        session,
        "https://robloxscripts.com/api/v1/scripts",
        params=params,
        headers={"User-Agent": "Team-Fime-Search/7.1", "Accept": "application/json"},
    )
    if not isinstance(data, dict):
        return [], status == -1
    rows = data.get("data") or []
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            item = dict(row)
            item["_fime_api"] = "robloxscripts"
            item["_fime_page"] = page
            # توحيد الحقول الجديدة.
            item.setdefault("title", item.get("name") or "بدون عنوان")
            item.setdefault("views", item.get("viewCount", 0) or 0)
            item.setdefault("image", item.get("imageUrl") or item.get("thumbnailUrl"))
            if isinstance(item.get("game"), dict):
                g = item["game"]
                item.setdefault("gameName", g.get("name") or g.get("title") or g.get("displayName"))
                item.setdefault("_fime_game_image", g.get("thumbnailUrl") or g.get("imageUrl") or g.get("logoUrl"))
            item.setdefault("rawScript", item.get("rawScriptUrl"))
            out.append(item)
    return out, False


async def _rscripts_page(session, query, page):
    if not RSCRIPTS_API_KEY:
        return [], False
    params = {
        "q": query,
        "index": "scripts",
        "page": page,
        "limit": min(AUTO_SEARCH_PAGE_SIZE, 20),
        "htmlDescription": "false",
        "includeScript": "false",
    }
    data, status = await _http_json(
        session,
        "https://api.rscripts.net/v1/search",
        params=params,
        headers={
            "User-Agent": "Team-Fime-Search/7.1",
            "Accept": "application/json",
            "Authorization": f"Bearer {RSCRIPTS_API_KEY}",
        },
    )
    if not isinstance(data, dict):
        return [], status == -1
    raw = ((data.get("data") or {}).get("scripts") or [])
    out = []
    for row in raw if isinstance(raw, list) else []:
        if isinstance(row, dict):
            item = dict(row)
            item["_fime_api"] = "rscripts"
            item["_fime_page"] = page
            game = item.get("game")
            if isinstance(game, dict):
                item.setdefault("gameName", game.get("title") or game.get("name"))
                item.setdefault("_fime_game_image", game.get("thumbnailUrl") or game.get("logoUrl"))
            creator = item.get("creator") or {}
            if isinstance(creator, dict):
                item.setdefault("_fime_creator_image", creator.get("avatarUrl"))
                item.setdefault("user", creator)
            out.append(item)
    return out, False


async def _generic_site_search_async(session, query, source, base_url):
    """HTML fallback. لا يدعي أنه API: يلتقط الروابط والصور المتاحة فقط."""
    q = urllib.parse.quote_plus(str(query))
    url = base_url.format(query=q)
    headers = {"User-Agent": "Team-Fime-Search/7.1", "Accept": "text/html,application/xhtml+xml"}
    try:
        async with session.get(url, headers=headers, allow_redirects=True) as response:
            if response.status != 200:
                return [], True
            html = await response.text(errors="ignore")
        if not html:
            return [], False
        image_matches = re.findall(
            r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',
            html, re.I
        )
        image = image_matches[0] if image_matches else None
        link_re = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
        results, seen = [], set()
        for href, raw_text in link_re.findall(html):
            text_value = re.sub(r'<[^>]+>', ' ', raw_text)
            text_value = re.sub(r'\s+', ' ', text_value).strip()
            if len(text_value) < 3:
                continue
            absolute = urllib.parse.urljoin(url, href)
            if not absolute.startswith(("http://", "https://")):
                continue
            key = absolute.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "title": text_value[:180],
                "gameName": query,
                "url": absolute,
                "image": image,
                "_fime_api": source,
                "_fime_fallback": True,
            })
            if len(results) >= 40:
                break
        return results, False
    except (asyncio.TimeoutError, aiohttp.ClientError):
        return [], True
    except Exception:
        return [], True


async def _search_one_source(session, source, query):
    if source == "scriptblox":
        tasks = [_scriptblox_page(session, query, page) for page in SEARCH_PAGES]
    elif source == "robloxscripts":
        tasks = [_robloxscripts_page(session, query, page) for page in SEARCH_PAGES]
    elif source == "rscripts":
        tasks = [_rscripts_page(session, query, page) for page in SEARCH_PAGES]
    elif source == "haxhell":
        return await _generic_site_search_async(session, query, "haxhell", "https://haxhell.com/?q={query}")
    elif source == "roscripts":
        return await _generic_site_search_async(session, query, "roscripts", "https://roscripts.net/?q={query}")
    elif source == "rbxscripts":
        return await _generic_site_search_async(session, query, "rbxscripts", "https://rbxscripts.net/?q={query}")
    else:
        return [], False

    results = await asyncio.gather(*tasks, return_exceptions=True)
    collected, failed = [], False
    for result in results:
        if isinstance(result, Exception):
            failed = True
            continue
        rows, network_error = result
        failed = failed or network_error
        collected.extend(rows)
    return collected, failed


async def fetch_auto_search_mode(search_query, key_mode="all"):
    """بحث شامل نسبيًا: عدة صيغ × عدة مصادر × صفحات متوازية × إزالة تكرار."""
    cache_key = _auto_cache_key(search_query, key_mode)
    cache = await get_auto_cache(search_query, key_mode)
    if cache is not None:
        return cache, False, True

    existing = _auto_search_inflight.get(cache_key)
    if existing:
        try:
            rows, err = await existing
            return _copy_cached_scripts(rows), err, True
        except Exception:
            pass

    async def worker():
        queries = list(get_game_search_queries(search_query))[:SEARCH_MAX_QUERIES_PER_SOURCE]
        if not queries:
            queries = [str(search_query).strip()]

        timeout = aiohttp.ClientTimeout(
            total=AUTO_SEARCH_TOTAL_TIMEOUT,
            connect=AUTO_SEARCH_CONNECT_TIMEOUT,
            sock_read=AUTO_SEARCH_READ_TIMEOUT,
        )
        sources = ["scriptblox", "robloxscripts", "haxhell", "roscripts", "rbxscripts"]
        if RSCRIPTS_API_KEY:
            sources.insert(2, "rscripts")

        collected, seen, had_error = [], set(), False
        async with aiohttp.ClientSession(timeout=timeout) as session:
            jobs = [
                _search_one_source(session, source, candidate)
                for candidate in queries
                for source in sources
            ]
            results = await asyncio.gather(*jobs, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    had_error = True
                    continue
                rows, error = result
                had_error = had_error or error
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    key = f"{row.get('_fime_api','x')}:{_script_key(row)}"
                    if key in seen:
                        continue
                    if _game_name_from_script(row):
                        relevance = _game_relevance_score(_game_name_from_script(row), search_query)
                        if relevance < 0.58:
                            continue
                    seen.add(key)
                    collected.append(row)

        # ترتيب عالي الاستدعاء مع الحفاظ على أفضل التطابقات في الأعلى.
        collected.sort(key=lambda item: _score_auto_result(item, search_query), reverse=True)
        collected = collected[:AUTO_SEARCH_MAX_RESULTS]
        await set_auto_cache(search_query, key_mode, collected)
        return collected, had_error

    task = asyncio.create_task(worker())
    _auto_search_inflight[cache_key] = task
    try:
        rows, err = await task
        return rows, err, False
    finally:
        if _auto_search_inflight.get(cache_key) is task:
            _auto_search_inflight.pop(cache_key, None)


async def process_auto_search_request(message, requester_id, query, key_mode="all"):
    started = time.perf_counter()
    try:
        rows, had_error, _ = await fetch_auto_search_mode(query, key_mode)
        await _attach_roblox_thumbnail_if_missing(rows[:40])
        rows = _filter_relevant_results(rows, query, None)
        rows.sort(key=lambda item: _score_auto_result(item, query), reverse=True)
        rows = rows[:AUTO_SEARCH_MAX_RESULTS]
        elapsed = time.perf_counter() - started

        if not rows:
            text_value = (
                f"❌ ما لقيت نتائج مطابقة لـ **{query}**."
                if not had_error else
                f"⚠️ مصادر البحث ما ردت بالكامل، وما وصلت نتيجة مؤكدة لـ **{query}**."
            )
            await message.channel.send(text_value, allowed_mentions=discord.AllowedMentions.none())
            return

        view = AutoSearchResultBrowseView(requester_id, rows, query, ["all"])
        embed = view.build_embed()
        await message.channel.send(
            content=(
                f"✅ **{len(rows)} نتيجة** لـ **{query}** • "
                f"⚡ {elapsed:.1f}s\n"
                "يمكنك تبديل النتائج من الأسهم، ونسخ الكود من زر **نسخ**."
            ),
            embed=embed,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception as exc:
        print(f"❌ Auto search background error: {exc}")
        await message.channel.send("❌ صار خطأ أثناء تجهيز البحث.", allowed_mentions=discord.AllowedMentions.none())


# ============================================================
# AUTO SEARCH RESULT BROWSER
# ============================================================


# ============================================================
# AUTO SEARCH RESULT BROWSER
# ============================================================

class AutoSearchResultBrowseView(discord.ui.View):
    """واجهة نظيفة: تبديل النتائج + نسخ فقط، مع قائمة فلترة صغيرة."""

    def __init__(self, requester_id, scripts, query, selected_modes=None):
        super().__init__(timeout=600)
        self.requester_id = requester_id
        self.all_scripts = list(scripts or [])
        self.scripts = list(self.all_scripts)
        self.query = query
        self.index = 0
        self.filter_mode = "all"
        self.refresh_items()

    async def interaction_check(self, interaction):
        return True

    def _filtered(self):
        if self.filter_mode == "no_key":
            return [s for s in self.all_scripts if not _script_needs_key(s)]
        if self.filter_mode == "with_key":
            return [s for s in self.all_scripts if _script_needs_key(s)]
        return list(self.all_scripts)

    def refresh_items(self):
        self.scripts = self._filtered()
        if not self.scripts:
            self.index = 0
        else:
            self.index = min(self.index, len(self.scripts) - 1)
        self.clear_items()

        selector = discord.ui.Select(
            placeholder="فلترة الوصول: الكل / بدون مفتاح / بمفتاح",
            options=[
                discord.SelectOption(label="الكل", value="all", emoji="🌐", default=self.filter_mode == "all"),
                discord.SelectOption(label="بدون مفتاح", value="no_key", emoji="🔓", default=self.filter_mode == "no_key"),
                discord.SelectOption(label="بمفتاح", value="with_key", emoji="🔑", default=self.filter_mode == "with_key"),
            ],
            row=0,
        )
        selector.callback = self.filter_callback
        self.add_item(selector)

        previous = discord.ui.Button(label="◀️", style=discord.ButtonStyle.secondary, disabled=self.index <= 0, row=1)
        previous.callback = self.previous_callback
        self.add_item(previous)

        position = discord.ui.Button(
            label=f"{self.index + 1}/{len(self.scripts)}" if self.scripts else "0/0",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=1,
        )
        self.add_item(position)

        nxt = discord.ui.Button(
            label="▶️", style=discord.ButtonStyle.secondary,
            disabled=not self.scripts or self.index >= len(self.scripts) - 1,
            row=1,
        )
        nxt.callback = self.next_callback
        self.add_item(nxt)

        copy_button = discord.ui.Button(label="نسخ", emoji="📋", style=discord.ButtonStyle.success, row=1, disabled=not bool(self.scripts))
        copy_button.callback = self.copy_callback
        self.add_item(copy_button)

    def build_embed(self):
        if not self.scripts:
            return discord.Embed(title="لا توجد نتائج بهذا الفلتر", description="جرّب فلترًا آخر.", color=0x206694)
        script = self.scripts[self.index]
        return create_embed(script, self.index + 1, len(self.scripts), script.get("_fime_api", "scriptblox"))

    async def filter_callback(self, interaction):
        self.filter_mode = interaction.data["values"][0]
        self.index = 0
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def previous_callback(self, interaction):
        if self.index <= 0:
            return await interaction.response.defer()
        self.index -= 1
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def next_callback(self, interaction):
        if self.index >= len(self.scripts) - 1:
            return await interaction.response.defer()
        self.index += 1
        self.refresh_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def copy_callback(self, interaction):
        if not self.scripts:
            return await interaction.response.send_message("❌ لا توجد نتيجة حاليًا.", ephemeral=True)
        script = self.scripts[self.index]
        source = script.get("_fime_api")
        content = str(script.get("script") or script.get("rawScript") or "").strip()
        if source == "rscripts" and content.startswith("http"):
            content = f'loadstring(game:HttpGet("{content}"))()'
        if not content:
            raw_url = _script_raw_url(script)
            if raw_url:
                content = f'loadstring(game:HttpGet("{raw_url}"))()'
        if not content:
            return await interaction.response.send_message("❌ الكود غير متوفر من المصدر.", ephemeral=True)
        if len(content) <= 1900:
            await interaction.response.send_message(f"```lua\n{content}\n```", ephemeral=True)
        else:
            import io
            await interaction.response.send_message(
                "📜 الكود طويل، أرفقته كملف.",
                file=discord.File(io.BytesIO(content.encode("utf-8")), filename="script.lua"),
                ephemeral=True,
            )

    async def on_timeout(self):
        self.clear_items()


# ============================================================
# AUTOMATIC GAME SEARCH
# ============================================================


# ============================================================
# AUTOMATIC GAME SEARCH
# ============================================================

class _MessageResponder:
    """يخلي نتائج البحث تتحدث داخل رسالة عادية بنفس طريقة interaction."""

    def __init__(self, message, guild):
        self.message = message
        self.guild = guild

    async def edit_original_response(self, **kwargs):
        await self.message.edit(**kwargs)

    async def delete_original_response(self):
        try:
            await self.message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


async def automatic_game_search(message, query):
    """يبدأ البحث فورًا. لا توجد خطوة اختيار قبل ظهور النتائج."""
    status = await message.channel.send(
        f"🔎 **جاري البحث عن:** `{query}`\n"
        "⚡ أفحص المصادر المتاحة وأجمع النتائج المتشابهة ثم أرتبها."
    )
    try:
        await process_auto_search_request(message, message.author.id, query, "all")
    finally:
        try:
            await status.delete()
        except Exception:
            pass




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
        self.active_search_tasks = set()

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

    if len(query) > 120:

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

    original_query = query
    query = prepare_search_query(query)

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
                timeout=AUTO_SEARCH_TOTAL_TIMEOUT
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
                f"matching '{original_query}'"
            )

        elif api == "rscripts":

            not_paid = (
                False
                if mode.lower() == "paid"
                else True
            )

            params = {
                "q": str(query),
                "page": int(page),
                "notPaid": "true" if not_paid else "false"
            }

            if filters.get(
                "noKeySystem"
            ) is not None:

                params["noKeySystem"] = "true" if bool(filters["noKeySystem"]) else "false"

            if filters.get(
                "mobileOnly"
            ) is not None:

                params["mobileOnly"] = "true" if bool(filters["mobileOnly"]) else "false"

            if filters.get(
                "verifiedOnly"
            ) is not None:

                params["verifiedOnly"] = "true" if bool(filters["verifiedOnly"]) else "false"

            if filters.get(
                "unpatched"
            ) is not None:

                params["unpatched"] = "true" if bool(filters["unpatched"]) else "false"

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
                timeout=AUTO_SEARCH_TOTAL_TIMEOUT
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
                f"matching '{original_query}'"
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


def get_static_image_url(*candidates):
    """يرجع أول صورة ثابتة صالحة، ويمنع GIF/Tenor/Giphy كصور نتائج."""
    for candidate in candidates:
        if not candidate or not isinstance(candidate, str):
            continue
        url = candidate.strip()
        if not validators.url(url):
            continue
        lowered = url.lower()
        parsed = urllib.parse.urlparse(lowered)
        path = parsed.path or ""
        host = parsed.netloc or ""
        if path.endswith((".gif", ".gifv")):
            continue
        if "tenor.com" in host or "giphy.com" in host:
            continue
        return url
    return None


async def _attach_roblox_thumbnail_if_missing(scripts):
    """يحاول إضافة صورة اللعبة من Roblox فقط عند غياب الصورة الأصلية."""
    candidates = [
        script for script in (scripts or [])
        if isinstance(script, dict) and not get_static_image_url(
            script.get("image"),
            (script.get("game") or {}).get("imageUrl") if isinstance(script.get("game"), dict) else None,
            (script.get("game") or {}).get("image") if isinstance(script.get("game"), dict) else None,
            (script.get("game") or {}).get("thumbnail") if isinstance(script.get("game"), dict) else None,
        )
    ]

    # لا نفتح متصفحًا؛ طلب HTTP خفيف فقط، وبحد أقصى 8 ألعاب مختلفة.
    place_ids = []
    seen_ids = set()

    for script in candidates:
        game = script.get("game", {})
        if not isinstance(game, dict):
            continue

        raw_id = (
            game.get("gameId")
            or game.get("placeId")
            or script.get("placeId")
        )
        try:
            place_id = int(str(raw_id))
        except (TypeError, ValueError):
            continue

        if place_id and place_id not in seen_ids:
            seen_ids.add(place_id)
            place_ids.append((place_id, script))

        if len(place_ids) >= 8:
            break

    if not place_ids:
        return

    ids = ",".join(str(pid) for pid, _ in place_ids)
    url = (
        "https://thumbnails.roblox.com/v1/games/icons"
        f"?placeIds={ids}&returnPolicy=PlaceHolder"
        "&size=512x512&format=Png&isCircular=false"
    )

    timeout = aiohttp.ClientTimeout(total=3, connect=1.5, sock_read=2.5)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url,
                headers={"User-Agent": "Team-Fime-Search/5.0", "Accept": "application/json"},
            ) as response:
                if response.status != 200:
                    return
                data = await response.json(content_type=None)

        image_by_id = {}
        for item in data.get("data", []) if isinstance(data, dict) else []:
            try:
                pid = int(item.get("targetId"))
            except (TypeError, ValueError):
                continue
            image = item.get("imageUrl")
            if image:
                image_by_id[pid] = image

        for pid, script in place_ids:
            image = image_by_id.get(pid)
            if image:
                script["_fime_game_image"] = image

    except Exception as exc:
        print(f"⚠️ Roblox thumbnail lookup skipped: {exc}")


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
            f"📜 "
            f"{script.get('title', 'No Title')}"
        )

        game = script.get(
            "game",
            {}
        )

        game_name = game.get(
            "name",
            "لعبة غير معروفة"
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

        owner = script.get("user") or script.get("owner") or {}
        if not isinstance(owner, dict):
            owner = {}
        script_image = get_static_image_url(
            script.get("image"),
            game.get("imageUrl"),
            game.get("image"),
            game.get("thumbnail"),
            owner.get("image"),
            owner.get("avatar"),
            owner.get("avatarUrl"),
            script.get("_fime_game_image"),
        )

        views = script.get(
            "views",
            0
        )

        script_type = (
            "مجاني"
            if script.get(
                "scriptType",
                "free"
            ).lower() == "free"
            else "مدفوع"
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
            "لا يوجد كود"
        )

        if len(
            truncated_script
        ) > 400:

            truncated_script = (
                truncated_script[:397]
                + "..."
            )

        embed.add_field(
            name="🎮 الماب",
            value=(
                f"[{game_name}]"
                f"({game_link})"
            ),
            inline=True
        )

        embed.add_field(
            name="التحقق",
            value=verified_status,
            inline=True
        )

        embed.add_field(
            name="النوع",
            value=script_type,
            inline=True
        )

        embed.add_field(
            name="عالمي",
            value=universal_status,
            inline=True
        )

        embed.add_field(
            name="المشاهدات",
            value=f"👁️ {views}",
            inline=True
        )

        embed.add_field(
            name="🔐 المفتاح",
            value=key_status,
            inline=True
        )

        embed.add_field(
            name="الحالة",
            value=patched_status,
            inline=True
        )

        source_type = script.get(
            "_fime_key_source"
        )

        if not source_type:
            source_type = (
                "بمفتاح"
                if script.get("key", False)
                else "بدون مفتاح"
            )

        if source_type:

            embed.add_field(
                name="🔐 البحث",
                value=source_type,
                inline=True
            )

        embed.add_field(
            name="🔗 الروابط",
            value=(
                f"[الكود الخام]"
                f"(https://rawscripts.net/raw/"
                f"{script.get('slug','')}) - "
                f"[صفحة السكربت]"
                f"(https://scriptblox.com/script/"
                f"{script.get('slug','')})"
            ),
            inline=False
        )

        embed.add_field(
            name="📜 السكربت",
            value=(
                f"```\n"
                f"{truncated_script}"
                f"\n```"
            ),
            inline=False
        )

        embed.add_field(
            name="🕒 الوقت",
            value=format_timestamps(
                script
            ),
            inline=False
        )

        if script_image:
            embed.set_image(url=script_image)

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

        user_avatar_url = get_static_image_url(
            user.get("image"),
            user.get("avatar"),
            user.get("avatarUrl"),
        )

        embed.add_field(
            name="المشاهدات",
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
            name="التحقق",
            value=verified_status,
            inline=True
        )

        embed.add_field(
            name="Cost",
            value=paid_status,
            inline=True
        )

        embed.add_field(
            name="📜 السكربت",
            value=script_text,
            inline=False
        )

        embed.add_field(
            name="🔗 الروابط",
            value=(
                f"[صفحة السكربت]"
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

        if user_avatar_url:
            embed.set_author(
                name=user_name,
                icon_url=user_avatar_url
            )
        else:
            embed.set_author(name=user_name)

        image_url = get_static_image_url(
            script.get("image"),
            script.get("_fime_game_image"),
            user_avatar_url,
        )

        if image_url:
            embed.set_image(url=image_url)

    elif api not in ("scriptblox", "rscripts"):

        title = str(script.get("title") or script.get("name") or "نتيجة بدون عنوان")
        game_name = str(script.get("gameName") or _game_name_from_script(script) or "لعبة غير معروفة")
        views = script.get("views", script.get("viewCount", 0)) or 0
        likes = script.get("likes", script.get("likeCount", 0)) or 0
        image_url = get_static_image_url(
            script.get("image"),
            script.get("imageUrl"),
            script.get("thumbnailUrl"),
            script.get("_fime_game_image"),
        )
        post_url = _script_view_url(script)
        raw_url = _script_raw_url(script)

        embed.title = f"📜 {title[:240]}"
        embed.add_field(name="🎮 الماب", value=game_name[:1024], inline=False)
        embed.add_field(name="👁️ المشاهدات", value=str(views), inline=True)
        embed.add_field(name="👍 الإعجابات", value=str(likes), inline=True)
        embed.add_field(name="🌐 المصدر", value=SEARCH_SOURCE_NAMES.get(api, "مصدر خارجي"), inline=True)
        if post_url:
            embed.add_field(name="🔗 الصفحة", value=f"[فتح النتيجة]({post_url})", inline=False)
        if raw_url:
            embed.add_field(name="📄 الكود الخام", value=f"[فتح الكود]({raw_url})", inline=False)
        if image_url:
            embed.set_image(url=image_url)

    embed.set_footer(
        text=(
            f"Team Fime • {SEARCH_SOURCE_NAMES.get(api, 'مصدر البحث')} • "
            f"النتيجة {page}/{total_items}"
        )
    )

    return embed


def _script_source_label(script):
    return SEARCH_SOURCE_NAMES.get(
        str(script.get("_fime_api") or ""),
        "مصدر خارجي",
    )


def _script_view_url(script):
    source = str(script.get("_fime_api") or "")
    slug = str(
        script.get("slug")
        or script.get("_id")
        or script.get("id")
        or ""
    ).strip()

    if source == "scriptblox" and slug:
        return f"https://scriptblox.com/script/{urllib.parse.quote(slug)}"
    if source == "rscripts" and slug:
        return f"https://rscripts.net/script/{urllib.parse.quote(slug)}"

    for key in ("url", "scriptUrl", "webUrl", "pageUrl", "link"):
        value = str(script.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    return ""


def _script_raw_url(script):
    source = str(script.get("_fime_api") or "")
    slug = str(
        script.get("slug")
        or script.get("_id")
        or script.get("id")
        or ""
    ).strip()

    if source == "scriptblox" and slug:
        return f"https://rawscripts.net/raw/{urllib.parse.quote(slug)}"

    for key in ("rawScriptUrl", "rawUrl", "raw_url"):
        value = str(script.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value
    return ""


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
                label="فتح الصفحة",
                url=post_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        view.add_item(
            discord.ui.Button(
                label="الكود الخام",
                url=raw_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        view.add_item(
            discord.ui.Button(
                label="تحميل",
                url=download_url,
                style=discord.ButtonStyle.link,
                row=1
            )
        )

        copy_button = discord.ui.Button(
            label="نسخ",
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
                f"🔎 Team Fime Multi-Search • {SEARCH_SOURCE_NAMES.get(api, 'Scripts')}"
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
                    "بدون عنوان"
                )

                game = script.get(
                    "game",
                    {}
                ).get(
                    "name",
                    "لعبة غير معروفة"
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
                    "بدون عنوان"
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
        "🔎 العضو يكتب اسم الماب (عربي أو إنجليزي) والبوت يبحث له تلقائيًا فورًا."
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
# SEARCH RESULT HELP ROOMS — OWNER CONFIG
# ============================================================

@bot.tree.command(
    name="addsearchhelproom",
    description="إضافة روم يظهر للعضو إذا لم يجد نتيجة"
)
@app_commands.describe(channel="الروم الذي تريد إضافته للقائمة")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_add_search_help_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
):
    guild_key = str(interaction.guild.id)
    rooms = get_configured_help_channel_ids(interaction.guild.id)
    if str(channel.id) not in rooms:
        rooms.append(str(channel.id))
    search_help_rooms[guild_key] = rooms[:25]
    save_search_help_rooms(search_help_rooms)
    await interaction.response.send_message(
        f"✅ تمت إضافة {channel.mention} لقائمة رومات المساعدة.",
        ephemeral=True,
    )


@bot.tree.command(
    name="removesearchhelproom",
    description="إزالة روم من قائمة رومات المساعدة"
)
@app_commands.describe(channel="الروم الذي تريد إزالته")
@app_commands.checks.has_permissions(manage_guild=True)
async def slash_remove_search_help_room(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
):
    guild_key = str(interaction.guild.id)
    rooms = [
        item for item in get_configured_help_channel_ids(interaction.guild.id)
        if str(item) != str(channel.id)
    ]
    search_help_rooms[guild_key] = rooms
    save_search_help_rooms(search_help_rooms)
    await interaction.response.send_message(
        f"🗑️ تمت إزالة {channel.mention} من القائمة.",
        ephemeral=True,
    )


@bot.tree.command(
    name="searchhelprooms",
    description="عرض رومات المساعدة المحددة عند عدم وجود نتيجة"
)
async def slash_show_search_help_rooms(interaction: discord.Interaction):
    rooms = []
    for channel_id in get_configured_help_channel_ids(interaction.guild.id):
        channel = interaction.guild.get_channel(int(channel_id))
        if channel:
            rooms.append(channel.mention)
    await interaction.response.send_message(
        "📚 **رومات المساعدة:**\n" + (", ".join(rooms) if rooms else "لا توجد رومات محددة."),
        ephemeral=True,
    )


@bot.command(name="اضافة_روم_مساعدة")
@commands.has_permissions(manage_guild=True)
async def add_search_help_room_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    guild_key = str(ctx.guild.id)
    rooms = get_configured_help_channel_ids(ctx.guild.id)
    if str(channel.id) not in rooms:
        rooms.append(str(channel.id))
    search_help_rooms[guild_key] = rooms[:25]
    save_search_help_rooms(search_help_rooms)
    await ctx.send(f"✅ تمت إضافة {channel.mention} لقائمة رومات المساعدة.")


@bot.command(name="حذف_روم_مساعدة")
@commands.has_permissions(manage_guild=True)
async def remove_search_help_room_prefix(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    guild_key = str(ctx.guild.id)
    search_help_rooms[guild_key] = [
        item for item in get_configured_help_channel_ids(ctx.guild.id)
        if str(item) != str(channel.id)
    ]
    save_search_help_rooms(search_help_rooms)
    await ctx.send(f"🗑️ تمت إزالة {channel.mention} من القائمة.")


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
                label="مصدر ScriptBlox",
                value="scriptblox",
                description=(
                    "Search scripts from "
                    "ScriptBlox API"
                )
            ),

            discord.SelectOption(
                label="مصدر RScripts",
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
        "notPaid": "true"
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
