
# 🔎 نظام بحث Roblox Scripts (متعدد المصادر)
# =========================================================
#
# فكرة النظام:
# 1) نحدد "اللعبة المستهدفة" من كلام العضو (عربي/إنجليزي/مختصر/فيه غلطة إملائية)
#    عبر قاعدة بيانات ألعاب + مطابقة تقريبية (fuzzy) تتحمل الأخطاء البسيطة.
# 2) نبحث بالتوازي في كل المصادر المفعّلة (ScriptBlox دائمًا، و Rscripts لو
#    توفّر مفتاح API)، ثم نفلتر النتائج بحيث ما تطلع نتيجة من لعبة مختلفة
#    عن اللي طلبها العضو.
# 3) نرتب النتائج (موثّق > غير Patched > بدون Key > أكثر أمانًا) ونعرض
#    أفضلها، مع زر لعرض نتيجة بديلة لو فيه أكثر من خيار.
#
# ملاحظة عن المصادر الإضافية (cheater.fun / scriptrb.com / robscript.com):
# لم أتمكن من التأكد من وجود واجهة برمجية (API) عامة وموثقة لهذه المواقع
# وقت كتابة هذا الكود، لذلك لم يتم ربطها لتفادي كود يعتمد على تخمين
# مسارات غير موثوقة قد تتغيّر أو تتوقف بدون سابق إنذار. القاعدة
# `fetch_<source>_results()` موحّدة الشكل، فإضافة مصدر جديد لاحقًا (بعد
# التأكد من الـAPI الخاص فيه) يكون بإضافة دالة بنفس الشكل وتسجيلها في
# `search_all_sources`.

SCRIPTBLOX_API = "https://scriptblox.com/api/script/search"
SCRIPTBLOX_RAW_API = "https://scriptblox.com/api/script/raw"

RSCRIPTS_API_BASE = "https://api.rscripts.net"
# مصدر ثانوي اختياري: يعمل فقط لو تم ضبط متغير البيئة RSCRIPTS_API_KEY
# (يُنشأ مفتاح مجاني من https://rscripts.net/dashboard/api). بدونه يتم
# تجاهل هذا المصدر بصمت والاعتماد على ScriptBlox فقط.
RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY")


# ---------------------------------------------------------
# قاعدة بيانات أشهر ألعاب Roblox + اختصاراتها العربية/الإنجليزية
# ---------------------------------------------------------
# كل عنصر: (الاسم الإنجليزي الرسمي، [قائمة أسماء/اختصارات شائعة]).
# ما فيه داعي نكتب كل تركيبة مسافات ممكنة يدويًا؛ عند التحميل يتم توليد
# نسخة بدون مسافات تلقائيًا لكل اسم مستعار، والمطابقة التقريبية تتكفل
# بالباقي (أخطاء إملائية بسيطة، حروف زايدة أو ناقصة).
ROBLOX_GAMES = [
    ("Blox Fruits", [
        "بلوكس فروت", "بلوكس فروتس", "بلوكس فروز", "بلف", "بلوكس",
        "blox fruit", "blox fruits", "bf",
    ]),
    ("Grow a Garden", [
        "جرو جاردن", "جرو", "ماب المزرعه", "المزرعه", "مزرعه",
        "قرو قاردن", "قرو جاردن", "قرو", "grow a garden", "gag",
    ]),
    ("Steal a Brainrot", [
        "ستيل ابرين روت", "ستيل برين روت", "برين روت", "برينروت",
        "steal brainrot", "steal a brainrot", "brainrot",
    ]),
    ("Steal an Egg", [
        "سرقه البيض", "سرقة البيض", "سرقه بيض", "سرقة بيض",
        "سرقه بيضه", "سرقة بيضة", "بيض", "steal an egg", "steal egg",
    ]),
    ("Murder Mystery 2", [
        "مردر مستري", "ممر", "ميم", "ام ام تو", "ام ام 2", "ام ام",
        "مردر", "mm2", "mm 2", "murder mystery",
    ]),
    ("DOORS", [
        "دورز", "دور", "دورس", "الباب", "باب", "doors",
    ]),
    ("Brookhaven", [
        "بروك هيفن", "بروكهافن", "ماب البيوت", "ماب بيوت", "بيوت",
        "brookhaven", "brookhaven rp",
    ]),
    ("Fisch", [
        "فش", "فيش", "سي فش", "الصيد", "صيد", "السمك", "سمك", "fisch",
    ]),
    ("BedWars", [
        "بد وارز", "بدورز", "bed wars", "bedwars",
    ]),
    ("Blade Ball", [
        "بليد بول", "بليدبال", "بليد", "blade ball",
    ]),
    ("The Strongest Battlegrounds", [
        "سترونقست", "سترونجست", "ذا سترونجست", "strongest", "tsb",
        "ماب القتال",
    ]),
    ("Pet Simulator 99", [
        "بت سيم", "بت سيموليتر", "بيت سيموليتر", "pet sim", "ps99",
    ]),
    ("Adopt Me!", [
        "ادوبت مي", "ادوبت", "تبني", "ماب الحيوانات", "adopt me",
    ]),
    ("Dress To Impress", [
        "دريس تو امبرس", "دريس تو", "dti", "dress to impress",
        "ماب الملابس",
    ]),
    ("99 Nights in the Forest", [
        "99 نايت", "99 نايتس", "ناينتي ناين", "99 nights", "الغابة",
        "ماب الغابه", "ماب الغابة",
    ]),
    ("RIVALS", [
        "رايفلز", "رايفل", "ريفلز", "rivals", "ماب رايفلز",
    ]),
    ("Evade", [
        "ايفيد", "ايفيدد", "evade", "ماب الهروب",
    ]),
    ("Arsenal", [
        "ارسنال", "ارسنل", "arsenal", "تصويب",
    ]),
    ("Jailbreak", [
        "جيل بريك", "جيلبريك", "jailbreak",
    ]),
    ("Piggy", [
        "بيجي", "بقي", "piggy",
    ]),
    ("Tower of Hell", [
        "تاور اوف هيل", "تاور", "برج الجحيم", "tower of hell", "toh",
    ]),
    ("Da Hood", [
        "دا هود", "دهود", "da hood",
    ]),
    ("Build A Boat For Treasure", [
        "بيلد بوت", "بيلد اي بوت", "بناء القارب", "ماب القارب",
        "build a boat",
    ]),
    ("Natural Disaster Survival", [
        "ناشورال ديزاستر", "ديزاستر", "الكوارث", "ماب الكوارث",
    ]),
    ("MeepCity", [
        "ميب سيتي", "ميبستي", "meepcity",
    ]),
    ("Bee Swarm Simulator", [
        "بي سوارم", "محاكي النحل", "النحل", "bee swarm", "bss",
    ]),
    ("Tower Defense Simulator", [
        "تاور ديفنس", "دفاع الأبراج", "tower defense simulator", "tds",
    ]),
    ("Anime Vanguards", [
        "انمي فانقاردز", "انمي فانجاردز", "anime vanguards", "av",
    ]),
    ("King Legacy", [
        "كينق ليقاسي", "كنق ليجاسي", "king legacy", "kl",
    ]),
    ("Shindo Life", [
        "شيندو لايف", "شيندو", "shindo life", "shindo",
    ]),
    ("Islands", [
        "ايلاندز", "سكاي بلوك", "islands", "skyblock",
    ]),
    ("Welcome to Bloxburg", [
        "بلوكسبيرق", "بلوكس بيرج", "بلوكسبورج", "bloxburg",
    ]),
    ("Royale High", [
        "رويال هاي", "رويال", "royale high",
    ]),
    ("Sonic Speed Simulator", [
        "سونيك سبيد", "سونيك", "sonic speed simulator",
    ]),
    ("Funky Friday", [
        "فانكي فرايدي", "فانكي", "funky friday",
    ]),
    ("Phantom Forces", [
        "فانتوم فورسز", "فانتوم", "phantom forces", "pf",
    ]),
    ("Combat Warriors", [
        "كومبات واريورز", "combat warriors", "cw",
    ]),
    ("Pls Donate", [
        "بليز دونيت", "pls donate",
    ]),
    ("Slap Battles", [
        "سلاب باتلز", "slap battles",
    ]),
    ("Untitled Boxing Game", [
        "بوكسينق قيم", "الملاكمة", "untitled boxing game", "ubg",
    ]),
    ("Volleyball Legends", [
        "فولي بول ليجندز", "الكرة الطائرة", "volleyball legends",
    ]),
    ("Basketball Legends", [
        "باسكت بول ليجندز", "كرة السلة", "basketball legends",
    ]),
    ("Football Fusion 2", [
        "فوتبول فيوجن", "كرة القدم", "football fusion 2", "ff2",
    ]),
    ("Toilet Tower Defense", [
        "تواليت تاور ديفنس", "سكيبيدي", "toilet tower defense", "ttd",
    ]),
    ("Anime Last Stand", [
        "انمي لاست ستاند", "anime last stand", "als",
    ]),
    ("All Star Tower Defense", [
        "أول ستار تاور ديفنس", "all star tower defense", "astd",
    ]),
    ("Ninja Legends 2", [
        "نينجا ليجندز", "ninja legends 2", "nl2",
    ]),
]


def normalize_search_text(value: str):
    """
    يطبّع النص العربي/الإنجليزي حتى تتوحّد اختلافات الكتابة الشائعة
    قبل أي مقارنة (سواء مطابقة تامة أو تقريبية).
    """
    value = str(value or "").strip().casefold()
    # إزالة التشكيل (الحركات)
    value = re.sub(r"[\u064B-\u065F\u0670]", "", value)
    # توحيد الألف بأشكالها
    value = value.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    # توحيد الياء/الألف المقصورة، والتاء المربوطة/الهاء
    # (بدون هذا: "المزرعه" و"المزرعة" كانتا تُعاملان كأنهما كلمتان مختلفتان)
    value = value.replace("ى", "ي")
    value = value.replace("ة", "ه")
    # إزالة التطويل (ـ)
    value = value.replace("ـ", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _strip_arabic_definite_article(word: str):
    # يزيل "ال" التعريف من بداية الكلمة (الباب -> باب) حتى ما نحتاج
    # نكرر كل اسم مستعار بنسختين (بـ"ال" وبدونها).
    if word.startswith("ال") and len(word) > 3:
        return word[2:]
    return word


def _dealias_definite_article(text: str):
    return " ".join(_strip_arabic_definite_article(word) for word in text.split(" ") if word)


def clean_script_query(content: str):
    value = str(content or "").strip()
    value = re.sub(r"^!\s*بحث\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^بحث\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^!\s*search\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^search\s+", "", value, flags=re.IGNORECASE)
    return value.strip()


# ---------------------------------------------------------
# فهرسة أسماء الألعاب (تُبنى مرة واحدة عند أول استخدام)
# ---------------------------------------------------------

_GAME_EXACT_INDEX = None       # [(الاسم المطبَّع, الاسم الرسمي الإنجليزي), ...] مرتبة من الأطول للأقصر
_GAME_FUZZY_INDEX = None       # {الاسم الرسمي: {مجموعة الأسماء المطبَّعة}}


def _generate_alias_variants(text: str):
    variants = {text}
    no_space = text.replace(" ", "")
    if no_space:
        variants.add(no_space)
    return variants


def _build_game_indexes():
    global _GAME_EXACT_INDEX, _GAME_FUZZY_INDEX
    if _GAME_EXACT_INDEX is not None:
        return

    exact_lookup = {}
    fuzzy_lookup = {}

    for canonical_name, aliases in ROBLOX_GAMES:
        all_raw_aliases = set(aliases) | {canonical_name}
        normalized_set = set()
        for alias in all_raw_aliases:
            for variant in _generate_alias_variants(alias):
                normalized = normalize_search_text(variant)
                if normalized:
                    normalized_set.add(normalized)
        fuzzy_lookup[canonical_name] = normalized_set
        for normalized in normalized_set:
            # لو نفس الاسم المطبَّع يتكرر بين لعبتين (نادر)، أول تسجيل يفوز
            exact_lookup.setdefault(normalized, canonical_name)

    _GAME_EXACT_INDEX = sorted(exact_lookup.items(), key=lambda item: len(item[0]), reverse=True)
    _GAME_FUZZY_INDEX = fuzzy_lookup


def identify_target_game(query: str):
    """
    يحاول تحديد اللعبة المقصودة من كلام العضو.
    يرجع (الاسم_الإنجليزي_الرسمي أو None, مستوى_الثقة) حيث مستوى الثقة
    واحدة من: "exact" (مطابقة مباشرة/كجزء من النص) أو "fuzzy" (تقريبية،
    تتحمل خطأ إملائي بسيط) أو "none" (ما قدرنا نحدد اللعبة).
    """
    _build_game_indexes()

    normalized = normalize_search_text(query)
    if not normalized:
        return None, "none"

    normalized_no_al = _dealias_definite_article(normalized)
    candidates = [normalized]
    if normalized_no_al != normalized:
        candidates.append(normalized_no_al)

    # 1) مطابقة كاملة للاستعلام (مع/بدون "ال" التعريف)
    for candidate in candidates:
        for key, name in _GAME_EXACT_INDEX:
            if key == candidate:
                return name, "exact"

    # 2) اسم اللعبة موجود كجزء من نص أطول (الأطول أولًا لتفادي مطابقات
    #    خاطئة قصيرة، مثل استعلام يحتوي كلمات زائدة حول اسم اللعبة)
    for candidate in candidates:
        for key, name in _GAME_EXACT_INDEX:
            if key and key in candidate:
                return name, "exact"

    # 3) مطابقة تقريبية تتحمل الأخطاء الإملائية البسيطة
    best_name, best_ratio = None, 0.0
    for candidate in candidates:
        if len(candidate) < 2:
            continue
        for canonical_name, normalized_aliases in _GAME_FUZZY_INDEX.items():
            for alias in normalized_aliases:
                ratio = SequenceMatcher(None, candidate, alias).ratio()
                if ratio > best_ratio:
                    best_ratio, best_name = ratio, canonical_name

    # عتبة أعلى للنصوص القصيرة جدًا لتقليل احتمال مطابقة خاطئة
    threshold = 0.80 if len(normalized) >= 6 else 0.88
    if best_name and best_ratio >= threshold:
        return best_name, "fuzzy"

    return None, "none"


def translate_game_alias(query: str):
    """يحوّل اسم اللعبة (عربي/مختصر/فيه غلطة إملائية) إلى الاسم الإنجليزي الرسمي."""
    name, _confidence = identify_target_game(query)
    return name if name else query.strip()


# ---------------------------------------------------------
# طلبات الشبكة (مع إعادة محاولة بسيطة عند فشل مؤقت)
# ---------------------------------------------------------

async def _http_get_json(url: str, headers=None, retries: int = 1, timeout: int = 15):
    last_error = None
    request_headers = headers or {"User-Agent": "FimeDiscordBot/1.0", "Accept": "application/json"}
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=request_headers)

            def _do_request():
                with urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))

            return await asyncio.to_thread(_do_request)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                await asyncio.sleep(0.6)
    raise last_error


async def _http_get_text(url: str, headers=None, timeout: int = 15):
    request = Request(url, headers=headers or {"User-Agent": "FimeDiscordBot/1.0"})

    def _do_request():
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    return await asyncio.to_thread(_do_request)


# ---------------------------------------------------------
# المصادر (كل دالة ترجع قائمة نتائج موحّدة الشكل)
# ---------------------------------------------------------
# شكل النتيجة الموحّد:
# {title, game_name, game_image, script_image, url, verified, has_key,
#  is_patched, raw_script (نص جاهز أو None), raw_url (رابط لجلب النص أو None),
#  source, risk_level (اختياري)}

async def fetch_scriptblox_results(search_query: str, max_results: int, strict: bool):
    params = (
        f"q={quote_plus(search_query)}"
        f"&max={max(1, min(20, int(max_results)))}"
        f"&strict={'true' if strict else 'false'}"
        "&sortBy=updatedAt&order=desc"
    )
    url = f"{SCRIPTBLOX_API}?{params}"
    try:
        data = await _http_get_json(url, retries=1)
    except Exception as error:
        print(f"❌ ScriptBlox Search Error: {error}")
        return []

    result = data.get("result") if isinstance(data, dict) else None
    scripts = result.get("scripts", []) if isinstance(result, dict) else []
    normalized = []
    for item in (scripts if isinstance(scripts, list) else []):
        game = item.get("game") or {}
        slug_or_id = item.get("slug") or item.get("_id") or ""
        normalized.append({
            "title": str(item.get("title") or "بدون عنوان"),
            "game_name": str(game.get("name") or ""),
            "game_image": game.get("imageUrl"),
            "script_image": item.get("image"),
            "url": f"https://scriptblox.com/script/{slug_or_id}" if slug_or_id else "https://scriptblox.com/",
            "verified": bool(item.get("verified")),
            "has_key": bool(item.get("key")),
            "is_patched": bool(item.get("isPatched")),
            "raw_script": (str(item.get("script") or "").strip() or None),
            "raw_url": (f"{SCRIPTBLOX_RAW_API}/{quote_plus(str(slug_or_id))}" if slug_or_id else None),
            "source": "ScriptBlox",
            "risk_level": None,
        })
    return normalized


async def fetch_rscripts_results(search_query: str, max_results: int):
    if not RSCRIPTS_API_KEY:
        return []

    params = f"q={quote_plus(search_query)}&index=scripts&limit={max(1, min(20, int(max_results)))}"
    url = f"{RSCRIPTS_API_BASE}/v1/search?{params}"
    headers = {
        "Authorization": f"Bearer {RSCRIPTS_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "FimeDiscordBot/1.0",
    }
    try:
        data = await _http_get_json(url, headers=headers, retries=1)
    except Exception as error:
        print(f"❌ Rscripts Search Error: {error}")
        return []

    if not isinstance(data, dict) or not data.get("success"):
        return []

    scripts = ((data.get("data") or {}).get("scripts")) or []
    normalized = []
    for item in (scripts if isinstance(scripts, list) else []):
        game = item.get("game") or {}
        risk = item.get("risk") or {}
        creator = item.get("creator") or {}
        slug = item.get("slug") or ""
        normalized.append({
            "title": str(item.get("title") or "بدون عنوان"),
            "game_name": str(game.get("title") or ""),
            "game_image": game.get("thumbnailUrl") or game.get("logoUrl"),
            "script_image": None,
            "url": f"https://rscripts.net/script/{slug}" if slug else "https://rscripts.net/",
            "verified": bool(creator.get("isVerified")),
            "has_key": bool(item.get("isKeySystem")),
            "is_patched": bool(item.get("isPatched")),
            "raw_script": (str(item.get("script") or "").strip() or None),
            "raw_url": item.get("rawScript"),
            "source": "Rscripts",
            "risk_level": risk.get("level"),
        })
    return normalized


# قائمة المصادر المفعّلة. لإضافة مصدر جديد لاحقًا (بعد التأكد من وجود
# API عام وموثّق له): اكتب دالة async بنفس التوقيع (query, max_results)
# ترجع قائمة بنفس شكل النتيجة الموحّد أعلاه، ثم أضفها هنا.
_SCRIPT_SOURCES = (
    ("ScriptBlox", lambda query, max_results, strict: fetch_scriptblox_results(query, max_results, strict)),
    ("Rscripts", lambda query, max_results, strict: fetch_rscripts_results(query, max_results)),
)


def _game_matches_target(game_name: str, target_name: str):
    if not target_name:
        return True
    a = normalize_search_text(game_name)
    b = normalize_search_text(target_name)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def _score_result(result):
    score = 0
    if result.get("verified"):
        score += 2
    if not result.get("is_patched"):
        score += 2
    if not result.get("has_key"):
        score += 1
    if result.get("source") == "Rscripts" and result.get("risk_level") in ("Safe", "Low Risk"):
        score += 1
    return score


async def search_all_sources(original_query: str, max_results: int, strict: bool):
    """
    يبحث في كل المصادر المفعّلة بالتوازي، يفلتر النتائج حسب اللعبة
    المستهدفة (لمنع خلط النتائج بين لعبتين مختلفتين)، ثم يرتبها.
    يرجع: (نتائج مرتّبة, اسم اللعبة المستهدف أو None, مستوى الثقة)
    """
    target_name, confidence = identify_target_game(original_query)
    search_query = target_name or original_query.strip()

    fetched = await asyncio.gather(
        *[fetcher(search_query, max_results, strict) for _name, fetcher in _SCRIPT_SOURCES],
        return_exceptions=True,
    )

    combined = []
    for source_name, source_results in zip((name for name, _f in _SCRIPT_SOURCES), fetched):
        if isinstance(source_results, Exception):
            print(f"❌ {source_name} Error: {source_results}")
            continue
        combined.extend(source_results)

    if not combined:
        return [], target_name, confidence

    if target_name and confidence in ("exact", "fuzzy"):
        filtered = [r for r in combined if _game_matches_target(r["game_name"], target_name)]
        # لو الفلترة أزالت كل النتائج (مثلًا مصدر معيّن يسمّي اللعبة بشكل
        # مختلف قليلًا)، نرجّع للنتائج غير المفلترة بدل إظهار "لا نتائج" خطأً.
        if filtered:
            combined = filtered

    combined.sort(key=_score_result, reverse=True)
    return combined, target_name, confidence


async def _resolve_script_text(result: dict):
    """يرجع نص السكربت جاهزًا، يجلبه من raw_url لو ما كان متوفر مباشرة."""
    raw = result.get("raw_script")
    if raw:
        return raw
    raw_url = result.get("raw_url")
    if not raw_url:
        return ""
    try:
        raw = await _http_get_text(raw_url)
    except Exception as error:
        print(f"❌ Raw Script Fetch Error: {error}")
        return ""
    raw = str(raw or "").strip()
    # بعض المصادر ترجع JSON فيه حقل السكربت بدل النص الخام مباشرة
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return str(parsed.get("script") or parsed.get("raw") or parsed.get("content") or raw)
    except json.JSONDecodeError:
        pass
    return raw


def _build_result_embed(result: dict, query_label: str, index: int, total: int):
    verified = "✅ موثق" if result.get("verified") else "⚪ غير موثق"
    key = "🔑 Key" if result.get("has_key") else "🔓 بدون Key"
    patched = "⚠ Patched" if result.get("is_patched") else "🟢 غير Patched"

    description_lines = [
        f"**{result['title']}**",
        "",
        f"🎮 اللعبة: **{result.get('game_name') or 'غير معروف'}**",
        f"{verified} • {key} • {patched}",
    ]
    if result.get("risk_level"):
        description_lines.append(f"🛡 مستوى الأمان: **{result['risk_level']}**")
    description_lines.append("")
    description_lines.append(f"🔗 [فتح صفحة السكربت]({result['url']})")
    description_lines.append(f"📡 المصدر: {result.get('source', 'غير معروف')}")
    if total > 1:
        description_lines.append(f"\nنتيجة **{index + 1}** من **{total}** لـ \"{query_label}\"")

    embed = discord.Embed(
        title="🔎 نتيجة بحث السكربت",
        description="\n".join(description_lines),
        color=discord.Color.blurple(),
    )
    if result.get("game_image"):
        embed.set_thumbnail(url=str(result["game_image"]))
    if result.get("script_image"):
        embed.set_image(url=str(result["script_image"]))
    return embed


class ScriptResultView(discord.ui.View):
    """يسمح بتصفّح باقي النتائج المطابقة بدل ما نظهر خيار واحد فقط."""

    def __init__(self, results, query_label, owner_id):
        super().__init__(timeout=120)
        self.results = results
        self.query_label = query_label
        self.owner_id = owner_id
        self.index = 0
        if len(results) <= 1:
            self.clear_items()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ هذه القائمة ليست لك.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="نتيجة أخرى 🔁", style=discord.ButtonStyle.secondary)
    async def next_result(self, interaction, button):
        self.index = (self.index + 1) % len(self.results)
        result = self.results[self.index]
        embed = _build_result_embed(result, self.query_label, self.index, len(self.results))
        await interaction.response.edit_message(embed=embed, view=self)


async def send_script_result(message: discord.Message, query: str):
    guild = message.guild
    data = get_script_search_config(guild)

    results, target_name, confidence = await search_all_sources(
        query,
        max_results=data.get("max_results", 5),
        strict=bool(data.get("strict", False)),
    )

    if not results:
        hint = f" (فهمت إنك تقصد **{target_name}**)" if target_name else ""
        await message.channel.send(
            f"🔎 ما لقيت سكربت مناسب لـ **{query}**{hint}.\n"
            "جرب الاسم الإنجليزي أو اسم اللعبة بشكل أوضح."
        )
        return

    embed = _build_result_embed(results[0], query, 0, len(results))
    view = ScriptResultView(results, query, message.author.id)

    sent = await message.channel.send(embed=embed, view=view if len(results) > 1 else None)
    if len(results) <= 1:
        view.stop()

    # إرسال محتوى السكربت جاهزًا للنسخ
    raw = await _resolve_script_text(results[0])
    if raw:
        if len(raw) <= 1800:
            await message.channel.send(f"```lua\n{raw}\n```\n📋 انسخ الكود من المربع أعلاه.")
        else:
            data_file = io.BytesIO(raw.encode("utf-8"))
            data_file.seek(0)
            filename = re.sub(r"[^A-Za-z0-9_-]+", "_", results[0]["title"])[:60] or "script"
            await message.channel.send(
                "📋 السكربت طويل، لذلك أرسلته كملف نصي لسهولة النسخ.",
                file=discord.File(data_file, filename=f"{filename}.lua")
            )


@bot.tree.command(
    name="scriptsearch",
    description="تحديد روم بحث Roblox Scripts"
)
@app_commands.describe(
    channel="الروم الذي يعمل فيه البحث",
    enabled="تشغيل أو إيقاف البحث",
    max_results="عدد النتائج التي يبحث بينها البوت من 1 إلى 20",
    strict="تفعيل البحث المطابق بشكل أدق"
)
@admin_only()
async def scriptsearch_command(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    enabled: bool = True,
    max_results: int = 5,
    strict: bool = False,
):
    guild = interaction.guild
    data = get_script_search_config(guild)

    if not 1 <= max_results <= 20:
        await interaction.response.send_message("❌ عدد النتائج يجب أن يكون بين 1 و20.", ephemeral=True)
        return

    data.update({
        "enabled": bool(enabled),
        "channel_id": channel.id if channel else data.get("channel_id"),
        "max_results": max_results,
        "strict": bool(strict),
    })

    if channel is None and enabled and not data.get("channel_id"):
        await interaction.response.send_message("❌ لازم تحدد روم البحث أول مرة.", ephemeral=True)
        return

    save_config()
    target = get_configured_channel(guild, data.get("channel_id"))
    state = "مفعّل" if data.get("enabled") else "متوقف"
    sources_text = "ScriptBlox" + (" + Rscripts" if RSCRIPTS_API_KEY else "")
    await interaction.response.send_message(
        f"🔎 **نظام بحث السكربتات**\n\n"
        f"الحالة: **{state}**\n"
        f"الروم: {target.mention if target else 'غير موجود'}\n"
        f"النتائج: **{data.get('max_results', 5)}**\n"
        f"Strict: **{'ON' if data.get('strict') else 'OFF'}**\n"
        f"المصادر النشطة: **{sources_text}**\n\n"
        "يمكن للأعضاء الكتابة مثل:\n"
        "`بحث Blox Fruits`\n"
        "`!بحث Blox Fruits`\n"
        "أو كتابة اسم اللعبة عربي/مختصر حتى لو فيه غلطة إملائية بسيطة."
        , ephemeral=True
    )