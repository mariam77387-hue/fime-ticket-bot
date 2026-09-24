import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
from discord import ui
import json
import os
import asyncio


# ============================================================
# SCRIPTS DATA
# ============================================================

def load_scripts_data():
    try:
        with open('scripts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data
    except FileNotFoundError:
        print("ERROR: scripts.json file not found!")
        return []
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON format in scripts.json!")
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
    async def copy_full_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            await interaction.followup.send(
                f"✅ **تم نسخ السكربت بنجاح**\n\n```lua\n{self.script_to_copy}\n```",
                ephemeral=True
            )

        except Exception as e:
            try:
                await interaction.followup.send(
                    f"❌ حدث خطأ: {str(e)}",
                    ephemeral=True
                )
            except:
                pass

    @ui.button(label="🔗 نسخ رابط", style=discord.ButtonStyle.blurple)
    async def copy_loadstring_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button
    ):
        try:
            await interaction.response.defer(ephemeral=True)

            await interaction.followup.send(
                f"✅ **رابط التحميل:**\n\n```\n{self.script_to_copy}\n```",
                ephemeral=True
            )

        except Exception as e:
            try:
                await interaction.followup.send(
                    f"❌ خطأ: {str(e)}",
                    ephemeral=True
                )
            except:
                pass

    @ui.button(label="💾 حفظ", style=discord.ButtonStyle.grey)
    async def save_button(
        self,
        interaction: discord.Interaction,
        button: ui.Button
    ):
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
                await interaction.followup.send(
                    f"❌ خطأ: {str(e)}",
                    ephemeral=True
                )
            except:
                pass


# ============================================================
# SCRIPT EMBED
# ============================================================

async def create_script_embed(data):

    description = (
        f"**الماب** 📌 {data['map']}\n"
        f"**مـوثوقية** "
        f"{'✅ موثوقة' if data['is_safe'] else '❌ غير موثوقة'}\n"
        f"**مشـاهدات** 👀 {data['views']}\n"
        f"**يحتاج مفتاح** 🔑 "
        f"{'❌ لا' if data['is_keyless'] else '✅ نعم'}\n\n"
        f"**مصـحح** "
        f"{'✅ مصحح' if data['is_safe'] else '❌ غير مصحح'}\n"
        f"**السكربت (معاينة)** ⚙️\n"
        f"```lua\n{data['script_code'][:70]}...\n```\n"
        f"by {data['author']}"
    )

    embed = discord.Embed(
        title=data['title'],
        description=description,
        color=discord.Color.green()
    )

    embed.set_image(
        url=data['image_url']
    )

    return embed


# ============================================================
# FIME LIBRARY COG
# ============================================================

class FimeLibrary(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        # ====================================================
        # AUTO POST LOOPS
        # ====================================================

        self.active_loops = {}

        target_channel_env = os.getenv(
            'TARGET_CHANNEL_ID',
            '0'
        )

        try:
            self.TARGET_CHANNEL_ID = int(
                target_channel_env
            )
        except ValueError:
            self.TARGET_CHANNEL_ID = 0

        # ====================================================
        # AUTO SEARCH
        # ====================================================

        self.AUTO_SEARCH_CHANNELS_FILE = (
            "auto_search_channels.json"
        )

        self.auto_search_channels = {}

        self.load_auto_search_channels()

    # ========================================================
    # LOAD AUTO SEARCH CHANNELS
    # ========================================================

    def load_auto_search_channels(self):

        try:

            with open(
                self.AUTO_SEARCH_CHANNELS_FILE,
                "r",
                encoding="utf-8"
            ) as f:

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

        except (
            json.JSONDecodeError,
            ValueError,
            TypeError
        ):

            self.auto_search_channels = {}

    # ========================================================
    # SAVE AUTO SEARCH CHANNELS
    # ========================================================

    def save_auto_search_channels(self):

        try:

            with open(
                self.AUTO_SEARCH_CHANNELS_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    self.auto_search_channels,
                    f,
                    ensure_ascii=False,
                    indent=4
                )

        except Exception as e:

            print(
                f"ERROR saving auto search channels: {e}"
            )

    # ========================================================
    # NORMALIZE SEARCH TEXT
    # ========================================================

    def normalize_search_text(self, text):

        text = str(text).lower().strip()

        # إزالة التشكيل العربي

        arabic_diacritics = (
            "ًٌٍَُِّْـ"
        )

        for char in arabic_diacritics:

            text = text.replace(
                char,
                ""
            )

        # توحيد بعض الحروف العربية

        replacements = {

            "أ": "ا",
            "إ": "ا",
            "آ": "ا",
            "ٱ": "ا",
            "ى": "ي",
            "ؤ": "و",
            "ئ": "ي"

        }

        for old, new in replacements.items():

            text = text.replace(
                old,
                new
            )

        # توحيد المسافات

        text = " ".join(
            text.split()
        )

        return text

    # ========================================================
    # MATCH SCRIPT
    # ========================================================

    def script_matches_query(
        self,
        script,
        query
    ):

        query = self.normalize_search_text(
            query
        )

        if not query:
            return False

        map_name = self.normalize_search_text(
            script.get(
                "map",
                ""
            )
        )

        title = self.normalize_search_text(
            script.get(
                "title",
                ""
            )
        )

        return (
            query in map_name
            or
            query in title
        )

    # ========================================================
    # SEND AUTO SEARCH RESULT
    # ========================================================

    async def send_auto_search_result(
        self,
        channel,
        query
    ):

        script_data = load_scripts_data()

        if not script_data:

            await channel.send(
                "❌ ما فيه سكربتات متاحة حاليًا."
            )

            return

        matching_scripts = [

            script
            for script in script_data

            if self.script_matches_query(
                script,
                query
            )

        ]

        if not matching_scripts:

            await channel.send(
                f"❌ ما لقيت سكربت للماب: **{query}**"
            )

            return

        # إذا فيه أكثر من نتيجة نختار واحدة

        chosen_script = random.choice(
            matching_scripts
        )

        script_embed = await create_script_embed(
            chosen_script
        )

        view = ScriptCopyView(
            chosen_script['script_code'],
            chosen_script.get(
                'title',
                'Script'
            )
        )

        await channel.send(
            content=(
                f"🔎 لقيت **{len(matching_scripts)}** "
                f"نتيجة لـ **{query}**"
            ),
            embed=script_embed,
            view=view
        )

    # ========================================================
    # AUTO SEARCH MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        # تجاهل البوتات

        if message.author.bot:
            return

        # التأكد من السيرفر

        if not message.guild:
            return

        guild_id = str(
            message.guild.id
        )

        # هل يوجد روم بحث؟

        target_auto_search_channel = (
            self.auto_search_channels.get(
                guild_id
            )
        )

        if not target_auto_search_channel:
            return

        # هل الرسالة في روم البحث؟

        if message.channel.id != target_auto_search_channel:
            return

        query = message.content.strip()

        # تجاهل الفارغ

        if not query:
            return

        # تجاهل أوامر Discord

        if query.startswith(
            (
                "/",
                "!"
            )
        ):
            return

        # حماية من الرسائل الطويلة

        if len(query) > 100:
            return

        try:

            await self.send_auto_search_result(
                message.channel,
                query
            )

        except Exception as e:

            print(
                f"Auto search error: {e}"
            )

    # ========================================================
    # SET AUTO SEARCH
    # ========================================================

    @app_commands.command(
        name="set_auto_search",
        description="تحديد روم البحث التلقائي"
    )
    @app_commands.describe(
        channel="الروم الذي سيتم فيه البحث التلقائي"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def set_auto_search(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        guild_id = str(
            interaction.guild.id
        )

        self.auto_search_channels[
            guild_id
        ] = channel.id

        self.save_auto_search_channels()

        await interaction.response.send_message(

            f"✅ تم تحديد روم البحث التلقائي إلى "
            f"{channel.mention}\n\n"

            f"من الآن أي عضو يكتب اسم الماب داخل الروم، "
            f"البوت يبحث عنه تلقائيًا.",

            ephemeral=True
        )

    # ========================================================
    # SHOW AUTO SEARCH ROOM
    # ========================================================

    @app_commands.command(
        name="auto_search_room",
        description="معرفة روم البحث التلقائي الحالي"
    )
    async def auto_search_room(
        self,
        interaction: discord.Interaction
    ):

        guild_id = str(
            interaction.guild.id
        )

        channel_id = (
            self.auto_search_channels.get(
                guild_id
            )
        )

        if not channel_id:

            return await interaction.response.send_message(

                "❌ لم يتم تحديد روم للبحث التلقائي.",

                ephemeral=True
            )

        channel = interaction.guild.get_channel(
            channel_id
        )

        if not channel:

            return await interaction.response.send_message(

                "⚠️ روم البحث المحدد لم يعد موجودًا.",

                ephemeral=True
            )

        await interaction.response.send_message(

            f"🔎 روم البحث التلقائي الحالي: "
            f"{channel.mention}",

            ephemeral=True
        )

    # ========================================================
    # DISABLE AUTO SEARCH
    # ========================================================

    @app_commands.command(
        name="disable_auto_search",
        description="إيقاف البحث التلقائي"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def disable_auto_search(
        self,
        interaction: discord.Interaction
    ):

        guild_id = str(
            interaction.guild.id
        )

        if guild_id not in self.auto_search_channels:

            return await interaction.response.send_message(

                "❌ البحث التلقائي غير مفعل.",

                ephemeral=True
            )

        del self.auto_search_channels[
            guild_id
        ]

        self.save_auto_search_channels()

        await interaction.response.send_message(

            "⛔ تم إيقاف البحث التلقائي.",

            ephemeral=True
        )

    # ========================================================
    # RANDOM SCRIPT
    # ========================================================

    @app_commands.command(
        name="script",
        description="احصل على سكربت عشوائي"
    )
    async def slash_random_script(
        self,
        interaction: discord.Interaction
    ):

        script_data = load_scripts_data()

        if not script_data:

            return await interaction.response.send_message(
                "لا توجد سكربتات متاحة حاليًا."
            )

        chosen_script = random.choice(
            script_data
        )

        script_embed = await create_script_embed(
            chosen_script
        )

        view = ScriptCopyView(
            chosen_script['script_code'],
            chosen_script.get(
                'title',
                'Script'
            )
        )

        await interaction.response.send_message(
            embed=script_embed,
            view=view
        )

    # ========================================================
    # MANUAL SEARCH
    # ========================================================

    @app_commands.command(
        name="search",
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

        matching_scripts = [

            script

            for script in script_data

            if self.script_matches_query(
                script,
                query
            )

        ]

        if not matching_scripts:

            return await interaction.response.send_message(

                f"❌ لم يتم العثور على سكربتات "
                f"تتطابق مع: **{query}**",

                ephemeral=True
            )

        chosen_script = random.choice(
            matching_scripts
        )

        script_embed = await create_script_embed(
            chosen_script
        )

        view = ScriptCopyView(
            chosen_script['script_code'],
            chosen_script.get(
                'title',
                'Script'
            )
        )

        await interaction.response.send_message(

            f"✅ عثرت على **{len(matching_scripts)}** "
            f"سكربت يتطابق مع '{query}'\n",

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
    async def start_posting(
        self,
        interaction: discord.Interaction
    ):

        if self.post_random_script.is_running():

            return await interaction.response.send_message(

                "النشر التلقائي يعمل بالفعل! ✅",

                ephemeral=True
            )

        self.post_random_script.start()

        await interaction.response.send_message(

            "تم بدء النشر التلقائي! ✅\n"
            "سيتم نشر سكربت كل 10 دقائق 🎉",

            ephemeral=True
        )

    # ========================================================
    # STOP POSTING
    # ========================================================

    @app_commands.command(
        name="stop_posting",
        description="أوقف النشر التلقائي"
    )
    async def stop_posting(
        self,
        interaction: discord.Interaction
    ):

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

    async def auto_post_5min_loop(
        self,
        channel_id
    ):

        await self.bot.wait_until_ready()

        while True:

            try:

                if channel_id not in self.active_loops:
                    break

                script_data = load_scripts_data()

                if not script_data:

                    await asyncio.sleep(300)

                    continue

                channel = self.bot.get_channel(
                    channel_id
                )

                if (
                    not channel
                    or
                    not hasattr(channel, 'send')
                ):

                    break

                chosen_script = random.choice(
                    script_data
                )

                script_embed = await create_script_embed(
                    chosen_script
                )

                view = ScriptCopyView(
                    chosen_script['script_code'],
                    chosen_script.get(
                        'title',
                        'Script'
                    )
                )

                await channel.send(
                    embed=script_embed,
                    view=view
                )

                await asyncio.sleep(300)

            except Exception as e:

                print(
                    f"Auto post error: {e}"
                )

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

                f"النشر التلقائي يعمل بالفعل "
                f"في قناة {channel.mention}! ✅",

                ephemeral=True
            )

        self.active_loops[
            channel_id
        ] = True

        try:

            script_data = load_scripts_data()

            if script_data:

                chosen_script = random.choice(
                    script_data
                )

                script_embed = await create_script_embed(
                    chosen_script
                )

                view = ScriptCopyView(
                    chosen_script['script_code'],
                    chosen_script.get(
                        'title',
                        'Script'
                    )
                )

                await channel.send(
                    embed=script_embed,
                    view=view
                )

        except Exception as e:

            print(
                f"Auto post initial error: {e}"
            )

        asyncio.create_task(
            self.auto_post_5min_loop(
                channel_id
            )
        )

        await interaction.response.send_message(

            f"تم بدء النشر التلقائي كل 5 دقائق "
            f"في {channel.mention}! 🎉",

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

                f"النشر التلقائي غير مفعل "
                f"في {channel.mention}! ❌",

                ephemeral=True
            )

        del self.active_loops[
            channel_id
        ]

        await interaction.response.send_message(

            f"تم إيقاف النشر التلقائي "
            f"في {channel.mention}! ⛔",

            ephemeral=True
        )

    # ========================================================
    # RANDOM SCRIPT EVERY 10 MIN
    # ========================================================

    @tasks.loop(minutes=10)
    async def post_random_script(self):

        await self.bot.wait_until_ready()

        script_data = load_scripts_data()

        if (
            not script_data
            or
            self.TARGET_CHANNEL_ID == 0
        ):

            return

        channel = self.bot.get_channel(
            self.TARGET_CHANNEL_ID
        )

        if (
            channel
            and
            hasattr(channel, 'send')
        ):

            try:

                chosen_script = random.choice(
                    script_data
                )

                script_embed = await create_script_embed(
                    chosen_script
                )

                view = ScriptCopyView(
                    chosen_script['script_code'],
                    chosen_script.get(
                        'title',
                        'Script'
                    )
                )

                await channel.send(
                    embed=script_embed,
                    view=view
                )

            except Exception as e:

                print(
                    f"Random post error: {e}"
                )

    # ========================================================
    # START EXTENSION TASK
    # ========================================================

    async def cog_load(self):

        if not self.post_random_script.is_running():

            self.post_random_script.start()

        print(
            "✅ Fime Library system loaded."
        )

    # ========================================================
    # UNLOAD EXTENSION
    # ========================================================

    async def cog_unload(self):

        if self.post_random_script.is_running():

            self.post_random_script.cancel()

        # إيقاف حلقات النشر اليدوية

        self.active_loops.clear()

        print(
            "⛔ Fime Library system unloaded."
        )


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(bot):

    await bot.add_cog(
        FimeLibrary(bot)
    )

    print(
        "✅ تم تحميل fime_libary.py بنجاح داخل البوت الرئيسي."
    )