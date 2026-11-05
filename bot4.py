
# ============================================================
# Team Fime - bot4.py
# Professional Game / Script Search System
# Version: 9.0
# discord.py 2.x | aiohttp
# ============================================================

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
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIGURATION
# ============================================================

USER_AGENT = "Team-Fime-Search/9.0"

RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()

CACHE_TTL = 240
MAX_RESULTS = 150
PAGE_SIZE = 25
MAX_PAGES = 3
SEARCH_TIMEOUT = 12
HTTP_TIMEOUT = 7
HTTP_CONCURRENCY = 12

SEARCH_COOLDOWN = 3
RESULT_TIMEOUT = 300

COPY_TEXT_LIMIT = 1900
MIN_RELEVANCE = 0.43

PANEL_COLOR = 0x5865F2

NO_MENTIONS = discord.AllowedMentions.none()

SEARCH_SOURCES = (
    "scriptblox",
    "robloxscripts",
    "rscripts",
    "haxhell",
    "roscripts",
    "rbxscripts",
    "websearch",
)

SOURCE_NAMES = {
    "scriptblox": "ScriptBlox",
    "robloxscripts": "RobloxScripts",
    "rscripts": "RScripts",
    "haxhell": "HaxHell",
    "roscripts": "RoScripts",
    "rbxscripts": "RBXScripts",
    "websearch": "Web Search",
}

SOURCE_COLORS = {
    "scriptblox": 0x2ECC71,
    "robloxscripts": 0xE67E22,
    "rscripts": 0x9B59B6,
    "websearch": 0x3498DB,
}

HTML_SOURCES = {
    "haxhell": "https://haxhell.com/?q={query}",
    "roscripts": "https://roscripts.net/?q={query}",
    "rbxscripts": "https://rbxscripts.net/?q={query}",
}

WEB_SEARCH_SITES = (
    "scriptblox.com",
    "rscripts.net",
    "robloxscripts.com",
    "haxhell.com",
    "roscripts.net",
    "rbxscripts.net",
)


# ============================================================
# TEXT HELPERS
# ============================================================

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def clean(value, default=""):
    if value is None:
        return default
    value = str(value).strip()
    return value or default


def truncate(value, limit):
    value = clean(value)
    return value if len(value) <= limit else value[:limit - 3] + "..."


def to_int(value):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def has_arabic(value):
    return bool(ARABIC_RE.search(str(value or "")))


def normalize(value):
    value = clean(value).lower()

    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ة": "ه",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }

    for old, new in replacements.items():
        value = value.replace(old, new)

    value = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()

    words = []

    for word in value.split():
        if len(word) > 4 and word.startswith("ال"):
            word = word[2:]
        words.append(word)

    return " ".join(words)


ARABIC_WORDS = {
    "ماب": "",
    "روبلوكس": "",
    "سكربت": "",
    "سكريبت": "",
    "سكربتات": "",
    "لعبة": "",
    "تايكون": "tycoon",
    "تايكن": "tycoon",
    "سيمولاتور": "simulator",
    "سيميولاتور": "simulator",
    "اوبي": "obby",
    "تاور": "tower",
    "وورز": "wars",
    "باتل": "battle",
    "فروت": "fruit",
    "فروتس": "fruits",
    "سرفايفل": "survival",
    "ديفنس": "defense",
    "ستوري": "story",
    "لايف": "life",
    "ورلد": "world",
    "كينق": "king",
    "كينج": "king",
    "جاردن": "garden",
    "برينروت": "brainrot",
    "ستيل": "steal",
    "هيرو": "hero",
    "هيروز": "heroes",
    "ايلاند": "island",
    "فارم": "farm",
    "كليكر": "clicker",
    "فايتنق": "fighting",
    "فايتنج": "fighting",
    "ريسنق": "racing",
    "كار": "car",
    "زومبي": "zombie",
    "نينجا": "ninja",
    "انمي": "anime",
    "ماينكرافت": "minecraft",
    "فيش": "fish",
    "سيتي": "city",
    "ستريت": "street",
    "ديث": "death",
    "ريفت": "rift",
    "رايفلز": "rivals",
    "ريفالز": "rivals",
}

NOISE_WORDS = {
    "ماب", "الماب", "سكربت", "سكريبت", "سكربتات",
    "لعبة", "لعبه", "ابحث", "بحث", "عن", "ابي",
    "ابغى", "اريد", "هات", "جيب", "عطني",
    "please", "pls", "script", "scripts",
    "map", "game", "find", "search", "get",
    "give", "me", "for", "the", "roblox",
}


def arabic_queries(query):
    if not has_arabic(query):
        return []

    words = []

    for word in normalize(query).split():
        mapped = ARABIC_WORDS.get(word, word)
        if mapped:
            words.append(mapped)

    translated = " ".join(words).strip()

    return [translated] if translated else []


def query_variants(query):
    output = []
    seen = set()

    def add(value):
        value = clean(value)
        key = normalize(value)

        if key and key not in seen:
            seen.add(key)
            output.append(value)

    add(query)

    words = [
        word for word in normalize(query).split()
        if word not in NOISE_WORDS and len(word) >= 2
    ]

    if words:
        add(" ".join(words))

        for size in (3, 2):
            for i in range(len(words) - size + 1):
                add(" ".join(words[i:i + size]))

        for word in words:
            if len(word) >= 4:
                add(word)

    for translated in arabic_queries(query):
        add(translated)

    return output[:7]


def relevance(title, query):
    title = normalize(title)
    query = normalize(query)

    if not title or not query:
        return 0.0

    if title == query:
        return 1.0

    if query in title:
        return 0.94

    if title in query and len(title) >= 3:
        return 0.88

    best = difflib.SequenceMatcher(
        None, query, title
    ).ratio()

    query_words = set(query.split())
    title_words = set(title.split())

    if query_words and title_words:
        overlap = len(query_words & title_words) / len(query_words)
        best = max(best, overlap * 0.92)

    for candidate in query_variants(query):
        candidate = normalize(candidate)

        if candidate:
            best = max(
                best,
                difflib.SequenceMatcher(
                    None, candidate, title
                ).ratio()
            )

            if candidate in title:
                best = max(best, 0.91)

    return min(best, 1.0)


# ============================================================
# DATA HELPERS
# ============================================================

def rows_from(data, path):
    node = data

    for key in path:
        if not isinstance(node, dict):
            return []
        node = node.get(key)

    if not isinstance(node, list):
        return []

    return [item for item in node if isinstance(item, dict)]


def parse_date(value):
    if not value:
        return None

    try:
        result = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)

        return result

    except (ValueError, TypeError):
        return None


def relative_date(value):
    date = parse_date(value)

    if not date:
        return "Unknown"

    seconds = int(
        (datetime.now(timezone.utc) - date).total_seconds()
    )

    if seconds < 60:
        return "Just now"

    if seconds < 3600:
        return f"{seconds // 60} minutes ago"

    if seconds < 86400:
        return f"{seconds // 3600} hours ago"

    return f"{seconds // 86400} days ago"


def get_game_name(row):
    for key in (
        "gameName",
        "game_name",
        "gameTitle",
        "placeName",
        "experienceName",
    ):
        value = row.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    game = row.get("game")

    if isinstance(game, dict):
        for key in ("name", "title", "displayName"):
            if game.get(key):
                return str(game[key])

    elif isinstance(game, str):
        return game

    return ""


def valid_url(value):
    if not isinstance(value, str):
        return ""

    value = value.strip()

    parts = urllib.parse.urlsplit(value)

    if parts.scheme not in ("http", "https"):
        return ""

    if not parts.netloc:
        return ""

    return value


def normalize_row(row, source):
    item = dict(row)

    slug = clean(item.get("slug"))

    title = clean(
        item.get("title") or item.get("name"),
        "Untitled",
    )

    game = item.get("game")
    if not isinstance(game, dict):
        game = {}

    code = item.get("script")
    code = code.strip() if isinstance(code, str) else ""

    raw_url = ""

    for key in (
        "rawScriptUrl",
        "rawUrl",
        "rawScript",
    ):
        candidate = item.get(key)

        if isinstance(candidate, str):
            if candidate.startswith(("http://", "https://")):
                raw_url = valid_url(candidate)
            elif not code:
                code = candidate.strip()

            if raw_url:
                break

    if source == "scriptblox":
        page_url = (
            "https://scriptblox.com/script/"
            + urllib.parse.quote(slug)
            if slug else ""
        )

        if slug:
            raw_url = (
                "https://rawscripts.net/raw/"
                + urllib.parse.quote(slug)
            )

    elif source == "rscripts":
        page_url = (
            "https://rscripts.net/script/"
            + urllib.parse.quote(slug)
            if slug else ""
        )

    else:
        page_url = ""

        for key in (
            "url",
            "scriptUrl",
            "pageUrl",
            "webUrl",
            "link",
        ):
            page_url = valid_url(item.get(key))
            if page_url:
                break

    image = ""

    for key in (
        "image",
        "imageUrl",
        "thumbnailUrl",
    ):
        image = valid_url(item.get(key))
        if image:
            break

    place_id = to_int(
        game.get("gameId")
        or game.get("placeId")
        or item.get("placeId")
    )

    item.update({
        "title": truncate(title, 240),
        "gameName": get_game_name(item),
        "views": to_int(
            item.get("views", item.get("viewCount"))
        ),
        "likes": to_int(
            item.get("likes", item.get("likeCount"))
        ),
        "_source": source,
        "_code": code,
        "_raw_url": raw_url,
        "_page_url": page_url,
        "_image": image,
        "_place_id": place_id,
    })

    return item


def row_key(row):
    url = row.get("_page_url")

    if url:
        return url.lower()

    raw = (
        str(row.get("title"))
        + "|"
        + str(row.get("gameName"))
        + "|"
        + str(row.get("_source"))
    )

    return hashlib.sha1(
        raw.encode("utf-8", "ignore")
    ).hexdigest()


def get_key_status(row):
    for key in (
        "keySystem",
        "key_system",
        "requiresKey",
        "requires_key",
        "keyRequired",
        "key_required",
    ):
        value = row.get(key)

        if value is True or value == 1:
            return True

        if isinstance(value, str):
            if value.lower() in (
                "true", "yes", "1", "required"
            ):
                return True

    if row.get("keyLink"):
        return True

    description = normalize(
        row.get("description", "")
    )

    if "بدون مفتاح" in description:
        return False

    if "key system" in description:
        return True

    if "requires key" in description:
        return True

    return False


def get_paid_status(row):
    return (
        clean(row.get("scriptType")).lower() == "paid"
        or bool(row.get("paid"))
    )


# ============================================================
# HTTP CLIENT
# ============================================================

class HttpClient:

    def __init__(self):
        self.session = None
        self.semaphore = asyncio.Semaphore(
            HTTP_CONCURRENCY
        )

    def ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                },
                timeout=aiohttp.ClientTimeout(
                    total=HTTP_TIMEOUT,
                    connect=3,
                ),
            )

        return self.session

    async def get_json(
        self,
        url,
        params=None,
        headers=None,
    ):
        session = self.ensure_session()

        async with self.semaphore:
            try:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                ) as response:

                    if response.status != 200:
                        return None, response.status >= 500 or response.status == 429

                    return await response.json(
                        content_type=None
                    ), False

            except Exception as error:
                print(
                    f"[bot4] JSON request failed: {error}"
                )
                return None, True

    async def get_text(self, url):
        session = self.ensure_session()

        async with self.semaphore:
            try:
                async with session.get(
                    url,
                    headers={
                        "Accept": "text/html",
                    },
                ) as response:

                    if response.status != 200:
                        return "", response.status >= 500

                    return await response.text(
                        errors="ignore"
                    ), False

            except Exception as error:
                print(
                    f"[bot4] HTML request failed: {error}"
                )
                return "", True

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


# ============================================================
# SEARCH SOURCES
# ============================================================

async def source_scriptblox(http, query, page):
    data, error = await http.get_json(
        "https://scriptblox.com/api/script/search",
        params={
            "q": query,
            "page": page,
            "max": PAGE_SIZE,
            "sortBy": "accuracy",
            "order": "desc",
            "strict": "false",
        },
    )

    rows = [
        normalize_row(item, "scriptblox")
        for item in rows_from(
            data, ("result", "scripts")
        )
    ]

    return rows, error


async def source_robloxscripts(http, query, page):
    data, error = await http.get_json(
        "https://robloxscripts.com/api/v1/scripts",
        params={
            "q": query,
            "page": page,
            "limit": PAGE_SIZE,
            "sort": "most-liked",
        },
    )

    rows = [
        normalize_row(item, "robloxscripts")
        for item in rows_from(data, ("data",))
    ]

    return rows, error


async def source_rscripts(http, query, page):
    if RSCRIPTS_API_KEY:
        data, error = await http.get_json(
            "https://api.rscripts.net/v1/search",
            params={
                "q": query,
                "index": "scripts",
                "page": page,
                "limit": PAGE_SIZE,
                "htmlDescription": "false",
                "includeScript": "false",
            },
            headers={
                "Authorization": f"Bearer {RSCRIPTS_API_KEY}"
            },
        )

        items = rows_from(data, ("data", "scripts"))

    else:
        data, error = await http.get_json(
            "https://rscripts.net/api/v2/scripts",
            params={
                "q": query,
                "page": page,
            },
        )

        items = rows_from(data, ("scripts",))

    return [
        normalize_row(item, "rscripts")
        for item in items
    ], error


async def source_html(http, source, query):
    url = HTML_SOURCES[source].format(
        query=urllib.parse.quote_plus(query)
    )

    html, error = await http.get_text(url)

    if not html:
        return [], error

    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.I | re.S,
    )

    host = urllib.parse.urlsplit(url).netloc.lower()

    results = []
    seen = set()

    for href, raw_title in pattern.findall(html):
        title = re.sub(
            r"\s+",
            " ",
            re.sub(r"<[^>]+>", " ", raw_title),
        ).strip()

        if len(title) < 4:
            continue

        absolute = urllib.parse.urljoin(
            url, href.strip()
        )

        parts = urllib.parse.urlsplit(absolute)

        if parts.scheme not in ("http", "https"):
            continue

        if parts.netloc.lower() != host:
            continue

        if absolute in seen:
            continue

        seen.add(absolute)

        results.append(
            normalize_row({
                "title": title,
                "url": absolute,
            }, source)
        )

        if len(results) >= 30:
            break

    return results, error


async def source_websearch(http, query, page=1):
    """
    Additional discovery through DuckDuckGo HTML.
    Results are links to indexed pages, not extracted scripts.
    """

    search_terms = " OR ".join(
        f"site:{site}" for site in WEB_SEARCH_SITES
    )

    search_query = f"{query} Roblox script ({search_terms})"

    url = (
        "https://html.duckduckgo.com/html/?q="
        + urllib.parse.quote_plus(search_query)
    )

    html, error = await http.get_text(url)

    if not html:
        return [], error

    pattern = re.compile(
        r'class=["\']result__a["\'][^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.I | re.S,
    )

    results = []
    seen = set()

    for href, raw_title in pattern.findall(html):
        title = re.sub(
            r"\s+",
            " ",
            re.sub(r"<[^>]+>", " ", raw_title),
        ).strip()

        href = href.replace("&amp;", "&")

        if "uddg=" in href:
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            href = params.get("uddg", [href])[0]

        href = valid_url(href)

        if not href or href in seen:
            continue

        seen.add(href)

        host = urllib.parse.urlsplit(href).netloc.lower()

        if not any(site in host for site in WEB_SEARCH_SITES):
            continue

        results.append(
            normalize_row({
                "title": title,
                "url": href,
            }, "websearch")
        )

        if len(results) >= 20:
            break

    return results, error


PAGED_SOURCES = {
    "scriptblox": source_scriptblox,
    "robloxscripts": source_robloxscripts,
    "rscripts": source_rscripts,
}


# ============================================================
# SEARCH ENGINE
# ============================================================

class SearchEngine:

    def __init__(self, http):
        self.http = http
        self.cache = {}
        self.inflight = {}

    def cache_get(self, key):
        item = self.cache.get(key)

        if not item:
            return None

        if time.monotonic() - item["time"] > CACHE_TTL:
            self.cache.pop(key, None)
            return None

        return item["rows"]

    def cache_set(self, key, rows):
        self.cache[key] = {
            "time": time.monotonic(),
            "rows": rows,
        }

        if len(self.cache) > 250:
            now = time.monotonic()

            self.cache = {
                k: v for k, v in self.cache.items()
                if now - v["time"] < CACHE_TTL
            }

    async def search(self, query):
        key = normalize(query)

        cached = self.cache_get(key)

        if cached is not None:
            return [dict(row) for row in cached], False

        if key in self.inflight:
            return await asyncio.shield(
                self.inflight[key]
            )

        task = asyncio.create_task(
            self._perform_search(query)
        )

        self.inflight[key] = task

        try:
            rows, error = await asyncio.shield(task)

            if rows or not error:
                self.cache_set(
                    key,
                    [dict(row) for row in rows],
                )

            return rows, error

        finally:
            self.inflight.pop(key, None)

    async def _fetch_source(self, source, query):
        if source in PAGED_SOURCES:
            fetch = PAGED_SOURCES[source]

            jobs = [
                fetch(self.http, query, page)
                for page in range(1, MAX_PAGES + 1)
            ]

            results = await asyncio.gather(
                *jobs,
                return_exceptions=True,
            )

            rows = []
            error = False

            for result in results:
                if isinstance(result, BaseException):
                    error = True
                    continue

                items, failed = result
                rows.extend(items)
                error |= failed

            return rows, error

        if source in HTML_SOURCES:
            return await source_html(
                self.http, source, query
            )

        if source == "websearch":
            return await source_websearch(
                self.http, query
            )

        return [], False

    async def _perform_search(self, query):
        deadline = (
            asyncio.get_running_loop().time()
            + SEARCH_TIMEOUT
        )

        variants = query_variants(query)

        found = {}
        had_error = False

        for variant in variants:
            if asyncio.get_running_loop().time() >= deadline:
                break

            jobs = [
                self._fetch_source(source, variant)
                for source in SEARCH_SOURCES
            ]

            try:
                results = await asyncio.wait_for(
                    asyncio.gather(
                        *jobs,
                        return_exceptions=True,
                    ),
                    timeout=max(
                        0.5,
                        deadline - asyncio.get_running_loop().time()
                    ),
                )

            except asyncio.TimeoutError:
                had_error = True
                break

            for result in results:
                if isinstance(result, BaseException):
                    had_error = True
                    continue

                rows, error = result
                had_error |= error

                for row in rows:
                    title = (
                        row.get("gameName")
                        or row.get("title")
                    )

                    score = max(
                        relevance(title, query),
                        relevance(row.get("title"), query) * 0.92,
                    )

                    if score < MIN_RELEVANCE:
                        continue

                    row["_relevance"] = score

                    key = row_key(row)

                    if key not in found:
                        found[key] = row
                    elif score > found[key]["_relevance"]:
                        found[key] = row

            if len(found) >= 60:
                break

        rows = list(found.values())

        rows.sort(
            key=lambda row: (
                row.get("_relevance", 0) * 0.85
                + min(
                    1,
                    math.log10(
                        max(0, row.get("views", 0)) + 1
                    ) / 6
                ) * 0.10
                + min(
                    1,
                    math.log10(
                        max(0, row.get("likes", 0)) + 1
                    ) / 5
                ) * 0.05
            ),
            reverse=True,
        )

        return rows[:MAX_RESULTS], had_error


# ============================================================
# SCRIPT COPY
# ============================================================

async def resolve_script(http, row):
    code = clean(row.get("_code"))

    if code:
        return code

    if (
        row.get("_source") == "scriptblox"
        and row.get("_page_url")
    ):
        slug = row["_page_url"].rsplit("/", 1)[-1]

        data, _ = await http.get_json(
            "https://scriptblox.com/api/script/"
            + urllib.parse.quote(slug)
        )

        script = (
            data.get("script")
            if isinstance(data, dict)
            else None
        )

        if isinstance(script, dict):
            code = clean(script.get("script"))

            if code:
                row["_code"] = code
                return code

    raw_url = valid_url(row.get("_raw_url"))

    if raw_url:
        return (
            f'loadstring(game:HttpGet("{raw_url}"))()'
        )

    return ""


# ============================================================
# RESULT EMBED
# ============================================================

def build_result_embed(row, index, total, query):
    source = row.get("_source", "")

    embed = discord.Embed(
        title=truncate(
            "📜 " + row.get("title", "Untitled"),
            250,
        ),
        description=(
            f"**Search:** `{truncate(query, 80)}`\n"
            f"**Match:** {round(row.get('_relevance', 0) * 100)}%"
        ),
        color=SOURCE_COLORS.get(
            source, PANEL_COLOR
        ),
    )

    page = valid_url(row.get("_page_url"))

    if page:
        embed.url = page

    game = clean(
        row.get("gameName"),
        "Unknown game",
    )

    place_id = to_int(row.get("_place_id"))

    if place_id:
        game = (
            f"[{truncate(game, 80)}]"
            f"(https://www.roblox.com/games/{place_id})"
        )

    embed.add_field(
        name="🎮 Game",
        value=game,
        inline=False,
    )

    embed.add_field(
        name="📡 Source",
        value=SOURCE_NAMES.get(source, "External"),
        inline=True,
    )

    embed.add_field(
        name="🔐 Access",
        value=(
            "🔑 Key required"
            if get_key_status(row)
            else "🔓 No key detected"
        ),
        inline=True,
    )

    embed.add_field(
        name="💰 Type",
        value=(
            "Paid"
            if get_paid_status(row)
            else "Free / Unknown"
        ),
        inline=True,
    )

    embed.add_field(
        name="👁️ Views",
        value=f"{to_int(row.get('views')):,}",
        inline=True,
    )

    embed.add_field(
        name="👍 Likes",
        value=f"{to_int(row.get('likes')):,}",
        inline=True,
    )

    updated = (
        row.get("updatedAt")
        or row.get("lastUpdated")
        or row.get("createdAt")
    )

    if updated:
        embed.add_field(
            name="🕒 Updated",
            value=relative_date(updated),
            inline=True,
        )

    user = row.get("user")

    if isinstance(user, dict):
        username = clean(user.get("username"))

        if username:
            embed.set_author(
                name=truncate(
                    f"Created by {username}",
                    250,
                )
            )

    if row.get("_image"):
        embed.set_thumbnail(
            url=row["_image"]
        )

    if page:
        embed.add_field(
            name="🔗 Result",
            value=f"[Open source page]({page})",
            inline=False,
        )

    embed.set_footer(
        text=(
            f"Team Fime • {index}/{total} "
            f"• Search System v9.0"
        )
    )

    return embed


# ============================================================
# RESULT VIEW
# ============================================================

class ScriptBrowserView(discord.ui.View):

    def __init__(
        self,
        cog,
        requester_id,
        rows,
        query,
    ):
        super().__init__(timeout=RESULT_TIMEOUT)

        self.cog = cog
        self.requester_id = requester_id
        self.rows = rows
        self.query = query
        self.index = 0
        self.message = None
        self.expired = False

        self._build()

    def current(self):
        if not self.rows:
            return None

        return self.rows[self.index]

    def header(self):
        return (
            f"🔎 **Search results**\n"
            f"Found **{len(self.rows)}** matching results "
            f"for `{truncate(self.query, 70)}`.\n"
            f"Use the arrows to browse and Copy to retrieve the selected script."
        )

    def embed(self):
        row = self.current()

        if row is None:
            return discord.Embed(
                title="No results",
                color=PANEL_COLOR,
            )

        return build_result_embed(
            row,
            self.index + 1,
            len(self.rows),
            self.query,
        )

    def _build(self):
        self.clear_items()

        previous = discord.ui.Button(
            label="Previous",
            emoji="◀️",
            style=discord.ButtonStyle.secondary,
            disabled=self.index <= 0,
            custom_id="fime_results_previous",
        )

        previous.callback = self.previous
        self.add_item(previous)

        counter = discord.ui.Button(
            label=f"{self.index + 1}/{len(self.rows)}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )

        self.add_item(counter)

        next_button = discord.ui.Button(
            label="Next",
            emoji="▶️",
            style=discord.ButtonStyle.secondary,
            disabled=self.index >= len(self.rows) - 1,
            custom_id="fime_results_next",
        )

        next_button.callback = self.next
        self.add_item(next_button)

        copy_button = discord.ui.Button(
            label="Copy",
            emoji="📋",
            style=discord.ButtonStyle.success,
            custom_id="fime_results_copy",
        )

        copy_button.callback = self.copy
        self.add_item(copy_button)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "🔒 These results belong to another user.",
                ephemeral=True,
            )
            return False

        return True

    async def _update(self, interaction):
        self._build()

        await interaction.response.edit_message(
            content=self.header(),
            embed=self.embed(),
            view=self,
        )

    async def previous(self, interaction):
        if self.index > 0:
            self.index -= 1

        await self._update(interaction)

    async def next(self, interaction):
        if self.index < len(self.rows) - 1:
            self.index += 1

        await self._update(interaction)

    async def copy(self, interaction):
        row = self.current()

        if row is None:
            await interaction.response.send_message(
                "❌ No result selected.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        try:
            code = await resolve_script(
                self.cog.http,
                row,
            )

            if not code:
                page = valid_url(row.get("_page_url"))

                await interaction.followup.send(
                    (
                        "⚠️ The source does not provide "
                        "direct script content.\n"
                        + (
                            f"🔗 {page}"
                            if page else
                            "No direct source link is available."
                        )
                    ),
                    ephemeral=True,
                    allowed_mentions=NO_MENTIONS,
                )
                return

            if len(code) <= COPY_TEXT_LIMIT:
                await interaction.followup.send(
                    f"```lua\n{code}\n```",
                    ephemeral=True,
                    allowed_mentions=NO_MENTIONS,
                )

            else:
                filename = re.sub(
                    r"[^\w-]+",
                    "_",
                    clean(row.get("title"), "script"),
                )[:45]

                file = discord.File(
                    io.BytesIO(
                        code.encode("utf-8")
                    ),
                    filename=f"{filename}.lua",
                )

                await interaction.followup.send(
                    "📋 Script retrieved successfully.",
                    file=file,
                    ephemeral=True,
                    allowed_mentions=NO_MENTIONS,
                )

        except Exception as error:
            print(f"[bot4] Copy error: {error}")

            await interaction.followup.send(
                "❌ Could not retrieve this script.",
                ephemeral=True,
            )

    async def on_timeout(self):
        self.expired = True

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                item.label = "انتهى الوقت"
                item.emoji = None

        if self.message:
            try:
                await self.message.edit(
                    view=self
                )
            except discord.HTTPException:
                pass


# ============================================================
# SEARCH MODAL
# ============================================================

class SearchModal(discord.ui.Modal):

    def __init__(self, cog):
        super().__init__(
            title="Search Roblox Games",
            timeout=180,
        )

        self.cog = cog

        self.game_name = discord.ui.TextInput(
            label="Game or Map Name",
            placeholder=(
                "Enter the name in English or Arabic..."
            ),
            min_length=2,
            max_length=100,
            required=True,
            style=discord.TextStyle.short,
        )

        self.add_item(self.game_name)

    async def on_submit(self, interaction):
        query = clean(self.game_name.value)

        if len(query) < 2:
            await interaction.response.send_message(
                "Please enter a valid game name.",
                ephemeral=True,
            )
            return

        if self.cog.cooldown(
            interaction.user.id,
            interaction.guild_id or 0,
        ):
            await interaction.response.send_message(
                "⏳ Please wait a few seconds before searching again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        started = time.perf_counter()

        try:
            rows, had_error = await self.cog.engine.search(
                query
            )

            elapsed = time.perf_counter() - started

            if not rows:
                await interaction.followup.send(
                    (
                        f"❌ No matching results found for "
                        f"`{truncate(query, 80)}`."
                        if not had_error
                        else
                        "⚠️ Search sources did not respond. Please try again."
                    ),
                    ephemeral=True,
                    allowed_mentions=NO_MENTIONS,
                )
                return

            view = ScriptBrowserView(
                self.cog,
                interaction.user.id,
                rows,
                query,
            )

            message = await interaction.followup.send(
                content=(
                    view.header()
                    + f"\n⚡ Search completed in {elapsed:.2f}s."
                ),
                embed=view.embed(),
                view=view,
                ephemeral=True,
                allowed_mentions=NO_MENTIONS,
                wait=True,
            )

            view.message = message

        except Exception as error:
            print(f"[bot4] Modal search error: {error}")

            await interaction.followup.send(
                "❌ An unexpected error occurred during the search.",
                ephemeral=True,
            )


# ============================================================
# SEARCH PANEL
# ============================================================

class SearchPanelView(discord.ui.View):

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Search for a Game",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        custom_id="fime_game_search_start_v9",
    )
    async def search_button(self, interaction, button):
        await interaction.response.send_modal(
            SearchModal(self.cog)
        )


def build_panel_embed():
    embed = discord.Embed(
        title="🎮 Team Fime | Game Search",
        description=(
            "Discover scripts for your favorite Roblox games "
            "using our multi-source search system.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔎 **Search System**\n"
            "Find matching scripts using a game name.\n\n"
            "🌐 **Multiple Sources**\n"
            "Search across several supported script websites.\n\n"
            "🌍 **Arabic & English**\n"
            "Enter the game name in either language.\n\n"
            "🔒 **Private Results**\n"
            "Your search results are visible only to you.\n\n"
            "📋 **Copy**\n"
            "Retrieve the selected script privately.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "**Press the button below to start searching.**"
        ),
        color=PANEL_COLOR,
    )

    embed.set_footer(
        text="Team Fime • Advanced Search System v9.0"
    )

    return embed


# ============================================================
# COG
# ============================================================

class GameSearchCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.http = HttpClient()
        self.engine = SearchEngine(self.http)

        self.cooldowns = {}

    def cooldown(self, user_id, guild_id):
        key = f"{guild_id}:{user_id}"

        now = time.monotonic()
        last = self.cooldowns.get(key, 0)

        if now - last < SEARCH_COOLDOWN:
            return True

        self.cooldowns[key] = now

        if len(self.cooldowns) > 5000:
            self.cooldowns = {
                k: v for k, v in self.cooldowns.items()
                if now - v < 60
            }

        return False

    async def cog_load(self):
        # Persistent panel buttons survive bot restarts.
        self.bot.add_view(
            SearchPanelView(self)
        )

    async def cog_unload(self):
        await self.http.close()

    # ========================================================
    # PANEL COMMAND
    # ========================================================

    @app_commands.command(
        name="searchpanel",
        description="Create the interactive game search panel",
    )
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def search_panel(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(
            ephemeral=True
        )

        try:
            message = await interaction.channel.send(
                embed=build_panel_embed(),
                view=SearchPanelView(self),
                allowed_mentions=NO_MENTIONS,
            )

            await interaction.followup.send(
                (
                    "✅ Search panel created successfully.\n"
                    f"📌 {message.jump_url}"
                ),
                ephemeral=True,
            )

        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to send messages here.",
                ephemeral=True,
            )

    # ========================================================
    # HELP
    # ========================================================

    @app_commands.command(
        name="searchhelp",
        description="Show search system information",
    )
    async def search_help(
        self,
        interaction: discord.Interaction,
    ):
        embed = build_panel_embed()

        embed.add_field(
            name="⚙️ Management",
            value=(
                "`/searchpanel` Create the search panel\n"
                "`/searchhelp` Show this information\n"
                "`/search` Search directly using a command"
            ),
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    # ========================================================
    # DIRECT SLASH SEARCH
    # ========================================================

    @app_commands.command(
        name="search",
        description="Search Roblox scripts",
    )
    @app_commands.guild_only()
    async def slash_search(
        self,
        interaction: discord.Interaction,
        query: str,
    ):
        query = clean(query)

        if len(query) < 2:
            await interaction.response.send_message(
                "Please enter a longer game name.",
                ephemeral=True,
            )
            return

        if self.cooldown(
            interaction.user.id,
            interaction.guild_id or 0,
        ):
            await interaction.response.send_message(
                "⏳ Please wait before searching again.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        started = time.perf_counter()

        rows, error = await self.engine.search(query)

        elapsed = time.perf_counter() - started

        if not rows:
            await interaction.followup.send(
                "❌ No matching results were found."
                if not error else
                "⚠️ Search sources are temporarily unavailable.",
                ephemeral=True,
            )
            return

        view = ScriptBrowserView(
            self,
            interaction.user.id,
            rows,
            query,
        )

        message = await interaction.followup.send(
            content=(
                view.header()
                + f"\n⚡ {elapsed:.2f}s"
            ),
            embed=view.embed(),
            view=view,
            ephemeral=True,
            wait=True,
        )

        view.message = message

    # ========================================================
    # LEGACY SEARCH COMMAND
    # ========================================================

    @commands.command(name="search")
    async def prefix_search(
        self,
        ctx,
        *,
        query="",
    ):
        query = clean(query)

        if len(query) < 2:
            await ctx.reply(
                "Please provide a game name.",
                mention_author=False,
            )
            return

        if self.cooldown(
            ctx.author.id,
            ctx.guild.id if ctx.guild else 0,
        ):
            await ctx.reply(
                "⏳ Please wait before searching again.",
                mention_author=False,
            )
            return

        status = await ctx.reply(
            "🔎 Searching...",
            mention_author=False,
        )

        rows, error = await self.engine.search(query)

        if not rows:
            await status.edit(
                content=(
                    "❌ No results found."
                    if not error
                    else "⚠️ Search sources are unavailable."
                )
            )
            return

        view = ScriptBrowserView(
            self,
            ctx.author.id,
            rows,
            query,
        )

        # Prefix searches are public because the original
        # command is a public Discord message.
        message = await status.edit(
            content=view.header(),
            embed=view.embed(),
            view=view,
        )

        view.message = message

    # ========================================================
    # TRENDING
    # ========================================================

    @app_commands.command(
        name="trending",
        description="Browse trending scripts",
    )
    @app_commands.guild_only()
    async def trending(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        data, error = await self.http.get_json(
            "https://scriptblox.com/api/script/trending"
        )

        metas = rows_from(
            data,
            ("result", "scripts"),
        )

        rows = []

        for item in metas[:20]:
            rows.append(
                normalize_row(
                    item,
                    "scriptblox",
                )
            )

        if not rows:
            await interaction.followup.send(
                "❌ Trending scripts are unavailable.",
                ephemeral=True,
            )
            return

        view = ScriptBrowserView(
            self,
            interaction.user.id,
            rows,
            "Trending",
        )

        message = await interaction.followup.send(
            content=view.header(),
            embed=view.embed(),
            view=view,
            ephemeral=True,
            wait=True,
        )

        view.message = message

    # ========================================================
    # FETCH ONE SCRIPT
    # ========================================================

    @app_commands.command(
        name="script",
        description="Find one ScriptBlox script by ID or slug",
    )
    @app_commands.guild_only()
    async def fetch_script(
        self,
        interaction: discord.Interaction,
        script_id: str,
    ):
        await interaction.response.defer(
            ephemeral=True,
            thinking=True,
        )

        data, error = await self.http.get_json(
            "https://scriptblox.com/api/script/"
            + urllib.parse.quote(clean(script_id))
        )

        script = (
            data.get("script")
            if isinstance(data, dict)
            else None
        )

        if not isinstance(script, dict):
            await interaction.followup.send(
                "❌ Script not found.",
                ephemeral=True,
            )
            return

        row = normalize_row(
            script,
            "scriptblox",
        )

        row["_relevance"] = 1.0

        view = ScriptBrowserView(
            self,
            interaction.user.id,
            [row],
            row.get("title", script_id),
        )

        message = await interaction.followup.send(
            content=view.header(),
            embed=view.embed(),
            view=view,
            ephemeral=True,
            wait=True,
        )

        view.message = message


# ============================================================
# SETUP
# ============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(
        GameSearchCog(bot)
    )

    print(
        "✅ Team Fime Game Search v9.0 loaded successfully."
    )
