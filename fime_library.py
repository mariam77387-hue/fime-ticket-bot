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
    async def copy_full_button(self, interaction: discord.Interaction, button: ui.Button):
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
    async def copy_loadstring_button(self, interaction: discord.Interaction, button: ui.Button):
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
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            title = self.script_title or "Script"

            await interaction.followup.send(
                f"✅ **تم حفظ السكربت: {title}**\n\n```lua\n{self.script_to_copy[:500]}...\n```",
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
        f"**مـوثوقية** {'✅ موثوقة' if data['is_safe'] else '❌ غير موثوقة'}\n"
        f"**مشـاهدات** 👀 {data['views']}\n"
        f"**يحتاج مفتاح** 🔑 {'❌ لا' if data['is_keyless'] else '✅ نعم'}\n\n"
        f"**مصـحح** {'✅ مصحح' if data['is_safe'] else '❌ غير مصحح'}\n"
        f"**السكربت (معاينة)** ⚙️\n"
        f"```lua\n{data['script_code'][:70]}...\n```\n"
        f"by {data['author']}"
    )

    embed = discord.Embed(
        title=data['title'],
        description=description,
        color=discord.Color.green()
    )

    embed.set_image(url=data['image_url'])

    return embed


# ============================================================
# BOT CONFIG
# ============================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None
)

active_loops = {}

target_channel_env = os.getenv('TARGET_CHANNEL_ID', '0')

try:
    TARGET_CHANNEL_ID = int(target_channel_env)
except ValueError:
    TARGET_CHANNEL_ID = 0


# ============================================================
# AUTO SEARCH SYSTEM
# ============================================================
# روم البحث التلقائي.
# يتم تحديده من خلال /set_auto_search
# ============================================================

AUTO_SEARCH_CHANNELS_FILE = "auto_search_channels.json"

auto_search_channels = {}


def load_auto_search_channels():
    global auto_search_channels

    try:
        with open(AUTO_SEARCH_CHANNELS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

            if isinstance(data, dict):
                auto_search_channels = {
                    str(guild_id): int(channel_id)
                    for guild_id, channel_id in data.items()
                }
            else:
                auto_search_channels = {}

    except FileNotFoundError:
        auto_search_channels = {}

    except (json.JSONDecodeError, ValueError, TypeError):
        auto_search_channels = {}


def save_auto_search_channels():
    try:
        with open(AUTO_SEARCH_CHANNELS_FILE, "w", encoding="utf-8") as f:
            json.dump(
                auto_search_channels,
                f,
                ensure_ascii=False,
                indent=4
            )
    except Exception as e:
        print(f"ERROR saving auto search channels: {e}")


def normalize_search_text(text):
    """
    تحسين البحث العربي والإنجليزي.
    """

    text = str(text).lower().strip()

    # إزالة التشكيل العربي
    arabic_diacritics = "ًٌٍَُِّْـ"
    for char in arabic_diacritics:
        text = text.replace(char, "")

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
        text = text.replace(old, new)

    # توحيد المسافات
    text = " ".join(text.split())

    return text


def script_matches_query(script, query):
    """
    يبحث في:
    - اسم الماب
    - عنوان السكربت
    """

    query = normalize_search_text(query)

    if not query:
        return False

    map_name = normalize_search_text(
        script.get("map", "")
    )

    title = normalize_search_text(
        script.get("title", "")
    )

    return query in map_name or query in title


async def send_auto_search_result(channel, query):
    script_data = load_scripts_data()

    if not script_data:
        await channel.send(
            "❌ ما فيه سكربتات متاحة حاليًا."
        )
        return

    matching_scripts = [
        script
        for script in script_data
        if script_matches_query(script, query)
    ]

    if not matching_scripts:
        await channel.send(
            f"❌ ما لقيت سكربت للماب: **{query}**"
        )
        return

    # إذا فيه أكثر من نتيجة نختار واحدة
    chosen_script = random.choice(matching_scripts)

    script_embed = await create_script_embed(chosen_script)

    view = ScriptCopyView(
        chosen_script['script_code'],
        chosen_script.get('title', 'Script')
    )

    await channel.send(
        content=f"🔎 لقيت **{len(matching_scripts)}** نتيجة لـ **{query}**",
        embed=script_embed,
        view=view
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as: {bot.user}')

    load_auto_search_channels()

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    if not post_random_script.is_running():
        post_random_script.start()


# ============================================================
# AUTO SEARCH MESSAGE LISTENER
# ============================================================

@bot.event
async def on_message(message):

    # تجاهل رسائل البوتات
    if message.author.bot:
        return

    # تشغيل أوامر البوت العادية
    await bot.process_commands(message)

    # التأكد أن الرسالة داخل سيرفر
    if not message.guild:
        return

    guild_id = str(message.guild.id)

    # هل يوجد روم بحث محدد لهذا السيرفر؟
    target_auto_search_channel = auto_search_channels.get(guild_id)

    if not target_auto_search_channel:
        return

    # هل الرسالة في روم البحث؟
    if message.channel.id != target_auto_search_channel:
        return

    query = message.content.strip()

    # تجاهل الرسائل الفارغة
    if not query:
        return

    # تجاهل الأوامر
    if query.startswith(("/", "!")):
        return

    # منع البحث عن رسائل طويلة جدًا
    if len(query) > 100:
        return

    try:
        await send_auto_search_result(
            message.channel,
            query
        )
    except Exception as e:
        print(f"Auto search error: {e}")


# ============================================================
# SET AUTO SEARCH CHANNEL
# ============================================================

@bot.tree.command(
    name="set_auto_search",
    description="تحديد روم البحث التلقائي"
)
@app_commands.describe(
    channel="الروم الذي سيتم فيه البحث التلقائي"
)
@app_commands.checks.has_permissions(administrator=True)
async def set_auto_search(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    guild_id = str(interaction.guild.id)

    auto_search_channels[guild_id] = channel.id

    save_auto_search_channels()

    await interaction.response.send_message(
        f"✅ تم تحديد روم البحث التلقائي إلى {channel.mention}\n\n"
        f"من الآن أي عضو يكتب اسم الماب داخل الروم، "
        f"البوت يبحث عنه تلقائيًا.",
        ephemeral=True
    )


# ============================================================
# SHOW AUTO SEARCH CHANNEL
# ============================================================

@bot.tree.command(
    name="auto_search_room",
    description="معرفة روم البحث التلقائي الحالي"
)
async def auto_search_room(
    interaction: discord.Interaction
):

    guild_id = str(interaction.guild.id)

    channel_id = auto_search_channels.get(guild_id)

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

    await interaction.response.send_message(
        f"🔎 روم البحث التلقائي الحالي: {channel.mention}",
        ephemeral=True
    )


# ============================================================
# DISABLE AUTO SEARCH
# ============================================================

@bot.tree.command(
    name="disable_auto_search",
    description="إيقاف البحث التلقائي"
)
@app_commands.checks.has_permissions(administrator=True)
async def disable_auto_search(
    interaction: discord.Interaction
):

    guild_id = str(interaction.guild.id)

    if guild_id not in auto_search_channels:
        return await interaction.response.send_message(
            "❌ البحث التلقائي غير مفعل.",
            ephemeral=True
        )

    del auto_search_channels[guild_id]

    save_auto_search_channels()

    await interaction.response.send_message(
        "⛔ تم إيقاف البحث التلقائي.",
        ephemeral=True
    )


# ============================================================
# RANDOM SCRIPT
# ============================================================

@bot.tree.command(
    name="script",
    description="احصل على سكربت عشوائي"
)
async def slash_random_script(
    interaction: discord.Interaction
):

    script_data = load_scripts_data()

    if not script_data:
        return await interaction.response.send_message(
            "لا توجد سكربتات متاحة حاليًا."
        )

    chosen_script = random.choice(script_data)

    script_embed = await create_script_embed(
        chosen_script
    )

    view = ScriptCopyView(
        chosen_script['script_code'],
        chosen_script.get('title', 'Script')
    )

    await interaction.response.send_message(
        embed=script_embed,
        view=view
    )


# ============================================================
# MANUAL SEARCH
# ============================================================

@bot.tree.command(
    name="search",
    description="ابحث عن سكربت باسم الماب أو اللعبة"
)
async def search_scripts(
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
        if script_matches_query(script, query)
    ]

    if not matching_scripts:
        return await interaction.response.send_message(
            f"❌ لم يتم العثور على سكربتات تتطابق مع: **{query}**",
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
        chosen_script.get('title', 'Script')
    )

    await interaction.response.send_message(
        f"✅ عثرت على **{len(matching_scripts)}** سكربت يتطابق مع '{query}'\n",
        embed=script_embed,
        view=view
    )


# ============================================================
# START POSTING
# ============================================================

@bot.tree.command(
    name="start_posting",
    description="ابدأ النشر التلقائي للسكربتات كل 10 دقائق"
)
async def start_posting(
    interaction: discord.Interaction
):

    if post_random_script.is_running():
        return await interaction.response.send_message(
            "النشر التلقائي يعمل بالفعل! ✅",
            ephemeral=True
        )

    post_random_script.start()

    await interaction.response.send_message(
        "تم بدء النشر التلقائي! ✅\n"
        "سيتم نشر سكربت كل 10 دقائق 🎉",
        ephemeral=True
    )


# ============================================================
# STOP POSTING
# ============================================================

@bot.tree.command(
    name="stop_posting",
    description="أوقف النشر التلقائي"
)
async def stop_posting(
    interaction: discord.Interaction
):

    if not post_random_script.is_running():
        return await interaction.response.send_message(
            "النشر التلقائي متوقف بالفعل! ❌",
            ephemeral=True
        )

    post_random_script.stop()

    await interaction.response.send_message(
        "تم إيقاف النشر التلقائي! ⛔",
        ephemeral=True
    )


# ============================================================
# AUTO POST 5 MIN LOOP
# ============================================================

async def auto_post_5min_loop(channel_id):

    await bot.wait_until_ready()

    while True:

        try:

            if channel_id not in active_loops:
                break

            script_data = load_scripts_data()

            if not script_data:
                await asyncio.sleep(300)
                continue

            channel = bot.get_channel(channel_id)

            if not channel or not hasattr(channel, 'send'):
                break

            chosen_script = random.choice(
                script_data
            )

            script_embed = await create_script_embed(
                chosen_script
            )

            view = ScriptCopyView(
                chosen_script['script_code'],
                chosen_script.get('title', 'Script')
            )

            await channel.send(
                embed=script_embed,
                view=view
            )

            await asyncio.sleep(300)

        except Exception as e:
            print(f"Auto post error: {e}")
            await asyncio.sleep(300)


# ============================================================
# AUTO POST 5 MIN
# ============================================================

@bot.tree.command(
    name="auto_post_5min",
    description="نشر سكربت عشوائي كل 5 دقائق في قناة محددة"
)
async def auto_post_5min(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    channel_id = channel.id

    if channel_id in active_loops:
        return await interaction.response.send_message(
            f"النشر التلقائي يعمل بالفعل في قناة {channel.mention}! ✅",
            ephemeral=True
        )

    active_loops[channel_id] = True

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
                chosen_script.get('title', 'Script')
            )

            await channel.send(
                embed=script_embed,
                view=view
            )

    except Exception as e:
        print(f"Auto post initial error: {e}")

    asyncio.create_task(
        auto_post_5min_loop(channel_id)
    )

    await interaction.response.send_message(
        f"تم بدء النشر التلقائي كل 5 دقائق في {channel.mention}! 🎉",
        ephemeral=True
    )


# ============================================================
# STOP AUTO 5 MIN
# ============================================================

@bot.tree.command(
    name="stop_auto_5min",
    description="أوقف النشر التلقائي للسكربتات كل 5 دقائق"
)
async def stop_auto_5min(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):

    channel_id = channel.id

    if channel_id not in active_loops:
        return await interaction.response.send_message(
            f"النشر التلقائي غير مفعل في {channel.mention}! ❌",
            ephemeral=True
        )

    del active_loops[channel_id]

    await interaction.response.send_message(
        f"تم إيقاف النشر التلقائي في {channel.mention}! ⛔",
        ephemeral=True
    )


# ============================================================
# RANDOM SCRIPT EVERY 10 MIN
# ============================================================

@tasks.loop(minutes=10)
async def post_random_script():

    await bot.wait_until_ready()

    script_data = load_scripts_data()

    if not script_data or TARGET_CHANNEL_ID == 0:
        return

    channel = bot.get_channel(
        TARGET_CHANNEL_ID
    )

    if channel and hasattr(channel, 'send'):

        try:

            chosen_script = random.choice(
                script_data
            )

            script_embed = await create_script_embed(
                chosen_script
            )

            view = ScriptCopyView(
                chosen_script['script_code'],
                chosen_script.get('title', 'Script')
            )

            await channel.send(
                embed=script_embed,
                view=view
            )

        except Exception as e:
            print(f"Random post error: {e}")


# ============================================================
# TOKEN
# ============================================================

TOKEN = os.getenv('TOKEN')


# ============================================================
# BOT START
# ============================================================

# ملاحظة:
# هذا الملف يتم تحميله من bot.py
# لذلك لا يوجد bot.run(TOKEN) هنا.
# bot.py هو المسؤول عن تشغيل البوت الرئيسي.

