# ============================================================
# Team Fime — bot4.py
# Game Search Cog
# Version: 8.0
# ============================================================
#
# الملف يعمل كـ extension:  await bot.load_extension("bot4")
# المتطلبات: discord.py 2.x و aiohttp
# اختياري: RSCRIPTS_API_KEY في Environment لتفعيل RScripts API v1

import asyncio
import difflib
import hashlib
import io
import json
import math
import os
import re
import time
import urllib.parse
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# SETTINGS
# ============================================================

SEARCH_ROOMS_FILE = "bot4_search_rooms.json"
SEARCH_HELP_ROOMS_FILE = "bot4_search_help_rooms.json"

RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()
USER_AGENT = "Team-Fime-Search/8.0"

AUTO_SEARCH_COOLDOWN = 2            # ثواني بين بحثين لنفس العضو
AUTO_SEARCH_CACHE_TTL = 180         # ثواني
AUTO_SEARCH_MAX_RESULTS = 250
AUTO_SEARCH_PAGE_SIZE = 20
AUTO_SEARCH_MAX_PAGES = 6
AUTO_SEARCH_MAX_QUERIES = 6         # أقصى عدد صيغ بحث لكل استعلام
AUTO_SEARCH_TARGET = 60             # نوقف التوسع إذا وصلنا لهذا العدد من النتائج المتطابقة
AUTO_SEARCH_DEADLINE = 9.0          # أقصى وقت لبحث كامل (ثواني)
HTTP_TIMEOUT_TOTAL = 6.0
HTTP_CONCURRENCY = 8
RELEVANCE_MIN = 0.55
COPY_TEXT_LIMIT = 1900              # أكبر من هذا يروح كملف .lua
DISCORD_TEXT_LIMIT = 1900

ENABLED_SOURCES = ("scriptblox", "robloxscripts", "rscripts", "haxhell", "roscripts", "rbxscripts")

SOURCE_NAMES = {
    "scriptblox": "ScriptBlox",
    "robloxscripts": "RobloxScripts",
    "rscripts": "RScripts",
    "haxhell": "HaxHell",
    "roscripts": "RoScripts",
    "rbxscripts": "RBXScripts",
}

SOURCE_COLORS = {
    "scriptblox": 0x2ECC71,
    "rscripts": 0x9B59B6,
    "robloxscripts": 0xE67E22,
}

# مصادر HTML احتياطية: تُستخدم مع الاستعلام الأول فقط، ونتائجها تُفلتر بالعنوان.
HTML_SOURCES = {
    "haxhell": "https://haxhell.com/?q={query}",
    "roscripts": "https://roscripts.net/?q={query}",
    "rbxscripts": "https://rbxscripts.net/?q={query}",
}

ACCESS_OPTIONS = (
    ("all", "الكل", "🌐"),
    ("no_key", "بدون مفتاح", "🔓"),
    ("with_key", "بمفتاح", "🔑"),
)

SOURCE_CHOICES = [
    app_commands.Choice(name="الكل", value="all"),
    app_commands.Choice(name="ScriptBlox", value="scriptblox"),
    app_commands.Choice(name="RScripts", value="rscripts"),
    app_commands.Choice(name="RobloxScripts", value="robloxscripts"),
]

MODE_CHOICES = [
    app_commands.Choice(name="الكل", value="any"),
    app_commands.Choice(name="مجاني", value="free"),
    app_commands.Choice(name="مدفوع", value="paid"),
]

SORT_CHOICES = [
    app_commands.Choice(name="الأكثر تطابقًا", value="relevance"),
    app_commands.Choice(name="المشاهدات", value="views"),
    app_commands.Choice(name="الإعجابات", value="likes"),
    app_commands.Choice(name="الأحدث تحديثًا", value="date"),
]

ORDER_CHOICES = [
    app_commands.Choice(name="تنازلي", value="desc"),
    app_commands.Choice(name="تصاعدي", value="asc"),
]

FETCH_SORT_CHOICES = [
    app_commands.Choice(name="المشاهدات", value="views"),
    app_commands.Choice(name="الإعجابات", value="likeCount"),
    app_commands.Choice(name="تاريخ الإنشاء", value="createdAt"),
    app_commands.Choice(name="تاريخ التحديث", value="updatedAt"),
    app_commands.Choice(name="عدد عدم الإعجاب", value="dislikeCount"),
]

NO_MENTIONS = discord.AllowedMentions.none()


# ============================================================
# PERSISTENCE
# ============================================================

def _load_json_dict(path: str) -> Dict[str, Any]:
    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception as error:
        print(f"⚠️ تعذر قراءة {path}: {error}")
        return {}


def _save_json_dict(path: str, data: Dict[str, Any]) -> bool:
    temp_path = f"{path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
        return True
    except Exception as error:
        print(f"❌ تعذر حفظ {path}: {error}")
        return False


search_rooms: Dict[str, Any] = _load_json_dict(SEARCH_ROOMS_FILE)
search_help_rooms: Dict[str, Any] = _load_json_dict(SEARCH_HELP_ROOMS_FILE)


def save_search_rooms() -> bool:
    return _save_json_dict(SEARCH_ROOMS_FILE, search_rooms)


def get_help_channel_ids(guild_id: int) -> List[str]:
    value = search_help_rooms.get(str(guild_id), [])
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    ids: List[str] = []
    for item in value:
        item = str(item)
        if item.isdigit() and item not in ids:
            ids.append(item)
    return ids[:25]


def set_help_channel_ids(guild_id: int, ids: List[str]) -> bool:
    search_help_rooms[str(guild_id)] = [str(item) for item in ids][:25]
    return _save_json_dict(SEARCH_HELP_ROOMS_FILE, search_help_rooms)


# ============================================================
# GENERIC HELPERS
# ============================================================

def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def truncate(text: Any, limit: int) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[: max(limit - 3, 0)] + "..."


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def as_flag(value: bool) -> str:
    return "true" if value else "false"


def rows_from(data: Any, path: Tuple[str, ...]) -> List[Dict[str, Any]]:
    node = data
    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)
    if not isinstance(node, list):
        return []
    return [item for item in node if isinstance(item, dict)]


def parse_iso(value: Any) -> Optional[datetime]:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def format_relative_ar(value: Any) -> str:
    parsed = parse_iso(value)
    if parsed is None:
        return "غير معروف"
    seconds = int((datetime.now(timezone.utc) - parsed).total_seconds())
    if seconds < 60:
        return "الآن"
    minutes = seconds // 60
    if minutes < 60:
        return f"قبل {minutes} دقيقة"
    hours = minutes // 60
    if hours < 24:
        return f"قبل {hours} ساعة"
    days = hours // 24
    if days < 30:
        return f"قبل {days} يوم"
    months = days // 30
    if months < 12:
        return f"قبل {months} شهر"
    return f"قبل {months // 12} سنة"


def timestamp_of(row: Dict[str, Any]) -> float:
    for field in ("updatedAt", "lastUpdated", "createdAt"):
        parsed = parse_iso(row.get(field))
        if parsed is not None:
            return parsed.timestamp()
    return 0.0


def empty_text(query: str, had_error: bool) -> str:
    if had_error:
        return f"⚠️ بعض مصادر البحث ما ردت، وما لقيت نتيجة مؤكدة لـ **{truncate(query, 60)}**. جرّب بعد شوي."
    return f"❌ ما لقيت نتائج مطابقة لـ **{truncate(query, 60)}**."


# ============================================================
# ARABIC / ENGLISH NAME NORMALIZATION
# ============================================================

_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")


def has_arabic(text: Any) -> bool:
    return bool(_ARABIC_CHAR_RE.search(str(text or "")))


def normalize_game_name(text: Any) -> str:
    if not text:
        return ""
    value = str(text).lower().strip()
    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ة", "ه")
        .replace("ى", "ي")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ـ", "")
    )
    value = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    words = []
    for word in value.split():
        words.append(word[2:] if len(word) > 4 and word.startswith("ال") else word)
    return " ".join(words)


def compact_game_name(text: Any) -> str:
    normalized = normalize_game_name(text)
    normalized = re.sub(r"(.)\1{1,}", r"\1", normalized)
    return normalized.replace(" ", "")


def _word_set(words) -> frozenset:
    return frozenset(normalize_game_name(word) for word in words)


# ============================================================
# ARABIC → LATIN TRANSLITERATION
# ============================================================

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

_AR_WORD_MAP: Dict[str, str] = {}
for _word, _english in _AR_WORD_SOURCE.items():
    _normalized_word = normalize_game_name(_word)
    if _normalized_word:
        _AR_WORD_MAP[_normalized_word] = _english

# نسختان صوتيتان لأن الحروف العربية تُنطق بأكثر من طريقة (ق = g أو q، ج = j أو g ...).
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


def _translit_word(word: str, variant: int) -> str:
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


def arabic_to_latin_queries(text: Any, limit: int = 2) -> List[str]:
    normalized = normalize_game_name(text)
    if not normalized or not has_arabic(normalized):
        return []

    results: List[str] = []
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


def latin_skeleton(text: Any) -> str:
    value = re.sub(r"[^a-z0-9]", "", str(text or "").lower())
    for old, new in (
        ("x", "ks"), ("ph", "f"), ("ck", "k"), ("sh", "s"),
        ("th", "t"), ("kh", "k"), ("ch", "s"),
    ):
        value = value.replace(old, new)
    value = value.translate(str.maketrans({"q": "k", "c": "k", "v": "f", "p": "b", "z": "s", "j": "g"}))
    value = re.sub(r"[aeiouyw]", "", value)
    return re.sub(r"(.)\1+", r"\1", value)


def phonetic_similarity(query: str, text: str) -> float:
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
            ratio = difflib.SequenceMatcher(None, skeleton_query, skeleton_text).ratio()
        best = max(best, ratio)
    return best


_NOISE_WORDS = {
    "ماب", "الماب", "سكربت", "سكريبت", "سكربتات", "اسكربت", "لعبه", "لعبة",
    "بوت", "ابحث", "بحث", "عن", "ابي", "ابغى", "ابغا", "اريد", "ابيكم", "ابيها",
    "هات", "جيب", "اعطني", "عطني", "تكفى", "تكفون", "لو", "ممكن", "احتاج", "احتاجه",
    "please", "pls", "script", "scripts", "map", "game", "find", "search", "get", "give", "me",
    "for", "the", "a", "an", "roblox", "روبلوكس",
}


@lru_cache(maxsize=512)
def search_query_candidates(query: str) -> Tuple[str, ...]:
    """يبني صيغ بحث متعددة من كلام العضو، حتى لو أضاف كلامًا لا علاقة له باسم الماب."""
    query = clean_text(query)
    if not query:
        return ()

    output: List[str] = []
    seen = set()

    def add(value: str) -> None:
        value = clean_text(value)
        key = normalize_game_name(value)
        if not value or not key or key in seen:
            return
        seen.add(key)
        output.append(value)

    # الأصل أولًا: إذا كتب العضو اسم الماب وحده، تبقى الدقة كما هي.
    add(query)

    tokens = normalize_game_name(query).split()
    useful = [token for token in tokens if token not in _NOISE_WORDS and len(token) >= 2]

    if useful:
        add(" ".join(useful))
        for size in (3, 2):
            for start in range(max(0, len(useful) - size + 1)):
                add(" ".join(useful[start:start + size]))
        for token in useful:
            if len(token) >= 4:
                add(token)

    if has_arabic(query):
        for item in arabic_to_latin_queries(query, limit=4):
            add(item)
        if useful:
            for item in arabic_to_latin_queries(" ".join(useful), limit=4):
                add(item)

    return tuple(output[:10])


# ============================================================
# RELEVANCE / RANKING
# ============================================================

def name_relevance(name: Any, query: Any) -> float:
    game = clean_text(name)
    q = clean_text(query)
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
    if q_norm in game_norm or (len(q_compact) >= 3 and q_compact in game_compact):
        return 0.90
    if game_norm in q_norm and len(game_compact) >= 3:
        return 0.86

    best = max(
        difflib.SequenceMatcher(None, q_norm, game_norm).ratio(),
        phonetic_similarity(q_norm, game_norm),
    )
    for candidate in search_query_candidates(q):
        cand_norm = normalize_game_name(candidate)
        if not cand_norm:
            continue
        cand_compact = compact_game_name(cand_norm)
        if cand_norm == game_norm or cand_compact == game_compact:
            return 1.0
        if cand_norm in game_norm or (len(cand_compact) >= 3 and cand_compact in game_compact):
            best = max(best, 0.90)
        else:
            best = max(
                best,
                difflib.SequenceMatcher(None, cand_norm, game_norm).ratio(),
                phonetic_similarity(cand_norm, game_norm),
            )
    return min(1.0, best)


def row_relevance(row: Dict[str, Any], query: str) -> float:
    game_score = name_relevance(row.get("gameName"), query) if row.get("gameName") else 0.0
    title_score = name_relevance(row.get("title"), query) * 0.85
    return max(game_score, title_score)


def rank_score(row: Dict[str, Any], query: str) -> float:
    relevance = row_relevance(row, query)
    title_score = name_relevance(row.get("title"), query)
    views = min(1.0, math.log10(max(to_int(row.get("views")), 0) + 1) / 6)
    likes = min(1.0, math.log10(max(to_int(row.get("likes")), 0) + 1) / 5)
    source_bonus = {"scriptblox": 0.04, "robloxscripts": 0.035, "rscripts": 0.03}.get(row.get("_fime_api", ""), 0.0)
    return relevance * 0.72 + title_score * 0.16 + views * 0.07 + likes * 0.05 + source_bonus


# ============================================================
# SCRIPT ROW HELPERS
# ============================================================

_KEY_TRUE_VALUES = {"true", "yes", "1", "required", "key", "withkey", "with_key", "keysystem"}
_KEY_TEXT_RE = re.compile(r"\b(key system|key required|requires key|keysystem)\b")
_NO_KEY_TEXT_RE = re.compile(r"\b(no key|no keys|without key|no key system)\b")
_KEY_FIELDS = (
    "keySystem", "key_system", "requiresKey", "requires_key", "keyRequired",
    "key_required", "hasKeySystem", "has_key_system", "isKey", "key",
)


def script_needs_key(row: Dict[str, Any]) -> bool:
    if clean_text(row.get("keyLink")):
        return True

    for field in _KEY_FIELDS:
        value = row.get(field)
        if isinstance(value, bool):
            if value:
                return True
        elif isinstance(value, (int, float)) and value == 1:
            return True
        elif isinstance(value, str) and value.strip().lower() in _KEY_TRUE_VALUES:
            return True
        elif isinstance(value, dict):
            for nested_field in ("required", "enabled", "active", "hasKey", "has_key"):
                nested = value.get(nested_field)
                if nested is True or nested == 1:
                    return True
                if isinstance(nested, str) and nested.strip().lower() in _KEY_TRUE_VALUES:
                    return True

    for field in ("description", "desc", "notes", "status"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        text = normalize_game_name(value)
        if _NO_KEY_TEXT_RE.search(text) or "بدون مفتاح" in text:
            continue
        if _KEY_TEXT_RE.search(text) or "مفتاح" in text or "كي سيستم" in text:
            return True
    return False


def _is_verified(row: Dict[str, Any]) -> bool:
    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    return bool(row.get("verified") or user.get("verified"))


def _is_paid(row: Dict[str, Any]) -> bool:
    if clean_text(row.get("scriptType")).lower() == "paid":
        return True
    return bool(row.get("paid"))


def _is_patched(row: Dict[str, Any]) -> bool:
    return bool(row.get("isPatched"))


def _is_universal(row: Dict[str, Any]) -> bool:
    return bool(row.get("isUniversal"))


def _is_mobile(row: Dict[str, Any]) -> bool:
    return bool(row.get("mobileReady"))


def row_key(row: Dict[str, Any]) -> str:
    if row.get("_page_url"):
        return row["_page_url"]
    if row.get("_id"):
        return f"{row.get('_fime_api')}:{row['_id']}"
    raw = f"{row.get('title')}|{row.get('gameName')}|{clean_text(row.get('_code'))[:200]}"
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()


def get_static_image_url(*candidates) -> Optional[str]:
    """يرجع أول صورة صالحة (http/https)، ويستبعد GIF و Tenor و Giphy."""
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        url = candidate.strip()
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            continue
        path = parts.path.lower()
        host = parts.netloc.lower()
        if path.endswith((".gif", ".gifv")) or "tenor.com" in host or "giphy.com" in host:
            continue
        return url
    return None


def _normalize_row(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    """يوحّد شكل النتيجة من أي مصدر. الحقول الأصلية تبقى كما هي."""
    item = dict(row)
    game = item.get("game") if isinstance(item.get("game"), dict) else {}

    slug = clean_text(item.get("slug"))
    script_id = clean_text(item.get("_id") or item.get("id") or item.get("scriptId"))
    title = clean_text(item.get("title") or item.get("name")) or "بدون عنوان"

    code = item.get("script")
    code = code.strip() if isinstance(code, str) else ""

    raw_candidate = item.get("rawScript") or item.get("rawScriptUrl") or item.get("rawUrl") or ""
    raw_candidate = raw_candidate.strip() if isinstance(raw_candidate, str) else ""
    if not code and raw_candidate and not raw_candidate.startswith(("http://", "https://")):
        code, raw_candidate = raw_candidate, ""
    if raw_candidate and not raw_candidate.startswith(("http://", "https://")):
        raw_candidate = ""

    if source == "scriptblox":
        page_url = f"https://scriptblox.com/script/{urllib.parse.quote(slug)}" if slug else ""
        raw_url = f"https://rawscripts.net/raw/{urllib.parse.quote(slug)}" if slug else raw_candidate
    elif source == "rscripts":
        page_url = f"https://rscripts.net/script/{urllib.parse.quote(slug)}" if slug else ""
        raw_url = raw_candidate
    else:
        page_url = ""
        for key in ("url", "scriptUrl", "pageUrl", "webUrl", "link"):
            value = clean_text(item.get(key))
            if value.startswith(("http://", "https://")):
                page_url = value
                break
        raw_url = raw_candidate

    item.update({
        "title": truncate(title, 240),
        "gameName": _game_name_of(item),
        "views": to_int(item.get("views", item.get("viewCount"))),
        "likes": to_int(item.get("likes", item.get("likeCount"))),
        "_fime_api": source,
        "_id": script_id,
        "_slug": slug,
        "_code": code,
        "_raw_url": raw_url,
        "_page_url": page_url,
        "_place_id": to_int(game.get("gameId") or game.get("placeId") or item.get("placeId")),
        "_image": get_static_image_url(
            item.get("image"),
            item.get("imageUrl"),
            item.get("thumbnailUrl"),
            game.get("imageUrl"),
            game.get("thumbnailUrl"),
            game.get("image"),
        ),
    })
    return item


def _game_name_of(row: Dict[str, Any]) -> str:
    for field in ("gameName", "game_name", "gameTitle", "placeName", "experienceName"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()

    game = row.get("game")
    if isinstance(game, dict):
        for field in ("name", "title", "displayName", "gameName"):
            value = game.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    elif isinstance(game, str) and game.strip():
        return game.strip()

    nested = row.get("experience") or row.get("place")
    if isinstance(nested, dict):
        for field in ("name", "title", "displayName"):
            value = nested.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


# ============================================================
# FILTERS / SORTING
# ============================================================

def apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, Any], query: str = "") -> List[Dict[str, Any]]:
    mode = filters.get("mode", "any")
    checks = (
        ("verified", _is_verified),
        ("patched", _is_patched),
        ("universal", _is_universal),
        ("mobile_only", _is_mobile),
    )

    output = []
    for row in rows:
        if mode == "free" and _is_paid(row):
            continue
        if mode == "paid" and not _is_paid(row):
            continue

        skip = False
        for key, check in checks:
            wanted = filters.get(key)
            if wanted is not None and bool(check(row)) != bool(wanted):
                skip = True
                break
        if skip:
            continue

        wanted_key = filters.get("key_system")
        if wanted_key is not None and script_needs_key(row) != bool(wanted_key):
            continue

        output.append(row)

    sort_by = filters.get("sort_by", "relevance")
    reverse = filters.get("sort_order", "desc") != "asc"
    if sort_by == "views":
        output.sort(key=lambda r: to_int(r.get("views")), reverse=reverse)
    elif sort_by == "likes":
        output.sort(key=lambda r: to_int(r.get("likes")), reverse=reverse)
    elif sort_by == "date":
        output.sort(key=timestamp_of, reverse=reverse)
    elif query:
        output.sort(key=lambda r: rank_score(r, query), reverse=True)
    return output


# ============================================================
# HTTP CLIENT
# ============================================================

class HttpClient:
    """عميل HTTP مشترك: جلسة واحدة، حد للتزامن، ومهلة لكل طلب."""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._sem: Optional[asyncio.Semaphore] = None

    def _ensure(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_TOTAL, connect=2.5),
            )
        if self._sem is None:
            self._sem = asyncio.Semaphore(HTTP_CONCURRENCY)
        return self._session

    async def get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None,
                       headers: Optional[Dict[str, str]] = None) -> Tuple[Any, bool]:
        """يرجع (البيانات, هل_فيه_خطأ_شبكة_أو_خادم)."""
        session = self._ensure()
        async with self._sem:
            try:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status == 429 or response.status >= 500:
                        return None, True
                    if response.status != 200:
                        return None, False
                    return await response.json(content_type=None), False
            except (asyncio.TimeoutError, aiohttp.ClientError):
                return None, True
            except Exception as error:
                print(f"⚠️ HTTP JSON error ({url}): {error}")
                return None, True

    async def get_text(self, url: str) -> Tuple[str, bool]:
        session = self._ensure()
        async with self._sem:
            try:
                async with session.get(url, headers={"Accept": "text/html"}) as response:
                    if response.status != 200:
                        return "", response.status >= 500
                    return await response.text(errors="ignore"), False
            except (asyncio.TimeoutError, aiohttp.ClientError):
                return "", True
            except Exception as error:
                print(f"⚠️ HTTP text error ({url}): {error}")
                return "", True

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()


# ============================================================
# SOURCE ADAPTERS
# ============================================================

async def _src_scriptblox(http: HttpClient, query: str, page: int):
    data, error = await http.get_json(
        "https://scriptblox.com/api/script/search",
        params={
            "q": query,
            "page": page,
            "max": AUTO_SEARCH_PAGE_SIZE,
            "sortBy": "accuracy",
            "order": "desc",
            "strict": "false",
        },
    )
    rows = [_normalize_row(item, "scriptblox") for item in rows_from(data, ("result", "scripts"))]
    return rows, error


async def _src_robloxscripts(http: HttpClient, query: str, page: int):
    data, error = await http.get_json(
        "https://robloxscripts.com/api/v1/scripts",
        params={"q": query, "page": page, "limit": 50, "sort": "most-liked"},
    )
    rows = [_normalize_row(item, "robloxscripts") for item in rows_from(data, ("data",))]
    return rows, error


async def _src_rscripts(http: HttpClient, query: str, page: int):
    if RSCRIPTS_API_KEY:
        data, error = await http.get_json(
            "https://api.rscripts.net/v1/search",
            params={
                "q": query,
                "index": "scripts",
                "page": page,
                "limit": AUTO_SEARCH_PAGE_SIZE,
                "htmlDescription": "false",
                "includeScript": "false",
            },
            headers={"Authorization": f"Bearer {RSCRIPTS_API_KEY}"},
        )
        items = rows_from(data, ("data", "scripts"))
    else:
        # بدون مفتاح نستخدم الـ API العام، وإلا ما يرجع شيء.
        data, error = await http.get_json(
            "https://rscripts.net/api/v2/scripts",
            params={"q": query, "page": page},
        )
        items = rows_from(data, ("scripts",))
    return [_normalize_row(item, "rscripts") for item in items], error


async def _src_html(http: HttpClient, source: str, query: str):
    """مصدر HTML احتياطي: يلتقط روابط نفس الموقع فقط."""
    url = HTML_SOURCES[source].format(query=urllib.parse.quote_plus(query))
    html, error = await http.get_text(url)
    if not html:
        return [], error

    link_re = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    base_host = urllib.parse.urlsplit(url).netloc.lower()
    rows, seen = [], set()
    for href, raw_text in link_re.findall(html):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw_text)).strip()
        if len(title) < 4:
            continue
        absolute = urllib.parse.urljoin(url, href.strip())
        parts = urllib.parse.urlsplit(absolute)
        if parts.scheme not in ("http", "https") or parts.netloc.lower() != base_host:
            continue
        key = absolute.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        rows.append(_normalize_row({"title": truncate(title, 180), "url": key}, source))
        if len(rows) >= 40:
            break
    return rows, False


PAGED_SOURCES = {
    "scriptblox": (_src_scriptblox, AUTO_SEARCH_PAGE_SIZE),
    "robloxscripts": (_src_robloxscripts, 50),
    "rscripts": (_src_rscripts, AUTO_SEARCH_PAGE_SIZE),
}


async def _fetch_pages(http: HttpClient, fetch, query: str, page_size: int, deadline: float):
    """يسحب الصفحات بدفعات من صفحتين. يتوقف إذا الصفحة ما اكتملت أو انتهى الوقت."""
    loop = asyncio.get_running_loop()
    collected: List[Dict[str, Any]] = []
    had_error = False
    page = 1
    while page <= AUTO_SEARCH_MAX_PAGES and loop.time() < deadline:
        batch = list(range(page, min(page + 2, AUTO_SEARCH_MAX_PAGES + 1)))
        results = await asyncio.gather(*(fetch(http, query, p) for p in batch), return_exceptions=True)

        full = True
        for result in results:
            if isinstance(result, BaseException):
                had_error = True
                full = False
                continue
            rows, error = result
            had_error = had_error or error
            collected.extend(rows)
            if len(rows) < page_size:
                full = False
        if not full:
            break
        page = batch[-1] + 1
    return collected, had_error


# ============================================================
# COPY / DELIVERY
# ============================================================

async def resolve_copy_text(http: HttpClient, row: Dict[str, Any]) -> str:
    """يرجع نص الكود الجاهز للنسخ (بدون أي تنسيق)."""
    code = clean_text(row.get("_code"))

    if not code and row.get("_fime_api") == "scriptblox" and row.get("_slug"):
        data, _ = await http.get_json(
            f"https://scriptblox.com/api/script/{urllib.parse.quote(row['_slug'])}"
        )
        script = data.get("script") if isinstance(data, dict) else None
        if isinstance(script, dict):
            code = clean_text(script.get("script"))
            if code:
                row["_code"] = code

    if code:
        return code

    raw_url = clean_text(row.get("_raw_url"))
    if raw_url:
        return f'loadstring(game:HttpGet("{raw_url}"))()'
    return ""


async def send_copy_text(followup, text: str, title: str) -> None:
    """يرسل النص خامًا بدون ``` . إذا كان طويلًا يرسله كملف .lua."""
    if len(text) <= COPY_TEXT_LIMIT:
        await followup.send(text, ephemeral=True, allowed_mentions=NO_MENTIONS)
        return

    safe_name = re.sub(r"[^\w\-]+", "_", clean_text(title)).strip("_")[:40] or "script"
    file = discord.File(io.BytesIO(text.encode("utf-8")), filename=f"{safe_name}.lua")
    await followup.send(
        "📜 الكود طويل، أرفقته كملف.",
        file=file,
        ephemeral=True,
        allowed_mentions=NO_MENTIONS,
    )


# ============================================================
# EMBEDS
# ============================================================

def build_script_embed(row: Dict[str, Any], index: int, total: int) -> discord.Embed:
    source = row.get("_fime_api", "")
    embed = discord.Embed(
        title=truncate(f"📜 {row.get('title') or 'بدون عنوان'}", 250),
        color=SOURCE_COLORS.get(source, 0x206694),
    )

    page_url = row.get("_page_url")
    if page_url:
        embed.url = page_url

    game = clean_text(row.get("gameName"), "لعبة غير معروفة")
    place_id = to_int(row.get("_place_id"))
    game_value = (
        f"[{truncate(game, 80)}](https://www.roblox.com/games/{place_id})"
        if place_id
        else truncate(game, 80)
    )
    embed.add_field(name="🎮 الماب", value=game_value, inline=False)

    if source == "scriptblox":
        embed.add_field(name="✅ التحقق", value="Verified" if _is_verified(row) else "غير موثق", inline=True)
        embed.add_field(name="💲 النوع", value="مدفوع" if _is_paid(row) else "مجاني", inline=True)
        embed.add_field(name="🌐 يونيفيرسال", value="نعم" if _is_universal(row) else "لا", inline=True)
        embed.add_field(name="🩹 الحالة", value="❌ متضرر" if _is_patched(row) else "✅ يعمل", inline=True)
    elif source == "rscripts":
        embed.add_field(name="📱 الجوال", value="✅ يدعم" if _is_mobile(row) else "❌ لا يدعم", inline=True)
        embed.add_field(name="✅ التحقق", value="Verified" if _is_verified(row) else "غير موثق", inline=True)
        embed.add_field(name="💲 النوع", value="مدفوع" if _is_paid(row) else "مجاني", inline=True)

    embed.add_field(name="👁️ المشاهدات", value=f"{to_int(row.get('views')):,}", inline=True)
    embed.add_field(name="👍 الإعجابات", value=f"{to_int(row.get('likes')):,}", inline=True)

    key_text = "🔑 يحتاج مفتاح" if script_needs_key(row) else "🔓 بدون مفتاح"
    key_link = clean_text(row.get("keyLink"))
    if key_link.startswith(("http://", "https://")) and script_needs_key(row):
        key_text = f"[🔑 يحتاج مفتاح]({key_link})"
    embed.add_field(name="🔐 الوصول", value=key_text, inline=True)

    links = []
    if page_url:
        links.append(f"[فتح الصفحة]({page_url})")
    if row.get("_raw_url"):
        links.append(f"[الكود الخام]({row['_raw_url']})")
    embed.add_field(name="🔗 الروابط", value=" • ".join(links) or "—", inline=False)

    updated = row.get("updatedAt") or row.get("lastUpdated") or row.get("createdAt")
    if updated:
        embed.add_field(name="🕒 آخر تحديث", value=format_relative_ar(updated), inline=True)

    code = clean_text(row.get("_code"))
    if code:
        embed.add_field(name="📜 معاينة الكود", value=f"```\n{truncate(code, 380)}\n```", inline=False)

    user = row.get("user") if isinstance(row.get("user"), dict) else {}
    creator = clean_text(user.get("username"))
    if creator:
        embed.set_author(name=truncate(f"بواسطة {creator}", 250))

    if row.get("_image"):
        embed.set_image(url=row["_image"])

    embed.set_footer(text=f"{SOURCE_NAMES.get(source, 'مصدر خارجي')} • {index}/{total} • Team Fime")
    return embed


# ============================================================
# VIEWS
# ============================================================

class _BaseView(discord.ui.View):
    """أساس مشترك: إضافة أزرار، وتحقق أن صاحب الأمر فقط يتصفح، وإزالة الواجهة عند الانتهاء."""

    def __init__(self, requester_id: int, timeout: float):
        super().__init__(timeout=timeout)
        self.requester_id = requester_id
        self.message = None

    def _add_button(self, label, callback, *, row: int, disabled: bool = False,
                    style=None, emoji=None) -> None:
        button = discord.ui.Button(
            label=label,
            emoji=emoji,
            style=style or discord.ButtonStyle.secondary,
            row=row,
            disabled=disabled,
        )
        button.callback = callback
        self.add_item(button)

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message(
            "🔒 هذي النتائج لصاحب البحث فقط. ابحث بنفسك عشان تتصفح.",
            ephemeral=True,
        )
        return False

    async def on_timeout(self):
        self.clear_items()
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass


class ScriptBrowserView(_BaseView):
    """تصفح النتائج: نتيجة في كل صفحة، فلتر الوصول، زر نسخ، وروابط."""

    def __init__(self, http: HttpClient, requester_id: int, rows: List[Dict[str, Any]],
                 query: str, elapsed: Optional[float] = None):
        super().__init__(requester_id, timeout=300)
        self.http = http
        self.query = query
        self.rows = list(rows)
        self.elapsed = elapsed
        self.access = "all"
        self.index = 0
        self._rebuild()

    # ---- state ----

    def visible_rows(self) -> List[Dict[str, Any]]:
        if self.access == "no_key":
            return [row for row in self.rows if not script_needs_key(row)]
        if self.access == "with_key":
            return [row for row in self.rows if script_needs_key(row)]
        return self.rows

    def current(self) -> Optional[Dict[str, Any]]:
        visible = self.visible_rows()
        if not visible:
            return None
        return visible[min(max(self.index, 0), len(visible) - 1)]

    def header(self) -> str:
        visible = self.visible_rows()
        text = f"✅ **{len(self.rows)} نتيجة** لـ **{truncate(self.query, 60)}**"
        if len(visible) != len(self.rows):
            text += f" • المعروض: {len(visible)}"
        if self.elapsed is not None:
            text += f" • ⚡ {self.elapsed:.1f}s"
        return text + "\nتصفح بالأسهم، وانسخ الكود من زر **نسخ**."

    def build_embed(self) -> discord.Embed:
        row = self.current()
        if row is None:
            return discord.Embed(
                title="لا توجد نتائج بهذا الفلتر",
                description="جرّب فلترًا آخر.",
                color=0x206694,
            )
        return build_script_embed(row, self.index + 1, len(self.visible_rows()))

    def _rebuild(self) -> None:
        visible = self.visible_rows()
        if visible:
            self.index = min(max(self.index, 0), len(visible) - 1)
        else:
            self.index = 0
        row = self.current()

        self.clear_items()

        select = discord.ui.Select(
            placeholder="فلترة حسب الوصول",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=label, value=value, emoji=emoji, default=(value == self.access))
                for value, label, emoji in ACCESS_OPTIONS
            ],
            row=0,
        )
        select.callback = self._on_access
        self.add_item(select)

        self._add_button("◀️", self._prev, row=1, disabled=(not visible or self.index <= 0))
        self.add_item(discord.ui.Button(
            label=f"{self.index + 1}/{len(visible)}" if visible else "0/0",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=1,
        ))
        self._add_button("▶️", self._next, row=1, disabled=(not visible or self.index >= len(visible) - 1))
        self._add_button(
            "نسخ", self._copy, row=1, disabled=(row is None),
            style=discord.ButtonStyle.success, emoji="📋",
        )

        if row:
            if row.get("_page_url"):
                self.add_item(discord.ui.Button(
                    label="فتح الصفحة", url=row["_page_url"],
                    style=discord.ButtonStyle.link, row=2,
                ))
            if row.get("_raw_url"):
                self.add_item(discord.ui.Button(
                    label="الكود الخام", url=row["_raw_url"],
                    style=discord.ButtonStyle.link, row=2,
                ))

    # ---- callbacks ----

    async def _on_access(self, interaction: discord.Interaction):
        if not await self._check_owner(interaction):
            return
        values = interaction.data.get("values") or ["all"]
        self.access = values[0]
        self.index = 0
        self._rebuild()
        await interaction.response.edit_message(content=self.header(), embed=self.build_embed(), view=self)

    async def _move(self, interaction: discord.Interaction, delta: int):
        if not await self._check_owner(interaction):
            return
        self.index += delta
        self._rebuild()
        await interaction.response.edit_message(content=self.header(), embed=self.build_embed(), view=self)

    async def _prev(self, interaction: discord.Interaction):
        await self._move(interaction, -1)

    async def _next(self, interaction: discord.Interaction):
        await self._move(interaction, 1)

    async def _copy(self, interaction: discord.Interaction):
        # النسخ متاح لأي عضو، والرسالة مخفية له فقط.
        row = self.current()
        if row is None:
            await interaction.response.send_message("❌ ما فيه نتيجة حاليًا.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        text = await resolve_copy_text(self.http, row)
        if not text:
            await interaction.followup.send("❌ ما قدرت أجيب الكود من المصدر.", ephemeral=True)
            return
        await send_copy_text(interaction.followup, text, row.get("title", "script"))


class PagerView(_BaseView):
    """تصفح صفحات Embed (مثل قائمة الإكسبلويترات)."""

    def __init__(self, requester_id: int, total_pages: int, render):
        super().__init__(requester_id, timeout=180)
        self.total_pages = max(1, total_pages)
        self.render = render
        self.index = 0
        self._rebuild()

    def _rebuild(self) -> None:
        last = self.total_pages - 1
        self.clear_items()
        self._add_button("⏪", self._first, row=0, disabled=(self.index == 0))
        self._add_button("◀️", self._prev, row=0, disabled=(self.index == 0))
        self.add_item(discord.ui.Button(
            label=f"{self.index + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0,
        ))
        self._add_button("▶️", self._next, row=0, disabled=(self.index >= last))
        self._add_button("⏩", self._last, row=0, disabled=(self.index >= last))

    async def _move(self, interaction: discord.Interaction, index: int):
        if not await self._check_owner(interaction):
            return
        self.index = min(max(index, 0), self.total_pages - 1)
        self._rebuild()
        await interaction.response.edit_message(embed=self.render(self.index), view=self)

    async def _first(self, interaction: discord.Interaction):
        await self._move(interaction, 0)

    async def _prev(self, interaction: discord.Interaction):
        await self._move(interaction, self.index - 1)

    async def _next(self, interaction: discord.Interaction):
        await self._move(interaction, self.index + 1)

    async def _last(self, interaction: discord.Interaction):
        await self._move(interaction, self.total_pages - 1)


class SearchHelpRoomSelect(discord.ui.Select):
    def __init__(self, options: List[discord.SelectOption]):
        super().__init__(
            placeholder="اختر الروم اللي تبي تتوجه له...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        channel = None
        if interaction.guild is not None:
            channel = interaction.guild.get_channel(int(self.values[0]))
        if channel is None:
            await interaction.response.send_message("❌ الروم المحفوظ لم يعد موجودًا.", ephemeral=True)
            return
        await interaction.response.send_message(f"📍 توجه إلى {channel.mention}", ephemeral=True)


class SearchHelpRoomsView(discord.ui.View):
    def __init__(self, guild, channel_ids: List[str]):
        super().__init__(timeout=120)
        options = []
        for channel_id in channel_ids[:25]:
            channel = guild.get_channel(int(channel_id)) if guild is not None else None
            if isinstance(channel, discord.TextChannel):
                options.append(discord.SelectOption(
                    label=truncate(channel.name, 100),
                    value=str(channel.id),
                    emoji="📌",
                ))
        if options:
            self.add_item(SearchHelpRoomSelect(options))


class SearchHelpButtonView(discord.ui.View):
    """يظهر تحت رسالة "ما لقيت نتائج" إذا المالك حدد رومات مساعدة."""

    def __init__(self, guild, requester_id: int):
        super().__init__(timeout=120)
        self.guild_id = guild.id
        self.requester_id = requester_id
        button = discord.ui.Button(
            label="توجه إلى الرومات",
            emoji="📚",
            style=discord.ButtonStyle.primary,
        )
        button.callback = self._open_rooms
        self.add_item(button)

    async def _open_rooms(self, interaction: discord.Interaction):
        ids = get_help_channel_ids(self.guild_id)
        if not ids:
            await interaction.response.send_message("ℹ️ المالك ما حدد رومات للتوجه لها حتى الآن.", ephemeral=True)
            return
        view = SearchHelpRoomsView(interaction.guild, ids)
        if not view.children:
            await interaction.response.send_message("⚠️ الرومات المحددة لم تعد موجودة.", ephemeral=True)
            return
        await interaction.response.send_message("📚 **اختر الروم المناسب:**", view=view, ephemeral=True)


def no_results_view(guild, requester_id: int) -> Optional[discord.ui.View]:
    if guild is None or not get_help_channel_ids(guild.id):
        return None
    return SearchHelpButtonView(guild, requester_id)


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔍 Team Fime • بحث السكربتات",
        description=(
            "ابحث عن السكربتات من ScriptBlox و RScripts و RobloxScripts.\n"
            "اكتب اسم الماب مباشرة في روم البحث التلقائي، أو استخدم الأوامر."
        ),
        color=0x3498DB,
    )
    embed.add_field(
        name="🔎 البحث",
        value=(
            "`/search query` بحث في كل المصادر مع فلاتر\n"
            "`!search <اسم>` بحث سريع في كل المصادر\n"
            "اكتب اسم الماب في روم البحث التلقائي"
        ),
        inline=False,
    )
    embed.add_field(
        name="📚 التصفح",
        value=(
            "`/fetch` تصفح سكربتات ScriptBlox مع فلاتر\n"
            "`/trending` الأكثر رواجًا الآن\n"
            "`/script id` سكربت محدد بالمعرف أو الـ slug\n"
            "`/rscripts_fetch` تصفح RScripts\n"
            "`/rscripts_by_user username` سكربتات صانع معين\n"
            "`/executors` قائمة الإكسبلويترات"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠️ الإدارة (صلاحية إدارة السيرفر)",
        value=(
            "`/setscriptroom` تحديد روم البحث التلقائي\n"
            "`/searchroom` عرض روم البحث الحالي\n"
            "`/addsearchhelproom` / `/removesearchhelproom` رومات المساعدة\n"
            "`/searchhelprooms` عرض رومات المساعدة\n"
            "`!تحديد_روم` / `!الغاء_روم_البحث` / `!روم_البحث`"
        ),
        inline=False,
    )
    embed.set_footer(text="Team Fime • Game Search v8.0")
    return embed


# ============================================================
# COG
# ============================================================

class GameSearchCog(commands.Cog):
    """بحث السكربتات: تلقائي داخل روم محددة، وأوامر سلاش وبريفكس."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http = HttpClient()
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._inflight: Dict[str, asyncio.Task] = {}
        self._cooldowns: Dict[str, float] = {}

    def cog_unload(self):
        for task in list(self._inflight.values()):
            task.cancel()
        try:
            asyncio.get_running_loop().create_task(self.http.close())
        except RuntimeError:
            pass

    # -----------------------------------------------------
    # cooldown + cache
    # -----------------------------------------------------

    def _on_cooldown(self, user_id: int, guild_id: int) -> bool:
        key = f"{guild_id}:{user_id}"
        now = time.monotonic()
        last = self._cooldowns.get(key)
        if last is not None and now - last < AUTO_SEARCH_COOLDOWN:
            return True
        self._cooldowns[key] = now
        if len(self._cooldowns) > 5000:
            cutoff = now - 60
            for stale in [k for k, v in self._cooldowns.items() if v < cutoff]:
                self._cooldowns.pop(stale, None)
        return False

    def _cache_get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        item = self._cache.get(key)
        if not item:
            return None
        if time.monotonic() - item["ts"] > AUTO_SEARCH_CACHE_TTL:
            self._cache.pop(key, None)
            return None
        return [dict(row) for row in item["rows"]]

    def _cache_set(self, key: str, rows: List[Dict[str, Any]]) -> None:
        self._cache[key] = {"ts": time.monotonic(), "rows": [dict(row) for row in rows]}
        if len(self._cache) > 200:
            now = time.monotonic()
            for stale in [k for k, v in self._cache.items() if now - v["ts"] > AUTO_SEARCH_CACHE_TTL]:
                self._cache.pop(stale, None)

    # -----------------------------------------------------
    # search engine
    # -----------------------------------------------------

    async def search(self, query: str, sources) -> Tuple[List[Dict[str, Any]], bool]:
        """يرجع (النتائج الخام المرتبة, هل_فيه_خطأ). الفلاتر تُطبق بعدها."""
        key = f"{compact_game_name(query)}|{','.join(sorted(sources))}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached, False

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._run_search(query, tuple(sources), key))
            self._inflight[key] = task
            task.add_done_callback(lambda _done, k=key: self._inflight.pop(k, None))

        rows, had_error = await asyncio.shield(task)
        return [dict(row) for row in rows], had_error

    async def _run_search(self, query: str, sources: Tuple[str, ...], cache_key: str):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + AUTO_SEARCH_DEADLINE
        candidates = list(search_query_candidates(query))[:AUTO_SEARCH_MAX_QUERIES] or [query]

        found: List[Dict[str, Any]] = []
        seen = set()
        had_error = False

        try:
            # ندرج صيغ البحث على دفعات من اثنتين. إذا وصلنا للهدف نوقف.
            for start in range(0, len(candidates), 2):
                if loop.time() >= deadline:
                    break

                jobs = []
                for offset, candidate in enumerate(candidates[start:start + 2]):
                    for source in sources:
                        if source in HTML_SOURCES and start + offset != 0:
                            continue
                        jobs.append(self._search_source(source, candidate, deadline))

                results = await asyncio.gather(*jobs, return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        had_error = True
                        continue
                    rows, error = result
                    had_error = had_error or error
                    for row in rows:
                        key = row_key(row)
                        if key in seen:
                            continue
                        if row_relevance(row, query) < RELEVANCE_MIN:
                            continue
                        seen.add(key)
                        found.append(row)

                if len(found) >= AUTO_SEARCH_TARGET:
                    break
        except Exception as error:
            print(f"❌ Search engine error: {error}")
            had_error = True

        found.sort(key=lambda row: rank_score(row, query), reverse=True)
        found = found[:AUTO_SEARCH_MAX_RESULTS]

        if found:
            await self._enrich_thumbnails(found[:40])

        if found or not had_error:
            self._cache_set(cache_key, found)
        return found, had_error

    async def _search_source(self, source: str, candidate: str, deadline: float):
        if source in PAGED_SOURCES:
            fetch, page_size = PAGED_SOURCES[source]
            return await _fetch_pages(self.http, fetch, candidate, page_size, deadline)
        if source in HTML_SOURCES:
            return await _src_html(self.http, source, candidate)
        return [], False

    async def _enrich_thumbnails(self, rows: List[Dict[str, Any]]) -> None:
        """يجيب صور الألعاب من Roblox للنتائج اللي ما عندها صورة (طلب واحد لكل دفعة)."""
        wanted: Dict[int, List[Dict[str, Any]]] = {}
        for row in rows:
            if row.get("_image") or not row.get("_place_id"):
                continue
            wanted.setdefault(row["_place_id"], []).append(row)
        if not wanted:
            return

        place_ids = list(wanted)[:8]
        try:
            data, _ = await self.http.get_json(
                "https://thumbnails.roblox.com/v1/places/gameicons",
                params={
                    "placeIds": ",".join(str(pid) for pid in place_ids),
                    "returnPolicy": "PlaceHolder",
                    "size": "512x512",
                    "format": "Png",
                    "isCircular": "false",
                },
            )
            for item in rows_from(data, ("data",)):
                place_id = to_int(item.get("targetId"))
                image = get_static_image_url(item.get("imageUrl"))
                if place_id in wanted and image:
                    for row in wanted[place_id]:
                        row["_image"] = image
        except Exception as error:
            print(f"⚠️ Roblox thumbnail lookup skipped: {error}")

    # -----------------------------------------------------
    # other fetchers
    # -----------------------------------------------------

    async def _fetch_trending(self, api: str) -> Tuple[List[Dict[str, Any]], bool]:
        if api == "scriptblox":
            data, error = await self.http.get_json("https://scriptblox.com/api/script/trending")
            metas = rows_from(data, ("result", "scripts"))[:12]
            slugs = [clean_text(meta.get("slug")) for meta in metas if clean_text(meta.get("slug"))]
            payloads = await asyncio.gather(
                *(self.http.get_json(f"https://scriptblox.com/api/script/{urllib.parse.quote(s)}") for s in slugs),
                return_exceptions=True,
            )
            rows = []
            for payload in payloads:
                if isinstance(payload, BaseException):
                    continue
                body, _ = payload
                script = body.get("script") if isinstance(body, dict) else None
                if isinstance(script, dict):
                    rows.append(_normalize_row(script, "scriptblox"))
            return rows, bool(error and not rows)

        data, error = await self.http.get_json("https://rscripts.net/api/v2/trending")
        rows = []
        for item in rows_from(data, ("success",)):
            script = item.get("script") if isinstance(item.get("script"), dict) else None
            if not script:
                continue
            merged = dict(script)
            merged.setdefault("views", item.get("views", 0))
            if isinstance(item.get("user"), dict):
                merged.setdefault("user", item["user"])
            rows.append(_normalize_row(merged, "rscripts"))
        return rows, bool(error and not rows)

    async def _fetch_one(self, api: str, script_id: str) -> Optional[Dict[str, Any]]:
        if api == "scriptblox":
            data, _ = await self.http.get_json(
                f"https://scriptblox.com/api/script/{urllib.parse.quote(script_id)}"
            )
            script = data.get("script") if isinstance(data, dict) else None
            return _normalize_row(script, "scriptblox") if isinstance(script, dict) else None

        data, _ = await self.http.get_json("https://rscripts.net/api/v2/script", params={"id": script_id})
        items = rows_from(data, ("script",))
        return _normalize_row(items[0], "rscripts") if items else None

    async def _fetch_rscripts_user(self, username: str) -> List[Dict[str, Any]]:
        """يسحب عدة صفحات ثم يفلتر بالمستخدم محليًا، لأن الفلتر على السيرفر غير مضمون."""
        tasks = [
            self.http.get_json(
                "https://rscripts.net/api/v2/scripts",
                params={"page": page, "orderBy": "date", "sort": "desc", "username": username},
                headers={"Username": username},
            )
            for page in range(1, 5)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        wanted = username.lower()
        rows, seen = [], set()
        for result in results:
            if isinstance(result, BaseException):
                continue
            data, _ = result
            for item in rows_from(data, ("scripts",)):
                owner = item.get("user") if isinstance(item.get("user"), dict) else {}
                if clean_text(owner.get("username")).lower() != wanted:
                    continue
                slug = clean_text(item.get("slug")) or clean_text(item.get("title"))
                if slug in seen:
                    continue
                seen.add(slug)
                rows.append(_normalize_row(item, "rscripts"))
        return rows

    # -----------------------------------------------------
    # delivery helpers
    # -----------------------------------------------------

    async def _send_rows_via_interaction(self, interaction: discord.Interaction, rows, query: str,
                                         had_error: bool = False) -> None:
        if not rows:
            kwargs: Dict[str, Any] = {
                "content": empty_text(query, had_error),
                "allowed_mentions": NO_MENTIONS,
            }
            view = no_results_view(interaction.guild, interaction.user.id)
            if view is not None:
                kwargs["view"] = view
            await interaction.followup.send(**kwargs)
            return

        view = ScriptBrowserView(self.http, interaction.user.id, rows, query)
        message = await interaction.followup.send(
            content=view.header(),
            embed=view.build_embed(),
            view=view,
            allowed_mentions=NO_MENTIONS,
            wait=True,
        )
        view.message = message

    async def _edit_or_send(self, status: discord.Message, content: str,
                            embed: Optional[discord.Embed] = None,
                            view: Optional[discord.ui.View] = None) -> discord.Message:
        try:
            return await status.edit(content=content, embed=embed, view=view)
        except discord.HTTPException:
            kwargs: Dict[str, Any] = {"content": content, "allowed_mentions": NO_MENTIONS}
            if embed is not None:
                kwargs["embed"] = embed
            if view is not None:
                kwargs["view"] = view
            return await status.channel.send(**kwargs)

    async def _run_message_search(self, message: discord.Message, query: str, sources, filters: Dict[str, Any]):
        started = time.perf_counter()
        status = await message.reply("🔎 جاري البحث...", mention_author=False)

        rows, had_error = await self.search(query, sources)
        rows = apply_filters(rows, filters, query)
        elapsed = time.perf_counter() - started

        if not rows:
            sent = await self._edit_or_send(
                status,
                empty_text(query, had_error),
                None,
                no_results_view(message.guild, message.author.id),
            )
            return

        view = ScriptBrowserView(self.http, message.author.id, rows, query, elapsed)
        sent = await self._edit_or_send(status, view.header(), view.build_embed(), view)
        view.message = sent

    # -----------------------------------------------------
    # listener: بحث تلقائي داخل روم البحث
    # -----------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        room_id = search_rooms.get(str(message.guild.id))
        if not room_id or str(message.channel.id) != str(room_id):
            return

        query = clean_text(message.content)
        if not (2 <= len(query) <= 120):
            return
        if query.startswith(("!", "/", "http://", "https://")):
            return
        if self._on_cooldown(message.author.id, message.guild.id):
            return

        try:
            await self._run_message_search(message, query, ENABLED_SOURCES, {})
        except Exception as error:
            print(f"❌ Automatic search error: {error}")
            try:
                await message.reply("❌ صار خطأ أثناء البحث، حاول مرة ثانية.", mention_author=False)
            except Exception:
                pass

    # =====================================================
    # PREFIX COMMANDS
    # =====================================================

    @commands.command(name="bothelp")
    async def prefix_help(self, ctx: commands.Context):
        await ctx.send(embed=build_help_embed())

    @commands.command(name="search")
    async def prefix_search(self, ctx: commands.Context, *, query: str = ""):
        query = clean_text(query)
        if len(query) < 2:
            await ctx.send(embed=build_help_embed())
            return
        if self._on_cooldown(ctx.author.id, ctx.guild.id):
            await ctx.reply("⏳ خفف شوي، جرب بعد ثواني.", mention_author=False)
            return
        await self._run_message_search(ctx.message, query, ENABLED_SOURCES, {})

    @commands.command(name="تحديد_روم")
    @commands.has_permissions(manage_guild=True)
    async def prefix_set_search_room(self, ctx: commands.Context):
        search_rooms[str(ctx.guild.id)] = str(ctx.channel.id)
        save_search_rooms()
        await ctx.send(
            "✅ تم تحديد هذا الروم كروم البحث التلقائي.\n"
            "من الآن أي عضو يكتب اسم ماب هنا، البوت يبحث عنه تلقائيًا."
        )

    @commands.command(name="روم_البحث")
    async def prefix_show_search_room(self, ctx: commands.Context):
        channel_id = search_rooms.get(str(ctx.guild.id))
        if not channel_id:
            await ctx.send("❌ ما تم تحديد روم للبحث التلقائي في هذا السيرفر.")
            return
        channel = ctx.guild.get_channel(int(channel_id))
        if not channel:
            await ctx.send("⚠️ روم البحث المحفوظ لم يعد موجودًا.")
            return
        await ctx.send(f"🔎 روم البحث التلقائي الحالي: {channel.mention}")

    @commands.command(name="الغاء_روم_البحث")
    @commands.has_permissions(manage_guild=True)
    async def prefix_remove_search_room(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        if guild_id in search_rooms:
            del search_rooms[guild_id]
            save_search_rooms()
            await ctx.send("✅ تم إلغاء روم البحث التلقائي.")
        else:
            await ctx.send("ℹ️ ما فيه روم بحث محدد أصلًا.")

    @commands.command(name="اضافة_روم_مساعدة")
    @commands.has_permissions(manage_guild=True)
    async def prefix_add_help_room(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        ids = get_help_channel_ids(ctx.guild.id)
        if str(channel.id) not in ids:
            ids.append(str(channel.id))
        set_help_channel_ids(ctx.guild.id, ids)
        await ctx.send(f"✅ تمت إضافة {channel.mention} لقائمة رومات المساعدة.")

    @commands.command(name="حذف_روم_مساعدة")
    @commands.has_permissions(manage_guild=True)
    async def prefix_remove_help_room(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        ids = [item for item in get_help_channel_ids(ctx.guild.id) if item != str(channel.id)]
        set_help_channel_ids(ctx.guild.id, ids)
        await ctx.send(f"🗑️ تمت إزالة {channel.mention} من القائمة.")

    # =====================================================
    # SLASH: عام
    # =====================================================

    @app_commands.command(name="bothelp", description="عرض مساعدة بوت البحث")
    async def slash_help(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_help_embed(), ephemeral=True)

    @app_commands.command(name="search", description="البحث عن سكربتات من المصادر المتاحة")
    @app_commands.guild_only()
    @app_commands.describe(
        query="اسم الماب أو السكربت",
        source="المصدر",
        mode="مجاني أو مدفوع",
        verified="موثق فقط (true) أو غير موثق (false)",
        patched="حسب حالة التحديث",
        key_system="مع مفتاح (true) أو بدون (false)",
        universal="يونيفيرسال فقط",
        mobile_only="يعمل على الجوال فقط",
        sort_by="طريقة الترتيب",
        sort_order="الاتجاه",
    )
    @app_commands.choices(source=SOURCE_CHOICES, mode=MODE_CHOICES, sort_by=SORT_CHOICES, sort_order=ORDER_CHOICES)
    async def slash_search(
        self,
        interaction: discord.Interaction,
        query: str,
        source: str = "all",
        mode: str = "any",
        verified: Optional[bool] = None,
        patched: Optional[bool] = None,
        key_system: Optional[bool] = None,
        universal: Optional[bool] = None,
        mobile_only: Optional[bool] = None,
        sort_by: str = "relevance",
        sort_order: str = "desc",
    ):
        query = clean_text(query)
        if len(query) < 2:
            await interaction.response.send_message("❌ اكتب اسم أطول شوي.", ephemeral=True)
            return
        if self._on_cooldown(interaction.user.id, interaction.guild_id or 0):
            await interaction.response.send_message("⏳ خفف شوي، جرب بعد ثواني.", ephemeral=True)
            return

        await interaction.response.defer()

        filters = {
            "mode": mode,
            "verified": verified,
            "patched": patched,
            "key_system": key_system,
            "universal": universal,
            "mobile_only": mobile_only,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        sources = ENABLED_SOURCES if source == "all" else (source,)

        rows, had_error = await self.search(query, sources)
        rows = apply_filters(rows, filters, query)
        await self._send_rows_via_interaction(interaction, rows, query, had_error)

    @app_commands.command(name="fetch", description="تصفح سكربتات ScriptBlox مع فلاتر")
    @app_commands.guild_only()
    @app_commands.describe(
        mode="مجاني أو مدفوع",
        verified="موثق فقط",
        patched="حسب حالة التحديث",
        key_system="مع مفتاح أو بدون",
        universal="يونيفيرسال فقط",
        sort_by="الترتيب",
        sort_order="الاتجاه",
        owner="اسم صانع السكربت",
        place_id="معرف مكان اللعب (Place ID)",
        max_results="عدد النتائج (1-20)",
    )
    @app_commands.choices(mode=MODE_CHOICES, sort_by=FETCH_SORT_CHOICES, sort_order=ORDER_CHOICES)
    async def slash_fetch(
        self,
        interaction: discord.Interaction,
        mode: str = "any",
        verified: Optional[bool] = None,
        patched: Optional[bool] = None,
        key_system: Optional[bool] = None,
        universal: Optional[bool] = None,
        sort_by: str = "views",
        sort_order: str = "desc",
        owner: Optional[str] = None,
        place_id: Optional[str] = None,
        max_results: app_commands.Range[int, 1, 20] = 20,
    ):
        await interaction.response.defer()

        params: Dict[str, Any] = {"page": 1, "max": max_results, "sortBy": sort_by, "order": sort_order}
        if mode != "any":
            params["mode"] = mode
        if verified is not None:
            params["verified"] = "1" if verified else "0"
        if patched is not None:
            params["patched"] = "1" if patched else "0"
        if key_system is not None:
            params["key"] = "1" if key_system else "0"
        if universal is not None:
            params["universal"] = "1" if universal else "0"
        if owner:
            params["owner"] = owner
        if place_id:
            params["placeId"] = place_id

        data, error = await self.http.get_json("https://scriptblox.com/api/script/fetch", params=params)
        rows = [_normalize_row(item, "scriptblox") for item in rows_from(data, ("result", "scripts"))]
        await self._send_rows_via_interaction(interaction, rows, owner or place_id or "ScriptBlox", error)

    @app_commands.command(name="trending", description="أكثر السكربتات رواجًا الآن")
    @app_commands.guild_only()
    @app_commands.describe(api="المصدر")
    @app_commands.choices(api=[
        app_commands.Choice(name="ScriptBlox", value="scriptblox"),
        app_commands.Choice(name="RScripts", value="rscripts"),
    ])
    async def slash_trending(self, interaction: discord.Interaction, api: str = "scriptblox"):
        await interaction.response.defer()
        rows, error = await self._fetch_trending(api)
        await self._send_rows_via_interaction(interaction, rows, "الرائج الآن", error)

    @app_commands.command(name="script", description="جلب سكربت محدد بالمعرف أو الـ slug")
    @app_commands.guild_only()
    @app_commands.describe(script_id="معرف السكربت أو الـ slug", api="المصدر")
    @app_commands.choices(api=[
        app_commands.Choice(name="ScriptBlox", value="scriptblox"),
        app_commands.Choice(name="RScripts", value="rscripts"),
    ])
    async def slash_script(self, interaction: discord.Interaction, script_id: str, api: str = "scriptblox"):
        await interaction.response.defer()
        row = await self._fetch_one(api, clean_text(script_id))
        if row is None:
            await interaction.followup.send("❌ ما لقيت السكربت بهذا المعرف.", ephemeral=True)
            return
        await self._send_rows_via_interaction(interaction, [row], row.get("title", script_id))

    @app_commands.command(name="executors", description="قائمة الإكسبلويترات المتاحة")
    @app_commands.guild_only()
    async def slash_executors(self, interaction: discord.Interaction):
        await interaction.response.defer()

        data, error = await self.http.get_json("https://scriptblox.com/api/executor/list")
        executors = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        if not executors:
            text = "❌ ما قدرت أجيب قائمة الإكسبلويترات الحين." if error else "ما فيه إكسبلويترات مسجلة حاليًا."
            await interaction.followup.send(text, ephemeral=True)
            return

        per_page = 5
        total_pages = math.ceil(len(executors) / per_page)

        def render(index: int) -> discord.Embed:
            embed = discord.Embed(
                title="🎮 الإكسبلويترات المتاحة",
                description=f"المصدر: ScriptBlox • الصفحة {index + 1}/{total_pages}",
                color=0x206694,
            )
            for item in executors[index * per_page:(index + 1) * per_page]:
                lines = [
                    f"**المنصة:** {clean_text(item.get('platform'), '—')}",
                    f"**النوع:** {clean_text(item.get('type'), '—')}",
                    f"**الحالة:** {'❌ متضرر' if item.get('patched') else '✅ يعمل'}",
                    f"**الإصدار:** {clean_text(item.get('version'), '—')}",
                ]
                links = []
                website = clean_text(item.get("website"))
                discord_link = clean_text(item.get("discord"))
                if website.startswith(("http://", "https://")):
                    links.append(f"[الموقع]({website})")
                if discord_link.startswith(("http://", "https://")):
                    links.append(f"[ديسكورد]({discord_link})")
                if links:
                    lines.append(" • ".join(links))
                embed.add_field(
                    name=truncate(clean_text(item.get("name"), "Unknown"), 250),
                    value="\n".join(lines)[:1024],
                    inline=False,
                )
            embed.set_footer(text="Team Fime • ScriptBlox")
            return embed

        view = PagerView(interaction.user.id, total_pages, render)
        kwargs: Dict[str, Any] = {"embed": render(0), "allowed_mentions": NO_MENTIONS, "wait": True}
        if total_pages > 1:
            kwargs["view"] = view
        message = await interaction.followup.send(**kwargs)
        view.message = message

    @app_commands.command(name="rscripts_fetch", description="تصفح RScripts مع فلاتر")
    @app_commands.guild_only()
    @app_commands.describe(
        verified_only="موثق فقط",
        no_key_system="بدون نظام مفتاح فقط",
        mobile_only="يعمل على الجوال فقط",
        unpatched="غير متضرر فقط",
        order_by="الترتيب حسب (createdAt, updatedAt, views, name)",
        sort="الاتجاه (asc أو desc)",
        max_results="عدد النتائج (1-20)",
    )
    async def slash_rscripts_fetch(
        self,
        interaction: discord.Interaction,
        verified_only: Optional[bool] = None,
        no_key_system: Optional[bool] = None,
        mobile_only: Optional[bool] = None,
        unpatched: Optional[bool] = None,
        order_by: Optional[str] = None,
        sort: Optional[str] = None,
        max_results: app_commands.Range[int, 1, 20] = 20,
    ):
        await interaction.response.defer()

        params: Dict[str, Any] = {"q": "", "page": 1}
        if verified_only is not None:
            params["verifiedOnly"] = as_flag(verified_only)
        if no_key_system is not None:
            params["noKeySystem"] = as_flag(no_key_system)
        if mobile_only is not None:
            params["mobileOnly"] = as_flag(mobile_only)
        if unpatched is not None:
            params["unpatched"] = as_flag(unpatched)
        if order_by:
            params["orderBy"] = order_by
        if sort:
            params["sort"] = sort

        data, error = await self.http.get_json("https://rscripts.net/api/v2/scripts", params=params)
        rows = [_normalize_row(item, "rscripts") for item in rows_from(data, ("scripts",))][:max_results]
        await self._send_rows_via_interaction(interaction, rows, "RScripts", error)

    @app_commands.command(name="rscripts_by_user", description="سكربتات صانع معين في RScripts")
    @app_commands.guild_only()
    @app_commands.describe(username="اسم الصانع")
    async def slash_rscripts_by_user(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer()
        username = clean_text(username)
        rows = await self._fetch_rscripts_user(username)
        await self._send_rows_via_interaction(interaction, rows, f"سكربتات {username}")

    # =====================================================
    # SLASH: روم البحث ورومات المساعدة (صلاحية إدارة السيرفر)
    # =====================================================

    @app_commands.command(name="setscriptroom", description="تحديد روم البحث التلقائي")
    @app_commands.guild_only()
    @app_commands.describe(channel="الروم اللي يصير فيه البحث التلقائي")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_set_search_room(self, interaction: discord.Interaction, channel: discord.TextChannel):
        search_rooms[str(interaction.guild.id)] = str(channel.id)
        save_search_rooms()
        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} كروم البحث التلقائي.\n"
            "🔎 العضو يكتب اسم الماب (عربي أو إنجليزي) والبوت يبحث له فورًا."
        )

    @app_commands.command(name="searchroom", description="عرض روم البحث التلقائي")
    @app_commands.guild_only()
    async def slash_show_search_room(self, interaction: discord.Interaction):
        channel_id = search_rooms.get(str(interaction.guild.id))
        if not channel_id:
            await interaction.response.send_message("❌ ما تم تحديد روم للبحث التلقائي.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("⚠️ روم البحث المحفوظ لم يعد موجودًا.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔎 روم البحث التلقائي الحالي: {channel.mention}")

    @app_commands.command(name="addsearchhelproom", description="إضافة روم يظهر للعضو إذا ما لقى نتيجة")
    @app_commands.guild_only()
    @app_commands.describe(channel="الروم اللي تبي تضيفه")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_add_help_room(self, interaction: discord.Interaction, channel: discord.TextChannel):
        ids = get_help_channel_ids(interaction.guild.id)
        if str(channel.id) not in ids:
            ids.append(str(channel.id))
        set_help_channel_ids(interaction.guild.id, ids)
        await interaction.response.send_message(
            f"✅ تمت إضافة {channel.mention} لقائمة رومات المساعدة.", ephemeral=True
        )

    @app_commands.command(name="removesearchhelproom", description="إزالة روم من رومات المساعدة")
    @app_commands.guild_only()
    @app_commands.describe(channel="الروم اللي تبي تزيله")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_remove_help_room(self, interaction: discord.Interaction, channel: discord.TextChannel):
        ids = [item for item in get_help_channel_ids(interaction.guild.id) if item != str(channel.id)]
        set_help_channel_ids(interaction.guild.id, ids)
        await interaction.response.send_message(f"🗑️ تمت إزالة {channel.mention} من القائمة.", ephemeral=True)

    @app_commands.command(name="searchhelprooms", description="عرض رومات المساعدة المحددة")
    @app_commands.guild_only()
    async def slash_show_help_rooms(self, interaction: discord.Interaction):
        mentions = []
        for channel_id in get_help_channel_ids(interaction.guild.id):
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                mentions.append(channel.mention)
        text = ", ".join(mentions) if mentions else "لا توجد رومات محددة."
        await interaction.response.send_message(f"📚 **رومات المساعدة:**\n{text}", ephemeral=True)


# ============================================================
# SETUP
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(GameSearchCog(bot))
    print("✅ Game search cog loaded (bot4 v8.0).")
