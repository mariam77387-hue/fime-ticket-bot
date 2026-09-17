# ============================================================
# Team Fime — bot4.py
# Smart Script Search System
# Fime Scripts API
#
# الأوامر:
#
# الإدارة:
# /setscriptroom #الروم
#
# الجميع:
# /scriptroom
# /searchscript اسم اللعبة
#
# البحث التلقائي:
# يكتب العضو اسم اللعبة مباشرة داخل روم البحث.
#
# أمثلة:
# doors
# دورز
# الباب
# mm2
# ام ام تو
# بروكهافن
# ============================================================

import os
import re
import json
import sqlite3
import asyncio
import unicodedata
from difflib import SequenceMatcher
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIG
# ============================================================

FIME_API_URL = "https://fime-scripts.onrender.com/api/scripts"
FIME_WEBSITE_URL = "https://fime-scripts.onrender.com"

DATABASE = "script_search.db"

MAX_RESULTS = 20
REQUEST_TIMEOUT = 15

# حذف رسالة البحث التلقائي؟
DELETE_SEARCH_MESSAGE = True

# تأخير قبل البحث
SEARCH_DELAY = 0.0


# ============================================================
# GAME ALIASES
# ============================================================

GAME_ALIASES = {

    "steal an egg": [
        "steal an egg",
        "steal egg",
        "سرقه بيضه",
        "سرقة بيضة",
        "سرقه بيض",
        "سرقة بيض",
        "سرقه البيض",
        "سرقة البيض",
        "بيضه",
        "البيض",
    ],

    "murder mystery 2": [
        "murder mystery 2",
        "murder mystery",
        "mm2",
        "m m 2",
        "ام ام تو",
        "إم إم تو",
        "اي ام ام 2",
        "اي ام ام تو",
        "ام ام ٢",
        "مردر مستري",
        "مورد مستري",
    ],

    "keyboard escape": [
        "keyboard escape",
        "1 speed keyboard escape",
        "keyboard",
        "كيبورد",
        "ماب الكيبورد",
        "ماب كيبورد",
        "الهروب من الكيبورد",
    ],

    "brookhaven": [
        "brookhaven",
        "brook haven",
        "بروك هافن",
        "بروكهافن",
        "ماب البيوت",
        "ماب بيوت",
        "البيوت",
        "بيوت",
    ],

    "blox fruits": [
        "blox fruits",
        "bloxfruit",
        "بلوكس فروت",
        "بلوكس فروتس",
        "بلوكس",
    ],

    "dress to impress": [
        "dress to impress",
        "dti",
        "دريس تو امبريس",
        "دريس تو إمبريس",
        "دريس",
    ],

    "dead rails": [
        "dead rails",
        "deadrail",
        "ديد ريلز",
        "ديد ريل",
        "ديدريلز",
    ],

    "tower of hell": [
        "tower of hell",
        "tower hell",
        "towerofhell",
        "برج الجحيم",
        "ماب الجحيم",
        "الجحيم",
    ],

    "collect the alphabet": [
        "collect the alphabet",
        "collect alphabet",
        "alphabet",
        "اجمع الابجديه",
        "اجمع الأبجدية",
        "اجمع الحروف",
        "جمع الحروف",
        "الحروف",
    ],

    "driving simulator": [
        "driving simulator",
        "car simulator",
        "driving",
        "محاكي القيادة",
        "محاكي قياده",
        "محاكي السيارات",
        "محاكي سيارة",
        "السيارات",
    ],

    "infinite jump": [
        "infinite jump",
        "high jump",
        "hing jump",
        "jump",
        "قفز",
        "النط",
        "قوه النط",
        "قوة النط",
        "القفزه",
        "القفزة",
        "قفزه",
        "قفزة",
    ],

    "stands awakening": [
        "stands awakening",
        "stands",
        "ستاندز",
        "ستاندز اويكيننق",
        "ستاندز اويكننق",
    ],

    "aim bot": [
        "aim bot",
        "aimbot",
        "aim",
        "ايم بوت",
        "ايمبوت",
        "ايم",
    ],

    "doors": [
        "doors",
        "door",
        "دورز",
        "دورس",
        "باب",
        "الباب",
        "رعب",
        "ماب الرعب",
        "ماب رعب",
    ],
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

ARABIC_DIACRITICS = re.compile(
    r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]"
)


def normalize_text(text: str):

    if text is None:
        return ""

    text = str(text)

    text = unicodedata.normalize(
        "NFKC",
        text
    )

    text = ARABIC_DIACRITICS.sub(
        "",
        text
    )

    text = text.replace(
        "ـ",
        ""
    )

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new
        )

    text = text.lower()

    text = re.sub(
        r"[^\w\s\u0600-\u06FF]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def compact_text(text: str):

    return normalize_text(
        text
    ).replace(
        " ",
        ""
    )


# ============================================================
# DATABASE
# ============================================================

def init_database():

    conn = sqlite3.connect(
        DATABASE
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS script_search_settings (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()


def get_search_channel(
    guild_id: int
):

    conn = sqlite3.connect(
        DATABASE
    )

    row = conn.execute(
        """
        SELECT channel_id
        FROM script_search_settings
        WHERE guild_id = ?
        """,
        (guild_id,)
    ).fetchone()

    conn.close()

    return row[0] if row else None


def set_search_channel(
    guild_id: int,
    channel_id: int
):

    conn = sqlite3.connect(
        DATABASE
    )

    conn.execute(
        """
        INSERT INTO script_search_settings (
            guild_id,
            channel_id
        )
        VALUES (?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            channel_id = excluded.channel_id
        """,
        (
            guild_id,
            channel_id
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# SIMILARITY
# ============================================================

def similarity(
    a: str,
    b: str
):

    a = normalize_text(a)
    b = normalize_text(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


# ============================================================
# GAME DETECTION
# ============================================================

def detect_game(
    query: str
):

    normalized_query = normalize_text(
        query
    )

    compact_query = compact_text(
        query
    )

    best_game = None
    best_score = 0.0

    for game, aliases in GAME_ALIASES.items():

        for alias in aliases:

            alias_normalized = normalize_text(
                alias
            )

            alias_compact = compact_text(
                alias
            )

            score = 0.0

            if normalized_query == alias_normalized:

                score = 1.0

            elif compact_query == alias_compact:

                score = 0.98

            elif (
                alias_normalized
                and alias_normalized in normalized_query
            ):

                score = 0.94

            elif (
                normalized_query
                and normalized_query in alias_normalized
            ):

                score = 0.90

            else:

                score = similarity(
                    normalized_query,
                    alias_normalized
                )

            if score > best_score:

                best_score = score
                best_game = game

    if best_score < 0.58:

        return None, 0.0

    return best_game, best_score


# ============================================================
# HTTP
# ============================================================

def fetch_url(
    url: str
):

    request = Request(
        url,
        headers={
            "User-Agent": "Team-Fime-Script-Search/3.0",
            "Accept": "application/json",
        }
    )

    try:

        with urlopen(
            request,
            timeout=REQUEST_TIMEOUT
        ) as response:

            raw = response.read()

            return raw.decode(
                "utf-8",
                errors="replace"
            )

    except Exception as error:

        print(
            f"[bot4] API ERROR: {url} | {error}"
        )

        return None


# ============================================================
# FIME API
# ============================================================

async def fetch_fime_scripts():

    raw = await asyncio.to_thread(
        fetch_url,
        FIME_API_URL
    )

    if not raw:
        return []

    try:

        data = json.loads(
            raw
        )

    except json.JSONDecodeError as error:

        print(
            f"[bot4] Invalid JSON from Fime API: {error}"
        )

        return []

    if isinstance(
        data,
        list
    ):

        scripts = data

    elif isinstance(
        data,
        dict
    ):

        scripts = None

        for key in (
            "scripts",
            "data",
            "results",
            "items"
        ):

            value = data.get(
                key
            )

            if isinstance(
                value,
                list
            ):

                scripts = value
                break

        if scripts is None:

            print(
                "[bot4] Fime API returned an object "
                "but no script list was found."
            )

            return []

    else:

        return []

    print(
        f"[bot4] Fime API scripts loaded: "
        f"{len(scripts)}"
    )

    return [
        item
        for item in scripts
        if isinstance(
            item,
            dict
        )
    ]


# ============================================================
# SCRIPT HELPERS
# ============================================================

def get_value(
    script,
    *keys
):

    for key in keys:

        value = script.get(
            key
        )

        if value is not None:

            if isinstance(
                value,
                str
            ):

                if value.strip():

                    return value.strip()

            else:

                return value

    return ""


def get_script_title(
    script
):

    return str(
        get_value(
            script,
            "title",
            "name",
            "script_name"
        )
        or "بدون عنوان"
    )


def get_script_game(
    script
):

    return str(
        get_value(
            script,
            "game",
            "game_name",
            "gamename",
            "map"
        )
        or ""
    )


def get_script_description(
    script
):

    return str(
        get_value(
            script,
            "description",
            "desc",
            "summary"
        )
        or ""
    )


def get_script_category(
    script
):

    return str(
        get_value(
            script,
            "category",
            "type"
        )
        or ""
    )


def get_script_author(
    script
):

    return str(
        get_value(
            script,
            "author",
            "username",
            "owner"
        )
        or "Fime"
    )


def get_script_id(
    script
):

    return get_value(
        script,
        "id",
        "_id",
        "script_id"
    )


def get_script_image(
    script
):

    return str(
        get_value(
            script,
            "image",
            "image_url",
            "thumbnail",
            "thumbnail_url"
        )
        or ""
    )


def get_script_url(
    script
):

    script_id = get_script_id(
        script
    )

    if script_id:

        return (
            f"{FIME_WEBSITE_URL}/script"
            f"?id={script_id}"
        )

    direct_url = get_value(
        script,
        "url",
        "link",
        "script_url"
    )

    if direct_url:

        return str(
            direct_url
        )

    return ""


def get_script_text(
    script
):

    values = [
        get_script_title(script),
        get_script_game(script),
        get_script_description(script),
        get_script_category(script),
        get_script_author(script),
    ]

    return " ".join(
        str(value)
        for value in values
        if value
    )


# ============================================================
# CHECK GAME MATCH
# ============================================================

def script_matches_game(
    script,
    detected_game
):

    if not detected_game:

        return True

    script_game = get_script_game(
        script
    )

    if not script_game:

        all_text = normalize_text(
            get_script_text(
                script
            )
        )

        for alias in GAME_ALIASES.get(
            detected_game,
            []
        ):

            alias_normalized = normalize_text(
                alias
            )

            if (
                alias_normalized
                and alias_normalized in all_text
            ):

                return True

        return False

    script_game_normalized = normalize_text(
        script_game
    )

    detected_normalized = normalize_text(
        detected_game
    )

    if (
        script_game_normalized
        == detected_normalized
    ):

        return True

    if (
        compact_text(script_game)
        == compact_text(detected_game)
    ):

        return True

    aliases = GAME_ALIASES.get(
        detected_game,
        []
    )

    for alias in aliases:

        alias_normalized = normalize_text(
            alias
        )

        if (
            script_game_normalized
            == alias_normalized
        ):

            return True

        if (
            compact_text(script_game)
            == compact_text(alias)
        ):

            return True

        if similarity(
            script_game,
            alias
        ) >= 0.78:

            return True

    return similarity(
        script_game,
        detected_game
    ) >= 0.78


# ============================================================
# SCORE SCRIPT
# ============================================================

def score_script(
    script,
    query,
    detected_game
):

    title = get_script_title(
        script
    )

    game = get_script_game(
        script
    )

    description = get_script_description(
        script
    )

    category = get_script_category(
        script
    )

    normalized_query = normalize_text(
        query
    )

    score = 0.0

    # ========================================================
    # GAME
    # ========================================================

    if detected_game:

        if script_matches_game(
            script,
            detected_game
        ):

            score += 100

        else:

            score -= 100

    # ========================================================
    # TITLE
    # ========================================================

    normalized_title = normalize_text(
        title
    )

    if normalized_query == normalized_title:

        score += 80

    elif (
        normalized_query
        and normalized_query in normalized_title
    ):

        score += 65

    elif (
        normalized_title
        and normalized_title in normalized_query
    ):

        score += 45

    else:

        score += (
            similarity(
                query,
                title
            )
            * 35
        )

    # ========================================================
    # GAME FIELD
    # ========================================================

    if game:

        normalized_game = normalize_text(
            game
        )

        if normalized_query == normalized_game:

            score += 60

        elif (
            normalized_query
            and normalized_query in normalized_game
        ):

            score += 40

        if detected_game:

            score += (
                similarity(
                    game,
                    detected_game
                )
                * 30
            )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    if (
        normalized_query
        and normalized_query in normalize_text(
            description
        )
    ):

        score += 15

    # ========================================================
    # CATEGORY
    # ========================================================

    if (
        normalized_query
        and normalized_query in normalize_text(
            category
        )
    ):

        score += 8

    # ========================================================
    # FEATURED
    # ========================================================

    if script.get(
        "featured",
        False
    ):

        score += 5

    return score


# ============================================================
# SEARCH
# ============================================================

def search_fime_scripts(
    scripts,
    query,
    detected_game
):

    results = []

    for script in scripts:

        if not isinstance(
            script,
            dict
        ):

            continue

        if detected_game:

            if not script_matches_game(
                script,
                detected_game
            ):

                continue

        score = score_script(
            script,
            query,
            detected_game
        )

        if score < 20:

            continue

        result = dict(
            script
        )

        result["_search_score"] = score

        results.append(
            result
        )

    results.sort(
        key=lambda item: (
            item.get(
                "_search_score",
                0
            ),
            bool(
                item.get(
                    "featured",
                    False
                )
            ),
            get_script_id(item) or 0
        ),
        reverse=True
    )

    return results[
        :MAX_RESULTS
    ]


# ============================================================
# RESULT EMBED
# ============================================================

def make_result_embed(
    query,
    detected_game,
    detection_score,
    results
):

    embed = discord.Embed(
        title="🔎 نتائج البحث — Team Fime",
        description=(
            f"**البحث:** `{query}`\n"
            f"**اللعبة:** "
            f"`{detected_game or 'غير محددة'}`\n"
            f"**عدد النتائج:** `{len(results)}`"
        ),
        color=discord.Color.blurple()
    )

    if detected_game:

        embed.add_field(
            name="🧠 التعرف على اللعبة",
            value=(
                f"`{detected_game}`\n"
                f"دقة التعرف: "
                f"`{detection_score * 100:.0f}%`"
            ),
            inline=False
        )

    for index, script in enumerate(
        results[
            :MAX_RESULTS
        ],
        start=1
    ):

        title = get_script_title(
            script
        )

        game = get_script_game(
            script
        ) or "غير محددة"

        url = get_script_url(
            script
        )

        if url:

            value = (
                f"🎮 **اللعبة:** {game}\n"
                f"🔗 [فتح السكربت]({url})"
            )

        else:

            value = (
                f"🎮 **اللعبة:** {game}\n"
                "⚠️ لا يوجد رابط للسكربت"
            )

        score = script.get(
            "_search_score",
            0
        )

        value += (
            f"\n📊 التطابق: `{score:.0f}`"
        )

        embed.add_field(
            name=f"{index}. {title}",
            value=value,
            inline=False
        )

    embed.set_footer(
        text="Team Fime • Smart Script Search"
    )

    return embed


# ============================================================
# BUTTONS
# ============================================================

class SearchView(
    discord.ui.View
):

    def __init__(
        self
    ):

        super().__init__(
            timeout=180
        )

        self.add_item(
            discord.ui.Button(
                label="🌐 فتح Fime Scripts",
                url=(
                    f"{FIME_WEBSITE_URL}/scripts"
                )
            )
        )


# ============================================================
# SEARCH FUNCTION
# ============================================================

async def perform_search(
    query: str
):

    detected_game, detection_score = detect_game(
        query
    )

    print(
        f"[bot4] Search='{query}' | "
        f"Game='{detected_game}' | "
        f"Detection={detection_score:.2f}"
    )

    fime_scripts = await fetch_fime_scripts()

    results = search_fime_scripts(
        fime_scripts,
        query,
        detected_game
    )

    print(
        f"[bot4] Fime total={len(fime_scripts)} | "
        f"Results={len(results)}"
    )

    return (
        detected_game,
        detection_score,
        fime_scripts,
        results
    )


# ============================================================
# NO RESULTS EMBED
# ============================================================

def make_no_results_embed(
    query,
    detected_game,
    detection_score
):

    if detected_game:

        description = (
            f"لم أجد سكربتات متاحة حاليًا "
            f"للعبة **{detected_game}**.\n\n"
            "جرّب اسمًا آخر أو جرّب البحث "
            "بالإنجليزي."
        )

    else:

        description = (
            f"لم أتمكن من العثور على نتائج "
            f"مطابقة لـ **{query}**.\n\n"
            "جرّب اسم اللعبة بالعربي "
            "أو الإنجليزي."
        )

    embed = discord.Embed(
        title="🔎 لم نجد نتائج",
        description=description,
        color=discord.Color.orange()
    )

    if detected_game:

        embed.add_field(
            name="🧠 اللعبة المتعرف عليها",
            value=(
                f"`{detected_game}`\n"
                f"دقة التعرف: "
                f"`{detection_score * 100:.0f}%`"
            ),
            inline=False
        )

    embed.add_field(
        name="🌐 Fime Scripts",
        value=(
            f"[فتح موقع Fime]("
            f"{FIME_WEBSITE_URL}/scripts)"
        ),
        inline=False
    )

    embed.set_footer(
        text="Team Fime • Smart Search"
    )

    return embed


# ============================================================
# COG
# ============================================================

class ScriptSearchCog(
    commands.Cog
):

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        init_database()

        print(
            "✅ Team Fime bot4.py — "
            "Smart Script Search loaded."
        )

    # ========================================================
    # SET SEARCH ROOM
    # ========================================================

    @app_commands.command(
        name="setscriptroom",
        description="تحديد روم البحث عن السكربتات"
    )
    @app_commands.default_permissions(
        manage_guild=True
    )
    async def setscriptroom(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        if not interaction.user.guild_permissions.manage_guild:

            await interaction.response.send_message(
                "❌ تحتاج صلاحية Manage Server.",
                ephemeral=True
            )

            return

        set_search_channel(
            interaction.guild.id,
            channel.id
        )

        await interaction.response.send_message(
            (
                "✅ تم تحديد روم البحث بنجاح.\n\n"
                f"🔎 روم البحث: {channel.mention}\n\n"
                "الآن اكتب اسم اللعبة مباشرة داخل الروم."
            ),
            ephemeral=True
        )

    # ========================================================
    # SHOW SEARCH ROOM
    # ========================================================

    @app_commands.command(
        name="scriptroom",
        description="عرض روم البحث الحالي"
    )
    async def scriptroom(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        channel_id = get_search_channel(
            interaction.guild.id
        )

        if not channel_id:

            await interaction.response.send_message(
                "⚠️ لم يتم تحديد روم البحث حتى الآن.",
                ephemeral=True
            )

            return

        channel = interaction.guild.get_channel(
            channel_id
        )

        if not channel:

            await interaction.response.send_message(
                "⚠️ الروم المحدد لم يعد موجودًا.",
                ephemeral=True
            )

            return

        await interaction.response.send_message(
            f"🔎 روم البحث الحالي: {channel.mention}",
            ephemeral=True
        )

    # ========================================================
    # MANUAL SEARCH COMMAND
    # ========================================================

    @app_commands.command(
        name="searchscript",
        description="البحث عن سكربتات لعبة معينة"
    )
    @app_commands.describe(
        game="اكتب اسم اللعبة"
    )
    async def searchscript(
        self,
        interaction: discord.Interaction,
        game: str
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        game = game.strip()

        if not game:

            await interaction.response.send_message(
                "❌ اكتب اسم اللعبة.",
                ephemeral=True
            )

            return

        if len(game) > 100:

            await interaction.response.send_message(
                "❌ اسم اللعبة طويل جدًا.",
                ephemeral=True
            )

            return

        await interaction.response.defer()

        try:

            (
                detected_game,
                detection_score,
                fime_scripts,
                results
            ) = await perform_search(
                game
            )

            if not results:

                embed = make_no_results_embed(
                    game,
                    detected_game,
                    detection_score
                )

                await interaction.followup.send(
                    embed=embed,
                    view=SearchView()
                )

                return

            embed = make_result_embed(
                game,
                detected_game,
                detection_score,
                results
            )

            await interaction.followup.send(
                embed=embed,
                view=SearchView()
            )

        except Exception as error:

            print(
                f"[bot4] MANUAL SEARCH ERROR: "
                f"{repr(error)}"
            )

            await interaction.followup.send(
                embed=discord.Embed(
                    title="❌ حدث خطأ أثناء البحث",
                    description=(
                        "حدث خطأ أثناء الاتصال "
                        "بنظام Fime Scripts.\n\n"
                        "حاول مرة أخرى بعد قليل."
                    ),
                    color=discord.Color.red()
                )
            )

    # ========================================================
    # AUTOMATIC SEARCH
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        if message.author.bot:
            return

        if not message.guild:
            return

        configured_channel = get_search_channel(
            message.guild.id
        )

        if not configured_channel:
            return

        if message.channel.id != configured_channel:
            return

        query = message.content.strip()

        if not query:
            return

        if len(query) > 100:

            await message.reply(
                "❌ اسم اللعبة طويل جدًا.",
                mention_author=False,
                delete_after=5
            )

            return

        if SEARCH_DELAY > 0:

            await asyncio.sleep(
                SEARCH_DELAY
            )

        if DELETE_SEARCH_MESSAGE:

            try:

                await message.delete()

            except discord.HTTPException:

                pass

        searching_message = await message.channel.send(
            f"🔎 **جاري البحث عن:** `{query}`"
        )

        try:

            (
                detected_game,
                detection_score,
                fime_scripts,
                results
            ) = await perform_search(
                query
            )

            if not results:

                embed = make_no_results_embed(
                    query,
                    detected_game,
                    detection_score
                )

                await searching_message.edit(
                    content=None,
                    embed=embed,
                    view=SearchView()
                )

                return

            embed = make_result_embed(
                query,
                detected_game,
                detection_score,
                results
            )

            await searching_message.edit(
                content=None,
                embed=embed,
                view=SearchView()
            )

        except Exception as error:

            print(
                f"[bot4] SEARCH ERROR: "
                f"{repr(error)}"
            )

            error_embed = discord.Embed(
                title="❌ حدث خطأ أثناء البحث",
                description=(
                    "حدث خطأ أثناء الاتصال "
                    "بنظام Fime Scripts.\n\n"
                    "حاول البحث مرة أخرى بعد قليل."
                ),
                color=discord.Color.red()
            )

            try:

                await searching_message.edit(
                    content=None,
                    embed=error_embed,
                    view=None
                )

            except discord.HTTPException:

                pass


# ============================================================
# SETUP
# ============================================================

async def setup(
    bot: commands.Bot
):

    await bot.add_cog(
        ScriptSearchCog(bot)
    )

    print(
        "✅ تم تشغيل Team Fime bot4.py بالكامل."
    )