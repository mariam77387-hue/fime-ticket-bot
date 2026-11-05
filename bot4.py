# ============================================================
# Team Fime - bot4.py
# Game / Script Search + TikTok Short-Name Generator
# Version: 10.0
# Loaded by bot.py: await bot.load_extension("bot4")
# Requires: discord.py 2.x, aiohttp
# Optional: RSCRIPTS_API_KEY (RScripts API v1)
# ============================================================

from __future__ import annotations

import asyncio
import difflib
import hashlib
import io
import math
import os
import re
import secrets
import string
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "10.0"
USER_AGENT = f"Team-Fime-Search/{VERSION} (+Discord bot)"

RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()

CACHE_TTL = 300
MAX_RESULTS = 150
PAGE_SIZE = 20  # ScriptBlox documents a maximum of 20 per request.
MAX_PAGES_PER_SOURCE = 2
MAX_QUERY_VARIANTS = 3
SEARCH_TIMEOUT = 14.0
HTTP_TIMEOUT = 8.0
HTTP_CONCURRENCY = 8
SEARCH_COOLDOWN = 3.0
RESULT_TIMEOUT = 300.0
COPY_TEXT_LIMIT = 1800
MIN_RELEVANCE = 0.34
PANEL_COLOR = 0x5865F2

NO_MENTIONS = discord.AllowedMentions.none()

# Public API sources with current documented JSON endpoints.
API_SOURCES = ("scriptblox", "robloxscripts", "haxhell", "rscripts")
SOURCE_NAMES = {
    "scriptblox": "ScriptBlox",
    "robloxscripts": "RobloxScripts.com",
    "haxhell": "HaxHell",
    "rscripts": "RScripts",
    "websearch": "Web discovery",
}
SOURCE_COLORS = {
    "scriptblox": 0x2ECC71,
    "robloxscripts": 0xE67E22,
    "haxhell": 0x3498DB,
    "rscripts": 0x9B59B6,
    "websearch": 0x5865F2,
}

DISCOVERY_DOMAINS = (
    "scriptblox.com",
    "robloxscripts.com",
    "rscripts.net",
    "haxhell.com",
    "roscripts.net",
    "rbxscripts.net",
)

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


# ============================================================
# TEXT / NORMALIZATION
# ============================================================

def clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result or default


def truncate(value: Any, limit: int) -> str:
    value = clean(value)
    return value if len(value) <= limit else value[: max(0, limit - 3)] + "..."


def to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def has_arabic(value: Any) -> bool:
    return bool(ARABIC_RE.search(str(value or "")))


def normalize(value: Any) -> str:
    text = clean(value).lower()
    text = re.sub(r"[\u064B-\u065F\u0670]", "", text)
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي", "ـ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [word[2:] if len(word) > 4 and word.startswith("ال") else word
             for word in text.split()]
    return " ".join(words)


ARABIC_WORDS = {
    "ماب": "", "روبلوكس": "", "سكربت": "", "سكريبت": "",
    "سكربتات": "", "اسكربت": "", "لعبة": "", "لعبه": "",
    "تايكون": "tycoon", "تايكن": "tycoon", "سيمولاتور": "simulator",
    "سيميولاتور": "simulator", "اوبي": "obby", "تاور": "tower",
    "وورز": "wars", "باتل": "battle", "فروت": "fruit",
    "فروتس": "fruits", "سرفايفل": "survival", "ديفنس": "defense",
    "ستوري": "story", "لايف": "life", "ورلد": "world",
    "كينق": "king", "كينج": "king", "جاردن": "garden",
    "برينروت": "brainrot", "ستيل": "steal", "هيرو": "hero",
    "هيروز": "heroes", "ايلاند": "island", "فارم": "farm",
    "كليكر": "clicker", "فايتنق": "fighting", "فايتنج": "fighting",
    "ريسنق": "racing", "كار": "car", "زومبي": "zombie",
    "نينجا": "ninja", "انمي": "anime", "ماينكرافت": "minecraft",
    "فيش": "fish", "سيتي": "city", "ستريت": "street",
    "ديث": "death", "ريفت": "rift", "رايفلز": "rivals",
    "ريفالز": "rivals",
}

NOISE_WORDS = {
    "ماب", "الماب", "سكربت", "سكريبت", "سكربتات", "لعبة", "لعبه",
    "ابحث", "بحث", "عن", "ابي", "ابغى", "اريد", "هات", "جيب", "عطني",
    "please", "pls", "script", "scripts", "map", "game", "find",
    "search", "get", "give", "me", "for", "the", "roblox",
}


def arabic_queries(query: str) -> List[str]:
    if not has_arabic(query):
        return []
    translated = " ".join(
        ARABIC_WORDS.get(token, token)
        for token in normalize(query).split()
        if ARABIC_WORDS.get(token, token)
    ).strip()
    return [translated] if translated else []


def query_variants(query: str) -> List[str]:
    variants: List[str] = []
    seen = set()

    def add(value: str) -> None:
        value = clean(value)
        key = normalize(value)
        if key and key not in seen:
            seen.add(key)
            variants.append(value)

    add(query)
    useful = [w for w in normalize(query).split()
              if w not in NOISE_WORDS and len(w) >= 2]
    if useful:
        add(" ".join(useful))
        if len(useful) > 1:
            add(" ".join(useful[:2]))
    for candidate in arabic_queries(query):
        add(candidate)
    return variants[:MAX_QUERY_VARIANTS]


def relevance(text: Any, query: str) -> float:
    target = normalize(text)
    wanted = normalize(query)
    if not target or not wanted:
        return 0.0
    if target == wanted:
        return 1.0
    if wanted in target:
        return 0.95
    if target in wanted and len(target) >= 3:
        return 0.88

    seq = difflib.SequenceMatcher(None, wanted, target).ratio()
    q_words, t_words = set(wanted.split()), set(target.split())
    overlap = len(q_words & t_words) / max(1, len(q_words))
    return min(1.0, max(seq, overlap * 0.93))


# ============================================================
# GENERAL DATA HELPERS
# ============================================================

def get_path(data: Any, path: Sequence[str], default=None):
    node = data
    for part in path:
        if not isinstance(node, dict):
            return default
        node = node.get(part)
    return default if node is None else node


def list_at(data: Any, *paths: Sequence[str]) -> List[Dict[str, Any]]:
    for path in paths:
        value = get_path(data, path)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def valid_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return ""
    return value


def parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def relative_date(value: Any) -> str:
    parsed = parse_date(value)
    if not parsed:
        return "Unknown"
    seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def row_game_name(row: Dict[str, Any]) -> str:
    for key in ("gameName", "game_name", "gameTitle", "placeName", "experienceName"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    game = row.get("game")
    if isinstance(game, dict):
        for key in ("name", "title", "displayName", "gameName", "game_name"):
            if game.get(key):
                return str(game[key]).strip()
    elif isinstance(game, str) and game.strip():
        return game.strip()
    return ""


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "enabled", "required", "paid", "key"}
    return False


def normalize_row(row: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Convert source-specific fields into one stable result format."""
    item = dict(row)
    game = item.get("game") if isinstance(item.get("game"), dict) else {}
    stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    creator = item.get("creator") if isinstance(item.get("creator"), dict) else {}
    user = item.get("user") if isinstance(item.get("user"), dict) else {}

    title = clean(item.get("title") or item.get("name") or item.get("gameName"), "Untitled")
    slug = clean(item.get("slug"))
    code_value = item.get("script")
    code = code_value.strip() if isinstance(code_value, str) else ""

    raw_url = ""
    for key in ("rawScriptUrl", "rawScript", "rawUrl", "raw_url"):
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate.strip():
            if candidate.strip().startswith(("http://", "https://")):
                raw_url = valid_url(candidate)
            elif not code:
                code = candidate.strip()
            if raw_url or code:
                break

    page_url = ""
    for key in ("url", "scriptUrl", "pageUrl", "webUrl", "link", "permalink"):
        page_url = valid_url(item.get(key))
        if page_url:
            break

    if source == "scriptblox" and slug:
        page_url = f"https://scriptblox.com/script/{urllib.parse.quote(slug)}"
        if not raw_url:
            raw_url = f"https://rawscripts.net/raw/{urllib.parse.quote(slug)}"
    elif source == "rscripts" and slug and not page_url:
        page_url = f"https://rscripts.net/script/{urllib.parse.quote(slug)}"

    if not raw_url and source == "rscripts":
        raw_url = valid_url(item.get("rawScript"))

    image = ""
    for candidate in (
        item.get("image"), item.get("imageUrl"), item.get("thumbnailUrl"),
        game.get("iconUrl"), game.get("imageUrl"), game.get("thumbnailUrl"),
    ):
        image = valid_url(candidate)
        if image:
            break

    game_id = to_int(
        game.get("gameId") or game.get("placeId") or item.get("placeId")
        or item.get("gameId")
    )

    username = clean(
        author.get("username") or creator.get("username") or user.get("username")
    )

    views = to_int(item.get("views", stats.get("views", item.get("viewCount", 0))))
    likes = to_int(item.get("likes", stats.get("likes", item.get("likeCount", 0))))

    key_flag = item.get("key", item.get("keySystem", flags.get("keySystem")))
    paid_flag = item.get("paid", item.get("isPaid", flags.get("isPaid")))
    access_type = clean(item.get("accessType")).lower()
    verified_flag = item.get("verified", author.get("verified", creator.get("isVerified", False)))
    patched_flag = item.get("isPatched", item.get("patched", flags.get("patched")))
    mobile_flag = item.get("mobileReady", item.get("mobileSupported", flags.get("mobileSupported")))

    item.update({
        "title": truncate(title, 240),
        "gameName": row_game_name(item) or clean(game.get("name") or game.get("gameName")),
        "views": views,
        "likes": likes,
        "_source": source,
        "_id": clean(item.get("id") or item.get("_id") or item.get("scriptId")),
        "_slug": slug,
        "_code": code,
        "_raw_url": raw_url,
        "_page_url": page_url,
        "_image": image,
        "_place_id": game_id,
        "_creator": username,
        "_key": as_bool(key_flag) or access_type == "key",
        "_paid": as_bool(paid_flag) or access_type == "paid",
        "_verified": as_bool(verified_flag),
        "_patched": as_bool(patched_flag),
        "_mobile": as_bool(mobile_flag),
    })
    return item


def row_key(row: Dict[str, Any]) -> str:
    canonical = row.get("_page_url") or row.get("_raw_url")
    if canonical:
        return canonical.lower().split("?", 1)[0]
    raw = "|".join((
        clean(row.get("_source")), clean(row.get("_id")),
        clean(row.get("title")), clean(row.get("gameName")),
    ))
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()


def row_score(row: Dict[str, Any], query: str) -> float:
    title_score = relevance(row.get("title"), query)
    game_score = relevance(row.get("gameName"), query)
    description_score = relevance(row.get("description"), query) * 0.72
    tags = row.get("tags")
    tags_text = " ".join(str(x) for x in tags) if isinstance(tags, list) else clean(tags)
    tag_score = relevance(tags_text, query) * 0.70 if tags_text else 0.0
    best = max(title_score, game_score, description_score, tag_score)
    popularity = min(1.0, math.log10(max(0, to_int(row.get("views"))) + 1) / 6)
    likes = min(1.0, math.log10(max(0, to_int(row.get("likes"))) + 1) / 5)
    return min(1.0, best * 0.86 + popularity * 0.09 + likes * 0.05)


# ============================================================
# HTTP CLIENT
# ============================================================

class HttpClient:
    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(HTTP_CONCURRENCY)
        self._host_locks: Dict[str, asyncio.Lock] = {}
        self._host_last_request: Dict[str, float] = {}
        # RobloxScripts documents an approximate 60 requests/minute/IP limit.
        self._host_min_interval = {"robloxscripts.com": 1.05}

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.8, */*;q=0.5"},
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT, connect=3.0),
            )
        return self.session

    async def get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[Any, bool]:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        host_lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with host_lock:
            interval = self._host_min_interval.get(host, 0.0)
            elapsed = time.monotonic() - self._host_last_request.get(host, 0.0)
            if interval and elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            async with self.semaphore:
                self._host_last_request[host] = time.monotonic()
                try:
                    async with self._session().get(url, params=params, headers=headers) as response:
                        if response.status == 429:
                            retry_after = response.headers.get("Retry-After", "unknown")
                            print(f"[bot4] Rate limited by {urllib.parse.urlsplit(url).netloc}; Retry-After={retry_after}")
                            return None, True
                        if response.status >= 500:
                            return None, True
                        if response.status != 200:
                            return None, False
                        return await response.json(content_type=None), False
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    print(f"[bot4] JSON request failed ({urllib.parse.urlsplit(url).netloc}): {exc}")
                    return None, True
                except Exception as exc:
                    print(f"[bot4] Unexpected JSON error: {exc}")
                    return None, True

    async def get_text(self, url: str) -> Tuple[str, bool]:
        async with self.semaphore:
            try:
                async with self._session().get(url, headers={"Accept": "text/html"}) as response:
                    if response.status == 429:
                        print(f"[bot4] Discovery provider rate-limited the request.")
                        return "", True
                    if response.status >= 500:
                        return "", True
                    if response.status != 200:
                        return "", False
                    return await response.text(errors="ignore"), False
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                print(f"[bot4] HTML request failed: {exc}")
                return "", True
            except Exception as exc:
                print(f"[bot4] Unexpected HTML error: {exc}")
                return "", True

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()


# ============================================================
# SOURCE ADAPTERS
# ============================================================

async def fetch_scriptblox(http: HttpClient, query: str, page: int):
    data, error = await http.get_json(
        "https://scriptblox.com/api/script/search",
        params={"q": query, "page": page, "max": PAGE_SIZE,
                "sortBy": "accuracy", "order": "desc", "strict": "false"},
    )
    return [normalize_row(x, "scriptblox") for x in list_at(data, ("result", "scripts"))], error


async def fetch_robloxscripts(http: HttpClient, query: str, page: int):
    # Current public API v1; no token required. Credit is shown in the result footer.
    data, error = await http.get_json(
        "https://robloxscripts.com/api/v1/scripts",
        params={"q": query, "page": page, "limit": 24, "sort": "most-viewed"},
    )
    return [normalize_row(x, "robloxscripts") for x in list_at(data, ("data",))], error


async def fetch_haxhell(http: HttpClient, query: str, page: int):
    # Documented HaxHell API v1 endpoint.
    data, error = await http.get_json(
        "https://haxhell.com/api/v1/search/scripts",
        params={"q": query, "page": page, "limit": 30, "sort": "latest"},
    )
    return [normalize_row(x, "haxhell") for x in list_at(data, ("data",), ("scripts",))], error


async def fetch_rscripts(http: HttpClient, query: str, page: int):
    # Current RScripts v1 requires an API key. Skip cleanly if it is not configured.
    if not RSCRIPTS_API_KEY:
        return [], False
    data, error = await http.get_json(
        "https://api.rscripts.net/v1/search",
        params={"q": query, "index": "scripts", "page": page, "limit": 20,
                "htmlDescription": "false", "includeScript": "false"},
        headers={"Authorization": f"Bearer {RSCRIPTS_API_KEY}"},
    )
    items = list_at(data, ("data", "scripts"))
    return [normalize_row(x, "rscripts") for x in items], error


async def fetch_web_discovery(http: HttpClient, query: str):
    # Search-engine discovery only; it returns indexed page links, not extracted code.
    site_filter = " OR ".join(f"site:{domain}" for domain in DISCOVERY_DOMAINS)
    search_text = f"Roblox {query} script ({site_filter})"
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(search_text)
    html, error = await http.get_text(url)
    if not html:
        return [], error

    pattern = re.compile(
        r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.I | re.S,
    )
    rows: List[Dict[str, Any]] = []
    seen = set()

    for href, raw_title in pattern.findall(html):
        href = href.replace("&amp;", "&")
        try:
            parsed = urllib.parse.urlsplit(href)
            if "uddg" in urllib.parse.parse_qs(parsed.query):
                href = urllib.parse.parse_qs(parsed.query)["uddg"][0]
        except ValueError:
            continue
        href = valid_url(href)
        if not href or href in seen:
            continue
        host = (urllib.parse.urlsplit(href).hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in DISCOVERY_DOMAINS):
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw_title)).strip()
        if not title:
            continue
        seen.add(href)
        rows.append(normalize_row({"title": title, "url": href}, "websearch"))
        if len(rows) >= 20:
            break
    return rows, error


SOURCE_FETCHERS = {
    "scriptblox": fetch_scriptblox,
    "robloxscripts": fetch_robloxscripts,
    "haxhell": fetch_haxhell,
    "rscripts": fetch_rscripts,
}


# ============================================================
# SEARCH ENGINE
# ============================================================

class SearchEngine:
    def __init__(self, http: HttpClient) -> None:
        self.http = http
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.inflight: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    def _cache_get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        entry = self.cache.get(key)
        if not entry:
            return None
        if time.monotonic() - entry["created"] > CACHE_TTL:
            self.cache.pop(key, None)
            return None
        return [dict(row) for row in entry["rows"]]

    def _cache_set(self, key: str, rows: List[Dict[str, Any]]) -> None:
        self.cache[key] = {"created": time.monotonic(), "rows": [dict(x) for x in rows]}
        if len(self.cache) > 300:
            now = time.monotonic()
            self.cache = {k: v for k, v in self.cache.items()
                          if now - v["created"] <= CACHE_TTL}

    async def search(self, query: str) -> Tuple[List[Dict[str, Any]], bool]:
        key = normalize(query)
        cached = self._cache_get(key)
        if cached is not None:
            return cached, False

        async with self._lock:
            task = self.inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._perform_search(query))
                self.inflight[key] = task
                task.add_done_callback(lambda _task, k=key: self.inflight.pop(k, None))

        rows, had_error = await asyncio.shield(task)
        if rows or not had_error:
            self._cache_set(key, rows)
        return [dict(row) for row in rows], had_error

    async def _fetch_one_source(self, source: str, query: str):
        fetcher = SOURCE_FETCHERS[source]
        page_count = 1 if source == "robloxscripts" else MAX_PAGES_PER_SOURCE
        tasks = [fetcher(self.http, query, page)
                 for page in range(1, page_count + 1)]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        rows: List[Dict[str, Any]] = []
        had_error = False
        for response in responses:
            if isinstance(response, BaseException):
                had_error = True
                continue
            found, error = response
            rows.extend(found)
            had_error = had_error or error
        return rows, had_error

    async def _perform_search(self, query: str):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + SEARCH_TIMEOUT
        variants = query_variants(query)
        collected: Dict[str, Dict[str, Any]] = {}
        had_error = False

        # API sources run concurrently for the original query and one useful variant.
        query_batch = variants[:2] or [query]
        jobs = [
            self._fetch_one_source(source, variant)
            for variant in query_batch
            for source in API_SOURCES
        ]
        jobs.append(fetch_web_discovery(self.http, query))

        try:
            responses = await asyncio.wait_for(
                asyncio.gather(*jobs, return_exceptions=True),
                timeout=max(0.5, deadline - loop.time()),
            )
        except asyncio.TimeoutError:
            return [], True

        for response in responses:
            if isinstance(response, BaseException):
                had_error = True
                continue
            rows, error = response
            had_error = had_error or error
            for row in rows:
                title_score = relevance(row.get("title"), query)
                game_score = relevance(row.get("gameName"), query)
                description_score = relevance(row.get("description"), query) * 0.78
                tags = row.get("tags")
                tags_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else clean(tags)
                tags_score = relevance(tags_text, query) * 0.72 if tags_text else 0.0
                score = max(title_score, game_score, description_score, tags_score)
                if score < MIN_RELEVANCE:
                    continue
                row["_relevance"] = score
                key = row_key(row)
                previous = collected.get(key)
                if previous is None or score > previous.get("_relevance", 0):
                    collected[key] = row

        # Search broad descriptions/tags after source normalization, then rank once.
        ranked = list(collected.values())
        for row in ranked:
            row["_rank"] = row_score(row, query)
        ranked.sort(key=lambda x: x.get("_rank", 0), reverse=True)
        return ranked[:MAX_RESULTS], had_error


# ============================================================
# SCRIPT DELIVERY
# ============================================================

async def resolve_script(http: HttpClient, row: Dict[str, Any]) -> str:
    code = clean(row.get("_code"))
    if code:
        return code

    # ScriptBlox detail endpoint is the source-supported route for full script text.
    if row.get("_source") == "scriptblox" and row.get("_slug"):
        data, _ = await http.get_json(
            "https://scriptblox.com/api/script/" + urllib.parse.quote(row["_slug"])
        )
        script = data.get("script") if isinstance(data, dict) else None
        if isinstance(script, dict):
            code = clean(script.get("script"))
            if code:
                row["_code"] = code
                return code

    raw_url = valid_url(row.get("_raw_url"))
    if raw_url:
        # Return a loader when the source provides a raw-script URL but not inline code.
        return f'loadstring(game:HttpGet("{raw_url}"))()'
    return ""


# ============================================================
# RESULT EMBED + PRIVATE BROWSER
# ============================================================

def build_result_embed(row: Dict[str, Any], index: int, total: int, query: str) -> discord.Embed:
    source = row.get("_source", "")
    embed = discord.Embed(
        title=truncate("📜 " + clean(row.get("title"), "Untitled"), 250),
        description=(f"**Game search:** `{truncate(query, 75)}`\n"
                     f"**Match score:** {round(row.get('_relevance', 0) * 100)}%"),
        color=SOURCE_COLORS.get(source, PANEL_COLOR),
    )
    page = valid_url(row.get("_page_url"))
    if page:
        embed.url = page

    game = clean(row.get("gameName"), "Unknown game")
    place_id = to_int(row.get("_place_id"))
    if place_id:
        game = f"[{truncate(game, 75)}](https://www.roblox.com/games/{place_id})"
    embed.add_field(name="🎮 Game", value=game, inline=False)
    embed.add_field(name="📡 Source", value=SOURCE_NAMES.get(source, "External index"), inline=True)
    embed.add_field(name="🔐 Access", value="🔑 Key required" if row.get("_key") else "🔓 No key detected", inline=True)
    embed.add_field(name="💰 Type", value="Paid" if row.get("_paid") else "Free / Unknown", inline=True)
    embed.add_field(name="👁️ Views", value=f"{to_int(row.get('views')):,}", inline=True)
    embed.add_field(name="👍 Likes", value=f"{to_int(row.get('likes')):,}", inline=True)
    if row.get("_verified"):
        embed.add_field(name="✅ Creator", value="Verified", inline=True)
    updated = row.get("updatedAt") or row.get("lastUpdated") or row.get("createdAt")
    if updated:
        embed.add_field(name="🕒 Updated", value=relative_date(updated), inline=True)
    if row.get("_creator"):
        embed.set_author(name=truncate(f"Creator: {row['_creator']}", 250))
    if row.get("_image"):
        embed.set_thumbnail(url=row["_image"])
    if page:
        embed.add_field(name="🔗 Source page", value=f"[Open result]({page})", inline=False)
    embed.set_footer(text=f"Team Fime • Result {index}/{total} • Powered by ScriptBlox / RobloxScripts.com / HaxHell / RScripts")
    return embed


class ScriptBrowserView(discord.ui.View):
    def __init__(self, cog: "GameSearchCog", requester_id: int,
                 rows: List[Dict[str, Any]], query: str):
        super().__init__(timeout=RESULT_TIMEOUT)
        self.cog = cog
        self.requester_id = requester_id
        self.rows = rows
        self.query = query
        self.index = 0
        self.message = None
        self._build()

    def current(self) -> Optional[Dict[str, Any]]:
        return self.rows[self.index] if self.rows else None

    def header(self) -> str:
        return (f"🔎 **Search results** • **{len(self.rows)}** matches for "
                f"`{truncate(self.query, 65)}`\n"
                "Use Previous / Next to browse, or Copy to retrieve the selected script.")

    def embed(self) -> discord.Embed:
        row = self.current()
        if row is None:
            return discord.Embed(title="No results", color=PANEL_COLOR)
        return build_result_embed(row, self.index + 1, len(self.rows), self.query)

    def _build(self) -> None:
        self.clear_items()
        previous = discord.ui.Button(
            label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary,
            disabled=self.index <= 0, custom_id="fime_v10_previous",
        )
        previous.callback = self.previous
        self.add_item(previous)

        next_button = discord.ui.Button(
            label="Next", emoji="▶️", style=discord.ButtonStyle.secondary,
            disabled=self.index >= len(self.rows) - 1, custom_id="fime_v10_next",
        )
        next_button.callback = self.next
        self.add_item(next_button)

        copy_button = discord.ui.Button(
            label="Copy", emoji="📋", style=discord.ButtonStyle.success,
            custom_id="fime_v10_copy",
        )
        copy_button.callback = self.copy
        self.add_item(copy_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "🔒 These private results belong to another member.", ephemeral=True
            )
            return False
        return True

    async def _edit(self, interaction: discord.Interaction) -> None:
        self._build()
        await interaction.response.edit_message(
            content=self.header(), embed=self.embed(), view=self
        )

    async def previous(self, interaction: discord.Interaction) -> None:
        self.index = max(0, self.index - 1)
        await self._edit(interaction)

    async def next(self, interaction: discord.Interaction) -> None:
        self.index = min(len(self.rows) - 1, self.index + 1)
        await self._edit(interaction)

    async def copy(self, interaction: discord.Interaction) -> None:
        row = self.current()
        if not row:
            await interaction.response.send_message("❌ No result selected.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            code = await resolve_script(self.cog.http, row)
            if not code:
                page = valid_url(row.get("_page_url"))
                await interaction.followup.send(
                    "⚠️ This source does not expose a direct script payload.\n"
                    + (page or "No source link is available."),
                    ephemeral=True, allowed_mentions=NO_MENTIONS,
                )
                return
            if len(code) <= COPY_TEXT_LIMIT:
                await interaction.followup.send(
                    f"```lua\n{code}\n```", ephemeral=True,
                    allowed_mentions=NO_MENTIONS,
                )
            else:
                filename = re.sub(r"[^\w-]+", "_", clean(row.get("title"), "script"))[:45]
                upload = discord.File(io.BytesIO(code.encode("utf-8")), filename=f"{filename}.lua")
                await interaction.followup.send(
                    "📋 Script retrieved privately as a Lua file.", file=upload,
                    ephemeral=True, allowed_mentions=NO_MENTIONS,
                )
        except Exception as exc:
            print(f"[bot4] Copy failed: {exc}")
            await interaction.followup.send("❌ Could not retrieve this script.", ephemeral=True)

    async def on_timeout(self) -> None:
        # Keep the components visible, but disable every action after timeout.
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                item.label = "انتهى الوقت"
                item.emoji = None
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except (discord.HTTPException, discord.NotFound):
                pass


# ============================================================
# SEARCH MODAL + PANEL
# ============================================================

class SearchModal(discord.ui.Modal, title="Search Roblox Games"):
    game_name = discord.ui.TextInput(
        label="Game or map name",
        placeholder="Enter a name in English or Arabic...",
        min_length=2,
        max_length=100,
        required=True,
        style=discord.TextStyle.short,
    )

    def __init__(self, cog: "GameSearchCog"):
        super().__init__(timeout=180)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction) -> None:
        query = clean(self.game_name.value)
        if len(query) < 2:
            await interaction.response.send_message("Enter a longer game name.", ephemeral=True)
            return
        if self.cog.on_cooldown(interaction.user.id, interaction.guild_id or 0):
            await interaction.response.send_message("⏳ Please wait a few seconds before searching again.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        started = time.perf_counter()
        try:
            rows, had_error = await self.cog.engine.search(query)
            elapsed = time.perf_counter() - started
            if not rows:
                text = (f"❌ No matching results found for `{truncate(query, 70)}`."
                        if not had_error else
                        "⚠️ Search providers did not return results. Try again shortly.")
                await interaction.followup.send(text, ephemeral=True, allowed_mentions=NO_MENTIONS)
                return

            view = ScriptBrowserView(self.cog, interaction.user.id, rows, query)
            message = await interaction.followup.send(
                content=view.header() + f"\n⚡ Search completed in {elapsed:.2f}s.",
                embed=view.embed(), view=view, ephemeral=True,
                allowed_mentions=NO_MENTIONS, wait=True,
            )
            view.message = message
        except Exception as exc:
            print(f"[bot4] Modal search failed: {exc}")
            await interaction.followup.send("❌ An unexpected search error occurred.", ephemeral=True)


class SearchPanelView(discord.ui.View):
    def __init__(self, cog: "GameSearchCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Search for a Game", emoji="🔎", style=discord.ButtonStyle.primary,
        custom_id="team_fime_game_search_v10",
    )
    async def search_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SearchModal(self.cog))


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎮 Team Fime | Game Search",
        description=(
            "Find Roblox scripts from multiple indexed sources.\n\n"
            "🔎 **Smart search**  •  🌍 **Arabic & English**\n"
            "🌐 **Multiple catalogs**  •  🔒 **Private results**\n"
            "📋 **Private script retrieval**\n\n"
            "Press the button below and enter the game name."
        ),
        color=PANEL_COLOR,
    )
    embed.set_footer(text=f"Team Fime • Search System v{VERSION} • Powered by ScriptBlox / RobloxScripts / HaxHell")
    return embed


# ============================================================
# TIKTOK SHORT-HANDLE IDEAS
# ============================================================

TIKTOK_ALPHABET = string.ascii_lowercase + string.digits


def generate_tiktok_candidates(count: int, length: Optional[int] = None) -> List[str]:
    """Generate local username ideas only; this does not query TikTok."""
    count = max(1, min(int(count), 60))
    lengths = [length] if length in (2, 3, 4) else [2, 3, 4]
    output = set()
    capacity = sum(len(TIKTOK_ALPHABET) ** size for size in lengths)
    if count > capacity:
        count = capacity
    attempts = 0
    max_attempts = max(200, count * 30)

    while len(output) < count and attempts < max_attempts:
        size = secrets.choice(lengths)
        candidate = "".join(secrets.choice(TIKTOK_ALPHABET) for _ in range(size))
        output.add(candidate)
        attempts += 1

    # Deterministic fallback for tiny namespaces or unusually high requested counts.
    if len(output) < count:
        for size in lengths:
            for chars in __import__("itertools").product(TIKTOK_ALPHABET, repeat=size):
                output.add("".join(chars))
                if len(output) >= count:
                    break
            if len(output) >= count:
                break

    return sorted(output, key=lambda x: (len(x), x))[:count]


def build_tiktok_list(names: List[str]) -> str:
    lines = [
        "TikTok short-handle ideas",
        "Availability is NOT verified. Open each profile link and confirm inside TikTok.",
        "",
    ]
    for name in names:
        lines.append(f"@{name}  |  https://www.tiktok.com/@{name}")
    return "\n".join(lines)


# ============================================================
# MAIN COG
# ============================================================

class GameSearchCog(commands.Cog):
    """Loaded as a cog by bot.py. This file does not start its own bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http = HttpClient()
        self.engine = SearchEngine(self.http)
        self.cooldowns: Dict[str, float] = {}

    async def cog_load(self) -> None:
        # Registers persistent panel button after this extension is loaded.
        self.bot.add_view(SearchPanelView(self))

    async def cog_unload(self) -> None:
        await self.http.close()

    def on_cooldown(self, user_id: int, guild_id: int) -> bool:
        key = f"{guild_id}:{user_id}"
        now = time.monotonic()
        previous = self.cooldowns.get(key, 0.0)
        if now - previous < SEARCH_COOLDOWN:
            return True
        self.cooldowns[key] = now
        if len(self.cooldowns) > 5000:
            cutoff = now - 120
            self.cooldowns = {k: value for k, value in self.cooldowns.items() if value >= cutoff}
        return False

    # --------------------------------------------------------
    # Search panel command
    # --------------------------------------------------------

    @app_commands.command(name="searchpanel", description="Create the interactive game-search panel")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(manage_guild=True)
    async def search_panel(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            message = await interaction.channel.send(
                embed=build_panel_embed(), view=SearchPanelView(self),
                allowed_mentions=NO_MENTIONS,
            )
            await interaction.followup.send(f"✅ Search panel created.\n📌 {message.jump_url}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I cannot send messages in this channel.", ephemeral=True)

    @app_commands.command(name="searchhelp", description="Show Game Search information")
    async def search_help(self, interaction: discord.Interaction) -> None:
        embed = build_panel_embed()
        embed.add_field(
            name="Commands",
            value="`/searchpanel` Create the panel\n`/search query` Search directly\n`/trending` Browse trending ScriptBlox results\n`/script id` Fetch one ScriptBlox script",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # --------------------------------------------------------
    # Direct slash search
    # --------------------------------------------------------

    @app_commands.command(name="search", description="Search Roblox scripts across supported sources")
    @app_commands.guild_only()
    async def slash_search(self, interaction: discord.Interaction, query: str) -> None:
        query = clean(query)
        if len(query) < 2:
            await interaction.response.send_message("Please enter a longer game name.", ephemeral=True)
            return
        if self.on_cooldown(interaction.user.id, interaction.guild_id or 0):
            await interaction.response.send_message("⏳ Please wait before searching again.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        started = time.perf_counter()
        rows, had_error = await self.engine.search(query)
        if not rows:
            await interaction.followup.send(
                "❌ No matching results were found." if not had_error else "⚠️ Search providers are temporarily unavailable.",
                ephemeral=True,
            )
            return
        view = ScriptBrowserView(self, interaction.user.id, rows, query)
        message = await interaction.followup.send(
            content=view.header() + f"\n⚡ {time.perf_counter() - started:.2f}s",
            embed=view.embed(), view=view, ephemeral=True, wait=True,
        )
        view.message = message

    # --------------------------------------------------------
    # Trending and one-script lookup
    # --------------------------------------------------------

    @app_commands.command(name="trending", description="Browse trending ScriptBlox scripts")
    @app_commands.guild_only()
    async def trending(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        data, error = await self.http.get_json("https://scriptblox.com/api/script/trending")
        rows = [normalize_row(x, "scriptblox") for x in list_at(data, ("result", "scripts"))]
        if not rows:
            await interaction.followup.send("❌ Trending results are unavailable right now.", ephemeral=True)
            return
        for row in rows:
            row["_relevance"] = 1.0
        view = ScriptBrowserView(self, interaction.user.id, rows[:MAX_RESULTS], "Trending")
        message = await interaction.followup.send(content=view.header(), embed=view.embed(), view=view, ephemeral=True, wait=True)
        view.message = message

    @app_commands.command(name="script", description="Fetch one ScriptBlox script by ID or slug")
    @app_commands.guild_only()
    async def fetch_script(self, interaction: discord.Interaction, script_id: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        data, _ = await self.http.get_json(
            "https://scriptblox.com/api/script/" + urllib.parse.quote(clean(script_id))
        )
        script = data.get("script") if isinstance(data, dict) else None
        if not isinstance(script, dict):
            await interaction.followup.send("❌ Script not found.", ephemeral=True)
            return
        row = normalize_row(script, "scriptblox")
        row["_relevance"] = 1.0
        view = ScriptBrowserView(self, interaction.user.id, [row], row["title"])
        message = await interaction.followup.send(content=view.header(), embed=view.embed(), view=view, ephemeral=True, wait=True)
        view.message = message

    # --------------------------------------------------------
    # Prefix search compatibility
    # --------------------------------------------------------

    @commands.command(name="search")
    async def prefix_search(self, ctx: commands.Context, *, query: str = "") -> None:
        query = clean(query)
        if len(query) < 2:
            await ctx.reply("Please provide a game name.", mention_author=False)
            return
        if self.on_cooldown(ctx.author.id, ctx.guild.id if ctx.guild else 0):
            await ctx.reply("⏳ Please wait before searching again.", mention_author=False)
            return
        status = await ctx.reply("🔎 Searching...", mention_author=False)
        rows, had_error = await self.engine.search(query)
        if not rows:
            await status.edit(content="❌ No results found." if not had_error else "⚠️ Search providers are unavailable.")
            return
        view = ScriptBrowserView(self, ctx.author.id, rows, query)
        message = await status.edit(content=view.header(), embed=view.embed(), view=view)
        view.message = message

    # --------------------------------------------------------
    # Hidden-from-help TikTok short-name idea generator
    # --------------------------------------------------------

    @commands.command(name="q7v_x9", hidden=True, help=None)
    async def tiktok_short_names(self, ctx: commands.Context, *args: str) -> None:
        """Local idea generator. It does not contact TikTok or claim availability."""
        length: Optional[int] = None
        count = 25

        try:
            if len(args) == 1:
                if args[0].lower() in {"2", "3", "4"}:
                    length = int(args[0])
                else:
                    count = int(args[0])
            elif len(args) >= 2:
                length = int(args[0]) if args[0] in {"2", "3", "4"} else None
                count = int(args[1])
        except ValueError:
            await ctx.reply("Usage: `!q7v_x9 [2|3|4] [count]`", mention_author=False)
            return

        if count < 1 or count > 60:
            await ctx.reply("Choose between 1 and 60 names per request.", mention_author=False)
            return
        if length not in (None, 2, 3, 4):
            await ctx.reply("Allowed lengths: 2, 3 or 4.", mention_author=False)
            return

        names = generate_tiktok_candidates(count, length)
        payload = build_tiktok_list(names)
        file = discord.File(io.BytesIO(payload.encode("utf-8")), filename="tiktok_short_name_ideas.txt")

        try:
            await ctx.author.send(
                content=(f"Here are {len(names)} short TikTok username ideas.\n"
                         "**Availability is unverified:** TikTok has no public availability endpoint in the official API docs."),
                file=file,
                allowed_mentions=NO_MENTIONS,
            )
            try:
                await ctx.message.add_reaction("📩")
            except discord.HTTPException:
                pass
        except discord.Forbidden:
            await ctx.reply("I couldn't DM you. Enable server-member DMs and run the command again.", mention_author=False)


# ============================================================
# EXTENSION SETUP - bot.py loads this Cog
# ============================================================

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GameSearchCog(bot))
    print(f"✅ Team Fime bot4 v{VERSION} loaded (Search + TikTok Name Ideas).")
