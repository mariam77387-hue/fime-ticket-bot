import discord
from discord.ext import commands, tasks
from discord import app_commands
import random
from discord import ui
import json
import os
import asyncio

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

class ScriptCopyView(ui.View):
    def __init__(self, script_to_copy, script_title=None):
        super().__init__(timeout=None) 
        self.script_to_copy = script_to_copy
        self.script_title = script_title

    @ui.button(label="📋 نسخ السكربت", style=discord.ButtonStyle.green)
    async def copy_full_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"✅ **تم نسخ السكربت بنجاح**\n\n```lua\n{self.script_to_copy}\n```", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ حدث خطأ: {str(e)}", ephemeral=True)
            except:
                pass

    @ui.button(label="🔗 نسخ رابط", style=discord.ButtonStyle.blurple)
    async def copy_loadstring_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"✅ **رابط التحميل:**\n\n```\n{self.script_to_copy}\n```", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {str(e)}", ephemeral=True)
            except:
                pass

    @ui.button(label="💾 حفظ", style=discord.ButtonStyle.grey)
    async def save_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            title = self.script_title or "Script"
            await interaction.followup.send(f"✅ **تم حفظ السكربت: {title}**\n\n```lua\n{self.script_to_copy[:500]}...\n```", ephemeral=True)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ خطأ: {str(e)}", ephemeral=True)
            except:
                pass

async def create_script_embed(data):
    description = (f"**الماب** 📌 {data['map']}\n"
        f"**مـوثوقية** {'✅ موثوقة' if data['is_safe'] else '❌ غير موثوقة'}\n"
        f"**مشـاهدات** 👀 {data['views']}\n"
        f"**يحتاج مفتاح** 🔑 {'❌ لا' if data['is_keyless'] else '✅ نعم'}\n\n"
        f"**مصـحح** {'✅ مصحح' if data['is_safe'] else '❌ غير مصحح'}\n"
        f"**السكربت (معاينة)** ⚙️\n"
        f"```lua\n{data['script_code'][:70]}...\n```\n"
        f"by {data['author']}")

    embed = discord.Embed(title=data['title'], description=description, color=discord.Color.green())
    embed.set_image(url=data['image_url'])
    return embed

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
active_loops = {}
target_channel_env = os.getenv('TARGET_CHANNEL_ID', '0')
try:
    TARGET_CHANNEL_ID = int(target_channel_env)
except ValueError:
    TARGET_CHANNEL_ID = 0

@bot.event
async def on_ready():
    print(f'Bot is ready. Logged in as: {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    if not post_random_script.is_running():
        post_random_script.start()

@bot.tree.command(name="script", description="احصل على سكربت عشوائي")
async def slash_random_script(interaction: discord.Interaction):
    script_data = load_scripts_data()
    if not script_data:
        return await interaction.response.send_message("لا توجد سكربتات متاحة حاليًا.")
    chosen_script = random.choice(script_data)
    script_embed = await create_script_embed(chosen_script)
    view = ScriptCopyView(chosen_script['script_code'], chosen_script.get('title', 'Script'))
    await interaction.response.send_message(embed=script_embed, view=view)

@bot.tree.command(name="search", description="ابحث عن سكربت باسم الماب أو اللعبة")
async def search_scripts(interaction: discord.Interaction, query: str):
    script_data = load_scripts_data()
    if not script_data:
        return await interaction.response.send_message("لا توجد سكربتات متاحة حاليًا.", ephemeral=True)
    matching_scripts = [script for script in script_data if query.lower() in script.get('map', '').lower() or query.lower() in script.get('title', '').lower()]
    if not matching_scripts:
        return await interaction.response.send_message(f"❌ لم يتم العثور على سكربتات تتطابق مع: **{query}**", ephemeral=True)
    chosen_script = random.choice(matching_scripts)
    script_embed = await create_script_embed(chosen_script)
    view = ScriptCopyView(chosen_script['script_code'], chosen_script.get('title', 'Script'))
    await interaction.response.send_message(f"✅ عثرت على **{len(matching_scripts)}** سكربت يتطابق مع '{query}'\n", embed=script_embed, view=view)

@bot.tree.command(name="start_posting", description="ابدأ النشر التلقائي للسكربتات كل 10 دقائق")
async def start_posting(interaction: discord.Interaction):
    if post_random_script.is_running():
        return await interaction.response.send_message("النشر التلقائي يعمل بالفعل! ✅", ephemeral=True)
    post_random_script.start()
    await interaction.response.send_message("تم بدء النشر التلقائي! ✅\nسيتم نشر سكربت كل 10 دقائق 🎉", ephemeral=True)

@bot.tree.command(name="stop_posting", description="أوقف النشر التلقائي")
async def stop_posting(interaction: discord.Interaction):
    if not post_random_script.is_running():
        return await interaction.response.send_message("النشر التلقائي متوقف بالفعل! ❌", ephemeral=True)
    post_random_script.stop()
    await interaction.response.send_message("تم إيقاف النشر التلقائي! ⛔", ephemeral=True)

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
            chosen_script = random.choice(script_data)
            script_embed = await create_script_embed(chosen_script)
            view = ScriptCopyView(chosen_script['script_code'], chosen_script.get('title', 'Script'))
            await channel.send(embed=script_embed, view=view)
            await asyncio.sleep(300)
        except Exception as e:
            await asyncio.sleep(300)

@bot.tree.command(name="auto_post_5min", description="نشر سكربت عشوائي كل 5 دقائق في قناة محددة")
async def auto_post_5min(interaction: discord.Interaction, channel: discord.TextChannel):
    channel_id = channel.id
    if channel_id in active_loops:
        return await interaction.response.send_message(f"النشر التلقائي يعمل بالفعل في قناة {channel.mention}! ✅", ephemeral=True)
    active_loops[channel_id] = True
    try:
        script_data = load_scripts_data()
        if script_data:
            chosen_script = random.choice(script_data)
            script_embed = await create_script_embed(chosen_script)
            view = ScriptCopyView(chosen_script['script_code'], chosen_script.get('title', 'Script'))
            await channel.send(embed=script_embed, view=view)
    except Exception as e:
        pass
    asyncio.create_task(auto_post_5min_loop(channel_id))
    await interaction.response.send_message(f"تم بدء النشر التلقائي كل 5 دقائق في {channel.mention}! 🎉", ephemeral=True)

@bot.tree.command(name="stop_auto_5min", description="أوقف النشر التلقائي للسكربتات كل 5 دقائق")
async def stop_auto_5min(interaction: discord.Interaction, channel: discord.TextChannel):
    channel_id = channel.id
    if channel_id not in active_loops:
        return await interaction.response.send_message(f"النشر التلقائي غير مفعل في {channel.mention}! ❌", ephemeral=True)
    del active_loops[channel_id]
    await interaction.response.send_message(f"تم إيقاف النشر التلقائي في {channel.mention}! ⛔", ephemeral=True)

@tasks.loop(minutes=10)
async def post_random_script():
    await bot.wait_until_ready()
    script_data = load_scripts_data()
    if not script_data or TARGET_CHANNEL_ID == 0:
        return
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if channel and hasattr(channel, 'send'):
        try:
            chosen_script = random.choice(script_data)
            script_embed = await create_script_embed(chosen_script)
            view = ScriptCopyView(chosen_script['script_code'], chosen_script.get('title', 'Script'))
            await channel.send(embed=script_embed, view=view)
        except Exception as e:
            pass

BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if __name__ == '__main__':
    if not BOT_TOKEN:
        print("ERROR: DISCORD_BOT_TOKEN environment variable is not set!")
    else:
        bot.run(BOT_TOKEN)
