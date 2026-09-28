import discord
from discord.ext import commands
import aiohttp
from urllib.parse import urlparse, parse_qs

# المتغيرات الأساسية (يمكنك ربطها بملف التكوين أو ملف التشغيل الرئيسي)
ENDPOINT = "http://45.90.13.151:6041"
MADE_BY = "wmnd"  # ضع اسم المبرمج هنا أو استدعِه من bot.py

class BypassCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # أمر /bypass
    @discord.app_commands.command(name="bypass", description="Bypass Links You Enter")
    @discord.app_commands.describe(link="The link")
    async def bypass(self, interaction: discord.Interaction, link: str):
        box = "```"
        
        # التحقق من الروابط المدعومة
        if not (link.startswith("[https://gateway.platoboost.com/a/](https://gateway.platoboost.com/a/)") or
                link.startswith("[https://flux.li/android/external/start.php?HWID=](https://flux.li/android/external/start.php?HWID=)") or
                link.startswith("[https://linkvertise.com](https://linkvertise.com)")):
            
            embed = discord.Embed(
                title="Unsupported Link",
                color=0xFF3336
            )
            embed.add_field(name='Message:', value='```ml\nRun /supported To Get The List Of Supported Bypasses.\n```')
            embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
            await interaction.response.send_message(embed=embed)
            return

        # رسالة الانتظار
        embed_loading = discord.Embed(
            title="Bypassing..",
            color=0x59A53
        )
        embed_loading.add_field(name='Status', value='```Could Take A Few Seconds Depending On What Its Trying To Bypass```')
        embed_loading.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
        await interaction.response.send_message(embed=embed_loading)

        async with aiohttp.ClientSession() as session:
            # 1. معالجة رابط PlatoBoost
            if link.startswith('[https://gateway.platoboost.com/a/](https://gateway.platoboost.com/a/)'):
                parsed_url = urlparse(link)
                urlparam = parse_qs(parsed_url.query)
                hwid = urlparam.get('id', [None])[0]
                api_url = f"{ENDPOINT}/?url={link}"

                try:
                    async with session.get(api_url) as response:
                        json_data = await response.json()
                        status = json_data.get("status")

                        if status == "success":
                            embed = discord.Embed(title="PlatoBoost Bypass", color=0x6FD44)
                            embed.set_thumbnail(url='[https://gateway.platoboost.com/icon.svg](https://gateway.platoboost.com/icon.svg)')
                            embed.add_field(name='Key:', value=f"{box}{json_data.get('key')}{box}")
                            embed.add_field(name='HWID:', value=f"{box}yaml\n{hwid}\n{box}")
                            embed.add_field(name='Key Time Left:', value=f"{box}{json_data.get('timeleft')}{box}")
                            embed.add_field(name='Time Taken:', value=f"{box}{json_data.get('time')}{box}")
                        elif status == "fail" and json_data.get("message") == "Most Likely An Invalid PlatoBoost Link Or Un-Existing Author.":
                            embed = discord.Embed(title="Failed To Get PlatoBoost Key", color=0xFF3336)
                            embed.set_thumbnail(url='[https://gateway.platoboost.com/icon.svg](https://gateway.platoboost.com/icon.svg)')
                            embed.add_field(name='Message:', value='```ml\nMost Likely An Invalid PlatoBoost Link Or Un-Existing Author.\n```')
                        else:
                            embed = discord.Embed(title="PlatoBoost Error", color=0xFF3336)
                            embed.set_thumbnail(url='[https://gateway.platoboost.com/icon.svg](https://gateway.platoboost.com/icon.svg)')
                            embed.add_field(name='Message:', value='```ml\nEither Hwid Is Invalid Or Api Is Not Working.\n```')
                        
                        embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                        await interaction.edit_original_response(embed=embed)

                except Exception as e:
                    print(e)
                    embed = discord.Embed(title="PlatoBoost Error", color=0xFF3336)
                    embed.set_thumbnail(url='[https://media.discordapp.net/attachments/1160520088181542925/1199162006993895484/deltax.png](https://media.discordapp.net/attachments/1160520088181542925/1199162006993895484/deltax.png)')
                    embed.add_field(name='Message:', value='```ml\nEither Api Is Offline Or Not Responding.\n```')
                    embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                    await interaction.edit_original_response(embed=embed)

            # 2. معالجة رابط Fluxus
            elif link.startswith('[https://flux.li/android/external/start.php?HWID=](https://flux.li/android/external/start.php?HWID=)'):
                parsed_url = urlparse(link)
                url_params = parse_qs(parsed_url.query)
                hwid = url_params.get('HWID', [None])[0]
                api_url = f"{ENDPOINT}/?url={link}"

                try:
                    async with session.get(api_url) as response:
                        json_data = await response.json()
                        status = json_data.get("status")
                        flux_icon = '[https://media.discordapp.net/attachments/1205456615873052712/1239947639165026366/2558-fluxus.png](https://media.discordapp.net/attachments/1205456615873052712/1239947639165026366/2558-fluxus.png)'

                        if status == "success":
                            embed = discord.Embed(title="Fluxus Bypass", color=0x6FD44)
                            embed.set_thumbnail(url=flux_icon)
                            embed.add_field(name='Key:', value=f"{box}{json_data.get('key')}{box}")
                            embed.add_field(name='HWID:', value=f"{box}yaml\n{hwid}\n{box}")
                            embed.add_field(name='Time Taken:', value=f"{box}{json_data.get('time')}{box}")
                        else:
                            embed = discord.Embed(title="Fluxus Error", color=0xFF3336)
                            embed.set_thumbnail(url=flux_icon)
                            embed.add_field(name='Message:', value='```ml\nMost Likely An Invalid HWID/Fluxus Link Or Failed To Bypass. Please Try Again With A Valid Link.\n```')
                        
                        embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                        await interaction.edit_original_response(embed=embed)

                except Exception as e:
                    print(e)
                    embed = discord.Embed(title="Fluxus Error", color=0xFF3336)
                    embed.set_thumbnail(url='[https://media.discordapp.net/attachments/1205456615873052712/1239947639165026366/2558-fluxus.png](https://media.discordapp.net/attachments/1205456615873052712/1239947639165026366/2558-fluxus.png)')
                    embed.add_field(name='Message:', value='```ml\nEither Api Is Offline Or Not Responding.\n```')
                    embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                    await interaction.edit_original_response(embed=embed)

            # 3. معالجة رابط Linkvertise
            elif link.startswith('[https://linkvertise.com](https://linkvertise.com)'):
                api_url = f"{ENDPOINT}/?url={link}"

                try:
                    async with session.get(api_url) as response:
                        json_data = await response.json()
                        status = json_data.get("status")
                        link_icon = '[https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQDXWPxWgfrFsPT9M9NzG2PLeMg3nWE5LkAIw&s](https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQDXWPxWgfrFsPT9M9NzG2PLeMg3nWE5LkAIw&s)'

                        if status == "success":
                            embed = discord.Embed(title="Linkvertise Bypass", color=0x6FD44)
                            embed.set_thumbnail(url=link_icon)
                            embed.add_field(name='Direct URL:', value=f"{json_data.get('target')}")
                            embed.add_field(name='Time Taken:', value=f"{box}{json_data.get('time')}{box}")
                        elif status == "fail" and json_data.get("message") == "Invalid Linkvertise Link. Try Again With An Active/Working Linkvertise Link":
                            embed = discord.Embed(title="Linkvertise Error", color=0xFF3336)
                            embed.set_thumbnail(url=link_icon)
                            embed.add_field(name='Message:', value='```ml\nInvalid Linkvertise Link. Try Again With An Active/Working Linkvertise Link.\n```')
                        else:
                            embed = discord.Embed(title="Linkvertise Error", color=0xFF3336)
                            embed.set_thumbnail(url=link_icon)
                            embed.add_field(name='Message:', value='```ml\nMost Likely An Api Error. Try Again Later!\n```')
                        
                        embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                        await interaction.edit_original_response(embed=embed)

                except Exception as e:
                    print(e)
                    embed = discord.Embed(title="Linkvertise Error", color=0xFF3336)
                    embed.set_thumbnail(url='[https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQDXWPxWgfrFsPT9M9NzG2PLeMg3nWE5LkAIw&s](https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQDXWPxWgfrFsPT9M9NzG2PLeMg3nWE5LkAIw&s)')
                    embed.add_field(name='Message:', value='```ml\nEither Api Is Offline Or Not Responding.\n```')
                    embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
                    await interaction.edit_original_response(embed=embed)

    # أمر /supported
    @discord.app_commands.command(name="supported", description="Gets Supported List")
    async def supported(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Supported Bypasses", color=0x3498DB, timestamp=discord.utils.utcnow())
        embed.add_field(name='Supported Links:', value='```md\n1. [PlatoBoost](https://gateway.platoboost.com/a/)\n2. [Fluxus](https://flux.li/android/external/start.php?HWID=)\n3. [Linkvertise](https://linkvertise.com)\n```')
        embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
        await interaction.response.send_message(embed=embed)

    # أمر /apistatus
    @discord.app_commands.command(name="apistatus", description="Gets The Api Status")
    async def apistatus(self, interaction: discord.Interaction):
        status_url = f"{ENDPOINT}/status"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(status_url) as response:
                    data = await response.json()

                    if data.get("status") == 'online':
                        embed = discord.Embed(title="API Status", color=0x2ECC71, timestamp=discord.utils.utcnow())
                        embed.add_field(name='Ping:', value=f"`{data.get('ping')} ms`", inline=True)
                        embed.add_field(name='Uptime:', value=`{data.get('uptime')}` if False else f"`{data.get('uptime')}`", inline=True)
                    else:
                        embed = discord.Embed(title="API Status", color=0xE74C3C)
                        embed.add_field(name='Status:', value='The API is currently offline.')
            except Exception as e:
                print(e)
                embed = discord.Embed(title="API Status", color=0xE74C3C)
                embed.add_field(name='Message:', value='Failed to retrieve the API status.')

            embed.set_footer(text=f"Requested By {interaction.user.name} | Made by {MADE_BY} | Powered By Bypassi")
            await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(BypassCog(bot))
    