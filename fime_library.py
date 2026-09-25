# Fime Library Search Engine — Fast Arabic/English Search v3.0
import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
from discord import ui
import json
import os
import asyncio
import difflib
import re
import time
import copy

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


# ============================================================
# SCRIPTS DATA — FAST LOCAL CACHE + SEARCH INDEX
# ============================================================

_SCRIPT_DATA_CACHE = []
_SCRIPT_DATA_MTIME_NS = None
_SCRIPT_SEARCH_INDEX = []
_SCRIPT_QUERY_CACHE = {}
_SCRIPT_QUERY_CACHE_TTL = 90
_SCRIPT_DATA_PATH = "scripts.json"


def _normalize_local_search_text(text):
    text = str(text or "").lower().strip()

    for char in "ًٌٍَُِّْـ":
        text = text.replace(char, "")

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
        text = text.replace(old, new)

    text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
    text = " ".join(text.split())

    words = []
    for word in text.split():
        if len(word) > 4 and word.startswith("ال"):
            words.append(word[2:])
        else:
            words.append(word)

    return " ".join(words)


def _compact_local_search_text(text):
    normalized = _normalize_local_search_text(text)
    normalized = re.sub(r"(.)\1{1,}", r"\1", normalized)
    return normalized.replace(" ", "")


def _script_search_fields(script):
    candidates = [
        script.get("map", ""),
        script.get("title", ""),
        script.get("name", ""),
        script.get("game", ""),
        script.get("category", ""),
    ]

    for field in ("aliases", "alt_names", "tags", "keywords"):
        value = script.get(field)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, (list, tuple, set)):
            candidates.extend(
                item for item in value if isinstance(item, str)
            )

    return [str(item) for item in candidates if item]


def _build_search_index(data):
    index = []
    for script in data:
        if not isinstance(script, dict):
            continue

        fields = _script_search_fields(script)
        normalized_fields = [
            _normalize_local_search_text(field)
            for field in fields
            if field
        ]
        normalized_fields = [item for item in normalized_fields if item]

        compact_fields = [
            _compact_local_search_text(item)
            for item in normalized_fields
        ]

        first_chars = set()
        tokens = set()
        for field in normalized_fields:
            for token in field.split():
                if token:
                    tokens.add(token)
                    first_chars.add(token[0])

        index.append({
            "script": script,
            "fields": normalized_fields,
            "compact": compact_fields,
            "tokens": tokens,
            "first_chars": first_chars,
        })

    return index


def load_scripts_data(force=False):
    global _SCRIPT_DATA_CACHE
    global _SCRIPT_DATA_MTIME_NS
    global _SCRIPT_SEARCH_INDEX

    try:
        stat = os.stat(_SCRIPT_DATA_PATH)
        mtime_ns = stat.st_mtime_ns
    except FileNotFoundError:
        print("ERROR: scripts.json file not found!")
        _SCRIPT_DATA_CACHE = []
        _SCRIPT_SEARCH_INDEX = []
        _SCRIPT_DATA_MTIME_NS = None
        return []
    except Exception as e:
        print(f"ERROR reading scripts.json metadata: {e}")
        return _SCRIPT_DATA_CACHE

    if (
        not force
        and _SCRIPT_DATA_MTIME_NS == mtime_ns
    ):
        return _SCRIPT_DATA_CACHE

    try:
        with open(_SCRIPT_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print("ERROR: scripts.json must contain a list!")
            data = []

        _SCRIPT_DATA_CACHE = data
        _SCRIPT_SEARCH_INDEX = _build_search_index(data)
        _SCRIPT_DATA_MTIME_NS = mtime_ns
        _SCRIPT_QUERY_CACHE.clear()

        print(
            f"✅ Fime Library search index ready: "
            f"{len(_SCRIPT_DATA_CACHE)} scripts"
        )

        return _SCRIPT_DATA_CACHE

    except json.JSONDecodeError:
        print("ERROR: Invalid JSON format in scripts.json!")
        return _SCRIPT_DATA_CACHE
    except Exception as e:
        print(f"ERROR loading scripts.json: {e}")
        return _SCRIPT_DATA_CACHE


# ============================================================
# COPY BUTTONS
# ============================================================

class ScriptCopyView(ui.View):
    def __init__(self, script_to_copy, script_title=None):
        super().__init__(timeout=None)
        self.script_to_copy = str(script_to_copy or "")
        self.script_title = script_title

    @ui.button(label="📋 نسخ السكربت", style=discord.ButtonStyle.green)
    async def copy_full_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # Discord لا يسمح برسالة أطول من 2000 حرف؛ نرسل النص خام بدون ```.
            if len(self.script_to_copy) <= 2000:
                await interaction.response.send_message(
                    self.script_to_copy or "⚠️ السكربت فارغ.",
                    ephemeral=True
                )
                return

            import io
            await interaction.response.send_message(
                "⚠️ السكربت أطول من حد رسالة Discord، أرسلته لك كملف نصي بدون أي تنسيق.",
                file=discord.File(
                    io.BytesIO(self.script_to_copy.encode("utf-8")),
                    filename=f"{self.script_title or 'script'}.txt"
                ),
                ephemeral=True
            )
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ حدث خطأ: {e}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ حدث خطأ: {e}", ephemeral=True)
            except Exception:
                pass

    @ui.button(label="🔗 نسخ رابط", style=discord.ButtonStyle.blurple)
    async def copy_loadstring_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            # هذا الزر كان يعرض المحتوى داخل ```؛ الآن يعرضه خام أيضًا.
            await interaction.response.send_message(
                self.script_to_copy or "⚠️ السكربت فارغ.",
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)
            except Exception:
                pass

    @ui.button(label="💾 حفظ", style=discord.ButtonStyle.grey)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            import io
            title = self.script_title or "Script"
            await interaction.response.send_message(
                f"✅ تم تجهيز **{title}** للحفظ.",
                file=discord.File(
                    io.BytesIO(self.script_to_copy.encode("utf-8")),
                    filename=f"{title}.txt"
                ),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {e}", ephemeral=True)
            except Exception:
                pass


class ScriptBrowserView(ui.View):
    """تصفح نتائج البحث والتنقل بينها بدل إظهار أول نتيجة فقط."""

    def __init__(self, scripts, requester_id, query):
        super().__init__(timeout=180)
        self.scripts = list(scripts or [])
        self.requester_id = requester_id
        self.query = query
        self.index = 0
        self.message = None
        self.refresh_buttons()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "⚠️ أزرار البحث للشخص اللي طلب البحث فقط.",
                ephemeral=True
            )
            return False
        return True

    def refresh_buttons(self):
        self.clear_items()

        previous = ui.Button(
            label="◀️ السابق",
            style=discord.ButtonStyle.secondary,
            disabled=self.index <= 0,
            row=0
        )
        previous.callback = self.previous_callback
        self.add_item(previous)

        position = ui.Button(
            label=f"{self.index + 1}/{len(self.scripts)}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0
        )
        self.add_item(position)

        next_button = ui.Button(
            label="التالي ▶️",
            style=discord.ButtonStyle.secondary,
            disabled=self.index >= len(self.scripts) - 1,
            row=0
        )
        next_button.callback = self.next_callback
        self.add_item(next_button)

        copy_button = ui.Button(
            label="📋 نسخ السكربت",
            style=discord.ButtonStyle.success,
            row=1
        )
        copy_button.callback = self.copy_callback
        self.add_item(copy_button)

    async def render(self, interaction=None, initial=False):
        script = self.scripts[self.index]
        embed = await create_script_embed(script)
        self.refresh_buttons()

        content = (
            f"🔎 نتائج البحث عن **{self.query}**\n"
            f"📚 النتيجة **{self.index + 1} من {len(self.scripts)}**\n"
            f"🗺️ الماب: **{script.get('map') or script.get('title', 'غير معروف')}**"
        )

        if initial:
            return content, embed, self

        await interaction.response.edit_message(
            content=content,
            embed=embed,
            view=self
        )

    async def previous_callback(self, interaction: discord.Interaction):
        if self.index <= 0:
            return await interaction.response.defer()
        self.index -= 1
        await self.render(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if self.index >= len(self.scripts) - 1:
            return await interaction.response.defer()
        self.index += 1
        await self.render(interaction)

    async def copy_callback(self, interaction: discord.Interaction):
        script = self.scripts[self.index]
        code = str(script.get("script_code", "") or "")
        title = script.get("title") or script.get("map") or "Script"

        try:
            if len(code) <= 2000:
                await interaction.response.send_message(
                    code or "⚠️ السكربت فارغ.",
                    ephemeral=True
                )
                return

            import io
            await interaction.response.send_message(
                "⚠️ السكربت أطول من حد Discord، أرسلته لك كملف نصي خام.",
                file=discord.File(
                    io.BytesIO(code.encode("utf-8")),
                    filename=f"{title}.txt"
                ),
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ حدث خطأ أثناء النسخ: {e}", ephemeral=True)
            except Exception:
                pass

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


# ============================================================
# SCRIPT EMBED
# ============================================================

async def create_script_embed(data):
    is_safe = bool(data.get('is_safe', False))
    is_keyless = bool(data.get('is_keyless', False))
    script_code = str(data.get('script_code', ''))
    image_url = str(data.get('image_url', '') or '')

    description = (
        f"**الماب** 📌 {data.get('map', 'غير معروف')}\n"
        f"**مـوثوقية** {'✅ موثوقة' if is_safe else '❌ غير موثوقة'}\n"
        f"**مشـاهدات** 👀 {data.get('views', 0)}\n"
        f"**يحتاج مفتاح** 🔑 {'❌ لا' if is_keyless else '✅ نعم'}\n\n"
        f"**مصـحح** {'✅ مصحح' if is_safe else '❌ غير مصحح'}\n"
        f"**السكربت (معاينة)** ⚙️\n"
        f"```lua\n{script_code[:70]}...\n```\n"
        f"by {data.get('author', 'Fime')}"
    )

    embed = discord.Embed(
        title=data.get('title', data.get('map', 'Fime Script')),
        description=description,
        color=discord.Color.green()
    )

    if image_url:
        embed.set_image(url=image_url)

    return embed


# ============================================================
# FIME LIBRARY COG
# ============================================================

class FimeLibrary(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.active_loops = {}

        target_channel_env = os.getenv('TARGET_CHANNEL_ID', '0')
        try:
            self.TARGET_CHANNEL_ID = int(target_channel_env)
        except ValueError:
            self.TARGET_CHANNEL_ID = 0

        self.AUTO_SEARCH_CHANNELS_FILE = "auto_search_channels.json"
        self.AUTO_SEARCH_SETTINGS_FILE = "auto_search_settings.json"

        self.auto_search_channels = {}
        self.auto_search_settings = {}

        self.auto_search_cooldowns = {}
        self.auto_search_tasks = set()
        self.auto_search_result_cache = {}

        self.load_auto_search_channels()
        self.load_auto_search_settings()
        load_scripts_data(force=True)

    # ========================================================
    # AUTO SEARCH CONFIG
    # ========================================================

    def load_auto_search_channels(self):
        try:
            with open(self.AUTO_SEARCH_CHANNELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                self.auto_search_channels = {
                    str(guild_id): int(channel_id)
                    for guild_id, channel_id in data.items()
                }
            else:
                self.auto_search_channels = {}

        except FileNotFoundError:
            self.auto_search_channels = {}
        except (json.JSONDecodeError, ValueError, TypeError):
            self.auto_search_channels = {}

    def save_auto_search_channels(self):
        try:
            with open(self.AUTO_SEARCH_CHANNELS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.auto_search_channels, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ERROR saving auto search channels: {e}")

    def load_auto_search_settings(self):
        try:
            with open(self.AUTO_SEARCH_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.auto_search_settings = data if isinstance(data, dict) else {}
        except FileNotFoundError:
            self.auto_search_settings = {}
        except (json.JSONDecodeError, ValueError, TypeError):
            self.auto_search_settings = {}

    def save_auto_search_settings(self):
        try:
            with open(self.AUTO_SEARCH_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.auto_search_settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ERROR saving auto search settings: {e}")

    # ========================================================
    # FAST LOCAL SEARCH ENGINE
    # ========================================================

    def normalize_search_text(self, text):
        return _normalize_local_search_text(text)

    def similarity_score(self, query, candidate):
        query = _normalize_local_search_text(query)
        candidate = _normalize_local_search_text(candidate)

        if not query or not candidate:
            return 0.0
        if query == candidate:
            return 1.0

        if candidate.startswith(query) or query.startswith(candidate):
            return 0.96
        if query in candidate:
            return 0.93

        if fuzz is not None:
            return fuzz.WRatio(query, candidate) / 100.0

        return difflib.SequenceMatcher(
            None,
            query,
            candidate,
        ).ratio()

    def get_script_search_candidates(self, script):
        return _script_search_fields(script)

    def find_matching_scripts(self, script_data, query):
        normalized_query = _normalize_local_search_text(query)
        compact_query = _compact_local_search_text(query)

        if not normalized_query:
            return []

        # نستخدم الفهرس الجاهز، ونرجع للبيانات العادية فقط إذا لم تكن متزامنة.
        load_scripts_data()
        index = _SCRIPT_SEARCH_INDEX

        if not index or len(index) != len(script_data):
            index = _build_search_index(script_data)

        query_words = set(normalized_query.split())
        query_first = normalized_query[:1]

        candidate_entries = []
        seen_ids = set()

        # تضييق سريع للأسماء التي تشترك في حرف/كلمة قبل الفحص الدقيق.
        for entry in index:
            if query_first and entry["first_chars"] and query_first not in entry["first_chars"]:
                continue

            if query_words and entry["tokens"] & query_words:
                candidate_entries.append(entry)
                seen_ids.add(id(entry["script"]))

        # إذا لم نجد مرشحين كفاية، استخدم كل الفهرس للأخطاء الإملائية.
        if len(candidate_entries) < min(12, len(index)):
            for entry in index:
                if id(entry["script"]) not in seen_ids:
                    candidate_entries.append(entry)

        exact = []
        scored = []

        for entry in candidate_entries:
            script = entry["script"]
            fields = entry["fields"]
            compact_fields = entry["compact"]

            if normalized_query in fields:
                exact.append(script)
                continue

            best_score = 0.0

            for field in fields:
                if field == normalized_query:
                    best_score = 1.0
                    break

                if field.startswith(normalized_query) or normalized_query.startswith(field):
                    best_score = max(best_score, 0.96)
                    continue

                if normalized_query in field:
                    best_score = max(best_score, 0.93)
                    continue

                if fuzz is not None:
                    score = fuzz.WRatio(normalized_query, field) / 100.0
                else:
                    score = difflib.SequenceMatcher(
                        None,
                        normalized_query,
                        field,
                    ).ratio()

                best_score = max(best_score, score)

            # compact match يفيد في أخطاء المسافات وتكرار الأحرف.
            for compact_field in compact_fields:
                if not compact_field:
                    continue
                if compact_query in compact_field or compact_field in compact_query:
                    best_score = max(best_score, 0.91)

            if len(normalized_query) <= 2:
                minimum_score = 0.88
            elif len(normalized_query) <= 4:
                minimum_score = 0.70
            elif len(query_words) > 1:
                minimum_score = 0.50
            else:
                minimum_score = 0.45

            if best_score >= minimum_score:
                scored.append((best_score, script))

        exact_ids = {id(script) for script in exact}
        scored.sort(key=lambda item: item[0], reverse=True)

        result = list(exact)
        result.extend(
            script for _, script in scored
            if id(script) not in exact_ids
        )

        return result

    def script_matches_query(self, script, query):
        return bool(self.find_matching_scripts([script], query))


    # ========================================================
    # FAST AUTO SEARCH
    # ========================================================

    def _auto_search_cache_key(self, guild_id, query):
        return f"{guild_id}:{_compact_local_search_text(query)}"

    def _get_cached_auto_result(self, guild_id, query):
        key = self._auto_search_cache_key(guild_id, query)
        item = self.auto_search_result_cache.get(key)
        if not item:
            return None
        if time.monotonic() - item["timestamp"] > _SCRIPT_QUERY_CACHE_TTL:
            self.auto_search_result_cache.pop(key, None)
            return None
        return list(item["scripts"])

    def _set_cached_auto_result(self, guild_id, query, scripts):
        key = self._auto_search_cache_key(guild_id, query)
        self.auto_search_result_cache[key] = {
            "timestamp": time.monotonic(),
            "scripts": list(scripts),
        }

        if len(self.auto_search_result_cache) > 200:
            now = time.monotonic()
            expired = [
                cache_key
                for cache_key, item in self.auto_search_result_cache.items()
                if now - item.get("timestamp", 0) > _SCRIPT_QUERY_CACHE_TTL
            ]
            for cache_key in expired:
                self.auto_search_result_cache.pop(cache_key, None)

    def _bot4_search_room_owns_channel(self, guild_id, channel_id):
        """يمنع ردين تلقائيين من bot4 وFime Library في نفس الروم."""
        try:
            with open("bot4_search_rooms.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get(str(guild_id))) == str(channel_id)
        except Exception:
            return False

    async def send_auto_search_result(self, channel, query, requester_id=None, status_message=None):
        guild_id = str(channel.guild.id) if channel.guild else ""
        started = time.perf_counter()

        try:
            load_scripts_data()

            settings = self.auto_search_settings.get(guild_id, {})
            no_key_system = bool(settings.get("no_key_system", False)) if isinstance(settings, dict) else False

            matching_scripts = self._get_cached_auto_result(guild_id, query)

            if matching_scripts is None:
                matching_scripts = self.find_matching_scripts(
                    _SCRIPT_DATA_CACHE,
                    query,
                )

                if no_key_system:
                    matching_scripts = [
                        script for script in matching_scripts
                        if bool(script.get("is_keyless", False))
                    ]

                matching_scripts = matching_scripts[:25]
                self._set_cached_auto_result(
                    guild_id,
                    query,
                    matching_scripts,
                )

            if not matching_scripts:
                content = (
                    f"❌ ما لقيت سكربت مناسب لـ **{query}**."
                    if not no_key_system
                    else f"❌ ما لقيت سكربت مناسب لـ **{query}** بدون مفتاح."
                )
                if status_message:
                    await status_message.edit(content=content, embed=None, view=None)
                else:
                    await channel.send(content)
                return

            view = ScriptBrowserView(
                matching_scripts,
                requester_id or channel.guild.id,
                query,
            )

            content, embed, view = await view.render(initial=True)

            elapsed = time.perf_counter() - started
            content += f"\n⚡ البحث المحلي اكتمل خلال **{elapsed:.3f}s**"

            if status_message:
                message = await status_message.edit(
                    content=content,
                    embed=embed,
                    view=view,
                )
                view.message = status_message
            else:
                message = await channel.send(
                    content=content,
                    embed=embed,
                    view=view,
                )
                view.message = message

        except Exception as e:
            print(f"Auto search error: {e}")
            try:
                if status_message:
                    await status_message.edit(
                        content="❌ حدث خطأ أثناء البحث. جرب مرة ثانية.",
                        embed=None,
                        view=None,
                    )
                else:
                    await channel.send("❌ حدث خطأ أثناء البحث. جرب مرة ثانية.")
            except Exception:
                pass

    # ========================================================
    # AUTO SEARCH MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        guild_id = str(message.guild.id)
        target_auto_search_channel = self.auto_search_channels.get(guild_id)

        if not target_auto_search_channel:
            return

        if message.channel.id != target_auto_search_channel:
            return

        # لو bot4 محدد نفس الروم، هو صاحب البحث الخارجي ولا نرسل نتيجة ثانية.
        if self._bot4_search_room_owns_channel(guild_id, message.channel.id):
            return

        query = message.content.strip()
        if not query or query.startswith(("/", "!")) or len(query) > 100:
            return

        cooldown_key = f"{guild_id}:{message.author.id}"
        now = time.monotonic()
        last = self.auto_search_cooldowns.get(cooldown_key, 0)

        if now - last < 2.5:
            return

        self.auto_search_cooldowns[cooldown_key] = now

        # رد فوري ثم البحث بالخلفية.
        try:
            status_message = await message.channel.send(
                f"⏳ **جاري معالجة طلبك...**\n🎮 الماب: **{query}**"
            )

            task = asyncio.create_task(
                self.send_auto_search_result(
                    message.channel,
                    query,
                    message.author.id,
                    status_message,
                )
            )

            self.auto_search_tasks.add(task)
            task.add_done_callback(self.auto_search_tasks.discard)

        except Exception as e:
            print(f"Auto search start error: {e}")


    # ========================================================
    # SET AUTO SEARCH
    # ========================================================

    @app_commands.command(
        name="set_auto_search",
        description="تحديد روم البحث التلقائي"
    )
    @app_commands.describe(
        channel="الروم الذي سيتم فيه البحث التلقائي",
        no_key_system="هل تريد سكربتات بدون مفتاح فقط؟"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_auto_search(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        no_key_system: bool = False
    ):
        guild_id = str(interaction.guild.id)

        self.auto_search_channels[guild_id] = channel.id
        self.auto_search_settings[guild_id] = {
            "no_key_system": bool(no_key_system)
        }

        self.save_auto_search_channels()
        self.save_auto_search_settings()

        key_text = "بدون مفتاح فقط 🔓" if no_key_system else "كل السكربتات 🔑"

        await interaction.response.send_message(
            f"✅ تم تحديد روم البحث التلقائي إلى {channel.mention}\n"
            f"🔎 الوضع: **{key_text}**\n\n"
            f"الآن العضو يكتب اسم الماب، حتى لو الاسم مو مطابق 100٪، وفيمي يحاول يجيب أقرب نتيجة من `scripts.json`.",
            ephemeral=True
        )

    # ========================================================
    # SHOW AUTO SEARCH ROOM
    # ========================================================

    @app_commands.command(
        name="auto_search_room",
        description="معرفة روم البحث التلقائي الحالي"
    )
    async def auto_search_room(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)
        channel_id = self.auto_search_channels.get(guild_id)

        if not channel_id:
            return await interaction.response.send_message(
                "❌ لم يتم تحديد روم للبحث التلقائي.",
                ephemeral=True
            )

        channel = interaction.guild.get_channel(channel_id)
        if not channel:
            return await interaction.response.send_message(
                "⚠️ روم البحث المحدد لم يعد موجودًا.",
                ephemeral=True
            )

        settings = self.auto_search_settings.get(guild_id, {})
        no_key_system = bool(settings.get("no_key_system", False)) if isinstance(settings, dict) else False
        key_text = "بدون مفتاح فقط 🔓" if no_key_system else "كل السكربتات 🔑"

        await interaction.response.send_message(
            f"🔎 روم البحث التلقائي الحالي: {channel.mention}\n"
            f"🔑 وضع المفتاح: **{key_text}**",
            ephemeral=True
        )

    # ========================================================
    # CHANGE KEY MODE
    # ========================================================

    @app_commands.command(
        name="set_auto_search_key",
        description="تغيير وضع المفتاح للبحث التلقائي"
    )
    @app_commands.describe(
        no_key_system="True = بدون مفتاح فقط | False = كل السكربتات"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_auto_search_key(
        self,
        interaction: discord.Interaction,
        no_key_system: bool
    ):
        guild_id = str(interaction.guild.id)

        if guild_id not in self.auto_search_channels:
            return await interaction.response.send_message(
                "❌ حدد روم البحث أولًا باستخدام /set_auto_search.",
                ephemeral=True
            )

        self.auto_search_settings[guild_id] = {
            "no_key_system": bool(no_key_system)
        }
        self.save_auto_search_settings()

        key_text = "بدون مفتاح فقط 🔓" if no_key_system else "كل السكربتات 🔑"

        await interaction.response.send_message(
            f"✅ تم تغيير وضع البحث التلقائي إلى: **{key_text}**",
            ephemeral=True
        )

    # ========================================================
    # DISABLE AUTO SEARCH
    # ========================================================

    @app_commands.command(
        name="disable_auto_search",
        description="إيقاف البحث التلقائي"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_auto_search(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild.id)

        if guild_id not in self.auto_search_channels:
            return await interaction.response.send_message(
                "❌ البحث التلقائي غير مفعل.",
                ephemeral=True
            )

        del self.auto_search_channels[guild_id]
        self.auto_search_settings.pop(guild_id, None)

        self.save_auto_search_channels()
        self.save_auto_search_settings()

        await interaction.response.send_message(
            "⛔ تم إيقاف البحث التلقائي.",
            ephemeral=True
        )

    # ========================================================
    # RANDOM SCRIPT
    # ========================================================

    @app_commands.command(
        name="fime_script",
        description="احصل على سكربت عشوائي"
    )
    async def slash_random_script(self, interaction: discord.Interaction):
        script_data = load_scripts_data()

        if not script_data:
            return await interaction.response.send_message(
                "لا توجد سكربتات متاحة حاليًا."
            )

        chosen_script = random.choice(script_data)
        script_embed = await create_script_embed(chosen_script)

        view = ScriptCopyView(
            chosen_script.get('script_code', ''),
            chosen_script.get('title', 'Script')
        )

        await interaction.response.send_message(
            embed=script_embed,
            view=view
        )

    # ========================================================
    # MANUAL SEARCH
    # ========================================================

    @app_commands.command(
        name="fime_search",
        description="ابحث عن سكربت باسم الماب أو اللعبة"
    )
    async def search_scripts(
        self,
        interaction: discord.Interaction,
        query: str
    ):
        script_data = load_scripts_data()

        if not script_data:
            return await interaction.response.send_message(
                "لا توجد سكربتات متاحة حاليًا.",
                ephemeral=True
            )

        matching_scripts = self.find_matching_scripts(script_data, query)

        if not matching_scripts:
            return await interaction.response.send_message(
                f"❌ لم يتم العثور على سكربتات قريبة من: **{query}**",
                ephemeral=True
            )

        matching_scripts = matching_scripts[:25]
        view = ScriptBrowserView(matching_scripts, interaction.user.id, query)
        content, embed, view = await view.render(initial=True)

        await interaction.response.send_message(
            content=content,
            embed=embed,
            view=view
        )
        try:
            view.message = await interaction.original_response()
        except Exception:
            pass

    # ========================================================
    # START POSTING
    # ========================================================

    @app_commands.command(
        name="start_posting",
        description="ابدأ النشر التلقائي للسكربتات كل 10 دقائق"
    )
    async def start_posting(self, interaction: discord.Interaction):
        if self.post_random_script.is_running():
            return await interaction.response.send_message(
                "النشر التلقائي يعمل بالفعل! ✅",
                ephemeral=True
            )

        self.post_random_script.start()

        await interaction.response.send_message(
            "تم بدء النشر التلقائي! ✅\nسيتم نشر سكربت كل 10 دقائق 🎉",
            ephemeral=True
        )

    # ========================================================
    # STOP POSTING
    # ========================================================

    @app_commands.command(
        name="stop_posting",
        description="أوقف النشر التلقائي"
    )
    async def stop_posting(self, interaction: discord.Interaction):
        if not self.post_random_script.is_running():
            return await interaction.response.send_message(
                "النشر التلقائي متوقف بالفعل! ❌",
                ephemeral=True
            )

        self.post_random_script.stop()

        await interaction.response.send_message(
            "تم إيقاف النشر التلقائي! ⛔",
            ephemeral=True
        )

    # ========================================================
    # AUTO POST 5 MIN LOOP
    # ========================================================

    async def auto_post_5min_loop(self, channel_id):
        await self.bot.wait_until_ready()

        while True:
            try:
                if channel_id not in self.active_loops:
                    break

                script_data = load_scripts_data()
                if not script_data:
                    await asyncio.sleep(300)
                    continue

                channel = self.bot.get_channel(channel_id)
                if not channel or not hasattr(channel, 'send'):
                    break

                chosen_script = random.choice(script_data)
                script_embed = await create_script_embed(chosen_script)

                view = ScriptCopyView(
                    chosen_script.get('script_code', ''),
                    chosen_script.get('title', 'Script')
                )

                await channel.send(embed=script_embed, view=view)
                await asyncio.sleep(300)

            except Exception as e:
                print(f"Auto post error: {e}")
                await asyncio.sleep(300)

    # ========================================================
    # AUTO POST 5 MIN
    # ========================================================

    @app_commands.command(
        name="auto_post_5min",
        description="نشر سكربت عشوائي كل 5 دقائق في قناة محددة"
    )
    async def auto_post_5min(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        channel_id = channel.id

        if channel_id in self.active_loops:
            return await interaction.response.send_message(
                f"النشر التلقائي يعمل بالفعل في قناة {channel.mention}! ✅",
                ephemeral=True
            )

        self.active_loops[channel_id] = True

        try:
            script_data = load_scripts_data()
            if script_data:
                chosen_script = random.choice(script_data)
                script_embed = await create_script_embed(chosen_script)

                view = ScriptCopyView(
                    chosen_script.get('script_code', ''),
                    chosen_script.get('title', 'Script')
                )

                await channel.send(embed=script_embed, view=view)

        except Exception as e:
            print(f"Auto post initial error: {e}")

        asyncio.create_task(
            self.auto_post_5min_loop(channel_id)
        )

        await interaction.response.send_message(
            f"تم بدء النشر التلقائي كل 5 دقائق في {channel.mention}! 🎉",
            ephemeral=True
        )

    # ========================================================
    # STOP AUTO 5 MIN
    # ========================================================

    @app_commands.command(
        name="stop_auto_5min",
        description="أوقف النشر التلقائي للسكربتات كل 5 دقائق"
    )
    async def stop_auto_5min(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        channel_id = channel.id

        if channel_id not in self.active_loops:
            return await interaction.response.send_message(
                f"النشر التلقائي غير مفعل في {channel.mention}! ❌",
                ephemeral=True
            )

        del self.active_loops[channel_id]

        await interaction.response.send_message(
            f"تم إيقاف النشر التلقائي في {channel.mention}! ⛔",
            ephemeral=True
        )

    # ========================================================
    # RANDOM SCRIPT EVERY 10 MIN
    # ========================================================

    @tasks.loop(minutes=10)
    async def post_random_script(self):
        await self.bot.wait_until_ready()

        script_data = load_scripts_data()
        if not script_data or self.TARGET_CHANNEL_ID == 0:
            return

        channel = self.bot.get_channel(self.TARGET_CHANNEL_ID)
        if channel and hasattr(channel, 'send'):
            try:
                chosen_script = random.choice(script_data)
                script_embed = await create_script_embed(chosen_script)

                view = ScriptCopyView(
                    chosen_script.get('script_code', ''),
                    chosen_script.get('title', 'Script')
                )

                await channel.send(embed=script_embed, view=view)
            except Exception as e:
                print(f"Random post error: {e}")

    # ========================================================
    # START EXTENSION TASK
    # ========================================================

    async def cog_load(self):
        if not self.post_random_script.is_running():
            self.post_random_script.start()

        print("✅ Fime Library system loaded.")

    # ========================================================
    # UNLOAD EXTENSION
    # ========================================================

    async def cog_unload(self):
        if self.post_random_script.is_running():
            self.post_random_script.cancel()

        self.active_loops.clear()
        self.auto_search_cooldowns.clear()
        self.auto_search_result_cache.clear()

        for task in list(self.auto_search_tasks):
            task.cancel()

        self.auto_search_tasks.clear()
        print("⛔ Fime Library system unloaded.")


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(FimeLibrary(bot))
    print("✅ تم تحميل fime_library.py بنجاح داخل البوت الرئيسي.")
