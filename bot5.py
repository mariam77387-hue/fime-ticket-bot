# ============================================================
# Team Fime
# bot5.py
# Automatic Divider / Line Image System
# +
# Temporary Join Mention System
# +
# Fime Keyword Response System
# +
# GIF Support
# +
# TOP SYSTEM — DAY / WEEK / MONTH / ALL
# +
# SAY SYSTEM — BOT SPEAK + PROFILE MENU + AVATAR/BANNER/TEMPLATE
# ============================================================

from __future__ import annotations

import os
import io
import json
import asyncio
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone, timedelta
from textwrap import wrap

import discord
from discord.ext import commands
from discord import app_commands

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# دعم تشكيل العربية إذا كانت المكتبات موجودة
try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    ARABIC_SUPPORT = True
except Exception:
    ARABIC_SUPPORT = False


# ============================================================
# CONFIG
# ============================================================

OWNER_ID = 1388514481444880549

CONFIG_FILE = Path("bot5_config.json")
TOP_FILE = Path("bot5_top.json")

SAUDI_TZ = timezone(timedelta(hours=3))

DEFAULT_GUILD_CONFIG = {
    # ========================================================
    # LINE SYSTEM
    # ========================================================

    "enabled": False,
    "channel_id": None,
    "image_url": None,
    "storage_channel_id": None,
    "storage_message_id": None,
    "delete_after": 0,

    # ========================================================
    # JOIN MENTION SYSTEM
    # ========================================================

    "join_mention_enabled": False,
    "join_mention_channel_id": None,
    "join_mention_duration": 2,

    # ========================================================
    # FIME KEYWORD SYSTEM
    # ========================================================

    "fime_word_enabled": True,
    "fime_word_response": "هلا؟ وش تبي يا فايم؟",
    "fime_word_accept_fimi": False,

    # ========================================================
    # TOP COMMAND SYSTEM
    # ========================================================

    "top_channel_id": None,
    "top_allowed_role_ids": [],
}


# ============================================================
# JSON — CONFIG
# ============================================================

def load_config():
    try:
        if not CONFIG_FILE.exists():
            return {}

        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:
        print("❌ bot5 config load error:", error)
        return {}


def save_config(data):
    temp_file = CONFIG_FILE.with_suffix(".tmp")

    try:
        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, CONFIG_FILE)

    except Exception as error:
        print("❌ bot5 config save error:", error)

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass


# ============================================================
# JSON — TOP
# ============================================================

def load_top():
    try:
        if not TOP_FILE.exists():
            return {}

        with TOP_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:
        print("❌ bot5 top load error:", error)
        return {}


def save_top(data):
    temp_file = TOP_FILE.with_suffix(".tmp")

    try:
        with temp_file.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, TOP_FILE)

    except Exception as error:
        print("❌ bot5 top save error:", error)

        try:
            if temp_file.exists():
                temp_file.unlink()
        except Exception:
            pass


# ============================================================
# TOP SELECT MENU
# ============================================================

class TopSelect(discord.ui.Select):

    def __init__(self, cog, guild_id):

        self.cog = cog
        self.guild_id = guild_id

        options = [
            discord.SelectOption(
                label="توب اليوم",
                value="day",
                emoji="📅",
                description="عرض أكثر الأعضاء نشاطًا اليوم"
            ),
            discord.SelectOption(
                label="توب الأسبوع",
                value="week",
                emoji="📊",
                description="عرض أكثر الأعضاء نشاطًا هذا الأسبوع"
            ),
            discord.SelectOption(
                label="توب الشهر",
                value="month",
                emoji="🗓️",
                description="عرض أكثر الأعضاء نشاطًا هذا الشهر"
            ),
            discord.SelectOption(
                label="توب الكل",
                value="all",
                emoji="🏆",
                description="عرض التوب الكامل منذ بداية النظام"
            ),
        ]

        super().__init__(
            placeholder="اختر نوع التوب...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_top_select_{guild_id}"
        )

    async def callback(self, interaction: discord.Interaction):

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ هذا الخيار يعمل داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        period = self.values[0]

        embed = self.cog.build_top_embed(
            interaction.guild,
            period
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self.view
        )


class TopSelectView(discord.ui.View):

    def __init__(self, cog, guild_id):

        super().__init__(timeout=900)

        self.add_item(
            TopSelect(
                cog,
                guild_id
            )
        )


# ============================================================
# SAY PROFILE SELECT
# ============================================================

class SayProfileSelect(discord.ui.Select):

    def __init__(
        self,
        cog,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None,
        room_definition=None
    ):

        self.cog = cog
        self.avatar_bytes = avatar_bytes
        self.banner_bytes = banner_bytes
        self.full_profile_bytes = full_profile_bytes
        self.room_definition = room_definition

        options = [
            discord.SelectOption(
                label="الافتار",
                value="avatar",
                emoji="🖼️",
                description="إرسال الافتار كصورة"
            ),
            discord.SelectOption(
                label="البنر",
                value="banner",
                emoji="🎨",
                description="إرسال البنر كصورة"
            ),
            discord.SelectOption(
                label="البروفايل كامل",
                value="profile",
                emoji="👤",
                description="إرسال بطاقة البروفايل كاملة"
            ),
        ]

        if room_definition:
            options.append(
                discord.SelectOption(
                    label="تعريف الروم",
                    value="room",
                    emoji="📖",
                    description="عرض تعريف الروم"
                )
            )

        super().__init__(
            placeholder="اختر من القائمة...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_say_profile_{id(self)}"
        )

    async def callback(self, interaction: discord.Interaction):

        choice = self.values[0]

        if choice == "avatar":

            if not self.avatar_bytes:
                await interaction.response.send_message(
                    "❌ ما تم تحديد افتار في هذا الأمر.",
                    ephemeral=True
                )
                return

            file = discord.File(
                io.BytesIO(self.avatar_bytes),
                filename="fime-avatar.png"
            )

            await interaction.response.send_message(
                "🖼️ **الافتار**",
                file=file,
                ephemeral=True
            )

        elif choice == "banner":

            if not self.banner_bytes:
                await interaction.response.send_message(
                    "❌ ما تم تحديد بنر في هذا الأمر.",
                    ephemeral=True
                )
                return

            file = discord.File(
                io.BytesIO(self.banner_bytes),
                filename="fime-banner.png"
            )

            await interaction.response.send_message(
                "🎨 **البنر**",
                file=file,
                ephemeral=True
            )

        elif choice == "profile":

            if not self.full_profile_bytes:
                await interaction.response.send_message(
                    "❌ تعذر تجهيز البروفايل الكامل.",
                    ephemeral=True
                )
                return

            file = discord.File(
                io.BytesIO(self.full_profile_bytes),
                filename="fime-profile.png"
            )

            await interaction.response.send_message(
                "👤 **البروفايل كامل**",
                file=file,
                ephemeral=True
            )

        elif choice == "room":

            if not self.room_definition:
                await interaction.response.send_message(
                    "❌ ما تم إضافة تعريف لهذا الروم.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title="📖 تعريف الروم",
                description=self.room_definition,
                color=discord.Color.blurple()
            )

            embed.set_footer(
                text="Team Fime • Room Information"
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )


class SayProfileView(discord.ui.View):

    def __init__(
        self,
        cog,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None,
        room_definition=None
    ):

        super().__init__(timeout=1800)

        self.add_item(
            SayProfileSelect(
                cog=cog,
                avatar_bytes=avatar_bytes,
                banner_bytes=banner_bytes,
                full_profile_bytes=full_profile_bytes,
                room_definition=room_definition
            )
        )


# ============================================================
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.config = load_config()
        self.top_data = load_top()

        print(
            "✅ bot5 — Automatic Line + Join Mention + "
            "Fime Keyword + GIF + TOP + SAY loaded."
        )


    # ========================================================
    # CONFIG HELPERS
    # ========================================================

    def get_config(self, guild_id):

        key = str(guild_id)

        if key not in self.config:

            self.config[key] = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

            save_config(self.config)

        current = self.config[key]

        if not isinstance(current, dict):

            current = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

            self.config[key] = current

        changed = False

        for name, default in DEFAULT_GUILD_CONFIG.items():

            if name not in current:

                current[name] = deepcopy(default)
                changed = True

        if not isinstance(
            current.get("top_allowed_role_ids"),
            list
        ):

            current["top_allowed_role_ids"] = []
            changed = True

        if changed:
            save_config(self.config)

        return current


    # ========================================================
    # OWNER CHECK
    # ========================================================

    def is_owner(self, interaction):

        return interaction.user.id == OWNER_ID


    async def silently_ignore_if_not_owner(self, interaction):

        if self.is_owner(interaction):
            return False

        return True


    # ========================================================
    # IMAGE VALIDATION
    # ========================================================

    def is_supported_image(self, attachment):

        content_type = (
            attachment.content_type or ""
        ).lower().split(";")[0].strip()

        filename = (
            attachment.filename or ""
        ).lower().strip()

        supported_types = {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "image/gif",
            "image/apng"
        }

        supported_extensions = (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            ".apng"
        )

        return (
            content_type in supported_types
            or filename.endswith(
                supported_extensions
            )
        )


    # ========================================================
    # STORAGE FILENAME
    # ========================================================

    def get_storage_filename(self, attachment):

        original_name = (
            attachment.filename or ""
        ).strip()

        lower_name = original_name.lower()

        if lower_name.endswith(".gif"):
            return "fime-line.gif"

        if lower_name.endswith(".apng"):
            return "fime-line.apng"

        if lower_name.endswith(".webp"):
            return "fime-line.webp"

        if lower_name.endswith(".jpg"):
            return "fime-line.jpg"

        if lower_name.endswith(".jpeg"):
            return "fime-line.jpeg"

        return "fime-line.png"


    # ========================================================
    # STORAGE MESSAGE
    # ========================================================

    async def create_storage_copy(
        self,
        guild,
        image_attachment
    ):

        cfg = self.get_config(guild.id)

        storage_channel = None

        if cfg.get("storage_channel_id"):

            storage_channel = guild.get_channel(
                int(cfg["storage_channel_id"])
            )

        if storage_channel is None:

            configured_channel_id = cfg.get(
                "channel_id"
            )

            if configured_channel_id:

                storage_channel = guild.get_channel(
                    int(configured_channel_id)
                )

        if storage_channel is None:
            storage_channel = guild.system_channel

        if storage_channel is None:

            storage_channel = next(
                (
                    channel
                    for channel in guild.text_channels
                    if channel.permissions_for(
                        guild.me
                    ).send_messages
                ),
                None
            )

        if storage_channel is None:

            raise RuntimeError(
                "لم أجد روم أقدر أرسل فيه نسخة التخزين."
            )

        me = guild.me

        if me is None:

            raise RuntimeError(
                "تعذر معرفة صلاحيات البوت."
            )

        permissions = storage_channel.permissions_for(me)

        if not permissions.view_channel:

            raise RuntimeError(
                f"البوت لا يستطيع رؤية "
                f"{storage_channel.mention}."
            )

        if not permissions.send_messages:

            raise RuntimeError(
                f"البوت لا يستطيع الإرسال في "
                f"{storage_channel.mention}."
            )

        if not permissions.attach_files:

            raise RuntimeError(
                f"البوت يحتاج صلاحية Attach Files "
                f"في {storage_channel.mention}."
            )

        image_bytes = await image_attachment.read()

        if not image_bytes:

            raise RuntimeError(
                "الصورة المرفوعة فارغة."
            )

        storage_filename = self.get_storage_filename(
            image_attachment
        )

        file = discord.File(
            fp=io.BytesIO(image_bytes),
            filename=storage_filename
        )

        message = await storage_channel.send(
            "🖼️ **Fime Line Image Storage**",
            file=file
        )

        if not message.attachments:

            raise RuntimeError(
                "تعذر الحصول على رابط صورة التخزين."
            )

        stored_attachment = message.attachments[0]

        cfg["image_url"] = stored_attachment.url
        cfg["storage_channel_id"] = storage_channel.id
        cfg["storage_message_id"] = message.id

        save_config(self.config)

        return (
            stored_attachment.url,
            storage_channel,
            message
        )


    # ========================================================
    # DELETE OLD STORAGE
    # ========================================================

    async def delete_old_storage(self, guild):

        cfg = self.get_config(guild.id)

        channel_id = cfg.get("storage_channel_id")
        message_id = cfg.get("storage_message_id")

        if not channel_id or not message_id:
            return

        channel = guild.get_channel(
            int(channel_id)
        )

        if channel is None:
            return

        try:

            message = await channel.fetch_message(
                int(message_id)
            )

            await message.delete()

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException
        ):
            pass


    # ========================================================
    # TOP SYSTEM
    # ========================================================

    def get_now(self):

        return datetime.now(SAUDI_TZ)


    def get_period_keys(self):

        now = self.get_now()

        if now.hour >= 22:
            daily_date = now.date()
        else:
            daily_date = (
                now.date()
                - timedelta(days=1)
            )

        daily_key = daily_date.isoformat()

        week_start = (
            now.date()
            - timedelta(
                days=(now.weekday() + 2) % 7
            )
        )

        weekly_key = week_start.isoformat()

        monthly_key = (
            f"{now.year}-{now.month:02d}"
        )

        return (
            daily_key,
            weekly_key,
            monthly_key
        )


    def ensure_top_guild(self, guild_id):

        guild_key = str(guild_id)

        if guild_key not in self.top_data:

            self.top_data[guild_key] = {
                "day": {},
                "week": {},
                "month": {},
                "all": {}
            }

        guild_data = self.top_data[guild_key]

        for period in (
            "day",
            "week",
            "month",
            "all"
        ):

            if period not in guild_data:
                guild_data[period] = {}

        return guild_data


    def add_top_point(self, guild_id, user_id):

        guild_data = self.ensure_top_guild(
            guild_id
        )

        daily_key, weekly_key, monthly_key = (
            self.get_period_keys()
        )

        guild_data["day"].setdefault(
            "_period",
            daily_key
        )

        guild_data["week"].setdefault(
            "_period",
            weekly_key
        )

        guild_data["month"].setdefault(
            "_period",
            monthly_key
        )

        if guild_data["day"].get("_period") != daily_key:

            guild_data["day"] = {
                "_period": daily_key
            }

        if guild_data["week"].get("_period") != weekly_key:

            guild_data["week"] = {
                "_period": weekly_key
            }

        if guild_data["month"].get("_period") != monthly_key:

            guild_data["month"] = {
                "_period": monthly_key
            }

        user_key = str(user_id)

        guild_data["day"][user_key] = (
            guild_data["day"].get(user_key, 0) + 1
        )

        guild_data["week"][user_key] = (
            guild_data["week"].get(user_key, 0) + 1
        )

        guild_data["month"][user_key] = (
            guild_data["month"].get(user_key, 0) + 1
        )

        guild_data["all"][user_key] = (
            guild_data["all"].get(user_key, 0) + 1
        )

        save_top(self.top_data)


    def get_top_users(
        self,
        guild,
        period,
        limit=10
    ):

        guild_data = self.ensure_top_guild(
            guild.id
        )

        if period == "day":

            daily_key, _, _ = self.get_period_keys()

            if guild_data["day"].get("_period") != daily_key:

                guild_data["day"] = {
                    "_period": daily_key
                }

                save_top(self.top_data)

            source = guild_data["day"]

        elif period == "week":

            _, weekly_key, _ = self.get_period_keys()

            if guild_data["week"].get("_period") != weekly_key:

                guild_data["week"] = {
                    "_period": weekly_key
                }

                save_top(self.top_data)

            source = guild_data["week"]

        elif period == "month":

            _, _, monthly_key = self.get_period_keys()

            if guild_data["month"].get("_period") != monthly_key:

                guild_data["month"] = {
                    "_period": monthly_key
                }

                save_top(self.top_data)

            source = guild_data["month"]

        else:

            source = guild_data["all"]

        results = []

        for user_id, points in source.items():

            if user_id == "_period":
                continue

            try:
                member = guild.get_member(int(user_id))
            except Exception:
                member = None

            if member is None:
                continue

            results.append(
                (
                    member,
                    int(points)
                )
            )

        results.sort(
            key=lambda item: item[1],
            reverse=True
        )

        return results[:limit]


    def get_period_title(self, period):

        if period == "day":
            return "توب اليوم"

        if period == "week":
            return "توب الأسبوع"

        if period == "month":
            return "توب الشهر"

        return "توب الكل"


    def build_top_embed(self, guild, period):

        results = self.get_top_users(
            guild,
            period
        )

        title = self.get_period_title(
            period
        )

        if not results:

            return discord.Embed(
                title=f"🏆 {title}",
                description="ما فيه بيانات كافية للحين.",
                color=discord.Color.blurple()
            )

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉"
        }

        lines = []

        for index, (member, points) in enumerate(
            results,
            start=1
        ):

            medal = medals.get(
                index,
                f"`#{index}`"
            )

            lines.append(
                f"{medal} {member.mention} — **{points} نقطة**"
            )

        embed = discord.Embed(
            title=f"🏆 {title}",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Team Fime • Top System"
        )

        return embed


    async def send_top_to_channel(
        self,
        channel,
        period
    ):

        guild = channel.guild

        embed = self.build_top_embed(
            guild,
            period
        )

        view = TopSelectView(
            self,
            guild.id
        )

        await channel.send(
            embed=embed,
            view=view
        )


    def normalize_top_keyword(self, content):

        value = str(content or "").strip()

        value = " ".join(
            value.split()
        )

        return value.casefold()


    def get_top_keyword_period(self, content):

        normalized = self.normalize_top_keyword(
            content
        )

        keywords = {
            "day": "day",
            "week": "week",
            "month": "month",
            "all": "all",
        }

        return keywords.get(normalized)


    def member_can_use_top_keyword(
        self,
        message,
        cfg
    ):

        if message.author.id == OWNER_ID:
            return True

        allowed_roles = cfg.get(
            "top_allowed_role_ids",
            []
        )

        try:

            allowed_roles = {
                int(role_id)
                for role_id in allowed_roles
            }

        except Exception:

            allowed_roles = set()

        member_roles = {
            role.id
            for role in getattr(
                message.author,
                "roles",
                []
            )
        }

        if allowed_roles.intersection(
            member_roles
        ):
            return True

        top_channel_id = cfg.get(
            "top_channel_id"
        )

        if top_channel_id:

            try:

                return (
                    message.channel.id
                    == int(top_channel_id)
                )

            except Exception:

                return False

        return False


    async def handle_top_keyword(
        self,
        message,
        cfg
    ):

        period = self.get_top_keyword_period(
            message.content
        )

        if period is None:
            return False

        if not self.member_can_use_top_keyword(
            message,
            cfg
        ):
            return False

        try:

            await self.send_top_to_channel(
                message.channel,
                period
            )

        except Exception as error:

            print(
                "❌ bot5 TOP error:",
                error
            )

        return True


    # ========================================================
    # TOP ADMIN CONFIG
    # ========================================================

    @app_commands.command(
        name="توب-روم",
        description="تحديد روم أوامر التوب"
    )
    @app_commands.describe(
        channel="الروم الذي يستطيع الجميع استخدام كلمات التوب فيه"
    )
    async def top_channel(
        self,
        interaction,
        channel: discord.TextChannel = None
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if channel is None:

            cfg["top_channel_id"] = None
            save_config(self.config)

            await interaction.response.send_message(
                (
                    "✅ تم إلغاء تحديد روم التوب.\n"
                    "الآن فقط الرتب المسموح لها تستطيع "
                    "استخدام `day` و `week` و `month` و `all`."
                ),
                ephemeral=True
            )

            return

        me = interaction.guild.me

        if me is None:

            await interaction.response.send_message(
                "❌ تعذر معرفة صلاحيات البوت.",
                ephemeral=True
            )

            return

        permissions = channel.permissions_for(me)

        if not permissions.view_channel:

            await interaction.response.send_message(
                f"❌ ما أقدر أشوف {channel.mention}.",
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                f"❌ ما أقدر أرسل في {channel.mention}.",
                ephemeral=True
            )

            return

        cfg["top_channel_id"] = channel.id

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ **تم تحديد روم التوب.**\n\n"
                f"📍 الروم: {channel.mention}\n"
                "أي عضو يستطيع كتابة `day` أو `week` "
                "أو `month` أو `all` داخل هذا الروم."
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="توب-رتبة",
        description="إضافة رتبة تستطيع استخدام التوب في جميع الرومات"
    )
    @app_commands.describe(
        role="الرتبة المسموح لها"
    )
    async def top_role(
        self,
        interaction,
        role: discord.Role
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        roles = cfg.setdefault(
            "top_allowed_role_ids",
            []
        )

        if role.id in roles:

            await interaction.response.send_message(
                f"ℹ️ الرتبة {role.mention} مضافة مسبقًا.",
                ephemeral=True
            )

            return

        roles.append(role.id)

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ **تمت إضافة رتبة التوب.**\n\n"
                f"🎖️ الرتبة: {role.mention}\n"
                "أعضاء هذه الرتبة يستطيعون استخدام "
                "`day` و `week` و `month` و `all` "
                "في جميع الرومات."
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="توب-رتبة-إزالة",
        description="إزالة رتبة من صلاحية استخدام التوب في جميع الرومات"
    )
    @app_commands.describe(
        role="الرتبة التي تريد إزالتها"
    )
    async def top_role_remove(
        self,
        interaction,
        role: discord.Role
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        roles = cfg.setdefault(
            "top_allowed_role_ids",
            []
        )

        if role.id not in roles:

            await interaction.response.send_message(
                f"ℹ️ الرتبة {role.mention} ليست ضمن رتب التوب.",
                ephemeral=True
            )

            return

        roles.remove(role.id)

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم إزالة {role.mention} من رتب التوب.",
            ephemeral=True
        )


    @app_commands.command(
        name="توب-حالة",
        description="عرض إعدادات نظام التوب"
    )
    async def top_status(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        top_channel_id = cfg.get(
            "top_channel_id"
        )

        if top_channel_id:

            try:
                top_channel = interaction.guild.get_channel(
                    int(top_channel_id)
                )
            except Exception:
                top_channel = None

        else:
            top_channel = None

        roles = []

        for role_id in cfg.get(
            "top_allowed_role_ids",
            []
        ):

            try:
                role = interaction.guild.get_role(
                    int(role_id)
                )
            except Exception:
                role = None

            if role:
                roles.append(role.mention)

        channel_text = (
            top_channel.mention
            if top_channel
            else "غير محدد"
        )

        roles_text = (
            "\n".join(roles)
            if roles
            else "لا توجد رتب"
        )

        await interaction.response.send_message(
            (
                "## 🏆 حالة نظام التوب\n\n"
                f"📍 **روم التوب:** {channel_text}\n\n"
                "🎖️ **الرتب المسموح لها في كل الرومات:**\n"
                f"{roles_text}\n\n"
                "الكلمات:\n"
                "`day` — توب اليوم\n"
                "`week` — توب الأسبوع\n"
                "`month` — توب الشهر\n"
                "`all` — توب الكل"
            ),
            ephemeral=True
        )


    # ========================================================
    # /خط
    # ========================================================

    @app_commands.command(
        name="خط",
        description="إعداد صورة الخط التلقائي"
    )
    async def line_setup(
        self,
        interaction,
        image: discord.Attachment,
        channel: discord.TextChannel = None
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:

            await interaction.response.send_message(
                "هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        if not self.is_supported_image(image):

            await interaction.response.send_message(
                (
                    "❌ أرسل صورة بصيغة "
                    "`PNG` أو `JPG` أو `JPEG` أو "
                    "`WEBP` أو `GIF` أو `APNG`."
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        guild = interaction.guild

        cfg = self.get_config(guild.id)

        if channel is None:

            cfg["channel_id"] = None

        else:

            me = guild.me

            if me is None:

                await interaction.followup.send(
                    "❌ تعذر معرفة صلاحيات البوت.",
                    ephemeral=True
                )

                return

            permissions = channel.permissions_for(me)

            if not permissions.view_channel:

                await interaction.followup.send(
                    f"❌ ما أقدر أشوف {channel.mention}.",
                    ephemeral=True
                )

                return

            if not permissions.send_messages:

                await interaction.followup.send(
                    f"❌ ما أقدر أرسل في {channel.mention}.",
                    ephemeral=True
                )

                return

            cfg["channel_id"] = channel.id

        await self.delete_old_storage(guild)

        try:

            (
                image_url,
                storage_channel,
                storage_message
            ) = await self.create_storage_copy(
                guild,
                image
            )

        except Exception as error:

            print(
                "❌ bot5 image storage error:",
                error
            )

            await interaction.followup.send(
                (
                    "❌ ما قدرت أحفظ صورة الخط.\n"
                    f"السبب: `{type(error).__name__}`"
                ),
                ephemeral=True
            )

            return

        cfg["enabled"] = True

        save_config(self.config)

        target_text = (
            channel.mention
            if channel
            else "كل الرومات النصية التي يستطيع البوت الكتابة فيها"
        )

        await interaction.followup.send(
            (
                "✅ **تم تشغيل نظام الخط.**\n\n"
                f"🖼️ الصورة: تم حفظها\n"
                f"📍 النطاق: {target_text}\n"
                f"🗄️ التخزين: {storage_channel.mention}"
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="خط-إيقاف",
        description="إيقاف الخط التلقائي"
    )
    async def line_off(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["enabled"] = False

        save_config(self.config)

        await interaction.response.send_message(
            "🛑 تم إيقاف نظام الخط.",
            ephemeral=True
        )


    @app_commands.command(
        name="خط-حالة",
        description="عرض حالة نظام الخط"
    )
    async def line_status(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if not cfg.get("enabled"):

            await interaction.response.send_message(
                "🛑 نظام الخط متوقف.",
                ephemeral=True
            )

            return

        channel_id = cfg.get(
            "channel_id"
        )

        if channel_id:

            channel = interaction.guild.get_channel(
                int(channel_id)
            )

            target = (
                channel.mention
                if channel
                else "روم غير موجود"
            )

        else:

            target = (
                "كل الرومات النصية التي "
                "يستطيع البوت الكتابة فيها"
            )

        image_status = (
            "محفوظة"
            if cfg.get("image_url")
            else "غير موجودة"
        )

        await interaction.response.send_message(
            (
                "## 🖼️ حالة نظام الخط\n\n"
                "الحالة: **مفعل**\n"
                f"النطاق: {target}\n"
                f"الصورة: **{image_status}**"
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="خط-روم",
        description="تغيير نطاق الخط إلى روم محدد أو جميع الرومات"
    )
    async def line_channel(
        self,
        interaction,
        channel: discord.TextChannel = None
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if channel is None:

            cfg["channel_id"] = None

            save_config(self.config)

            await interaction.response.send_message(
                (
                    "✅ تم إلغاء تحديد روم معين.\n"
                    "الخط يعمل الآن في كل الرومات "
                    "التي يستطيع البوت الكتابة فيها."
                ),
                ephemeral=True
            )

            return

        me = interaction.guild.me

        if me is None:

            await interaction.response.send_message(
                "❌ تعذر معرفة صلاحيات البوت.",
                ephemeral=True
            )

            return

        permissions = channel.permissions_for(me)

        if not permissions.view_channel:

            await interaction.response.send_message(
                f"❌ ما أقدر أشوف {channel.mention}.",
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                f"❌ ما أقدر أرسل في {channel.mention}.",
                ephemeral=True
            )

            return

        cfg["channel_id"] = channel.id

        save_config(self.config)

        await interaction.response.send_message(
            (
                f"✅ صار الخط يعمل فقط في "
                f"{channel.mention}."
            ),
            ephemeral=True
        )


    # ========================================================
    # FIME KEYWORD SYSTEM
    # ========================================================

    def normalize_fime_keyword(self, content):

        value = str(content or "").strip()

        value = " ".join(
            value.split()
        )

        return value.casefold()


    def is_fime_keyword(
        self,
        content,
        accept_fimi=False
    ):

        normalized = self.normalize_fime_keyword(
            content
        )

        if normalized == "فيم":
            return True

        if accept_fimi and normalized == "فيمي":
            return True

        return False


    async def handle_fime_keyword(
        self,
        message,
        cfg
    ):

        if not cfg.get(
            "fime_word_enabled",
            True
        ):
            return False

        accept_fimi = bool(
            cfg.get(
                "fime_word_accept_fimi",
                False
            )
        )

        if not self.is_fime_keyword(
            message.content,
            accept_fimi
        ):
            return False

        response_text = str(
            cfg.get(
                "fime_word_response",
                ""
            ) or ""
        ).strip()

        if not response_text:
            return False

        try:

            await message.channel.send(
                response_text,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            print(
                "❌ bot5 Fime keyword error:",
                error
            )

        return True


    @app_commands.command(
        name="فيم-رسالة",
        description="تغيير الرسالة التي يرسلها البوت عند كتابة فيم"
    )
    @app_commands.describe(
        message="الرسالة التي تريد أن يرسلها البوت"
    )
    async def fime_message(
        self,
        interaction,
        message: str
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        message = str(message or "").strip()

        if not message:

            await interaction.response.send_message(
                "❌ اكتب الرسالة التي تريدها.",
                ephemeral=True
            )

            return

        if len(message) > 2000:

            await interaction.response.send_message(
                "❌ الرسالة لا يمكن أن تتجاوز 2000 حرف.",
                ephemeral=True
            )

            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["fime_word_response"] = message
        cfg["fime_word_enabled"] = True

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ **تم تغيير رسالة فيم.**\n\n"
                f"الرسالة الجديدة:\n{message}\n\n"
                "🟢 تم تشغيل النظام تلقائيًا."
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="فيم-تشغيل",
        description="تشغيل الرد التلقائي على كلمة فيم"
    )
    async def fime_enable(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["fime_word_enabled"] = True

        save_config(self.config)

        await interaction.response.send_message(
            "🟢 تم تشغيل نظام كلمة فيم.",
            ephemeral=True
        )


    @app_commands.command(
        name="فيم-إيقاف",
        description="إيقاف الرد التلقائي على كلمة فيم"
    )
    async def fime_disable(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["fime_word_enabled"] = False

        save_config(self.config)

        await interaction.response.send_message(
            "🛑 تم إيقاف نظام كلمة فيم.",
            ephemeral=True
        )


    @app_commands.command(
        name="فيم-حالة",
        description="عرض حالة نظام كلمة فيم"
    )
    async def fime_status(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        enabled = cfg.get(
            "fime_word_enabled",
            True
        )

        response_text = str(
            cfg.get(
                "fime_word_response",
                ""
            ) or ""
        ).strip()

        accept_fimi = cfg.get(
            "fime_word_accept_fimi",
            False
        )

        status = (
            "🟢 مفعل"
            if enabled
            else "🔴 متوقف"
        )

        fimi_status = (
            "🟢 نعم"
            if accept_fimi
            else "🔴 لا"
        )

        if not response_text:
            response_text = "غير محددة"

        await interaction.response.send_message(
            (
                "## 🌀 حالة نظام فيم\n\n"
                f"الحالة: **{status}**\n"
                f"كلمة **فيم**: تعمل\n"
                f"كلمة **فيمي**: {fimi_status}\n\n"
                "**الرسالة الحالية:**\n"
                f"{response_text}"
            ),
            ephemeral=True
        )


    # ========================================================
    # SAY IMAGE HELPERS
    # ========================================================

    def get_font(self, size, bold=False):

        candidates = []

        if bold:

            candidates.extend([
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            ])

        else:

            candidates.extend([
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            ])

        for path in candidates:

            try:
                if os.path.exists(path):
                    return ImageFont.truetype(
                        path,
                        size
                    )
            except Exception:
                pass

        return ImageFont.load_default()


    def prepare_text(self, text):

        text = str(text or "")

        if ARABIC_SUPPORT:

            try:
                reshaped = arabic_reshaper.reshape(text)
                return get_display(reshaped)
            except Exception:
                pass

        return text


    def crop_to_fill(self, image, size):

        target_width, target_height = size

        image = image.convert("RGBA")

        source_width, source_height = image.size

        if source_width <= 0 or source_height <= 0:

            return Image.new(
                "RGBA",
                size,
                (10, 12, 18, 255)
            )

        source_ratio = (
            source_width / source_height
        )

        target_ratio = (
            target_width / target_height
        )

        if source_ratio > target_ratio:

            new_height = target_height
            new_width = int(
                new_height * source_ratio
            )

        else:

            new_width = target_width
            new_height = int(
                new_width / source_ratio
            )

        image = image.resize(
            (
                new_width,
                new_height
            ),
            Image.Resampling.LANCZOS
        )

        left = (
            new_width - target_width
        ) // 2

        top = (
            new_height - target_height
        ) // 2

        return image.crop(
            (
                left,
                top,
                left + target_width,
                top + target_height
            )
        )


    def circle_avatar(self, image, size):

        image = self.crop_to_fill(
            image,
            (size, size)
        )

        mask = Image.new(
            "L",
            (size, size),
            0
        )

        draw = ImageDraw.Draw(mask)

        draw.ellipse(
            (
                0,
                0,
                size,
                size
            ),
            fill=255
        )

        result = Image.new(
            "RGBA",
            (size, size),
            (0, 0, 0, 0)
        )

        result.paste(
            image,
            (0, 0),
            mask
        )

        return result


    def draw_text_center(
        self,
        draw,
        center_x,
        y,
        text,
        font,
        fill
    ):

        bbox = draw.textbbox(
            (0, 0),
            text,
            font=font
        )

        width = bbox[2] - bbox[0]

        draw.text(
            (
                center_x - width / 2,
                y
            ),
            text,
            font=font,
            fill=fill
        )


    def wrap_text(
        self,
        draw,
        text,
        font,
        max_width
    ):

        words = text.split()

        if not words:
            return []

        lines = []
        current = ""

        for word in words:

            candidate = (
                f"{current} {word}".strip()
            )

            bbox = draw.textbbox(
                (0, 0),
                candidate,
                font=font
            )

            width = bbox[2] - bbox[0]

            if width <= max_width:

                current = candidate

            else:

                if current:
                    lines.append(current)

                current = word

        if current:
            lines.append(current)

        return lines


    def add_soft_shadow(
        self,
        canvas,
        box,
        radius=24,
        alpha=130,
        blur=18
    ):

        x1, y1, x2, y2 = box

        shadow = Image.new(
            "RGBA",
            canvas.size,
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(shadow)

        draw.rounded_rectangle(
            box,
            radius=radius,
            fill=(0, 0, 0, alpha)
        )

        shadow = shadow.filter(
            ImageFilter.GaussianBlur(blur)
        )

        canvas.alpha_composite(shadow)


    async def read_image_attachment(
        self,
        attachment
    ):

        if not self.is_supported_image(
            attachment
        ):

            raise ValueError(
                "صيغة الصورة غير مدعومة."
            )

        data = await attachment.read()

        if not data:

            raise ValueError(
                "الصورة فارغة."
            )

        try:

            image = Image.open(
                io.BytesIO(data)
            )

            try:
                image.seek(0)
            except Exception:
                pass

            return image.convert("RGBA")

        except Exception as error:

            raise ValueError(
                "تعذر قراءة الصورة."
            ) from error


    def render_room_definition(
        self,
        canvas,
        definition
    ):

        if not definition:
            return

        draw = ImageDraw.Draw(canvas)

        font = self.get_font(
            25,
            bold=False
        )

        title_font = self.get_font(
            19,
            bold=True
        )

        definition = str(
            definition
        ).strip()

        definition = self.prepare_text(
            definition
        )

        max_width = 680

        lines = self.wrap_text(
            draw,
            definition,
            font,
            max_width
        )

        if not lines:
            return

        lines = lines[:3]

        line_height = 35

        box_height = (
            76
            + len(lines) * line_height
        )

        box_x1 = 445
        box_y2 = 625
        box_y1 = box_y2 - box_height

        draw.rounded_rectangle(
            (
                box_x1,
                box_y1,
                1135,
                box_y2
            ),
            radius=24,
            fill=(17, 20, 30, 235),
            outline=(124, 92, 255, 95),
            width=2
        )

        draw.text(
            (
                box_x1 + 25,
                box_y1 + 18
            ),
            self.prepare_text("تعريف الروم"),
            font=title_font,
            fill=(245, 247, 251, 245)
        )

        start_y = box_y1 + 50

        for index, line in enumerate(lines):

            draw.text(
                (
                    box_x1 + 25,
                    start_y + index * line_height
                ),
                line,
                font=font,
                fill=(165, 171, 188, 230)
            )


    async def create_say_image(
        self,
        avatar_attachment=None,
        banner_attachment=None,
        template_attachment=None,
        room_definition=None
    ):

        # ====================================================
        # CANVAS
        # ====================================================

        WIDTH = 1400
        HEIGHT = 800

        if template_attachment:

            template_image = await self.read_image_attachment(
                template_attachment
            )

            canvas = self.crop_to_fill(
                template_image,
                (
                    WIDTH,
                    HEIGHT
                )
            )

            # طبقة داكنة خفيفة حتى يندمج المحتوى مع القالب
            dark = Image.new(
                "RGBA",
                canvas.size,
                (5, 7, 12, 65)
            )

            canvas.alpha_composite(dark)

        else:

            canvas = Image.new(
                "RGBA",
                (
                    WIDTH,
                    HEIGHT
                ),
                (
                    6,
                    7,
                    12,
                    255
                )
            )

            # =================================================
            # GRADIENT-LIKE PANELS
            # =================================================

            draw = ImageDraw.Draw(canvas)

            draw.rounded_rectangle(
                (
                    30,
                    30,
                    WIDTH - 30,
                    HEIGHT - 30
                ),
                radius=42,
                fill=(13, 16, 24, 255),
                outline=(40, 44, 58, 255),
                width=2
            )

            # وهج بنفسجي خلفي
            glow = Image.new(
                "RGBA",
                canvas.size,
                (0, 0, 0, 0)
            )

            glow_draw = ImageDraw.Draw(glow)

            glow_draw.ellipse(
                (
                    870,
                    -180,
                    1450,
                    390
                ),
                fill=(124, 92, 255, 70)
            )

            glow_draw.ellipse(
                (
                    -250,
                    530,
                    450,
                    1050
                ),
                fill=(45, 90, 255, 30)
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(90)
            )

            canvas.alpha_composite(glow)

            # خطوط زخرفية بسيطة
            draw = ImageDraw.Draw(canvas)

            draw.rounded_rectangle(
                (
                    65,
                    65,
                    WIDTH - 65,
                    HEIGHT - 65
                ),
                radius=32,
                outline=(124, 92, 255, 40),
                width=2
            )


        draw = ImageDraw.Draw(canvas)

        # ====================================================
        # BANNER
        # ====================================================

        if banner_attachment:

            banner = await self.read_image_attachment(
                banner_attachment
            )

            banner = self.crop_to_fill(
                banner,
                (
                    1270,
                    300
                )
            )

            # Rounded mask
            mask = Image.new(
                "L",
                banner.size,
                0
            )

            mask_draw = ImageDraw.Draw(mask)

            mask_draw.rounded_rectangle(
                (
                    0,
                    0,
                    banner.width,
                    banner.height
                ),
                radius=30,
                fill=255
            )

            banner_layer = Image.new(
                "RGBA",
                banner.size,
                (0, 0, 0, 0)
            )

            banner_layer.paste(
                banner,
                (0, 0),
                mask
            )

            # ظل
            self.add_soft_shadow(
                canvas,
                (
                    65,
                    65,
                    1335,
                    365
                ),
                radius=30,
                alpha=150,
                blur=20
            )

            canvas.alpha_composite(
                banner_layer,
                (
                    65,
                    65
                )
            )

            # Gradient داكن سفلي
            gradient = Image.new(
                "RGBA",
                (
                    1270,
                    300
                ),
                (0, 0, 0, 0)
            )

            gradient_draw = ImageDraw.Draw(
                gradient
            )

            gradient_draw.rectangle(
                (
                    0,
                    190,
                    1270,
                    300
                ),
                fill=(5, 7, 12, 165)
            )

            canvas.alpha_composite(
                gradient,
                (
                    65,
                    65
                )
            )

        else:

            draw.rounded_rectangle(
                (
                    65,
                    65,
                    1335,
                    365
                ),
                radius=30,
                fill=(10, 13, 21, 255),
                outline=(124, 92, 255, 45),
                width=2
            )

            # زخرفة خلفية
            for x in range(
                100,
                1300,
                70
            ):

                draw.line(
                    (
                        x,
                        340,
                        x + 100,
                        70
                    ),
                    fill=(124, 92, 255, 12),
                    width=2
                )


        # ====================================================
        # HEADER
        # ====================================================

        brand_font = self.get_font(
            24,
            bold=True
        )

        small_font = self.get_font(
            16,
            bold=False
        )

        draw.text(
            (
                95,
                90
            ),
            "TEAM FIME",
            font=brand_font,
            fill=(245, 247, 251, 235)
        )

        draw.text(
            (
                95,
                125
            ),
            "OFFICIAL MESSAGE",
            font=small_font,
            fill=(154, 132, 255, 225)
        )


        # ====================================================
        # AVATAR
        # ====================================================

        avatar_bytes = None

        if avatar_attachment:

            avatar_data = await avatar_attachment.read()

            if avatar_data:
                avatar_bytes = avatar_data

            avatar = await self.read_image_attachment(
                avatar_attachment
            )

            avatar = self.circle_avatar(
                avatar,
                225
            )

            # إطار خارجي
            ring = Image.new(
                "RGBA",
                (
                    255,
                    255
                ),
                (0, 0, 0, 0)
            )

            ring_draw = ImageDraw.Draw(ring)

            ring_draw.ellipse(
                (
                    7,
                    7,
                    248,
                    248
                ),
                fill=(7, 8, 13, 255),
                outline=(124, 92, 255, 255),
                width=5
            )

            ring_draw.ellipse(
                (
                    15,
                    15,
                    240,
                    240
                ),
                outline=(154, 131, 255, 85),
                width=2
            )

            # ظل
            shadow = Image.new(
                "RGBA",
                (
                    290,
                    290
                ),
                (0, 0, 0, 0)
            )

            shadow_draw = ImageDraw.Draw(shadow)

            shadow_draw.ellipse(
                (
                    25,
                    30,
                    265,
                    270
                ),
                fill=(0, 0, 0, 190)
            )

            shadow = shadow.filter(
                ImageFilter.GaussianBlur(18)
            )

            canvas.alpha_composite(
                shadow,
                (
                    75,
                    300
                )
            )

            canvas.alpha_composite(
                ring,
                (
                    90,
                    305
                )
            )

            canvas.alpha_composite(
                avatar,
                (
                    105,
                    320
                )
            )

        else:

            # إذا ما فيه افتار
            draw.rounded_rectangle(
                (
                    90,
                    320,
                    315,
                    545
                ),
                radius=112,
                fill=(24, 28, 40, 255),
                outline=(124, 92, 255, 100),
                width=3
            )

            default_font = self.get_font(
                70,
                bold=True
            )

            self.draw_text_center(
                draw,
                202,
                380,
                "F",
                default_font,
                (154, 132, 255, 230)
            )


        # ====================================================
        # MAIN PROFILE TEXT
        # ====================================================

        title_font = self.get_font(
            38,
            bold=True
        )

        subtitle_font = self.get_font(
            20,
            bold=False
        )

        draw.text(
            (
                390,
                335
            ),
            "Fime",
            font=title_font,
            fill=(245, 247, 251, 255)
        )

        draw.text(
            (
                390,
                390
            ),
            "Team Fime • Community",
            font=subtitle_font,
            fill=(151, 158, 176, 230)
        )

        # نقطة هوية
        draw.ellipse(
            (
                390,
                440,
                402,
                452
            ),
            fill=(124, 92, 255, 255)
        )

        draw.text(
            (
                420,
                430
            ),
            "Official profile card",
            font=small_font,
            fill=(124, 92, 255, 235)
        )


        # ====================================================
        # MESSAGE AREA
        # ====================================================

        message_title_font = self.get_font(
            17,
            bold=True
        )

        draw.text(
            (
                390,
                480
            ),
            "MESSAGE",
            font=message_title_font,
            fill=(130, 137, 156, 220)
        )

        # ====================================================
        # ROOM DEFINITION
        # ====================================================

        if room_definition:

            self.render_room_definition(
                canvas,
                room_definition
            )


        # ====================================================
        # BOTTOM BRAND BAR
        # ====================================================

        draw.rounded_rectangle(
            (
                65,
                700,
                1335,
                735
            ),
            radius=17,
            fill=(19, 22, 32, 230)
        )

        draw.rounded_rectangle(
            (
                65,
                700,
                250,
                735
            ),
            radius=17,
            fill=(124, 92, 255, 220)
        )

        draw.text(
            (
                88,
                707
            ),
            "FIME",
            font=self.get_font(
                16,
                bold=True
            ),
            fill=(255, 255, 255, 245)
        )

        draw.text(
            (
                1080,
                707
            ),
            "TEAM FIME",
            font=self.get_font(
                15,
                bold=True
            ),
            fill=(156, 162, 178, 220)
        )


        # ====================================================
        # OUTPUT
        # ====================================================

        output = io.BytesIO()

        canvas.convert("RGB").save(
            output,
            format="PNG",
            optimize=True
        )

        output.seek(0)

        return output


    async def create_avatar_output(
        self,
        avatar_attachment
    ):

        data = await avatar_attachment.read()

        if not data:
            return None

        return data


    async def create_banner_output(
        self,
        banner_attachment
    ):

        data = await banner_attachment.read()

        if not data:
            return None

        return data


    # ========================================================
    # /say
    # ========================================================

    @app_commands.command(
        name="say",
        description="يجعل البوت يرسل رسالة احترافية مع قائمة البروفايل"
    )
    @app_commands.describe(
        message="الرسالة التي تريد أن يرسلها البوت",
        channel="الروم الذي تريد إرسال الرسالة فيه",
        avatar="الافتار الذي سيظهر في التصميم",
        banner="البنر الذي سيظهر في التصميم",
        template="قالب مخصص اختياري",
        room_definition="تعريف اختياري للروم يظهر في قائمة البروفايل"
    )
    async def say(
        self,
        interaction,
        message: str,
        channel: discord.TextChannel = None,
        avatar: discord.Attachment = None,
        banner: discord.Attachment = None,
        template: discord.Attachment = None,
        room_definition: str = None
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:

            await interaction.response.send_message(
                "❌ هذا الأمر يعمل داخل السيرفر فقط.",
                ephemeral=True
            )

            return

        message = str(
            message or ""
        ).strip()

        if not message:

            await interaction.response.send_message(
                "❌ اكتب الرسالة التي تريد إرسالها.",
                ephemeral=True
            )

            return

        if len(message) > 2000:

            await interaction.response.send_message(
                "❌ الرسالة لا يمكن أن تتجاوز 2000 حرف.",
                ephemeral=True
            )

            return

        if room_definition:

            room_definition = str(
                room_definition
            ).strip()

            if len(room_definition) > 500:

                await interaction.response.send_message(
                    "❌ تعريف الروم لا يمكن أن يتجاوز 500 حرف.",
                    ephemeral=True
                )

                return

        target_channel = (
            channel
            or interaction.channel
        )

        if not isinstance(
            target_channel,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ اختر رومًا نصيًا صالحًا.",
                ephemeral=True
            )

            return

        me = interaction.guild.me

        if me is None:

            await interaction.response.send_message(
                "❌ تعذر معرفة صلاحيات البوت.",
                ephemeral=True
            )

            return

        permissions = target_channel.permissions_for(me)

        if not permissions.view_channel:

            await interaction.response.send_message(
                f"❌ ما أقدر أشوف {target_channel.mention}.",
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                f"❌ ما أقدر أرسل في {target_channel.mention}.",
                ephemeral=True
            )

            return

        has_profile_data = any(
            (
                avatar,
                banner,
                template,
                room_definition
            )
        )

        await interaction.response.defer(
            ephemeral=True
        )

        generated_file = None
        avatar_bytes = None
        banner_bytes = None
        full_profile_bytes = None

        # ====================================================
        # VALIDATE ATTACHMENTS
        # ====================================================

        for attachment, name in (
            (avatar, "الافتار"),
            (banner, "البنر"),
            (template, "القالب")
        ):

            if attachment and not self.is_supported_image(
                attachment
            ):

                await interaction.followup.send(
                    (
                        f"❌ {name} يجب أن يكون صورة "
                        "`PNG` أو `JPG` أو `JPEG` "
                        "`WEBP` أو `GIF` أو `APNG`."
                    ),
                    ephemeral=True
                )

                return

        # ====================================================
        # BUILD PROFILE
        # ====================================================

        if has_profile_data:

            if not permissions.attach_files:

                await interaction.followup.send(
                    (
                        f"❌ أحتاج صلاحية **Attach Files** "
                        f"في {target_channel.mention}."
                    ),
                    ephemeral=True
                )

                return

            try:

                if avatar:

                    avatar_bytes = await avatar.read()

                if banner:

                    banner_bytes = await banner.read()

                generated = await self.create_say_image(
                    avatar_attachment=avatar,
                    banner_attachment=banner,
                    template_attachment=template,
                    room_definition=room_definition
                )

                full_profile_bytes = generated.getvalue()

                generated.seek(0)

                generated_file = generated

            except ValueError as error:

                await interaction.followup.send(
                    f"❌ {error}",
                    ephemeral=True
                )

                return

            except Exception as error:

                print(
                    "❌ bot5 SAY image error:",
                    error
                )

                await interaction.followup.send(
                    (
                        "❌ حصل خطأ أثناء تجهيز التصميم.\n"
                        f"الخطأ: `{type(error).__name__}`"
                    ),
                    ephemeral=True
                )

                return

        # ====================================================
        # SEND MESSAGE
        # ====================================================

        try:

            if generated_file:

                file = discord.File(
                    generated_file,
                    filename="fime-profile.png"
                )

                view = SayProfileView(
                    cog=self,
                    avatar_bytes=avatar_bytes,
                    banner_bytes=banner_bytes,
                    full_profile_bytes=full_profile_bytes,
                    room_definition=room_definition
                )

                await target_channel.send(
                    content=message,
                    file=file,
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none()
                )

            else:

                await target_channel.send(
                    content=message,
                    allowed_mentions=discord.AllowedMentions.none()
                )

        except discord.Forbidden:

            await interaction.followup.send(
                (
                    f"❌ البوت ما يملك الصلاحيات الكافية "
                    f"في {target_channel.mention}."
                ),
                ephemeral=True
            )

            return

        except discord.HTTPException as error:

            print(
                "⚠️ bot5 SAY HTTP error:",
                error
            )

            await interaction.followup.send(
                "❌ فشل إرسال الرسالة.",
                ephemeral=True
            )

            return

        except Exception as error:

            print(
                "❌ bot5 SAY error:",
                error
            )

            await interaction.followup.send(
                (
                    "❌ حصل خطأ أثناء إرسال الرسالة.\n"
                    f"`{type(error).__name__}`"
                ),
                ephemeral=True
            )

            return

        # ====================================================
        # SUCCESS
        # ====================================================

        if generated_file:

            menu_text = (
                "\n"
                "🎛️ **تمت إضافة قائمة البروفايل تحت الرسالة:**\n"
                "🖼️ الافتار\n"
                "🎨 البنر\n"
                "👤 البروفايل كامل"
            )

            if room_definition:
                menu_text += "\n📖 تعريف الروم"

        else:

            menu_text = ""

        await interaction.followup.send(
            (
                "✅ **تم إرسال الرسالة بواسطة البوت.**\n"
                f"📍 الروم: {target_channel.mention}"
                f"{menu_text}"
            ),
            ephemeral=True
        )


    # ========================================================
    # LINE MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if message.guild is None:
            return

        cfg = self.get_config(
            message.guild.id
        )

        # ====================================================
        # TOP POINT
        # ====================================================

        self.add_top_point(
            message.guild.id,
            message.author.id
        )

        # ====================================================
        # TOP KEYWORDS
        # ====================================================

        top_handled = await self.handle_top_keyword(
            message,
            cfg
        )

        if top_handled:
            return

        # ====================================================
        # FIME KEYWORD
        # ====================================================

        await self.handle_fime_keyword(
            message,
            cfg
        )

        # ====================================================
        # LINE SYSTEM
        # ====================================================

        if not cfg.get("enabled"):
            return

        image_url = cfg.get("image_url")

        if not image_url:
            return

        configured_channel_id = cfg.get(
            "channel_id"
        )

        if configured_channel_id:

            if message.channel.id != int(
                configured_channel_id
            ):
                return

        me = message.guild.me

        if me is None:
            return

        permissions = message.channel.permissions_for(me)

        if not permissions.view_channel:
            return

        if not permissions.send_messages:
            return

        if not permissions.embed_links:
            return

        try:

            await message.channel.send(
                image_url,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except discord.Forbidden as error:

            print(
                "⚠️ bot5 cannot send line image "
                f"in #{message.channel}: {error}"
            )

        except discord.HTTPException as error:

            print(
                "⚠️ bot5 line image HTTP error "
                f"in #{message.channel}: {error}"
            )

        except Exception as error:

            print(
                "❌ bot5 line system error:",
                error
            )


    # ========================================================
    # JOIN MENTION SYSTEM
    # ========================================================

    async def send_join_mention(self, member):

        guild = member.guild

        cfg = self.get_config(
            guild.id
        )

        if not cfg.get(
            "join_mention_enabled"
        ):
            return

        channel_id = cfg.get(
            "join_mention_channel_id"
        )

        if not channel_id:
            return

        try:

            channel = guild.get_channel(
                int(channel_id)
            )

        except Exception:

            return

        if channel is None:
            return

        me = guild.me

        if me is None:
            return

        permissions = channel.permissions_for(me)

        if not permissions.view_channel:
            return

        if not permissions.send_messages:
            return

        try:

            duration = float(
                cfg.get(
                    "join_mention_duration",
                    2
                )
            )

        except Exception:

            duration = 2

        duration = max(
            1,
            min(
                duration,
                5
            )
        )

        try:

            sent_message = await channel.send(
                member.mention,
                allowed_mentions=discord.AllowedMentions(
                    users=True,
                    everyone=False,
                    roles=False,
                    replied_user=False
                )
            )

        except Exception as error:

            print(
                "❌ Join mention error:",
                error
            )

            return

        try:

            await asyncio.sleep(duration)

            await sent_message.delete()

        except discord.NotFound:
            pass

        except Exception as error:

            print(
                "❌ Join mention delete error:",
                error
            )


    # ========================================================
    # MEMBER JOIN
    # ========================================================

    @commands.Cog.listener()
    async def on_member_join(self, member):

        if member.bot:
            return

        await asyncio.sleep(0.5)

        await self.send_join_mention(
            member
        )


    # ========================================================
    # /منشن-روم
    # ========================================================

    @app_commands.command(
        name="منشن-روم",
        description="تحديد روم منشن الأعضاء الجدد"
    )
    async def mention_channel(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        guild = interaction.guild
        me = guild.me

        if me is None:

            await interaction.response.send_message(
                "❌ تعذر معرفة صلاحيات البوت.",
                ephemeral=True
            )

            return

        permissions = channel.permissions_for(me)

        if not permissions.view_channel:

            await interaction.response.send_message(
                f"❌ ما أقدر أشوف {channel.mention}.",
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                f"❌ ما أقدر أرسل في {channel.mention}.",
                ephemeral=True
            )

            return

        cfg = self.get_config(
            guild.id
        )

        cfg["join_mention_channel_id"] = channel.id
        cfg["join_mention_enabled"] = True
        cfg["join_mention_duration"] = 2

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ **تم تشغيل منشن دخول الأعضاء.**\n\n"
                f"📍 الروم: {channel.mention}\n"
                "⏱️ مدة ظهور المنشن: **ثانيتين**\n\n"
                "أي عضو جديد يدخل السيرفر "
                "سيتم منشنه هناك، وبعد ثانيتين "
                "تنحذف رسالة المنشن."
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="منشن-إيقاف",
        description="إيقاف منشن الأعضاء الجدد"
    )
    async def mention_off(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["join_mention_enabled"] = False

        save_config(self.config)

        await interaction.response.send_message(
            "🛑 تم إيقاف منشن دخول الأعضاء.",
            ephemeral=True
        )


    @app_commands.command(
        name="منشن-حالة",
        description="عرض حالة منشن الأعضاء الجدد"
    )
    async def mention_status(self, interaction):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        enabled = cfg.get(
            "join_mention_enabled",
            False
        )

        channel_id = cfg.get(
            "join_mention_channel_id"
        )

        if channel_id:

            try:

                channel = interaction.guild.get_channel(
                    int(channel_id)
                )

            except Exception:

                channel = None

        else:

            channel = None

        status = (
            "🟢 مفعل"
            if enabled
            else "🔴 متوقف"
        )

        channel_text = (
            channel.mention
            if channel
            else "غير محدد"
        )

        await interaction.response.send_message(
            (
                "## 👋 حالة منشن الدخول\n\n"
                f"الحالة: **{status}**\n"
                f"الروم: {channel_text}\n"
                "مدة ظهور المنشن: **ثانيتين**"
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="منشن-روم-إلغاء",
        description="إلغاء روم منشن الأعضاء"
    )
    async def mention_channel_clear(
        self,
        interaction
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["join_mention_enabled"] = False
        cfg["join_mention_channel_id"] = None

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ تم إلغاء روم منشن الدخول "
                "وإيقاف النظام."
            ),
            ephemeral=True
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):

    for cog in bot.cogs.values():

        if isinstance(
            cog,
            AutomaticLineSystem
        ):

            print(
                "⚠️ bot5 موجود مسبقًا، "
                "لن يتم تحميل نسخة ثانية."
            )

            return

    await bot.add_cog(
        AutomaticLineSystem(bot)
    )

    print(
        "✅ Team Fime bot5 — "
        "Automatic Line + Join Mention + "
        "Fime Keyword + GIF + TOP + SAY loaded."
    )