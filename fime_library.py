# Fime Library Search Engine — Improved Arabic/English Fuzzy Search v2.1
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


# ============================================================
# SCRIPTS DATA
# ============================================================

def load_scripts_data():
    try:
        with open('scripts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except FileNotFoundError:
        print("ERROR: scripts.json file not found!")
        return []
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON format in scripts.json!")
        return []
    except Exception as e:
        print(f"ERROR loading scripts.json: {e}")
        return []


# ============================================================
# COPY BUTTONS
# ============================================================

class ScriptCopyView(ui.View):
    def __init__(self, script_to_copy, script_title=None):
        super().__init__(timeout=None)
        self.script_to_copy = script_to_copy
        self.script_title = script_title

    @ui.button(label="📋 نسخ السكربت", style=discord.ButtonStyle.green)
    async def copy_full_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                f"✅ **تم نسخ السكربت بنجاح**\n\n```lua\n{self.script_to_copy}\n```",
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)
            except Exception:
                pass

    @ui.button(label="🔗 نسخ رابط", style=discord.ButtonStyle.blurple)
    async def copy_loadstring_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(
                f"✅ **رابط التحميل:**\n\n```\n{self.script_to_copy}\n```",
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {str(e)}", ephemeral=True)
            except Exception:
                pass

    @ui.button(label="💾 حفظ", style=discord.ButtonStyle.grey)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            title = self.script_title or "Script"
            await interaction.followup.send(
                f"✅ **تم حفظ السكربت: {title}**\n\n"
                f"```lua\n{self.script_to_copy[:500]}...\n```",
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {str(e)}", ephemeral=True)
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

        self.load_auto_search_channels()
        self.load_auto_search_settings()

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
    # NORMALIZE SEARCH TEXT
    # ========================================================

    def normalize_search_text(self, text):
        text = str(text or "").lower().strip()

        arabic_diacritics = "ًٌٍَُِّْـ"
        for char in arabic_diacritics:
            text = text.replace(char, "")

        replacements = {
            "أ": "ا",
            "إ": "ا",
            "آ": "ا",
            "ٱ": "ا",
            "ى": "ي",
            "ؤ": "و",
            "ئ": "ي",
            "ة": "ه"
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        # نخلي اختلاف المسافات والرموز ما يفسد البحث.
        text = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", text)
        text = " ".join(text.split())
        return text

    # ========================================================
    # FUZZY MATCHING
    # ========================================================

    def similarity_score(self, query, candidate):
        query = self.normalize_search_text(query)
        candidate = self.normalize_search_text(candidate)

        if not query or not candidate:
            return 0.0

        if query == candidate:
            return 1.0

        if query in candidate or candidate in query:
            shorter = min(len(query), len(candidate))
            longer = max(len(query), len(candidate))
            return 0.88 + (shorter / max(longer, 1)) * 0.12

        direct = difflib.SequenceMatcher(None, query, candidate).ratio()

        query_words = set(query.split())
        candidate_words = set(candidate.split())

        if query_words and candidate_words:
            overlap = len(query_words & candidate_words) / len(query_words | candidate_words)
        else:
            overlap = 0.0

        partial = 0.0
        for word in query_words:
            if len(word) < 3:
                continue
            for candidate_word in candidate_words:
                if len(candidate_word) < 3:
                    continue
                partial = max(
                    partial,
                    difflib.SequenceMatcher(None, word, candidate_word).ratio()
                )

        return (direct * 0.45) + (overlap * 0.30) + (partial * 0.25)

    def get_script_search_candidates(self, script):
        return [
            script.get("map", ""),
            script.get("title", "")
        ]

    def find_matching_scripts(self, script_data, query):
        normalized_query = self.normalize_search_text(query)
        if not normalized_query:
            return []

        exact = []
        scored = []

        for script in script_data:
            candidates = self.get_script_search_candidates(script)
            best_score = max(
                (self.similarity_score(normalized_query, candidate) for candidate in candidates),
                default=0.0
            )

            normalized_candidates = [
                self.normalize_search_text(candidate)
                for candidate in candidates
            ]

            if any(
                normalized_query in candidate
                for candidate in normalized_candidates
                if candidate
            ):
                exact.append(script)
                continue

            query_word_count = len(normalized_query.split())
            minimum_score = 0.62
            if len(normalized_query) <= 3 or (query_word_count == 1 and len(normalized_query) <= 4):
                minimum_score = 0.72

            if best_score >= minimum_score:
                scored.append((best_score, script))

        if exact:
            return exact

        scored.sort(key=lambda item: item[0], reverse=True)
        return [script for _, script in scored]

    def script_matches_query(self, script, query):
        return bool(self.find_matching_scripts([script], query))

    # ========================================================
    # SEND AUTO SEARCH RESULT
    # ========================================================

    async def send_auto_search_result(self, channel, query):
        script_data = load_scripts_data()

        if not script_data:
            await channel.send("❌ ما فيه سكربتات متاحة حاليًا.")
            return

        matching_scripts = self.find_matching_scripts(script_data, query)

        guild_id = str(channel.guild.id) if channel.guild else ""
        settings = self.auto_search_settings.get(guild_id, {})
        no_key_system = bool(settings.get("no_key_system", False)) if isinstance(settings, dict) else False

        if no_key_system:
            matching_scripts = [
                script for script in matching_scripts
                if bool(script.get("is_keyless", False))
            ]

        if not matching_scripts:
            if no_key_system:
                await channel.send(
                    f"❌ ما لقيت سكربت مناسب لـ **{query}** بدون مفتاح."
                )
            else:
                await channel.send(
                    f"❌ ما لقيت سكربت مناسب لـ **{query}**"
                )
            return

        chosen_script = matching_scripts[0]
        script_embed = await create_script_embed(chosen_script)

        view = ScriptCopyView(
            chosen_script.get('script_code', ''),
            chosen_script.get('title', 'Script')
        )

        matched_name = chosen_script.get("map") or chosen_script.get("title", query)
        prefix = "🔎" if self.normalize_search_text(query) == self.normalize_search_text(matched_name) else "🧠"

        await channel.send(
            content=(
                f"{prefix} لقيت **{matched_name}** من بحثك: **{query}**\n"
                f"📚 عدد النتائج المطابقة: **{len(matching_scripts)}**"
            ),
            embed=script_embed,
            view=view
        )

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

        query = message.content.strip()

        if not query:
            return

        if query.startswith(("/", "!")):
            return

        if len(query) > 100:
            return

        try:
            async with message.channel.typing():
                await self.send_auto_search_result(
                    message.channel,
                    query
                )
        except Exception as e:
            print(f"Auto search error: {e}")

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

        chosen_script = matching_scripts[0]
        script_embed = await create_script_embed(chosen_script)

        view = ScriptCopyView(
            chosen_script.get('script_code', ''),
            chosen_script.get('title', 'Script')
        )

        await interaction.response.send_message(
            f"🧠 عثرت على **{len(matching_scripts)}** نتيجة قريبة من **{query}**\n",
            embed=script_embed,
            view=view
        )

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
        print("⛔ Fime Library system unloaded.")


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(FimeLibrary(bot))
    print("✅ تم تحميل fime_library.py بنجاح داخل البوت الرئيسي.")
