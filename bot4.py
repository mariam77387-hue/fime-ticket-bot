"""
Discord Roblox Script Search Bot
================================

نسخة مستقلة قابلة للاستبدال لملف البحث القديم.

المتطلبات:
    pip install -U discord.py

متغيرات البيئة:
    DISCORD_TOKEN       توكن البوت - مطلوب
    RSCRIPTS_API_KEY    اختياري، لتفعيل Rscripts API
    BOT_CONFIG_PATH     اختياري، الافتراضي: script_search_config.json
    ROBLOX_DISCOVERY    اختياري، 1 مفعّل افتراضيًا

ملاحظات:
* لا يتم تنفيذ أي كود يتم جلبه من المصادر.
* المصدر الخارجي قد يحتوي على كود غير موثوق. البوت يعرضه فقط بعد طلب
  المستخدم، مع تنبيه واضح.
* لا يتم استخدام scraping للمواقع التي لا تملك API موثقًا؛ هذا يمنع توقف
  البوت بسبب تغيّر HTML ويقلل المشاكل القانونية/التشغيلية. هذه المواقع
  (PUBLIC_SOURCE_SITES) تُعرض كروابط يفتحها المستخدم يدويًا فقط، ولا يتم
  جلب أو تحليل محتواها من طرف البوت.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import time
import traceback
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.ext import commands


# ---------------------------------------------------------------------------
# الإعداد العام
# ---------------------------------------------------------------------------

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
RSCRIPTS_API_KEY = os.getenv("RSCRIPTS_API_KEY", "").strip()
ENABLE_ROBLOX_DISCOVERY = os.getenv("ROBLOX_DISCOVERY", "1").lower() not in {
    "0",
    "false",
    "no",
}
CONFIG_PATH = Path(os.getenv("BOT_CONFIG_PATH", "script_search_config.json"))

SCRIPTBLOX_SEARCH_API = "https://scriptblox.com/api/script/search"
SCRIPTBLOX_RAW_API = "https://scriptblox.com/api/script/raw"
RSCRIPTS_API_BASE = "https://api.rscripts.net"
ROBLOX_SEARCH_API = "https://apis.roblox.com/search-api/omni-search"

# هذه المواقع لا تملك API عامًا موثقًا في النسخة الحالية.
# لا يتم عمل scraping لها؛ تُعرض فقط كروابط إضافية يفتحها المستخدم بنفسه
# عندما لا نجد نتيجة مؤكدة من المصادر البرمجية (ScriptBlox / Rscripts).
PUBLIC_SOURCE_SITES = {
    "Cheater.fun": "https://cheater.fun/",
    "Scriptrb": "https://scriptrb.com/",
    "Rscripts": "https://rscripts.net/",
    "Robscript": "https://robscript.com/",
}

DEFAULT_GUILD_CONFIG = {
    "enabled": False,
    "channel_id": None,
    "max_results": 5,
    "strict": False,
}

HTTP_HEADERS = {
    "User-Agent": "RobloxScriptSearchBot/2.1 (+Discord)",
    "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
}

# مهلة كل مصدر بحث على حدة، حتى لو تأخر مصدر واحد لا يعلّق البحث كله.
SOURCE_FETCH_TIMEOUT = 9.0


# ---------------------------------------------------------------------------
# قاعدة ألعاب واسعة + aliases عربية وإنجليزية
# ---------------------------------------------------------------------------
# الأسماء القصيرة جدًا أو العامة لا تُستخدم كاختصار مستقل إلا إذا كان
# الاستعلام نفسه هو الاختصار؛ هذا يمنع "ماب" أو "بيوت" من اختيار لعبة خطأ.
ROBLOX_GAMES: list[tuple[str, list[str]]] = [
    ("Blox Fruits", [
        "بلوكس فروت", "بلوكس فروتس", "بلوكس فروز", "بلوكس", "بلف",
        "blox fruit", "blox fruits", "bf",
    ]),
    ("Grow a Garden", [
        "جرو جاردن", "قرو جاردن", "قرو قاردن", "جرو", "المزرعة",
        "مزرعة", "ماب المزرعة", "grow a garden", "gag",
    ]),
    ("Steal a Brainrot", [
        "ستيل ا برين روت", "ستيل ابرين روت", "ستيل برين روت",
        "برين روت", "برينروت", "brain rot", "brainrot",
        "steal a brainrot", "steal brainrot",
    ]),
    ("Steal an Egg", [
        "سرقة البيض", "سرقه البيض", "سرقة بيض", "سرقه بيض",
        "سرقة بيضة", "steal an egg", "steal egg",
    ]),
    ("Murder Mystery 2", [
        "مردر مستري", "مردر ميستري", "ام ام تو", "ام ام 2", "ام ام",
        "ممر", "mm2", "mm 2", "murder mystery", "murder mystery 2",
    ]),
    ("DOORS", [
        "دورز", "دورس", "دور", "الباب", "ابواب", "doors",
    ]),
    ("Brookhaven", [
        "بروك هيفن", "بروكهافن", "ماب البيوت", "ماب بيوت",
        "بيوت", "brookhaven", "brookhaven rp",
    ]),
    ("Fisch", [
        "فيش", "فش", "سي فش", "الصيد", "صيد", "السمك", "سمك", "fisch",
    ]),
    ("BedWars", [
        "بد وارز", "بدورز", "بد وورز", "bed wars", "bedwars",
    ]),
    ("Blade Ball", [
        "بليد بول", "بليدبال", "بليد", "blade ball", "bladeball",
    ]),
    ("The Strongest Battlegrounds", [
        "سترونقست", "سترونجست", "ذا سترونجست", "اقوى ساحات القتال",
        "ماب القتال", "strongest", "tsb", "the strongest battlegrounds",
    ]),
    ("Pet Simulator 99", [
        "بت سيم", "بت سيموليتر", "بيت سيموليتر", "محاكي الحيوانات",
        "pet sim", "pet simulator", "pet simulator 99", "ps99",
    ]),
    ("Adopt Me!", [
        "ادوبت مي", "ادوبت", "تبني", "ماب الحيوانات", "الحيوانات",
        "adopt me", "adoptme",
    ]),
    ("Dress To Impress", [
        "دريس تو امبرس", "دريس تو", "ماب الملابس", "الملابس",
        "dress to impress", "dti",
    ]),
    ("99 Nights in the Forest", [
        "99 نايت", "99 نايتس", "ناينتي ناين", "الغابة", "الغابه",
        "ماب الغابة", "99 nights", "99 nights in the forest",
    ]),
    ("RIVALS", [
        "رايفلز", "رايفل", "ريفلز", "ماب رايفلز", "rivals",
    ]),
    ("Evade", [
        "ايفيد", "ايفيدد", "الهروب", "ماب الهروب", "evade",
    ]),
    ("Arsenal", [
        "ارسنال", "ارسنل", "تصويب", "arsenal",
    ]),
    ("Jailbreak", [
        "جيل بريك", "جيلبريك", "الهروب من السجن", "jailbreak",
    ]),
    ("Piggy", [
        "بيجي", "بقي", "خنزير", "piggy",
    ]),
    ("Tower of Hell", [
        "تاور اوف هيل", "تاور هيل", "تاور", "برج الجحيم",
        "tower of hell", "toh",
    ]),
    ("Da Hood", [
        "دا هود", "دهود", "ماب الشوارع", "da hood", "dahood",
    ]),
    ("Build A Boat For Treasure", [
        "بيلد بوت", "بيلد اي بوت", "بناء القارب", "ماب القارب",
        "build a boat", "build a boat for treasure", "babft",
    ]),
    ("Natural Disaster Survival", [
        "ناشورال ديزاستر", "ديزاستر", "الكوارث", "ماب الكوارث",
        "natural disaster survival", "nds", "natural disasters",
        "كوارث طبيعية",
    ]),
    ("MeepCity", [
        "ميب سيتي", "ميبستي", "ميب", "meepcity", "meep city",
    ]),
    ("Bee Swarm Simulator", [
        "بي سوارم", "محاكي النحل", "النحل", "bee swarm", "bss",
    ]),
    ("Tower Defense Simulator", [
        "تاور ديفنس", "دفاع الابراج", "دفاع الأبراج",
        "tower defense simulator", "tds",
    ]),
    ("Anime Vanguards", [
        "انمي فانقاردز", "انمي فانجاردز", "anime vanguards", "av",
    ]),
    ("King Legacy", [
        "كينق ليقاسي", "كنق ليجاسي", "ملك ليجاسي", "king legacy", "kl",
    ]),
    ("Shindo Life", [
        "شيندو لايف", "شيندو", "shindo life", "shindo",
    ]),
    ("Islands", [
        "ايلاندز", "سكاي بلوك", "islands", "skyblock",
    ]),
    ("Welcome to Bloxburg", [
        "بلوكسبيرق", "بلوكس بيرج", "بلوكسبورج", "بلكسبرق",
        "bloxburg", "welcome to bloxburg",
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
        "كومبات واريورز", "كومبات", "combat warriors", "cw",
    ]),
    ("PLS DONATE", [
        "بليز دونيت", "بليز", "pls donate", "pls",
    ]),
    ("Slap Battles", [
        "سلاب باتلز", "سلاب", "slap battles",
    ]),
    ("Untitled Boxing Game", [
        "بوكسينق قيم", "لعبة الملاكمة", "الملاكمة",
        "untitled boxing game", "ubg",
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
        "اول ستار تاور ديفنس", "أول ستار تاور ديفنس",
        "all star tower defense", "astd",
    ]),
    ("Ninja Legends 2", [
        "نينجا ليجندز", "نينجا ليجند", "ninja legends 2", "nl2",
    ]),
    ("Anime Defenders", [
        "انمي ديفندرز", "انمي دفندرز", "anime defenders", "ad",
    ]),
    ("Anime Fighters Simulator", [
        "انمي فايترز", "مقاتلي الانمي", "anime fighters", "afs",
    ]),
    ("Pet Simulator X", [
        "بت سيم اكس", "pet simulator x", "psx",
    ]),
    ("Mining Simulator 2", [
        "مايننق سيم", "محاكي التعدين", "mining simulator 2", "ms2",
    ]),
    ("Bubble Gum Simulator INFINITY", [
        "ببل قم", "بابل قم", "bubble gum simulator", "bgs",
    ]),
    ("Fishing Simulator", [
        "فيشنق سيم", "محاكي الصيد", "fishing simulator",
    ]),
    ("Livetopia", [
        "ليفتوبيا", "لايف توبيا", "livetopia",
    ]),
    ("Berry Avenue", [
        "بيري افنيو", "بيري أفنيو", "berry avenue",
    ]),
    ("Murderers VS Sheriffs DUELS", [
        "ام في اس", "mvsd", "murderers vs sheriffs", "murderers vs sheriffs duels",
    ]),
    ("Flee the Facility", [
        "فلي ذا فاسيليتي", "الهروب من المنشأة", "flee the facility", "ftf",
    ]),
    ("Breaking Point", [
        "بريكنق بوينت", "breaking point",
    ]),
    ("Survive the Killer", [
        "سرفايف ذا كيلر", "نجا من القاتل", "survive the killer", "stk",
    ]),
    ("Rainbow Friends", [
        "رينبو فريندز", "اصدقاء قوس قزح", "rainbow friends",
    ]),
    ("Poppy Playtime", [
        "بوبي بلاي تايم", "poppy playtime",
    ]),
    ("The Mimic", [
        "ذا ميمك", "ميمك", "the mimic",
    ]),
    ("Apeirophobia", [
        "ابيروفوبيا", "ابيوروفوبيا", "apeirophobia",
    ]),
    ("Pressure", [
        "بريشر", "pressure",
    ]),
    ("Dandy's World", [
        "دانديس ورلد", "دانديز وورلد", "dandy's world", "dandys world",
    ]),
    ("Regretevator", [
        "ريجريتيفيتر", "ريغريتيفيتر", "regretevator",
    ]),
    ("Work at a Pizza Place", [
        "بيتزا", "البيتزا", "العمل في البيتزا", "work at a pizza place",
    ]),
    ("Theme Park Tycoon 2", [
        "ثيم بارك", "مدينة الملاهي", "theme park tycoon 2", "tpt2",
    ]),
    ("Restaurant Tycoon 2", [
        "مطعم تايكون", "restaurant tycoon 2", "rt2",
    ]),
    ("My Restaurant!", [
        "مطعمي", "my restaurant",
    ]),
    ("Lumber Tycoon 2", [
        "لومبر", "قطع الخشب", "lumber tycoon 2", "lt2",
    ]),
    ("SCP: Roleplay", [
        "اس سي بي", "scp", "scp roleplay",
    ]),
    ("Military Tycoon", [
        "ميلتري تايكون", "العسكري", "military tycoon",
    ]),
    ("War Tycoon", [
        "وار تايكون", "war tycoon",
    ]),
    ("Vehicle Legends", [
        "فيكل ليجندز", "سيارات", "vehicle legends",
    ]),
    ("Driving Empire", [
        "درايفنق امباير", "امبراطورية السيارات", "driving empire",
    ]),
    ("Car Crushers 2", [
        "كار كراشرز", "تكسير السيارات", "car crushers 2", "cc2",
    ]),
    ("Nico's Nextbots", [
        "نيكوز نكست بوت", "نيكوز", "nico's nextbots", "nicos nextbots",
    ]),
    ("Horrific Housing", [
        "هوريفك هاوسنق", "horrific housing",
    ]),
    ("Murder Party", [
        "مردر بارتي", "murder party",
    ]),
    ("Epic Minigames", [
        "ايبك ميني قيمز", "العاب مصغرة", "epic minigames",
    ]),
    ("Survive the Disasters 2", [
        "سرفايف ذا ديزاسترز", "survive the disasters 2", "std2",
    ]),
    ("Mega Hide and Seek", [
        "ميقا هايد اند سيك", "mega hide and seek",
    ]),
    ("Hide and Seek Extreme", [
        "هايد اند سيك", "الغميضة", "hide and seek extreme",
    ]),
    ("Catalog Avatar Creator", [
        "كاتالوج افاتار", "صانع الافاتار", "catalog avatar creator", "cac",
    ]),
    ("Rate My Avatar", [
        "ريت ماي افاتار", "قيم شكلي", "rate my avatar", "rma",
    ]),
    ("Voice Chat Hangout", [
        "فويس شات", "روم الفويس", "voice chat hangout",
    ]),
    ("Please Donate Me", [
        "بليز دونيت مي", "please donate me",
    ]),
    ("Strongman Simulator", [
        "سترونق مان", "محاكي القوة", "strongman simulator",
    ]),
    ("Muscle Legends", [
        "مسكل ليجندز", "عضلات", "muscle legends",
    ]),
    ("Legends of Speed", [
        "ليجندز اوف سبيد", "اسرع لعبة", "legends of speed",
    ]),
    ("Speed Run 4", [
        "سبيد رن", "speed run 4", "sr4",
    ]),
    ("Obby But You're on a Bike", [
        "اوبي دراجة", "obby but you're on a bike", "obby bike",
    ]),
    ("Easy Obby", [
        "اوبي", "obby", "easy obby",
    ]),
    # --- إضافات: ألعاب أنمي/RPG وقتالية منتشرة كانت ناقصة ---
    ("Project Slayers", [
        "بروجكت سلاير", "بروجكت سلايرز", "project slayers", "ps",
    ]),
    ("Demonfall", [
        "ديمون فول", "ديمونفول", "demonfall", "demon fall",
    ]),
    ("Type Soul", [
        "تايب سول", "type soul",
    ]),
    ("A Universal Time", [
        "يونيفرسال تايم", "ايه يونيفرسال تايم", "a universal time", "aut",
    ]),
    ("Sol's RNG", [
        "سولز ار ان جي", "سول ار ان جي", "sol's rng", "sols rng", "solsrng",
    ]),
    ("Deepwoken", [
        "ديبووكن", "ديب ووكن", "deepwoken",
    ]),
    ("Grand Piece Online", [
        "جراند بيس اونلاين", "gpo", "grand piece online",
    ]),
    ("Haze Piece", [
        "هيز بيس", "haze piece",
    ]),
    ("Blue Lock Rivals", [
        "بلو لوك رايفلز", "blue lock rivals",
    ]),
    ("World Zero", [
        "ورلد زيرو", "world zero",
    ]),
    ("Saitama Battlegrounds", [
        "سايتاما ساحات القتال", "saitama battlegrounds",
    ]),
    ("Weapon Fighting Simulator", [
        "ويبن فايتنق سيم", "weapon fighting simulator", "wfs",
    ]),
    ("Prison Life", [
        "بريزن لايف", "prison life",
    ]),
    ("Zombie Uprising", [
        "زومبي ابرايزنق", "zombie uprising",
    ]),
    ("Superhero Tycoon", [
        "سوبر هيرو تايكون", "superhero tycoon",
    ]),
    ("Project Mugetsu", [
        "بروجكت موجيتسو", "project mugetsu", "pm",
    ]),
    ("Blox Piece", [
        "بلوكس بيس", "blox piece",
    ]),
    ("Untitled Attack on Titan", [
        "اتاك اون تايتن", "untitled attack on titan", "uaot", "aot",
    ]),
    ("Rogue Lineage", [
        "روج لينيج", "rogue lineage",
    ]),
    ("Trade Roulette", [
        "تريد روليت", "trade roulette",
    ]),
    ("Da Hood Original", [
        "دا هود اورجنال", "da hood original",
    ]),
    ("Pet Sim 99", [
        "بت سيم ٩٩", "pet sim 99",
    ]),
    ("Elemental Battlegrounds", [
        "المنتال ساحات القتال", "elemental battlegrounds", "ebg",
    ]),
    ("Ability Wars", [
        "ابيليتي وارز", "ability wars",
    ]),
    ("Untitled Tag Game", [
        "تاق قيم", "untitled tag game",
    ]),
    # --- إضافات دفعة ثانية بناءً على طلب المستخدم ---
    ("Time Bomb", [
        "تايم بومب", "تايم بامب", "تايمبومب", "تايمبامب",
        "timebomb", "time bomb",
    ]),
    ("Prop Hunt", [
        "بروب هانت", "براب هنت", "prop hunt",
    ]),
    ("Wacky Wizards", [
        "واكي ويزاردز", "واكي ويزارد", "wacky wizards",
    ]),
    ("Anime Adventures", [
        "انمي ادفنتشرز", "انمي ادفنشرز", "anime adventures", "aa",
    ]),
    ("Anime Speed Simulator", [
        "انمي سبيد سيميوليتر", "anime speed simulator", "ass",
    ]),
    ("Peroxide", [
        "بيروكسايد", "بروكسايد", "peroxide",
    ]),
    ("Tapping Legends X", [
        "تابنق ليجندز اكس", "tapping legends x", "tlx",
    ]),
    ("The Backrooms", [
        "ذا باك رومز", "الباك رومز", "the backrooms", "backrooms",
    ]),
    ("Scary Elevator", [
        "سكيري اليفيتر", "المصعد المخيف", "scary elevator",
    ]),
    ("Pumpkin Days", [
        "بمبكن دايز", "pumpkin days",
    ]),
    ("Find the Markers", [
        "فايند ذا ماركرز", "find the markers", "ftm",
    ]),
    ("Doomspire Brickbattle", [
        "دومسباير بريك باتل", "doomspire brickbattle", "dsbb",
    ]),
    ("1 vs All", [
        "ون في اس اول", "1 vs all",
    ]),
    ("Zombie Attack: Last Stand", [
        "زومبي اتاك لاست ستاند", "zombie attack last stand", "zals",
    ]),
    ("Bloody Trapland 2 Reborn", [
        "بلودي تراب لاند", "bloody trapland 2 reborn", "bt2",
    ]),
    ("RoCitizens", [
        "روسيتيزنز", "rocitizens",
    ]),
    ("Basketball Stars", [
        "باسكت بول ستارز", "basketball stars",
    ]),
    ("Untitled Farming Game", [
        "لعبة الزراعة", "untitled farming game", "ufg",
    ]),
]


# ---------------------------------------------------------------------------
# تطبيع ومطابقة الألعاب
# ---------------------------------------------------------------------------

ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
ARABIC_CHARS = re.compile(r"[\u0600-\u06FF]")
NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
MULTI_SPACE = re.compile(r"\s+")


def normalize_search_text(value: Any) -> str:
    """توحيد الكتابة العربية والإنجليزية قبل البحث."""
    text = str(value or "").strip().casefold()
    text = text.replace("\u0640", "")  # التطويل
    text = ARABIC_DIACRITICS.sub("", text)
    text = (
        text.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    text = text.translate(str.maketrans({
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    }))
    text = text.replace("&", " and ")
    text = NON_WORD.sub(" ", text)
    return MULTI_SPACE.sub(" ", text).strip()


def compact_text(value: Any) -> str:
    return normalize_search_text(value).replace(" ", "")


def without_definite_article(value: str) -> str:
    words = []
    for word in value.split():
        words.append(word[2:] if word.startswith("ال") and len(word) > 3 else word)
    return " ".join(words)


# ---------------------------------------------------------------------------
# هيكل صوتي عام (Arabic → Latin تقريبي) لدعم مطابقة أي اسم لعبة عربي/إنجليزي
# دون الحاجة لإضافة alias يدوي لكل تهجئة ممكنة (تايم بومب / تايم بامب / ...).
# ---------------------------------------------------------------------------

_ARABIC_TO_LATIN = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h",
    "خ": "kh", "د": "d", "ذ": "th", "ر": "r", "ز": "z", "س": "s",
    "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a",
    "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "ة": "h", "و": "w", "ي": "y", "ء": "",
}
_VOWELS = set("aeiou")

# كلمات حشو عامة (عربي/إنجليزي) لا تحمل معنى مميّزًا لاسم اللعبة، ويجب
# استبعادها قبل حساب الهيكل الصوتي حتى لا تسبب تطابقات عشوائية بين
# جمل لا علاقة لها ببعض لمجرد احتوائها كلمات شائعة مثل "لعبة"/"ماب".
_PHONETIC_STOPWORDS = {
    "لعبه", "لعبة", "ماب", "سكربت", "كود", "ابغى", "ابي", "اريد",
    "بحث", "ابحث", "من", "في", "على", "رجاء", "الرجاء", "وجود",
    "مالها", "اصلا", "شي", "حلو", "script", "code", "map", "game",
    "please", "the", "a", "an", "search",
}


def _strip_phonetic_stopwords(normalized_text: str) -> str:
    words = [w for w in normalized_text.split() if w not in _PHONETIC_STOPWORDS]
    return " ".join(words)


def _transliterate_arabic(normalized_text: str) -> str:
    """تحويل تقريبي من عربي مُطبّع (بعد normalize_search_text) إلى لاتيني.
    أي حرف لاتيني أصلًا يبقى كما هو، لذلك تعمل على نص عربي أو إنجليزي أو مزيج."""
    return "".join(_ARABIC_TO_LATIN.get(ch, ch) for ch in normalized_text)


def _phonetic_skeleton(value: Any) -> str:
    """
    هيكل صوتي مبسّط: إزالة كلمات الحشو، تحويل تقريبي للاتيني، إزالة
    المسافات وحروف العلة (a/e/i/o/u)، ودمج الحروف المتكررة المتتالية.
    هذا يجعل تهجئات مختلفة لنفس الكلمة (تايم بومب / تايم بامب / TimeBomb)
    تتقارب على نفس الهيكل تقريبًا، عوضًا عن الاعتماد الكامل على aliases
    يدوية، مع حماية من التطابق العشوائي بسبب كلمات حشو مشتركة.
    """
    normalized = _strip_phonetic_stopwords(normalize_search_text(value))
    latin = _transliterate_arabic(normalized).replace(" ", "").casefold()
    skeleton_chars: list[str] = []
    prev = ""
    for ch in latin:
        if ch in _VOWELS:
            continue
        if ch == prev:
            continue
        skeleton_chars.append(ch)
        prev = ch
    return "".join(skeleton_chars)


def clean_script_query(content: str) -> str:
    """إزالة أوامر البحث والكلمات الحشو من دون حذف اسم اللعبة."""
    value = str(content or "").strip()
    value = re.sub(
        r"^\s*(?:[!؟?./]?\s*)?(?:بحث|ابحث|سكربت|كود|script|search)\b[:\-\s]*",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\s+", " ", value).strip(" -:،,")
    return value


def _alias_variants(value: str) -> set[str]:
    normalized = normalize_search_text(value)
    if not normalized:
        return set()
    variants = {normalized, compact_text(normalized)}
    no_article = without_definite_article(normalized)
    if no_article and no_article != normalized:
        variants.add(no_article)
        variants.add(compact_text(no_article))
    return {item for item in variants if item}


_GAME_EXACT_INDEX: dict[str, set[str]] | None = None
_GAME_ALIASES: dict[str, set[str]] | None = None
_GAME_CANONICAL_NORMALIZED: dict[str, str] | None = None
_GAME_SKELETONS: dict[str, set[str]] | None = None


def _build_game_indexes() -> None:
    global _GAME_EXACT_INDEX, _GAME_ALIASES, _GAME_CANONICAL_NORMALIZED, _GAME_SKELETONS
    if _GAME_EXACT_INDEX is not None:
        return

    exact: dict[str, set[str]] = {}
    aliases_by_game: dict[str, set[str]] = {}
    canonical_normalized: dict[str, str] = {}
    skeletons_by_game: dict[str, set[str]] = {}

    for canonical, raw_aliases in ROBLOX_GAMES:
        all_aliases = set(raw_aliases) | {canonical}
        normalized_aliases: set[str] = set()
        skeleton_set: set[str] = set()
        canonical_normalized[canonical] = normalize_search_text(canonical)
        for alias in all_aliases:
            for variant in _alias_variants(alias):
                normalized_aliases.add(variant)
                exact.setdefault(variant, set()).add(canonical)
                skeleton = _phonetic_skeleton(variant)
                if len(skeleton) >= 4:
                    skeleton_set.add(skeleton)
        aliases_by_game[canonical] = normalized_aliases
        skeletons_by_game[canonical] = skeleton_set

    _GAME_EXACT_INDEX = exact
    _GAME_ALIASES = aliases_by_game
    _GAME_CANONICAL_NORMALIZED = canonical_normalized
    _GAME_SKELETONS = skeletons_by_game


def _contains_alias(query: str, alias: str) -> bool:
    """مطابقة داخل النص مع حماية الاختصارات القصيرة من المطابقة الجزئية."""
    if not alias:
        return False
    if query == alias or compact_text(query) == alias:
        return True
    if len(alias) <= 3:
        return alias in query.split()
    return alias in query or alias in compact_text(query)


def _query_windows(text: str, max_words: int = 6) -> Iterable[str]:
    words = text.split()
    for size in range(min(max_words, len(words)), 0, -1):
        for start in range(0, len(words) - size + 1):
            yield " ".join(words[start:start + size])


def identify_target_game(query: str) -> tuple[str | None, str]:
    """
    يرجع (الاسم الرسمي، الثقة):
        exact  = alias أو اسم رسمي واضح
        fuzzy  = خطأ إملائي بسيط
        none   = لا توجد مطابقة آمنة

    (بدون تغيير عن النسخة الأصلية بناءً على طلب المستخدم)
    """
    _build_game_indexes()
    assert _GAME_EXACT_INDEX is not None
    assert _GAME_ALIASES is not None

    text = normalize_search_text(clean_script_query(query))
    if not text:
        return None, "none"

    for candidate in (text, compact_text(text), without_definite_article(text)):
        owners = _GAME_EXACT_INDEX.get(candidate, set())
        if len(owners) == 1:
            return next(iter(owners)), "exact"

    exact_hits: list[tuple[int, str]] = []
    for canonical, aliases in _GAME_ALIASES.items():
        for alias in aliases:
            if _contains_alias(text, alias):
                exact_hits.append((len(alias), canonical))
    if exact_hits:
        exact_hits.sort(reverse=True)
        longest_length = exact_hits[0][0]
        winners = {name for length, name in exact_hits if length == longest_length}
        if len(winners) == 1:
            return next(iter(winners)), "exact"

    best_by_game: dict[str, float] = {}
    for window in _query_windows(text):
        window_compact = compact_text(window)
        for canonical, aliases in _GAME_ALIASES.items():
            for alias in aliases:
                if len(alias) < 4:
                    continue
                ratio = max(
                    SequenceMatcher(None, window, alias).ratio(),
                    SequenceMatcher(None, window_compact, alias.replace(" ", "")).ratio(),
                )
                if ratio > best_by_game.get(canonical, 0.0):
                    best_by_game[canonical] = ratio

    # طبقة إضافية عامة: مقارنة "الهيكل الصوتي" للنص المكتوب (عربي أو
    # إنجليزي) مع الهيكل الصوتي لاسم كل لعبة وaliases الخاصة بها. هذا ما
    # يسمح بالتعرف على تهجئات جديدة لم تُضف كـ alias يدوي مسبقًا
    # (مثال: "تايم بامب" أو "تايمبومب" لنفس "Time Bomb")، بدل الاعتماد
    # الكامل على قائمة aliases يدوية لكل لعبة.
    # عتبة أعلى من الطبقة النصية العادية (0.86 بدل 0.84) لأن الهيكل
    # الصوتي أقصر وأكثر عرضة للتطابق العشوائي، وطول أدنى 4 بدل 3.
    assert _GAME_SKELETONS is not None
    SKELETON_THRESHOLD = 0.86
    query_skeleton = _phonetic_skeleton(text)
    if len(query_skeleton) >= 4:
        for window in _query_windows(text, max_words=4):
            window_skeleton = _phonetic_skeleton(window)
            if len(window_skeleton) < 4:
                continue
            for canonical, skeletons in _GAME_SKELETONS.items():
                for skeleton in skeletons:
                    ratio = SequenceMatcher(None, window_skeleton, skeleton).ratio()
                    if ratio >= SKELETON_THRESHOLD and ratio > best_by_game.get(canonical, 0.0):
                        best_by_game[canonical] = ratio

    ranked = sorted(
        ((ratio, canonical) for canonical, ratio in best_by_game.items()),
        reverse=True,
    )
    best = ranked[0] if ranked else (0.0, "")
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    threshold = 0.84 if len(text.replace(" ", "")) >= 7 else 0.90
    if best[1] and best[0] >= threshold and best[0] - second >= 0.025:
        return best[1], "fuzzy"
    return None, "none"


def translate_game_alias(query: str) -> str:
    # (بدون تغيير عن النسخة الأصلية بناءً على طلب المستخدم)
    name, _confidence = identify_target_game(query)
    return name or clean_script_query(query)


def _game_matches_target(
    game_name: str,
    target_name: str,
    strict: bool = True,
) -> bool:
    source = normalize_search_text(game_name)
    target = normalize_search_text(target_name)

    if not target:
        return False

    # إذا المصدر لم يرسل اسم اللعبة، لا نحذف النتيجة مباشرة
    if not source:
        return True

    # تطابق مباشر
    if source == target or compact_text(source) == compact_text(target):
        return True

    _build_game_indexes()
    assert _GAME_ALIASES is not None

    # فحص جميع أسماء اللعبة والاختصارات
    target_aliases = _GAME_ALIASES.get(target_name, set())

    for alias in target_aliases:
        if not alias:
            continue

        if _contains_alias(source, alias):
            return True

        # مقارنة مختصرة
        source_compact = compact_text(source)
        alias_compact = compact_text(alias)

        if alias_compact and alias_compact in source_compact:
            return True

    # نتأكد هل اسم المصدر يشير بوضوح إلى لعبة مختلفة
    detected, confidence = identify_target_game(source)

    if detected and detected != target_name:
        if confidence in {"exact", "fuzzy"}:
            return False

    # إذا strict مفعّل، لا نقبل مطابقة ضعيفة
    if strict:
        return False

    # مطابقة تقريبية احتياطية
    source_words = set(source.split())
    target_words = set(target.split())

    shared = source_words & target_words

    ratio = max(
        SequenceMatcher(None, source, target).ratio(),
        SequenceMatcher(
            None,
            compact_text(source),
            compact_text(target),
        ).ratio(),
    )

    if shared and ratio >= 0.55:
        return True

    return ratio >= 0.75


def _match_strength(game_name: str, target_name: str) -> str:
    """يميّز قوة المطابقة لأغراض الترتيب فقط (exact/alias مقابل fuzzy)."""
    source = normalize_search_text(game_name)
    target = normalize_search_text(target_name)
    if not source or not target:
        return "none"
    if source == target or compact_text(source) == compact_text(target):
        return "exact"

    _build_game_indexes()
    assert _GAME_ALIASES is not None
    for alias in _GAME_ALIASES.get(target_name, set()):
        if _contains_alias(source, alias):
            return "alias"
    return "fuzzy"


# ---------------------------------------------------------------------------
# HTTP + Roblox automatic discovery
# ---------------------------------------------------------------------------


async def _http_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    retries: int = 1,
) -> tuple[Any, dict[str, str]]:
    last_error: Exception | None = None
    request_headers = dict(HTTP_HEADERS)
    request_headers.update(headers or {})

    for attempt in range(retries + 1):
        try:
            request = Request(url, headers=request_headers)

            def do_request() -> tuple[Any, dict[str, str]]:
                with urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    response_headers = {
                        str(key).lower(): str(value)
                        for key, value in response.headers.items()
                    }
                    content_type = response_headers.get("content-type", "")
                    text = raw.decode("utf-8", errors="replace")
                    if "json" in content_type or text.lstrip().startswith(("{", "[")):
                        return json.loads(text), response_headers
                    return text, response_headers

            return await asyncio.to_thread(do_request)
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                await asyncio.sleep(0.45 * (attempt + 1))

    raise last_error or RuntimeError("HTTP request failed")


async def _http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 15,
    retries: int = 1,
) -> tuple[Any, dict[str, str]]:
    return await _http_request(
        url,
        headers=headers,
        timeout=timeout,
        retries=retries,
    )


async def _http_get_text(url: str, *, timeout: int = 15) -> str:
    data, _headers = await _http_request(url, timeout=timeout, retries=1)
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False)


_ROBLOX_DISCOVERY_CACHE: dict[str, tuple[float, str | None]] = {}
_ROBLOX_DISCOVERY_LOCK = asyncio.Lock()
DISCOVERY_CACHE_TTL = 60 * 60 * 12


def _contains_arabic(value: str) -> bool:
    return bool(ARABIC_CHARS.search(value))


async def discover_roblox_game(query: str) -> str | None:
    """
    fallback تلقائي للعبة غير الموجودة في القائمة المحلية.
    Roblox Search API يعيد أسماء ألعاب عامة؛ لا يتم اعتبار النتيجة مؤكدة
    إلا إذا كانت قريبة جدًا من الاستعلام الإنجليزي.
    """
    if not ENABLE_ROBLOX_DISCOVERY:
        return None

    raw = clean_script_query(query)
    normalized = normalize_search_text(raw)
    if not normalized or _contains_arabic(normalized):
        return None

    cache_key = compact_text(normalized)
    now = time.monotonic()
    cached = _ROBLOX_DISCOVERY_CACHE.get(cache_key)
    if cached and now - cached[0] < DISCOVERY_CACHE_TTL:
        return cached[1]

    async with _ROBLOX_DISCOVERY_LOCK:
        cached = _ROBLOX_DISCOVERY_CACHE.get(cache_key)
        if cached and now - cached[0] < DISCOVERY_CACHE_TTL:
            return cached[1]

        url = (
            f"{ROBLOX_SEARCH_API}?searchQuery={quote_plus(raw)}"
            f"&pageToken=&sessionId={quote_plus(uuid.uuid4().hex)}"
        )
        result: str | None = None
        try:
            data, _headers = await asyncio.wait_for(
                _http_get_json(url, timeout=8, retries=0),
                timeout=SOURCE_FETCH_TIMEOUT,
            )
            candidates: list[str] = []
            for group in (data or {}).get("searchResults", []) if isinstance(data, dict) else []:
                if not isinstance(group, dict):
                    continue
                if group.get("contentGroupType") not in {None, "Game"}:
                    continue
                for item in group.get("contents", []):
                    if isinstance(item, dict) and item.get("name"):
                        candidates.append(str(item["name"]))

            best_name = ""
            best_ratio = 0.0
            for name in candidates[:30]:
                candidate = normalize_search_text(name)
                ratio = max(
                    SequenceMatcher(None, normalized, candidate).ratio(),
                    SequenceMatcher(None, compact_text(normalized), compact_text(candidate)).ratio(),
                )
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_name = name
            if best_name and best_ratio >= 0.86:
                result = best_name
        except asyncio.TimeoutError:
            print("[roblox-discovery] timeout")
        except Exception as error:
            print(f"[roblox-discovery] {type(error).__name__}: {error}")

        _ROBLOX_DISCOVERY_CACHE[cache_key] = (now, result)
        return result


# ---------------------------------------------------------------------------
# مصادر السكربتات وتوحيد النتائج
# ---------------------------------------------------------------------------


def _empty_result(
    *,
    title: Any,
    game_name: Any,
    url: str,
    source: str,
    game_image: Any = None,
    script_image: Any = None,
    verified: Any = False,
    has_key: Any = False,
    is_patched: Any = False,
    raw_script: Any = None,
    raw_url: Any = None,
    risk_level: Any = None,
) -> dict[str, Any]:
    return {
        "title": str(title or "بدون عنوان").strip(),
        "game_name": str(game_name or "").strip(),
        "game_image": game_image,
        "script_image": script_image,
        "url": str(url or "").strip(),
        "verified": bool(verified),
        "has_key": bool(has_key),
        "is_patched": bool(is_patched),
        "raw_script": str(raw_script).strip() if raw_script else None,
        "raw_url": str(raw_url).strip() if raw_url else None,
        "source": source,
        "risk_level": str(risk_level).strip() if risk_level else None,
    }


async def _fetch_with_timeout(coro, source_name: str) -> list[dict[str, Any]]:
    try:
        return await asyncio.wait_for(coro, timeout=SOURCE_FETCH_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"[{source_name}] انتهت المهلة قبل الرد")
        return []
    except Exception as error:
        print(f"[{source_name}] {type(error).__name__}: {error}")
        return []


async def fetch_scriptblox_results(
    search_query: str,
    max_results: int,
    _strict: bool,
) -> list[dict[str, Any]]:
    # مهم: لا نمرر إعداد "strict" الخاص بالسيرفر إلى ScriptBlox API نفسه.
    # كان هذا هو السبب الفعلي لعدم ظهور نتائج مثل Evade: ScriptBlox كانت
    # تضيّق النتائج من عندها *قبل* ما تصل لمنطق المطابقة عندنا، فحتى لو
    # كانت مطابقتنا المحلية مرنة 100% ما كان عندها شي تشتغل عليه.
    # الآن نطلب دائمًا أوسع نتائج ممكنة من المصدر، والفلترة/الصرامة الحقيقية
    # تتم محليًا عبر _game_matches_target بحسب إعداد السيرفر.
    params = (
        f"q={quote_plus(search_query)}"
        f"&max={max(1, min(20, int(max_results)))}"
        "&strict=false"
        "&sortBy=updatedAt&order=desc"
    )
    data, _headers = await _http_get_json(
        f"{SCRIPTBLOX_SEARCH_API}?{params}",
        timeout=15,
        retries=1,
    )

    result = data.get("result") if isinstance(data, dict) else None
    scripts = result.get("scripts", []) if isinstance(result, dict) else []
    normalized: list[dict[str, Any]] = []
    for item in scripts if isinstance(scripts, list) else []:
        if not isinstance(item, dict):
            continue
        game = item.get("game") or {}
        slug_or_id = item.get("slug") or item.get("_id") or ""
        normalized.append(_empty_result(
            title=item.get("title"),
            game_name=game.get("name"),
            game_image=game.get("imageUrl"),
            script_image=item.get("image"),
            url=(
                f"https://scriptblox.com/script/{quote_plus(str(slug_or_id))}"
                if slug_or_id else "https://scriptblox.com/"
            ),
            verified=item.get("verified"),
            has_key=item.get("key"),
            is_patched=item.get("isPatched"),
            raw_script=item.get("script"),
            raw_url=(
                f"{SCRIPTBLOX_RAW_API}/{quote_plus(str(slug_or_id))}"
                if slug_or_id else None
            ),
            source="ScriptBlox",
        ))
    return normalized


async def fetch_rscripts_results(
    search_query: str,
    max_results: int,
    _strict: bool,
) -> list[dict[str, Any]]:
    if not RSCRIPTS_API_KEY:
        return []

    params = (
        f"q={quote_plus(search_query)}&index=scripts"
        f"&limit={max(1, min(20, int(max_results)))}"
    )
    headers = {
        "Authorization": f"Bearer {RSCRIPTS_API_KEY}",
        "Accept": "application/json",
    }
    data, _headers = await _http_get_json(
        f"{RSCRIPTS_API_BASE}/v1/search?{params}",
        headers=headers,
        timeout=15,
        retries=1,
    )

    if not isinstance(data, dict) or not data.get("success"):
        return []

    scripts = ((data.get("data") or {}).get("scripts")) or []
    normalized: list[dict[str, Any]] = []
    for item in scripts if isinstance(scripts, list) else []:
        if not isinstance(item, dict):
            continue
        game = item.get("game") or {}
        risk = item.get("risk") or {}
        creator = item.get("creator") or {}
        slug = item.get("slug") or ""
        normalized.append(_empty_result(
            title=item.get("title"),
            game_name=game.get("title") or game.get("name"),
            game_image=game.get("thumbnailUrl") or game.get("logoUrl"),
            url=f"https://rscripts.net/script/{slug}" if slug else "https://rscripts.net/",
            verified=creator.get("isVerified"),
            has_key=item.get("isKeySystem"),
            is_patched=item.get("isPatched"),
            raw_script=item.get("script"),
            raw_url=item.get("rawScript"),
            source="Rscripts",
            risk_level=risk.get("level"),
        ))
    return normalized


# ملاحظة عن cheater.fun / scriptrb.com / robscript.com:
# هذه المواقع ليس لديها API موثق حاليًا، لذلك لا يوجد لها fetcher هنا —
# عمل scraping غير موثّق عليها هش وقد ينكسر مع أي تحديث HTML، وهذا هو
# السبب الأصلي في استبعادها من البحث الآلي. بدلًا من ذلك تُعرض للمستخدم
# كروابط "مصادر إضافية يدويًا" في send_script_result أدناه عندما لا نجد
# نتيجة مؤكدة، دون أن يقوم البوت بجلب أو تحليل محتواها.
SOURCE_FETCHERS = (
    ("ScriptBlox", fetch_scriptblox_results),
    ("Rscripts", fetch_rscripts_results),
)


def _result_score(result: dict[str, Any], target_name: str) -> float:
    score = 0.0
    strength = _match_strength(result.get("game_name", ""), target_name)
    if strength == "exact":
        score += 100
    elif strength == "alias":
        score += 85
    elif strength == "fuzzy":
        score += 55

    if result.get("verified"):
        score += 12
    if not result.get("is_patched"):
        score += 8
    if not result.get("has_key"):
        score += 2
    if (result.get("risk_level") or "").casefold() in {"safe", "low risk", "low"}:
        score += 3
    if result.get("source") == "Rscripts":
        score += 0.5
    return score


def _deduplicate_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in results:
        key = (
            result.get("url")
            or f"{result.get('source')}|{result.get('title')}|{result.get('game_name')}"
        ).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


_SEARCH_CACHE: dict[str, tuple[float, tuple[list[dict[str, Any]], str | None, str]]] = {}
_SEARCH_CACHE_TTL = 45
_SEARCH_SEMAPHORE = asyncio.Semaphore(4)

async def search_all_sources(
    original_query: str,
    max_results: int = 5,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], str | None, str]:
    """
    البحث المتوازي ثم فلترة النتائج حسب اللعبة المتعرّف عليها.
    """

    query = clean_script_query(original_query)

    target_name, confidence = identify_target_game(query)

    if not target_name:
        discovered = await discover_roblox_game(query)

        if discovered:
            target_name, confidence = discovered, "discovered"

    if not query:
        return [], target_name, confidence

    cache_key = (
        f"{compact_text(target_name or query)}"
        f"|{max_results}|{strict}"
    )

    cached = _SEARCH_CACHE.get(cache_key)

    if cached and time.monotonic() - cached[0] < _SEARCH_CACHE_TTL:
        return cached[1]

    # نرسل اسم اللعبة للمصادر بدل الجملة كاملة
    search_query = target_name or query

    async with _SEARCH_SEMAPHORE:
        fetched = await asyncio.gather(
            *[
                _fetch_with_timeout(
                    fetcher(
                        search_query,
                        max_results,
                        strict,
                    ),
                    source_name,
                )
                for source_name, fetcher in SOURCE_FETCHERS
            ],
            return_exceptions=False,
        )

    combined: list[dict[str, Any]] = []

    for source_results in fetched:
        combined.extend(source_results)

    combined = _deduplicate_results(combined)

    # إذا تم التعرف على اللعبة، نفلتر النتائج حسبها
    if target_name:
        matched_results: list[dict[str, Any]] = []

        for result in combined:
            game_name = result.get("game_name") or ""

            if _game_matches_target(
                game_name,
                target_name,
                strict=strict,
            ):
                matched_results.append(result)

        combined = matched_results

        combined.sort(
            key=lambda result: _result_score(
                result,
                target_name,
            ),
            reverse=True,
        )

    # إذا لم يتم التعرف على لعبة محددة
    else:
        combined.sort(
            key=lambda result: (
                bool(result.get("verified")),
                not bool(result.get("is_patched")),
                not bool(result.get("has_key")),
            ),
            reverse=True,
        )

    final = (
    combined[
        : max(
            1,
            min(20, int(max_results)),
        )
    ],
    target_name,
    confidence,
)

_SEARCH_CACHE[cache_key] = (
    time.monotonic(),
    final,
)

return final



async def _resolve_script_text(result: dict[str, Any]) -> str:
    raw = result.get("raw_script")
    if raw:
        return str(raw).strip()

    raw_url = result.get("raw_url")
    if not raw_url:
        return ""

    try:
        raw = await asyncio.wait_for(
            _http_get_text(str(raw_url), timeout=15),
            timeout=SOURCE_FETCH_TIMEOUT,
        )
    except Exception as error:
        print(f"[raw-script] {type(error).__name__}: {error}")
        return ""

    raw = str(raw or "").strip()

    try:
        parsed = json.loads(raw)

        if isinstance(parsed, dict):
            return str(
                parsed.get("script")
                or parsed.get("raw")
                or parsed.get("content")
                or ""
            ).strip()

    except json.JSONDecodeError:
        pass

    return raw


# ---------------------------------------------------------------------------
# الإعدادات والتخزين
# ---------------------------------------------------------------------------


def _load_config() -> dict[str, dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as error:
        print(f"[config] تعذر قراءة الإعدادات: {error}")
        return {}


GUILD_CONFIG: dict[str, dict[str, Any]] = _load_config()


def save_config() -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(GUILD_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        print(f"[config] تعذر حفظ الإعدادات: {error}")


def get_script_search_config(guild: discord.Guild | None) -> dict[str, Any]:
    if guild is None:
        return dict(DEFAULT_GUILD_CONFIG)
    key = str(guild.id)
    current = dict(DEFAULT_GUILD_CONFIG)
    current.update(GUILD_CONFIG.get(key, {}))
    return current


def get_configured_channel(
    guild: discord.Guild | None,
    channel_id: Any,
) -> discord.TextChannel | None:
    if guild is None or not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    return channel if isinstance(channel, discord.TextChannel) else None


# ---------------------------------------------------------------------------
# Discord UI
# ---------------------------------------------------------------------------


def _embed_color(result: dict[str, Any]) -> discord.Color:
    if result.get("is_patched"):
        return discord.Color.red()
    if result.get("has_key"):
        return discord.Color.orange()
    if result.get("verified"):
        return discord.Color.green()
    return discord.Color.blurple()


def _build_result_embed(
    result: dict[str, Any],
    query_label: str,
    index: int,
    total: int,
    target_name: str | None,
) -> discord.Embed:
    verified = "✅ موثق" if result.get("verified") else "⚪ غير موثق"
    key = "🔑 يحتاج Key" if result.get("has_key") else "🔓 بدون Key"
    patched = "⚠️ Patched" if result.get("is_patched") else "🟢 غير Patched"
    game_name = result.get("game_name") or "غير معروف"

    lines = [
        f"**{result.get('title') or 'بدون عنوان'}**",
        "",
        f"🎮 اللعبة: **{game_name}**",
        f"{verified} • {key} • {patched}",
    ]
    if target_name:
        lines.append(f"🎯 المطابقة: **{target_name}**")
    if result.get("risk_level"):
        lines.append(f"🛡 مستوى الأمان المعلن من المصدر: **{result['risk_level']}**")
    lines.extend([
        "",
        f"🔗 [فتح صفحة السكربت]({result.get('url') or 'https://scriptblox.com/'})",
        "⚠️ لا تشغّل كودًا من مصدر غير موثوق قبل مراجعته.",
    ])
    if total > 1:
        lines.append(f"\nالنتيجة **{index + 1}** من **{total}** لـ `{query_label}`")

    embed = discord.Embed(
        title="🔎 نتيجة بحث Roblox",
        description="\n".join(lines),
        color=_embed_color(result),
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"المصدر: {result.get('source', 'غير معروف')}")
    if result.get("game_image"):
        embed.set_thumbnail(url=str(result["game_image"]))
    if result.get("script_image"):
        embed.set_image(url=str(result["script_image"]))
    return embed


class ScriptResultView(discord.ui.View):
    def __init__(
        self,
        results: list[dict[str, Any]],
        query_label: str,
        owner_id: int,
        target_name: str | None,
    ):
        super().__init__(timeout=180)
        self.results = results
        self.query_label = query_label
        self.owner_id = owner_id
        self.target_name = target_name
        self.index = 0
        if len(results) <= 1:
            self.previous_result.disabled = True
            self.next_result.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "❌ هذه النتائج مرتبطة بصاحب طلب البحث.",
                ephemeral=True,
            )
            return False
        return True

    def _current_embed(self) -> discord.Embed:
        return _build_result_embed(
            self.results[self.index],
            self.query_label,
            self.index,
            len(self.results),
            self.target_name,
        )

    @discord.ui.button(label="السابق", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def previous_result(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self.index = (self.index - 1) % len(self.results)
        await interaction.response.edit_message(
            embed=self._current_embed(),
            view=self,
        )

    @discord.ui.button(label="التالي", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next_result(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        self.index = (self.index + 1) % len(self.results)
        await interaction.response.edit_message(
            embed=self._current_embed(),
            view=self,
        )

    @discord.ui.button(label="عرض الكود", emoji="📄", style=discord.ButtonStyle.primary)
    async def show_code(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        result = self.results[self.index]
        raw = await _resolve_script_text(result)
        if not raw:
            await interaction.followup.send(
                "❌ المصدر لم يوفّر الكود الخام لهذه النتيجة.",
                ephemeral=True,
            )
            return

        if len(raw) <= 1800:
            await interaction.followup.send(
                "⚠️ راجع الكود قبل تشغيله؛ لا يوجد ضمان أن محتوى المصدر آمن.\n"
                f"```lua\n{raw}\n```",
                ephemeral=True,
            )
            return

        safe_name = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(result.get("title") or "script"),
        )[:60] or "script"
        file_data = io.BytesIO(raw.encode("utf-8"))
        file_data.seek(0)
        await interaction.followup.send(
            "⚠️ أرسلت الكود كملف؛ راجعه قبل تشغيله.",
            file=discord.File(file_data, filename=f"{safe_name}.lua"),
            ephemeral=True,
        )

    async def on_timeout(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True


def _manual_sources_view(target_name: str | None) -> discord.ui.View | None:
    """
    أزرار روابط فقط (لا يتم جلب أي محتوى منها) لمواقع لا تملك API موثقًا،
    تُعرض فقط عندما لا نجد نتيجة مؤكدة من المصادر البرمجية.
    """
    if not PUBLIC_SOURCE_SITES:
        return None
    view = discord.ui.View(timeout=None)
    for name, url in PUBLIC_SOURCE_SITES.items():
        view.add_item(discord.ui.Button(label=name, url=url, style=discord.ButtonStyle.link))
    return view


async def send_script_result(message: discord.Message, query: str) -> None:
    guild = message.guild
    data = get_script_search_config(guild)
    results, target_name, confidence = await search_all_sources(
        query,
        max_results=int(data.get("max_results", 5)),
        strict=bool(data.get("strict", True)),
    )

    if not results:
        if target_name:
            extra = (
                f"تعرفت على اللعبة: **{target_name}**، "
                "لكن لم أجد نتيجة مرتبطة بها في المصادر المفعّلة."
            )
        else:
            extra = (
                "لم أتعرف على اسم لعبة بشكل آمن. "
                "اكتب الاسم الإنجليزي أو الاسم العربي مع كلمة مميزة أخرى."
            )
        await message.channel.send(
            f"🔎 لا توجد نتائج مؤكدة لـ `{query}`.\n{extra}\n"
            "لن أعرض نتائج من لعبة مختلفة حتى لا تحصل على نتيجة مضللة.\n"
            "يمكنك تجربة المواقع التالية يدويًا (لا يتم فحص محتواها من قبل البوت):",
            view=_manual_sources_view(target_name),
        )
        return

    embed = _build_result_embed(
        results[0],
        query,
        0,
        len(results),
        target_name,
    )
    view = ScriptResultView(
        results,
        query,
        message.author.id,
        target_name,
    )
    await message.channel.send(embed=embed, view=view)


# ---------------------------------------------------------------------------
# Bot events and slash commands
# ---------------------------------------------------------------------------

class RobloxSearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------------------------------------------------
    # on_message
    # -----------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return

        data = get_script_search_config(message.guild)
        channel = get_configured_channel(
            message.guild,
            data.get("channel_id"),
        )

        if (
            not data.get("enabled")
            or not channel
            or message.channel.id != channel.id
        ):
            await self.bot.process_commands(message)
            return

        query = clean_script_query(message.content)

        if query:
            try:
                async with message.channel.typing():
                    await send_script_result(message, query)
            except Exception as error:
                print("❌ [auto-search] حدث خطأ أثناء البحث")
                print(f"نوع الخطأ: {type(error).__name__}")
                print(f"الخطأ: {error}")
                traceback.print_exc()
                try:
                    await message.channel.send(
                        "❌ حدث خطأ مؤقت أثناء البحث. راجع Logs لمعرفة السبب."
                    )
                except discord.DiscordException:
                    pass

        await self.bot.process_commands(message)

    # -----------------------------------------------------------------------
    # /scriptsearch
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="scriptsearch",
        description="تفعيل وإعداد روم بحث Roblox",
    )
    @app_commands.describe(
        channel="الروم الذي تتم فيه عمليات البحث",
        enabled="تشغيل أو إيقاف النظام",
        max_results="عدد النتائج من 1 إلى 20",
        strict="رفض أي نتيجة لا ترتبط باللعبة",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def scriptsearch_command(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
        enabled: bool = True,
        max_results: int = 5,
        strict: bool = True,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "❌ تحتاج صلاحية Manage Server.",
                ephemeral=True,
            )
            return

        if not 1 <= max_results <= 20:
            await interaction.response.send_message(
                "❌ عدد النتائج يجب أن يكون بين 1 و20.",
                ephemeral=True,
            )
            return

        current = get_script_search_config(interaction.guild)
        channel_id = channel.id if channel else current.get("channel_id")

        if enabled and not channel_id:
            await interaction.response.send_message(
                "❌ حدد الروم أول مرة عند تفعيل النظام.",
                ephemeral=True,
            )
            return

        GUILD_CONFIG[str(interaction.guild.id)] = {
            "enabled": bool(enabled),
            "channel_id": channel_id,
            "max_results": int(max_results),
            "strict": bool(strict),
        }
        save_config()

        target_channel = get_configured_channel(interaction.guild, channel_id)
        sources = "ScriptBlox"
        if RSCRIPTS_API_KEY:
            sources += " + Rscripts"
        state = "مفعّل" if enabled else "متوقف"

        await interaction.response.send_message(
            f"🔎 **إعداد بحث Roblox**\n"
            f"الحالة: **{state}**\n"
            f"الروم: {target_channel.mention if target_channel else 'غير محدد'}\n"
            f"النتائج: **{max_results}**\n"
            f"المطابقة الصارمة: **{'ON' if strict else 'OFF'}**\n"
            f"المصادر البرمجية: **{sources}**\n"
            f"اكتشاف Roblox التلقائي: **{'ON' if ENABLE_ROBLOX_DISCOVERY else 'OFF'}**",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # /script
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="script",
        description="بحث مباشر عن لعبة Roblox",
    )
    @app_commands.describe(
        query="اسم اللعبة بالعربي أو الإنجليزي أو الاختصار"
    )
    async def script_command(
        self,
        interaction: discord.Interaction,
        query: str,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        config = get_script_search_config(interaction.guild)

results, target_name, _confidence = await search_all_sources(
    query,
    max_results=config.get("max_results", 5),
    strict=config.get("strict", False),
)

        if not results:
            await interaction.followup.send(
                f"🔎 لا توجد نتائج مؤكدة للعبة: **{target_name or query}**.\n"
                "يمكنك تجربة المواقع التالية يدويًا:",
                view=_manual_sources_view(target_name),
            )
            return

        view = ScriptResultView(results, query, interaction.user.id, target_name)
        await interaction.followup.send(
            embed=_build_result_embed(results[0], query, 0, len(results), target_name),
            view=view,
        )

    # -----------------------------------------------------------------------
    # /scriptsearch-status
    # -----------------------------------------------------------------------

    @app_commands.command(
        name="scriptsearch-status",
        description="عرض حالة نظام بحث Roblox",
    )
    async def scriptsearch_status(self, interaction: discord.Interaction) -> None:
        data = get_script_search_config(interaction.guild)
        channel = get_configured_channel(interaction.guild, data.get("channel_id"))

        await interaction.response.send_message(
            f"🔎 الحالة: **{'مفعّل' if data.get('enabled') else 'متوقف'}**\n"
            f"الروم: {channel.mention if channel else 'غير محدد'}\n"
            f"المطابقة الصارمة: **{'ON' if data.get('strict') else 'OFF'}**\n"
            f"النتائج: **{data.get('max_results', 5)}**",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # معالج أخطاء موحّد لكل أوامر Slash في هذا الـ Cog
    # -----------------------------------------------------------------------

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        print(f"[app_command_error] {type(error).__name__}: {error}")
        traceback.print_exc()
        message = "❌ حدث خطأ غير متوقع أثناء تنفيذ الأمر."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.DiscordException:
            pass


# ---------------------------------------------------------------------------
# Extension Entry Point
# ---------------------------------------------------------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(RobloxSearchCog(bot))
    print("✅ تم تحميل bot4.py كـ Extension")
