# ============================================================
# Team Fime — bot4.py
# Smart Script Search System
# Fime Scripts + Manually Added External Sources
#
# طريقة الاستخدام:
# الإدارة:
# /setscriptroom #الروم
#
# الأعضاء:
# يكتبون اسم اللعبة مباشرة داخل روم البحث.
# مثال:
# doors
# دورز
# mm2
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

DATABASE = "script_search.db"

MAX_RESULTS = 20

REQUEST_TIMEOUT = 10

# حذف رسالة العضو بعد البحث؟
# True = يحذفها
# False = يخليها موجودة
DELETE_SEARCH_MESSAGE = True

# مدة الانتظار قبل بدء البحث بعد رسالة العضو
# 0 = مباشرة
SEARCH_DELAY = 0.0


# ============================================================
# EXTERNAL SOURCES
# ============================================================
#
# أضف هنا فقط المصادر التي تملكها أو لديك إذن باستخدامها.
#
# مثال:
#
# EXTERNAL_SOURCES = [
#     {
#         "name": "My Source",
#         "url": "https://cheater.fun/",
#         "games": [
#             "doors",
#             "دورز",
#             "باب"
#         ]
#     }
# ]
#
# ============================================================

EXTERNAL_SOURCES = []


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
        "بلوكس فروت",
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


def normalize_text(text: str) -> str:

    if not text:
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


def compact_text(text: str) -> str:

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


def get_search_channel(guild_id: int):

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
# GAME DETECTION
# ============================================================

def similarity(
    a: str,
    b: str
) -> float:

    if not a or not b:
        return 0.0

    return SequenceMatcher(
        None,
        normalize_text(a),
        normalize_text(b)
    ).ratio()


def detect_game(query: str):

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

            # تطابق كامل
            if normalized_query == alias_normalized:
                score = 1.0

            # بدون مسافات
            elif compact_query == alias_compact:
                score = 0.98

            # العبارة موجودة داخل البحث
            elif alias_normalized in normalized_query:
                score = 0.93

            # البحث موجود داخل alias
            elif normalized_query in alias_normalized:
                score = 0.90

            # تطابق تقريبي
            else:
                score = similarity(
                    normalized_query,
                    alias_normalized
                )

            if score > best_score:

                best_score = score
                best_game = game

    if best_score < 0.60:

        return None, 0.0

    return best_game, best_score


# ============================================================
# EXTERNAL SOURCE MATCHING
# ============================================================

def source_matches_game(
    source,
    game: str,
    query: str
):

    if not game:
        return False

    game_normalized = normalize_text(
        game
    )

    query_normalized = normalize_text(
        query
    )

    for source_game in source.get(
        "games",
        []
    ):

        normalized = normalize_text(
            source_game
        )

        if normalized == game_normalized:
            return True

        if compact_text(normalized) == compact_text(
            game_normalized
        ):
            return True

        if similarity(
            normalized,
            game_normalized
        ) >= 0.70:
            return True

        if normalized in query_normalized:
            return True

    return False


# ============================================================
# HTTP
# ============================================================

def fetch_url(url: str):

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Team-Fime-Script-Search/1.0"
            ),
            "Accept": "application/json"
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
            f"[bot4] Failed to fetch URL: "
            f"{url} | {error}"
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

    except json.JSONDecodeError:

        print(
            "[bot4] Fime API returned invalid JSON."
        )

        return []

    if isinstance(data, dict):

        if isinstance(
            data.get("scripts"),
            list
        ):
            return data["scripts"]

        if isinstance(
            data.get("data"),
            list
        ):
            return data["data"]

        return []

    if isinstance(data, list):

        return data

    return []


# ============================================================
# SCRIPT TEXT
# ============================================================

def get_script_text(script):

    fields = [
        script.get("title", ""),
        script.get("description", ""),
        script.get("category", ""),
        script.get("game", ""),
        script.get("author", ""),
    ]

    return " ".join(
        str(value)
        for value in fields
        if value
    )


# ============================================================
# SCRIPT SCORING
# ============================================================

def score_script(
    script,
    query,
    detected_game
):

    title = str(
        script.get(
            "title",
            ""
        )
    )

    description = str(
        script.get(
            "description",
            ""
        )
    )

    game = str(
        script.get(
            "game",
            ""
        )
    )

    category = str(
        script.get(
            "category",
            ""
        )
    )

    normalized_query = normalize_text(
        query
    )

    normalized_title = normalize_text(
        title
    )

    normalized_game = normalize_text(
        game
    )

    score = 0.0

    # ========================================================
    # GAME MATCH
    # ========================================================

    if detected_game:

        normalized_detected = normalize_text(
            detected_game
        )

        if normalized_game == normalized_detected:

            score += 100

        elif compact_text(game) == compact_text(
            detected_game
        ):

            score += 95

        elif similarity(
            game,
            detected_game
        ) >= 0.80:

            score += 75

        elif normalized_detected in normalize_text(
            get_script_text(script)
        ):

            score += 50

    # ========================================================
    # TITLE
    # ========================================================

    if normalized_query == normalized_title:

        score += 80

    elif normalized_query in normalized_title:

        score += 60

    elif normalized_title in normalized_query:

        score += 45

    else:

        score += (
            similarity(
                normalized_query,
                normalized_title
            ) * 40
        )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    if normalized_query in normalize_text(
        description
    ):

        score += 10

    # ========================================================
    # CATEGORY
    # ========================================================

    if normalized_query in normalize_text(
        category
    ):

        score += 5

    return score


# ============================================================
# SEARCH FIME
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

        score = score_script(
            script,
            query,
            detected_game
        )

        # ----------------------------------------------------
        # حماية من نتائج لعبة ثانية
        # ----------------------------------------------------

        if detected_game:

            script_game = normalize_text(
                str(
                    script.get(
                        "game",
                        ""
                    )
                )
            )

            detected_normalized = normalize_text(
                detected_game
            )

            game_match = (

                script_game == detected_normalized

                or

                compact_text(
                    script_game
                ) == compact_text(
                    detected_normalized
                )

                or

                similarity(
                    script_game,
                    detected_normalized
                ) >= 0.72
            )

            if not game_match:

                all_text = normalize_text(
                    get_script_text(
                        script
                    )
                )

                # إذا اسم اللعبة غير موجود
                # في بيانات السكربت، نتعامل بحذر.
                if detected_normalized not in all_text:

                    continue

        if score < 25:

            continue

        clean_script = dict(
            script
        )

        clean_script[
            "_search_score"
        ] = score

        results.append(
            clean_script
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
            item.get(
                "id",
                0
            )
        ),
        reverse=True
    )

    return results[:MAX_RESULTS]


# ============================================================
# EMBED
# ============================================================

def make_result_embed(
    query,
    detected_game,
    detection_score,
    results,
    external_results
):

    total = (
        len(results)
        +
        len(external_results)
    )

    embed = discord.Embed(
        title="🔎 نتائج البحث — Team Fime",
        description=(
            f"**البحث:** `{query}`\n"
            f"**اللعبة:** "
            f"`{detected_game or 'غير محددة'}`\n"
            f"**النتائج:** `{total}`"
        ),
        color=discord.Color.blurple()
    )

    if detected_game:

        embed.add_field(
            name="🧠 التعرف على اللعبة",
            value=(
                f"`{detected_game}` "
                f"• دقة التعرف: "
                f"`{detection_score * 100:.0f}%`"
            ),
            inline=False
        )

    counter = 1

    # ========================================================
    # FIME
    # ========================================================

    for script in results:

        if counter > MAX_RESULTS:
            break

        title = str(
            script.get(
                "title",
                "بدون عنوان"
            )
            or "بدون عنوان"
        )

        game = str(
            script.get(
                "game",
                "غير محددة"
            )
            or "غير محددة"
        )

        script_id = script.get(
            "id"
        )

        if script_id is not None:

            url = (
                "https://fime-scripts.onrender.com/"
                f"script?id={script_id}"
            )

            value = (
                f"🎮 **اللعبة:** {game}\n"
                f"🔗 [فتح السكربت]({url})"
            )

        else:

            value = (
                f"🎮 **اللعبة:** {game}\n"
                "⚠️ لا يوجد رابط متاح"
            )

        embed.add_field(
            name=f"{counter}. {title}",
            value=value,
            inline=False
        )

        counter += 1

    # ========================================================
    # EXTERNAL
    # ========================================================

    for source in external_results:

        if counter > MAX_RESULTS:
            break

        name = source.get(
            "name",
            "مصدر خارجي"
        )

        url = source.get(
            "url",
            ""
        )

        if not url:
            continue

        embed.add_field(
            name=f"{counter}. 🌐 {name}",
            value=f"[فتح المصدر]({url})",
            inline=False
        )

        counter += 1

    embed.set_footer(
        text=(
            "Team Fime • Smart Script Search"
        )
    )

    return embed


# ============================================================
# BUTTONS
# ============================================================

class SearchView(
    discord.ui.View
):

    def __init__(
        self,
        fime_results,
        external_results
    ):

        super().__init__(
            timeout=180
        )

        # ----------------------------------------------------
        # Fime
        # ----------------------------------------------------

        if fime_results:

            self.add_item(
                discord.ui.Button(
                    label="🌐 Fime Scripts",
                    url=(
                        "https://fime-scripts.onrender.com/"
                        "scripts"
                    )
                )
            )

        # ----------------------------------------------------
        # External
        # ----------------------------------------------------

        added = 0

        for source in external_results:

            if added >= 4:
                break

            url = source.get(
                "url"
            )

            if not url:
                continue

            name = source.get(
                "name",
                "مصدر"
            )

            if len(name) > 70:

                name = (
                    name[:67]
                    +
                    "..."
                )

            self.add_item(
                discord.ui.Button(
                    label=f"🔗 {name}",
                    url=url
                )
            )

            added += 1


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
            "Script Search loaded."
        )

    # ========================================================
    # SET SEARCH ROOM
    # ========================================================

    @app_commands.command(
        name="setscriptroom",
        description=(
            "تحديد روم البحث عن السكربتات"
        )
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
                "الآن الأعضاء يكتبون اسم اللعبة "
                "مباشرة بدون أي أمر."
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
    # AUTOMATIC MESSAGE SEARCH
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        # ----------------------------------------------------
        # تجاهل البوتات
        # ----------------------------------------------------

        if message.author.bot:
            return

        # ----------------------------------------------------
        # لازم يكون داخل سيرفر
        # ----------------------------------------------------

        if not message.guild:
            return

        # ----------------------------------------------------
        # جلب روم البحث
        # ----------------------------------------------------

        configured_channel = get_search_channel(
            message.guild.id
        )

        if not configured_channel:
            return

        # ----------------------------------------------------
        # تجاهل أي روم ثاني
        # ----------------------------------------------------

        if message.channel.id != configured_channel:
            return

        # ----------------------------------------------------
        # قراءة البحث
        # ----------------------------------------------------

        query = message.content.strip()

        if not query:
            return

        # ----------------------------------------------------
        # منع الرسائل الطويلة جدًا
        # ----------------------------------------------------

        if len(query) > 100:

            await message.reply(
                "❌ اسم اللعبة طويل جدًا.",
                mention_author=False,
                delete_after=5
            )

            return

        # ----------------------------------------------------
        # انتظار اختياري
        # ----------------------------------------------------

        if SEARCH_DELAY > 0:

            await asyncio.sleep(
                SEARCH_DELAY
            )

        # ----------------------------------------------------
        # حذف رسالة العضو
        # ----------------------------------------------------

        if DELETE_SEARCH_MESSAGE:

            try:

                await message.delete()

            except discord.HTTPException:

                pass

        # ----------------------------------------------------
        # رسالة البحث
        # ----------------------------------------------------

        searching_message = await message.channel.send(
            (
                f"🔎 **جاري البحث عن:** `{query}`"
            )
        )

        try:

            # ------------------------------------------------
            # تحديد اللعبة
            # ------------------------------------------------

            detected_game, detection_score = detect_game(
                query
            )

            print(
                f"[bot4] Search: {query} | "
                f"Game: {detected_game} | "
                f"Score: {detection_score:.2f} | "
                f"Guild: {message.guild.id} | "
                f"Channel: {message.channel.id}"
            )

            # ------------------------------------------------
            # Fime API
            # ------------------------------------------------

            fime_scripts = await fetch_fime_scripts()

            fime_results = search_fime_scripts(
                fime_scripts,
                query,
                detected_game
            )

            # ------------------------------------------------
            # External sources
            # ------------------------------------------------

            external_results = []

            for source in EXTERNAL_SOURCES:

                if not isinstance(
                    source,
                    dict
                ):
                    continue

                if source_matches_game(
                    source,
                    detected_game,
                    query
                ):

                    external_results.append(
                        source
                    )

            # ------------------------------------------------
            # لا توجد نتائج
            # ------------------------------------------------

            if (
                not fime_results
                and
                not external_results
            ):

                embed = discord.Embed(
                    title="🔎 لم نجد نتائج",
                    description=(
                        f"لم أجد نتائج مناسبة لـ "
                        f"**{query}**.\n\n"
                        "جرّب اسم اللعبة بالعربي "
                        "أو الإنجليزي."
                    ),
                    color=discord.Color.orange()
                )

                if detected_game:

                    embed.add_field(
                        name="🧠 اللعبة التي تم التعرف عليها",
                        value=(
                            f"`{detected_game}`\n"
                            f"دقة التعرف: "
                            f"`{detection_score * 100:.0f}%`"
                        ),
                        inline=False
                    )

                embed.set_footer(
                    text="Team Fime • Smart Search"
                )

                await searching_message.edit(
                    content=None,
                    embed=embed,
                    view=None
                )

                return

            # ------------------------------------------------
            # النتيجة
            # ------------------------------------------------

            embed = make_result_embed(
                query,
                detected_game,
                detection_score,
                fime_results,
                external_results
            )

            view = SearchView(
                fime_results,
                external_results
            )

            await searching_message.edit(
                content=None,
                embed=embed,
                view=view
            )

        except Exception as error:

            print(
                f"[bot4] Search error: {error}"
            )

            error_embed = discord.Embed(
                title="❌ حدث خطأ أثناء البحث",
                description=(
                    "حصل خطأ غير متوقع أثناء "
                    "البحث.\n"
                    "جرّب مرة ثانية بعد قليل."
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