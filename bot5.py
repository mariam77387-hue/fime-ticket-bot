# ============================================================
# Team Fime
# bot5.py
# Automatic Divider / Line Image System
# +
# Temporary Join Mention System
# +
# Fime Keyword Response System
# +
# TOP SYSTEM — DAY / WEEK / MONTH / ALL
# +
# SAY SYSTEM — PROFESSIONAL PROFILE + FAST DOWNLOADS
# +
# SERVER INFORMATION SYSTEM
# +
# BOT MESSAGE EDIT SYSTEM
# +
# SMART SUGGESTIONS SYSTEM
# ============================================================

from __future__ import annotations

import os
import io
import json
import asyncio
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands
from discord import app_commands

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
SUGGESTIONS_FILE = Path("bot5_suggestions.json")

SAUDI_TZ = timezone(timedelta(hours=3))


DEFAULT_GUILD_CONFIG = {
    # LINE
    "enabled": False,
    "channel_id": None,
    "image_url": None,
    "storage_channel_id": None,
    "storage_message_id": None,
    "delete_after": 0,

    # JOIN
    "join_mention_enabled": False,
    "join_mention_channel_id": None,
    "join_mention_duration": 2,

    # FIME
    "fime_word_enabled": True,
    "fime_word_response": "هلا؟ وش تبي يا فايم؟",
    "fime_word_accept_fimi": False,

    # TOP
    "top_channel_id": None,
    "top_allowed_role_ids": [],

    # SAY
    "say_room_definition": "",

    # SUGGESTIONS
    "suggestions_channel_id": None,
    "suggestions_log_channel_id": None,
}


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    try:
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:
        print(f"❌ JSON load error [{path}]:", error)
        return {}


def save_json(path, data):
    temp = path.with_suffix(".tmp")

    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp, path)

    except Exception as error:
        print(f"❌ JSON save error [{path}]:", error)

        try:
            if temp.exists():
                temp.unlink()
        except Exception:
            pass


def load_config():
    return load_json(CONFIG_FILE)


def save_config(data):
    save_json(CONFIG_FILE, data)


def load_top():
    return load_json(TOP_FILE)


def save_top(data):
    return save_json(TOP_FILE, data)


def load_suggestions():
    return load_json(SUGGESTIONS_FILE)


def save_suggestions(data):
    save_json(SUGGESTIONS_FILE, data)


# ============================================================
# TOP SELECT
# ============================================================

class TopSelect(discord.ui.Select):

    def __init__(self, cog, guild_id):

        self.cog = cog

        options = [
            discord.SelectOption(
                label="توب اليوم",
                value="day",
                emoji="📅"
            ),
            discord.SelectOption(
                label="توب الأسبوع",
                value="week",
                emoji="📊"
            ),
            discord.SelectOption(
                label="توب الشهر",
                value="month",
                emoji="🗓️"
            ),
            discord.SelectOption(
                label="توب الكل",
                value="all",
                emoji="🏆"
            ),
        ]

        super().__init__(
            placeholder="اختر نوع التوب...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_top_select_{guild_id}"
        )

    async def callback(self, interaction):

        if interaction.guild is None:
            await interaction.response.send_message(
                "❌ هذا الخيار يعمل داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        embed = self.cog.build_top_embed(
            interaction.guild,
            self.values[0]
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
# SAY PROFILE MENU
# ============================================================

class SayProfileSelect(discord.ui.Select):

    def __init__(
        self,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None,
        avatar_url=None,
        banner_url=None,
        username=None
    ):

        self.avatar_bytes = avatar_bytes
        self.banner_bytes = banner_bytes
        self.full_profile_bytes = full_profile_bytes

        self.avatar_url = avatar_url
        self.banner_url = banner_url
        self.username = username or "Unknown"

        options = [
            discord.SelectOption(
                label="أخذ الافتار",
                value="avatar",
                emoji="👤",
                description="إرسال صورة الافتار"
            ),
            discord.SelectOption(
                label="أخذ البنر",
                value="banner",
                emoji="🎨",
                description="إرسال صورة البنر"
            ),
            discord.SelectOption(
                label="البروفايل الكامل",
                value="profile",
                emoji="🪪",
                description="البنر والافتار معًا"
            ),
            discord.SelectOption(
                label="معلومات البروفايل",
                value="info",
                emoji="📊",
                description="عرض معلومات البروفايل"
            ),
        ]

        super().__init__(
            placeholder="خيارات البروفايل...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_profile_menu_{id(self)}"
        )

    async def callback(self, interaction):

        choice = self.values[0]

        # ====================================================
        # AVATAR
        # ====================================================

        if choice == "avatar":

            if not self.avatar_bytes:
                await interaction.response.send_message(
                    "❌ ما فيه افتار متوفر لهذا الـ /say.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "👤 **الافتار**",
                file=discord.File(
                    io.BytesIO(self.avatar_bytes),
                    filename="fime-avatar.jpg"
                ),
                ephemeral=True
            )
            return

        # ====================================================
        # BANNER
        # ====================================================

        if choice == "banner":

            if not self.banner_bytes:
                await interaction.response.send_message(
                    "❌ ما فيه بنر متوفر لهذا الـ /say.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "🎨 **البنر**",
                file=discord.File(
                    io.BytesIO(self.banner_bytes),
                    filename="fime-banner.jpg"
                ),
                ephemeral=True
            )
            return

        # ====================================================
        # FULL PROFILE
        # ====================================================

        if choice == "profile":

            if not self.full_profile_bytes:
                await interaction.response.send_message(
                    "❌ تعذر تجهيز البروفايل الكامل.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "🪪 **البروفايل الكامل**",
                file=discord.File(
                    io.BytesIO(self.full_profile_bytes),
                    filename="fime-full-profile.jpg"
                ),
                ephemeral=True
            )
            return

        # ====================================================
        # PROFILE INFO
        # ====================================================

        if choice == "info":

            embed = discord.Embed(
                title="📊 معلومات البروفايل",
                color=discord.Color.blurple()
            )

            embed.add_field(
                name="👤 المستخدم",
                value=f"`{self.username}`",
                inline=False
            )

            embed.add_field(
                name="🖼️ الافتار",
                value="متوفر ✅" if self.avatar_bytes else "غير متوفر ❌",
                inline=True
            )

            embed.add_field(
                name="🎨 البنر",
                value="متوفر ✅" if self.banner_bytes else "غير متوفر ❌",
                inline=True
            )

            embed.add_field(
                name="🪪 البروفايل",
                value="جاهز ✅" if self.full_profile_bytes else "غير متوفر ❌",
                inline=True
            )

            embed.set_footer(
                text="Team Fime • Profile System"
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )


# ============================================================
# PROFILE BUTTON
# ============================================================

class ProfileURLButton(discord.ui.Button):

    def __init__(
        self,
        label,
        emoji,
        url,
        custom_id
    ):

        self.target_url = url

        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.link,
            url=url
        )


# ============================================================
# ROOM DEFINITION BUTTON
# ============================================================

class SayRoomDefinitionButton(discord.ui.Button):

    def __init__(self, room_definition):

        self.room_definition = str(
            room_definition or ""
        ).strip()

        super().__init__(
            label="تعريف الروم",
            emoji="📖",
            style=discord.ButtonStyle.secondary,
            custom_id=f"fime_room_definition_{id(self)}",
            disabled=not bool(self.room_definition)
        )

    async def callback(self, interaction):

        if not self.room_definition:
            await interaction.response.send_message(
                "❌ ما فيه تعريف محفوظ لهذا الروم.",
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


# ============================================================
# SAY VIEW
# ============================================================

class SayProfileView(discord.ui.View):

    def __init__(
        self,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None,
        room_definition=None,
        avatar_url=None,
        banner_url=None,
        username=None
    ):

        super().__init__(timeout=1800)

        self.add_item(
            SayProfileSelect(
                avatar_bytes=avatar_bytes,
                banner_bytes=banner_bytes,
                full_profile_bytes=full_profile_bytes,
                avatar_url=avatar_url,
                banner_url=banner_url,
                username=username
            )
        )

        if avatar_url:
            self.add_item(
                ProfileURLButton(
                    "رابط الافتار",
                    "🔗",
                    avatar_url,
                    f"fime_avatar_link_{id(self)}"
                )
            )

        if banner_url:
            self.add_item(
                ProfileURLButton(
                    "رابط البنر",
                    "🖼️",
                    banner_url,
                    f"fime_banner_link_{id(self)}"
                )
            )

        self.add_item(
            SayRoomDefinitionButton(
                room_definition
            )
        )

    async def on_timeout(self):

        for item in self.children:

            if not isinstance(
                item,
                discord.ui.Button
            ) or item.style != discord.ButtonStyle.link:

                item.disabled = True


# ============================================================
# SUGGESTIONS VIEW
# ============================================================

class SuggestionView(discord.ui.View):

    def __init__(
        self,
        cog,
        suggestion_id
    ):

        super().__init__(timeout=None)

        self.cog = cog
        self.suggestion_id = str(
            suggestion_id
        )

        approve = discord.ui.Button(
            label="قبول",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"fime_suggest_approve_{suggestion_id}"
        )

        reject = discord.ui.Button(
            label="رفض",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"fime_suggest_reject_{suggestion_id}"
        )

        approve.callback = self.approve
        reject.callback = self.reject

        self.add_item(approve)
        self.add_item(reject)

    async def approve(self, interaction):

        await self.cog.change_suggestion_status(
            interaction,
            self.suggestion_id,
            "مقبول"
        )

    async def reject(self, interaction):

        await self.cog.change_suggestion_status(
            interaction,
            self.suggestion_id,
            "مرفوض"
        )


# ============================================================
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.config = load_config()
        self.top_data = load_top()
        self.suggestions = load_suggestions()

        print(
            "✅ bot5 — Line + Join + Fime + TOP + SAY "
            "+ Server + Edit + Suggestions loaded."
        )

    # ========================================================
    # CONFIG
    # ========================================================

    def get_config(self, guild_id):

        key = str(guild_id)

        if key not in self.config:

            self.config[key] = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

        current = self.config[key]

        if not isinstance(current, dict):

            current = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

            self.config[key] = current

        changed = False

        for key_name, default in DEFAULT_GUILD_CONFIG.items():

            if key_name not in current:

                current[key_name] = deepcopy(
                    default
                )

                changed = True

        if not isinstance(
            current.get("top_allowed_role_ids"),
            list
        ):

            current["top_allowed_role_ids"] = []
            changed = True

        if not isinstance(
            current.get("say_room_definition"),
            str
        ):

            current["say_room_definition"] = ""
            changed = True

        if changed:
            save_config(self.config)

        return current

    # ========================================================
    # OWNER
    # ========================================================

    def is_owner(self, interaction):

        return interaction.user.id == OWNER_ID

    async def owner_only(self, interaction):

        return not self.is_owner(
            interaction
        )

    # ========================================================
    # IMAGE
    # ========================================================

    def is_supported_image(self, attachment):

        if not attachment:
            return False

        content_type = (
            attachment.content_type or ""
        ).lower().split(";")[0]

        filename = (
            attachment.filename or ""
        ).lower()

        return (
            content_type in {
                "image/png",
                "image/jpeg",
                "image/jpg",
                "image/webp",
                "image/gif",
                "image/apng"
            }
            or filename.endswith(
                (
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".gif",
                    ".apng"
                )
            )
        )

    async def read_image_attachment(self, attachment):

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

            image.seek(0)

            return image.convert(
                "RGBA"
            )

        except Exception as error:

            raise ValueError(
                "تعذر قراءة الصورة."
            ) from error

    def get_font(
        self,
        size,
        bold=False
    ):

        if bold:

            paths = [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            ]

        else:

            paths = [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            ]

        for path in paths:

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

        text = str(
            text or ""
        )

        if ARABIC_SUPPORT:

            try:

                return get_display(
                    arabic_reshaper.reshape(
                        text
                    )
                )

            except Exception:
                pass

        return text

    def crop_to_fill(
        self,
        image,
        size
    ):

        width, height = size

        image = image.convert(
            "RGBA"
        )

        if image.width <= 0 or image.height <= 0:

            return Image.new(
                "RGBA",
                size,
                (10, 12, 18, 255)
            )

        source_ratio = (
            image.width /
            image.height
        )

        target_ratio = (
            width /
            height
        )

        if source_ratio > target_ratio:

            new_height = height

            new_width = int(
                new_height *
                source_ratio
            )

        else:

            new_width = width

            new_height = int(
                new_width /
                source_ratio
            )

        image = image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

        left = (
            new_width -
            width
        ) // 2

        top = (
            new_height -
            height
        ) // 2

        return image.crop(
            (
                left,
                top,
                left + width,
                top + height
            )
        )

    def image_to_jpeg(
        self,
        image,
        size=None,
        quality=84
    ):

        if size:

            image = self.crop_to_fill(
                image,
                size
            )

        output = io.BytesIO()

        image.convert(
            "RGB"
        ).save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True
        )

        return output.getvalue()

    # ========================================================
    # DRAW CENTER
    # ========================================================

    def draw_center(
        self,
        draw,
        x,
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

        width = (
            bbox[2] -
            bbox[0]
        )

        draw.text(
            (
                x -
                width / 2,
                y
            ),
            text,
            font=font,
            fill=fill
        )

    # ========================================================
    # FAST FULL PROFILE
    # ========================================================

    def create_fast_profile(
        self,
        avatar_image,
        banner_image
    ):

        width = 1200
        height = 675

        canvas = Image.new(
            "RGB",
            (width, height),
            (7, 8, 13)
        )

        draw = ImageDraw.Draw(
            canvas
        )

        if banner_image:

            banner = self.crop_to_fill(
                banner_image,
                (width - 70, 360)
            )

            canvas.paste(
                banner.convert("RGB"),
                (35, 35)
            )

            overlay = Image.new(
                "RGBA",
                (width - 70, 360),
                (0, 0, 0, 0)
            )

            overlay_draw = ImageDraw.Draw(
                overlay
            )

            overlay_draw.rectangle(
                (
                    0,
                    230,
                    width,
                    360
                ),
                fill=(4, 5, 9, 150)
            )

            canvas.paste(
                overlay,
                (35, 35),
                overlay
            )

        else:

            draw.rounded_rectangle(
                (
                    35,
                    35,
                    width - 35,
                    395
                ),
                radius=30,
                fill=(15, 18, 28)
            )

        if avatar_image:

            avatar = self.crop_to_fill(
                avatar_image,
                (300, 300)
            )

            mask = Image.new(
                "L",
                (300, 300),
                0
            )

            ImageDraw.Draw(
                mask
            ).ellipse(
                (0, 0, 300, 300),
                fill=255
            )

            avatar_rgba = Image.new(
                "RGBA",
                (300, 300),
                (0, 0, 0, 0)
            )

            avatar_rgba.paste(
                avatar,
                (0, 0),
                mask
            )

            canvas.paste(
                avatar_rgba,
                (75, 310),
                avatar_rgba
            )

            draw.ellipse(
                (68, 303, 382, 617),
                outline=(124, 92, 255),
                width=7
            )

        else:

            draw.ellipse(
                (75, 310, 375, 610),
                fill=(25, 29, 42),
                outline=(124, 92, 255),
                width=6
            )

            self.draw_center(
                draw,
                225,
                395,
                "F",
                self.get_font(
                    100,
                    True
                ),
                (154, 132, 255)
            )

        draw.text(
            (440, 425),
            "TEAM FIME",
            font=self.get_font(
                32,
                True
            ),
            fill=(245, 247, 251)
        )

        draw.text(
            (440, 475),
            "Fime • Community Profile",
            font=self.get_font(
                22
            ),
            fill=(150, 157, 175)
        )

        draw.rounded_rectangle(
            (
                440,
                530,
                750,
                575
            ),
            radius=20,
            fill=(124, 92, 255)
        )

        draw.text(
            (468, 541),
            "FULL PROFILE",
            font=self.get_font(
                16,
                True
            ),
            fill="white"
        )

        draw.text(
            (850, 610),
            "TEAM FIME",
            font=self.get_font(
                17,
                True
            ),
            fill=(130, 137, 155)
        )

        return self.image_to_jpeg(
            canvas,
            quality=86
        )

    # ========================================================
    # NEW PROFESSIONAL SAY TEMPLATE
    # ========================================================

    async def create_say_image(
        self,
        avatar_image=None,
        banner_image=None,
        template_image=None,
        room_definition=None
    ):

        WIDTH = 1600
        HEIGHT = 900

        # ====================================================
        # CUSTOM TEMPLATE
        # ====================================================

        if template_image:

            canvas = self.crop_to_fill(
                template_image,
                (WIDTH, HEIGHT)
            )

            overlay = Image.new(
                "RGBA",
                canvas.size,
                (3, 5, 10, 90)
            )

            canvas.alpha_composite(
                overlay
            )

        else:

            canvas = Image.new(
                "RGBA",
                (
                    WIDTH,
                    HEIGHT
                ),
                (5, 7, 13, 255)
            )

            glow = Image.new(
                "RGBA",
                canvas.size,
                (0, 0, 0, 0)
            )

            gd = ImageDraw.Draw(
                glow
            )

            gd.ellipse(
                (
                    950,
                    -300,
                    1800,
                    520
                ),
                fill=(124, 92, 255, 75)
            )

            gd.ellipse(
                (
                    -450,
                    580,
                    650,
                    1250
                ),
                fill=(35, 110, 255, 42)
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(
                    110
                )
            )

            canvas.alpha_composite(
                glow
            )

            draw = ImageDraw.Draw(
                canvas
            )

            # Main frame
            draw.rounded_rectangle(
                (
                    35,
                    35,
                    WIDTH - 35,
                    HEIGHT - 35
                ),
                radius=48,
                fill=(10, 13, 22, 247),
                outline=(55, 61, 82),
                width=2
            )

        draw = ImageDraw.Draw(
            canvas
        )

        # ====================================================
        # HEADER
        # ====================================================

        draw.text(
            (90, 72),
            "TEAM FIME",
            font=self.get_font(
                35,
                True
            ),
            fill=(248, 249, 252)
        )

        draw.text(
            (92, 118),
            "OFFICIAL COMMUNITY",
            font=self.get_font(
                16,
                True
            ),
            fill=(154, 132, 255)
        )

        # Small status pill
        draw.rounded_rectangle(
            (
                1310,
                78,
                1505,
                122
            ),
            radius=22,
            fill=(124, 92, 255, 35),
            outline=(124, 92, 255, 90),
            width=1
        )

        draw.ellipse(
            (
                1330,
                91,
                1346,
                107
            ),
            fill=(76, 220, 130)
        )

        draw.text(
            (1360, 88),
            "FIME",
            font=self.get_font(
                15,
                True
            ),
            fill=(220, 221, 230)
        )

        # ====================================================
        # BANNER
        # ====================================================

        if banner_image:

            banner = self.crop_to_fill(
                banner_image,
                (1410, 330)
            )

            canvas.paste(
                banner,
                (95, 170)
            )

            dark = Image.new(
                "RGBA",
                (
                    1410,
                    330
                ),
                (0, 0, 0, 0)
            )

            dd = ImageDraw.Draw(
                dark
            )

            dd.rectangle(
                (
                    0,
                    205,
                    1410,
                    330
                ),
                fill=(3, 4, 8, 155)
            )

            canvas.alpha_composite(
                dark,
                (95, 170)
            )

        else:

            draw.rounded_rectangle(
                (
                    95,
                    170,
                    1505,
                    500
                ),
                radius=32,
                fill=(15, 18, 29),
                outline=(124, 92, 255, 60),
                width=2
            )

            draw.text(
                (145, 280),
                "FIME",
                font=self.get_font(
                    110,
                    True
                ),
                fill=(124, 92, 255, 65)
            )

            draw.text(
                (148, 405),
                "TEAM FIME COMMUNITY",
                font=self.get_font(
                    18,
                    True
                ),
                fill=(140, 147, 165)
            )

        # ====================================================
        # AVATAR
        # ====================================================

        if avatar_image:

            avatar = self.crop_to_fill(
                avatar_image,
                (250, 250)
            )

            mask = Image.new(
                "L",
                (
                    250,
                    250
                ),
                0
            )

            ImageDraw.Draw(
                mask
            ).ellipse(
                (
                    0,
                    0,
                    250,
                    250
                ),
                fill=255
            )

            avatar_rgba = Image.new(
                "RGBA",
                (
                    250,
                    250
                ),
                (0, 0, 0, 0)
            )

            avatar_rgba.paste(
                avatar,
                (0, 0),
                mask
            )

            canvas.paste(
                avatar_rgba,
                (125, 390),
                avatar_rgba
            )

            draw.ellipse(
                (
                    115,
                    380,
                    385,
                    650
                ),
                outline=(6, 8, 14),
                width=14
            )

            draw.ellipse(
                (
                    115,
                    380,
                    385,
                    650
                ),
                outline=(124, 92, 255),
                width=5
            )

        else:

            draw.ellipse(
                (
                    125,
                    390,
                    375,
                    640
                ),
                fill=(24, 28, 40),
                outline=(124, 92, 255),
                width=5
            )

            self.draw_center(
                draw,
                250,
                460,
                "F",
                self.get_font(
                    80,
                    True
                ),
                (154, 132, 255)
            )

        # ====================================================
        # PROFILE AREA
        # ====================================================

        draw.text(
            (435, 405),
            "FIME",
            font=self.get_font(
                52,
                True
            ),
            fill=(247, 248, 252)
        )

        draw.text(
            (438, 472),
            "Official Community Message",
            font=self.get_font(
                23
            ),
            fill=(151, 158, 176)
        )

        draw.rounded_rectangle(
            (
                435,
                520,
                735,
                565
            ),
            radius=22,
            fill=(124, 92, 255, 35),
            outline=(124, 92, 255, 100)
        )

        draw.text(
            (460, 532),
            "OFFICIAL PROFILE",
            font=self.get_font(
                15,
                True
            ),
            fill=(166, 147, 255)
        )

        # ====================================================
        # ROOM DEFINITION
        # ====================================================

        if room_definition:

            text = self.prepare_text(
                room_definition
            )

            words = text.split()

            lines = []

            current = ""

            font = self.get_font(
                20
            )

            for word in words:

                candidate = (
                    f"{current} {word}".strip()
                )

                bbox = draw.textbbox(
                    (0, 0),
                    candidate,
                    font=font
                )

                if (
                    bbox[2] -
                    bbox[0]
                ) <= 830:

                    current = candidate

                else:

                    if current:
                        lines.append(
                            current
                        )

                    current = word

            if current:
                lines.append(
                    current
                )

            lines = lines[:3]

            draw.rounded_rectangle(
                (
                    435,
                    595,
                    1500,
                    770
                ),
                radius=28,
                fill=(14, 17, 27, 240),
                outline=(124, 92, 255, 70),
                width=2
            )

            draw.text(
                (470, 620),
                self.prepare_text(
                    "📖 تعريف الروم"
                ),
                font=self.get_font(
                    18,
                    True
                ),
                fill=(154, 132, 255)
            )

            for index, line in enumerate(
                lines
            ):

                draw.text(
                    (
                        470,
                        658 +
                        index * 31
                    ),
                    line,
                    font=font,
                    fill=(190, 195, 207)
                )

        else:

            draw.rounded_rectangle(
                (
                    435,
                    595,
                    1500,
                    735
                ),
                radius=28,
                fill=(14, 17, 27, 240),
                outline=(48, 53, 70),
                width=2
            )

            draw.text(
                (470, 630),
                "FIME COMMUNITY",
                font=self.get_font(
                    18,
                    True
                ),
                fill=(124, 92, 255)
            )

            draw.text(
                (470, 670),
                "Official message • Team Fime",
                font=self.get_font(
                    22
                ),
                fill=(175, 181, 194)
            )

        # ====================================================
        # FOOTER
        # ====================================================

        draw.rounded_rectangle(
            (
                95,
                815,
                1505,
                848
            ),
            radius=16,
            fill=(124, 92, 255)
        )

        draw.text(
            (115, 821),
            "FIME",
            font=self.get_font(
                14,
                True
            ),
            fill="white"
        )

        draw.text(
            (1335, 821),
            "TEAM FIME",
            font=self.get_font(
                14,
                True
            ),
            fill=(235, 236, 242)
        )

        return self.image_to_jpeg(
            canvas,
            quality=88
        )

    # ========================================================
    # TOP SYSTEM
    # ========================================================

    def get_now(self):

        return datetime.now(
            SAUDI_TZ
        )

    def get_period_keys(self):

        now = self.get_now()

        if now.hour >= 22:
            daily_date = now.date()
        else:
            daily_date = (
                now.date() -
                timedelta(days=1)
            )

        daily = daily_date.isoformat()

        week_start = (
            now.date() -
            timedelta(
                days=(now.weekday() + 2) % 7
            )
        )

        weekly = week_start.isoformat()

        monthly = (
            f"{now.year}-{now.month:02d}"
        )

        return (
            daily,
            weekly,
            monthly
        )

    def ensure_top_guild(
        self,
        guild_id
    ):

        key = str(guild_id)

        if key not in self.top_data:

            self.top_data[key] = {
                "day": {},
                "week": {},
                "month": {},
                "all": {}
            }

        for period in (
            "day",
            "week",
            "month",
            "all"
        ):

            self.top_data[key].setdefault(
                period,
                {}
            )

        return self.top_data[key]

    def add_top_point(
        self,
        guild_id,
        user_id
    ):

        guild_data = self.ensure_top_guild(
            guild_id
        )

        daily, weekly, monthly = (
            self.get_period_keys()
        )

        if (
            guild_data["day"].get(
                "_period"
            ) != daily
        ):

            guild_data["day"] = {
                "_period": daily
            }

        if (
            guild_data["week"].get(
                "_period"
            ) != weekly
        ):

            guild_data["week"] = {
                "_period": weekly
            }

        if (
            guild_data["month"].get(
                "_period"
            ) != monthly
        ):

            guild_data["month"] = {
                "_period": monthly
            }

        uid = str(
            user_id
        )

        for period in (
            "day",
            "week",
            "month",
            "all"
        ):

            guild_data[period][uid] = (
                guild_data[period].get(
                    uid,
                    0
                ) + 1
            )

        save_top(
            self.top_data
        )

    def get_top_users(
        self,
        guild,
        period,
        limit=10
    ):

        guild_data = self.ensure_top_guild(
            guild.id
        )

        daily, weekly, monthly = (
            self.get_period_keys()
        )

        if period == "day":

            if (
                guild_data["day"].get(
                    "_period"
                ) != daily
            ):

                guild_data["day"] = {
                    "_period": daily
                }

            source = guild_data["day"]

        elif period == "week":

            if (
                guild_data["week"].get(
                    "_period"
                ) != weekly
            ):

                guild_data["week"] = {
                    "_period": weekly
                }

            source = guild_data["week"]

        elif period == "month":

            if (
                guild_data["month"].get(
                    "_period"
                ) != monthly
            ):

                guild_data["month"] = {
                    "_period": monthly
                }

            source = guild_data["month"]

        else:

            source = guild_data["all"]

        results = []

        for uid, points in source.items():

            if uid == "_period":
                continue

            try:

                member = guild.get_member(
                    int(uid)
                )

            except Exception:
                member = None

            if member:

                results.append(
                    (
                        member,
                        int(points)
                    )
                )

        results.sort(
            key=lambda x: x[1],
            reverse=True
        )

        return results[:limit]

    def build_top_embed(
        self,
        guild,
        period
    ):

        names = {
            "day": "توب اليوم",
            "week": "توب الأسبوع",
            "month": "توب الشهر",
            "all": "توب الكل"
        }

        results = self.get_top_users(
            guild,
            period
        )

        if not results:

            return discord.Embed(
                title=f"🏆 {names[period]}",
                description="ما فيه بيانات كافية للحين.",
                color=discord.Color.blurple()
            )

        medals = {
            1: "🥇",
            2: "🥈",
            3: "🥉"
        }

        lines = []

        for index, (
            member,
            points
        ) in enumerate(
            results,
            1
        ):

            medal = medals.get(
                index,
                f"`#{index}`"
            )

            lines.append(
                f"{medal} {member.mention} — **{points} نقطة**"
            )

        embed = discord.Embed(
            title=f"🏆 {names[period]}",
            description="\n".join(
                lines
            ),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Team Fime • Top System"
        )

        return embed

    def normalize_top(
        self,
        content
    ):

        return " ".join(
            str(content or "").split()
        ).casefold()

    def top_period(
        self,
        content
    ):

        return {
            "day": "day",
            "week": "week",
            "month": "month",
            "all": "all"
        }.get(
            self.normalize_top(
                content
            )
        )

    def can_use_top(
        self,
        message,
        cfg
    ):

        if message.author.id == OWNER_ID:
            return True

        roles = {
            int(x)
            for x in cfg.get(
                "top_allowed_role_ids",
                []
            )
            if str(x).isdigit()
        }

        if roles.intersection(
            role.id
            for role in getattr(
                message.author,
                "roles",
                []
            )
        ):
            return True

        channel_id = cfg.get(
            "top_channel_id"
        )

        return (
            channel_id
            and
            message.channel.id ==
            int(channel_id)
        )

    # ========================================================
    # TOP COMMANDS
    # ========================================================

    @app_commands.command(
        name="توب-روم",
        description="تحديد روم التوب"
    )
    async def top_channel(
        self,
        interaction,
        channel: discord.TextChannel = None
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["top_channel_id"] = (
            channel.id
            if channel
            else None
        )

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ تم تحديد روم التوب: {channel.mention}"
                if channel
                else
                "✅ تم إلغاء تحديد روم التوب."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="توب-رتبة",
        description="إضافة رتبة للتوب"
    )
    async def top_role(
        self,
        interaction,
        role: discord.Role
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        roles = cfg[
            "top_allowed_role_ids"
        ]

        if role.id not in roles:
            roles.append(
                role.id
            )

        save_config(
            self.config
        )

        await interaction.response.send_message(
            f"✅ تمت إضافة {role.mention} للتوب.",
            ephemeral=True
        )

    @app_commands.command(
        name="توب-رتبة-إزالة",
        description="إزالة رتبة من التوب"
    )
    async def top_role_remove(
        self,
        interaction,
        role: discord.Role
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if role.id in cfg[
            "top_allowed_role_ids"
        ]:

            cfg[
                "top_allowed_role_ids"
            ].remove(
                role.id
            )

        save_config(
            self.config
        )

        await interaction.response.send_message(
            f"✅ تمت إزالة {role.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="توب-حالة",
        description="عرض حالة التوب"
    )
    async def top_status(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel = None

        if cfg.get(
            "top_channel_id"
        ):

            channel = interaction.guild.get_channel(
                int(
                    cfg[
                        "top_channel_id"
                    ]
                )
            )

        roles = []

        for rid in cfg[
            "top_allowed_role_ids"
        ]:

            role = interaction.guild.get_role(
                int(rid)
            )

            if role:
                roles.append(
                    role.mention
                )

        await interaction.response.send_message(
            (
                "## 🏆 حالة التوب\n\n"
                f"📍 **الروم:** "
                f"{channel.mention if channel else 'غير محدد'}\n\n"
                f"🎖️ **الرتب:** "
                f"{', '.join(roles) if roles else 'لا توجد'}"
            ),
            ephemeral=True
        )

    # ========================================================
    # LINE SYSTEM
    # ========================================================

    @app_commands.command(
        name="خط",
        description="تشغيل نظام الخط"
    )
    async def line_setup(
        self,
        interaction,
        image: discord.Attachment,
        channel: discord.TextChannel = None
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        if not self.is_supported_image(
            image
        ):

            await interaction.response.send_message(
                "❌ صيغة الصورة غير مدعومة.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        cfg = self.get_config(
            interaction.guild.id
        )

        try:

            data = await image.read()

            storage = (
                channel
                or
                interaction.channel
            )

            if not isinstance(
                storage,
                discord.TextChannel
            ):

                raise RuntimeError(
                    "ما لقيت روم تخزين."
                )

            old_channel = None

            if cfg.get(
                "storage_channel_id"
            ):

                old_channel = interaction.guild.get_channel(
                    int(
                        cfg[
                            "storage_channel_id"
                        ]
                    )
                )

            if (
                old_channel
                and
                cfg.get(
                    "storage_message_id"
                )
            ):

                try:

                    old = await old_channel.fetch_message(
                        int(
                            cfg[
                                "storage_message_id"
                            ]
                        )
                    )

                    await old.delete()

                except Exception:
                    pass

            stored = await storage.send(
                "🖼️ **Fime Line Storage**",
                file=discord.File(
                    io.BytesIO(data),
                    filename=image.filename
                )
            )

            cfg["image_url"] = (
                stored.attachments[0].url
            )

            cfg[
                "storage_channel_id"
            ] = storage.id

            cfg[
                "storage_message_id"
            ] = stored.id

            cfg["channel_id"] = (
                channel.id
                if channel
                else None
            )

            cfg["enabled"] = True

            save_config(
                self.config
            )

            await interaction.followup.send(
                "✅ **تم تشغيل نظام الخط.**",
                ephemeral=True
            )

        except Exception as error:

            print(
                "❌ Line error:",
                error
            )

            await interaction.followup.send(
                f"❌ فشل تشغيل الخط: `{type(error).__name__}`",
                ephemeral=True
            )

    @app_commands.command(
        name="خط-إيقاف",
        description="إيقاف نظام الخط"
    )
    async def line_off(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["enabled"] = False

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🛑 تم إيقاف الخط.",
            ephemeral=True
        )

    @app_commands.command(
        name="خط-حالة",
        description="حالة الخط"
    )
    async def line_status(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel = None

        if cfg.get(
            "channel_id"
        ):

            channel = interaction.guild.get_channel(
                int(
                    cfg[
                        "channel_id"
                    ]
                )
            )

        await interaction.response.send_message(
            (
                "## 🖼️ حالة الخط\n\n"
                f"الحالة: **"
                f"{'🟢 مفعل' if cfg['enabled'] else '🔴 متوقف'}"
                f"**\n"
                f"الروم: "
                f"{channel.mention if channel else 'كل الرومات'}"
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="خط-روم",
        description="تغيير روم الخط"
    )
    async def line_channel(
        self,
        interaction,
        channel: discord.TextChannel = None
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["channel_id"] = (
            channel.id
            if channel
            else None
        )

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ الخط يعمل الآن في {channel.mention}."
                if channel
                else
                "✅ الخط يعمل الآن في جميع الرومات."
            ),
            ephemeral=True
        )

    # ========================================================
    # FIME
    # ========================================================

    @app_commands.command(
        name="فيم-رسالة",
        description="تغيير رد كلمة فيم"
    )
    async def fime_message(
        self,
        interaction,
        message: str
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        if len(message) > 2000:

            await interaction.response.send_message(
                "❌ الرسالة طويلة جدًا.",
                ephemeral=True
            )
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "fime_word_response"
        ] = message

        cfg[
            "fime_word_enabled"
        ] = True

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "✅ تم تحديث رد فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-تشغيل",
        description="تشغيل نظام فيم"
    )
    async def fime_enable(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "fime_word_enabled"
        ] = True

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🟢 تم تشغيل نظام فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-إيقاف",
        description="إيقاف نظام فيم"
    )
    async def fime_disable(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "fime_word_enabled"
        ] = False

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🔴 تم إيقاف نظام فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-حالة",
        description="حالة نظام فيم"
    )
    async def fime_status(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        await interaction.response.send_message(
            (
                "## 🌀 حالة فيم\n\n"
                f"الحالة: **"
                f"{'🟢 مفعل' if cfg['fime_word_enabled'] else '🔴 متوقف'}"
                f"**\n\n"
                f"**الرد:**\n"
                f"{cfg['fime_word_response']}"
            ),
            ephemeral=True
        )

    # ========================================================
    # ROOM DEFINITION
    # ========================================================

    @app_commands.command(
        name="تعريف-الروم",
        description="حفظ تعريف الروم"
    )
    async def set_room_definition(
        self,
        interaction,
        definition: str
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        if len(definition) > 800:

            await interaction.response.send_message(
                "❌ التعريف طويل جدًا.",
                ephemeral=True
            )
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "say_room_definition"
        ] = definition

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "✅ تم حفظ تعريف الروم.",
            ephemeral=True
        )

    @app_commands.command(
        name="تعريف-الروم-حذف",
        description="حذف تعريف الروم"
    )
    async def delete_room_definition(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "say_room_definition"
        ] = ""

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🗑️ تم حذف تعريف الروم.",
            ephemeral=True
        )

    # ========================================================
    # SAY
    # ========================================================

    @app_commands.command(
        name="say",
        description="إرسال رسالة احترافية من البوت"
    )
    @app_commands.describe(
        message="الرسالة",
        channel="الروم",
        avatar="الافتار",
        banner="البنر",
        template="قالب اختياري",
        room_definition="تعريف اختياري لهذا الـ /say"
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

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        if len(message) > 2000:

            await interaction.response.send_message(
                "❌ الرسالة لا تتجاوز 2000 حرف.",
                ephemeral=True
            )
            return

        target = (
            channel
            or
            interaction.channel
        )

        if not isinstance(
            target,
            discord.TextChannel
        ):

            await interaction.response.send_message(
                "❌ اختر رومًا نصيًا.",
                ephemeral=True
            )
            return

        for attachment in (
            avatar,
            banner,
            template
        ):

            if (
                attachment
                and
                not self.is_supported_image(
                    attachment
                )
            ):

                await interaction.response.send_message(
                    "❌ أحد الملفات المرفوعة ليس صورة مدعومة.",
                    ephemeral=True
                )
                return

        cfg = self.get_config(
            interaction.guild.id
        )

        definition = str(
            room_definition
            if room_definition is not None
            else cfg.get(
                "say_room_definition",
                ""
            )
        ).strip()

        await interaction.response.defer(
            ephemeral=True
        )

        has_media = any(
            (
                avatar,
                banner,
                template,
                definition
            )
        )

        try:

            if has_media:

                # ==================================================
                # IMPORTANT:
                # كل صورة تنقرأ مرة واحدة فقط.
                # ==================================================

                avatar_image = None
                banner_image = None
                template_image = None

                tasks = []

                if avatar:
                    tasks.append(
                        (
                            "avatar",
                            self.read_image_attachment(
                                avatar
                            )
                        )
                    )

                if banner:
                    tasks.append(
                        (
                            "banner",
                            self.read_image_attachment(
                                banner
                            )
                        )
                    )

                if template:
                    tasks.append(
                        (
                            "template",
                            self.read_image_attachment(
                                template
                            )
                        )
                    )

                if tasks:

                    results = await asyncio.gather(
                        *[
                            task
                            for _, task in tasks
                        ]
                    )

                    for (
                        index,
                        (
                            name,
                            _
                        )
                    ) in enumerate(
                        tasks
                    ):

                        if name == "avatar":
                            avatar_image = results[index]

                        elif name == "banner":
                            banner_image = results[index]

                        elif name == "template":
                            template_image = results[index]

                # ==================================================
                # FAST DOWNLOAD FILES
                # ==================================================

                avatar_bytes = (
                    self.image_to_jpeg(
                        avatar_image,
                        (700, 700),
                        82
                    )
                    if avatar_image
                    else None
                )

                banner_bytes = (
                    self.image_to_jpeg(
                        banner_image,
                        (1400, 650),
                        82
                    )
                    if banner_image
                    else None
                )

                # ==================================================
                # FULL PROFILE
                # ==================================================

                full_profile_bytes = (
                    self.create_fast_profile(
                        avatar_image,
                        banner_image
                    )
                    if (
                        avatar_image
                        or
                        banner_image
                    )
                    else None
                )

                # ==================================================
                # SAY IMAGE
                # لا يعيد تحميل الصور من Discord
                # ==================================================

                generated_bytes = (
                    await asyncio.to_thread(
                        self.create_say_image_sync,
                        avatar_image,
                        banner_image,
                        template_image,
                        definition
                    )
                )

                avatar_url = (
                    avatar.url
                    if avatar
                    else None
                )

                banner_url = (
                    banner.url
                    if banner
                    else None
                )

                view = SayProfileView(
                    avatar_bytes=avatar_bytes,
                    banner_bytes=banner_bytes,
                    full_profile_bytes=full_profile_bytes,
                    room_definition=definition,
                    avatar_url=avatar_url,
                    banner_url=banner_url,
                    username=interaction.user.display_name
                )

                await target.send(
                    content=message,
                    file=discord.File(
                        io.BytesIO(
                            generated_bytes
                        ),
                        filename="fime-say.jpg"
                    ),
                    view=view,
                    allowed_mentions=discord.AllowedMentions.none()
                )

            else:

                await target.send(
                    content=message,
                    allowed_mentions=discord.AllowedMentions.none()
                )

        except Exception as error:

            print(
                "❌ SAY error:",
                error
            )

            await interaction.followup.send(
                f"❌ فشل /say: `{type(error).__name__}`",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            (
                "✅ **تم إرسال الرسالة.**\n"
                f"📍 {target.mention}"
            ),
            ephemeral=True
        )

    # ========================================================
    # SYNC WRAPPER
    # ========================================================

    def create_say_image_sync(
        self,
        avatar_image,
        banner_image,
        template_image,
        room_definition
    ):

        WIDTH = 1600
        HEIGHT = 900

        if template_image:

            canvas = self.crop_to_fill(
                template_image,
                (
                    WIDTH,
                    HEIGHT
                )
            )

            overlay = Image.new(
                "RGBA",
                canvas.size,
                (3, 5, 10, 90)
            )

            canvas.alpha_composite(
                overlay
            )

        else:

            canvas = Image.new(
                "RGBA",
                (
                    WIDTH,
                    HEIGHT
                ),
                (5, 7, 13, 255)
            )

            glow = Image.new(
                "RGBA",
                canvas.size,
                (0, 0, 0, 0)
            )

            gd = ImageDraw.Draw(
                glow
            )

            gd.ellipse(
                (
                    950,
                    -300,
                    1800,
                    520
                ),
                fill=(124, 92, 255, 75)
            )

            gd.ellipse(
                (
                    -450,
                    580,
                    650,
                    1250
                ),
                fill=(35, 110, 255, 42)
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(
                    110
                )
            )

            canvas.alpha_composite(
                glow
            )

            draw = ImageDraw.Draw(
                canvas
            )

            draw.rounded_rectangle(
                (
                    35,
                    35,
                    WIDTH - 35,
                    HEIGHT - 35
                ),
                radius=48,
                fill=(10, 13, 22, 247),
                outline=(55, 61, 82),
                width=2
            )

        draw = ImageDraw.Draw(
            canvas
        )

        # ====================================================
        # HEADER
        # ====================================================

        draw.text(
            (90, 72),
            "TEAM FIME",
            font=self.get_font(
                35,
                True
            ),
            fill=(248, 249, 252)
        )

        draw.text(
            (92, 118),
            "OFFICIAL COMMUNITY",
            font=self.get_font(
                16,
                True
            ),
            fill=(154, 132, 255)
        )

        draw.rounded_rectangle(
            (
                1310,
                78,
                1505,
                122
            ),
            radius=22,
            fill=(124, 92, 255, 35),
            outline=(124, 92, 255, 90),
            width=1
        )

        draw.ellipse(
            (
                1330,
                91,
                1346,
                107
            ),
            fill=(76, 220, 130)
        )

        draw.text(
            (1360, 88),
            "FIME",
            font=self.get_font(
                15,
                True
            ),
            fill=(220, 221, 230)
        )

        # ====================================================
        # BANNER
        # ====================================================

        if banner_image:

            banner = self.crop_to_fill(
                banner_image,
                (
                    1410,
                    330
                )
            )

            canvas.paste(
                banner,
                (
                    95,
                    170
                )
            )

            dark = Image.new(
                "RGBA",
                (
                    1410,
                    330
                ),
                (0, 0, 0, 0)
            )

            dd = ImageDraw.Draw(
                dark
            )

            dd.rectangle(
                (
                    0,
                    205,
                    1410,
                    330
                ),
                fill=(3, 4, 8, 155)
            )

            canvas.alpha_composite(
                dark,
                (
                    95,
                    170
                )
            )

        else:

            draw.rounded_rectangle(
                (
                    95,
                    170,
                    1505,
                    500
                ),
                radius=32,
                fill=(15, 18, 29),
                outline=(124, 92, 255, 60),
                width=2
            )

            draw.text(
                (145, 280),
                "FIME",
                font=self.get_font(
                    110,
                    True
                ),
                fill=(124, 92, 255, 65)
            )

        # ====================================================
        # AVATAR
        # ====================================================

        if avatar_image:

            avatar = self.crop_to_fill(
                avatar_image,
                (
                    250,
                    250
                )
            )

            mask = Image.new(
                "L",
                (
                    250,
                    250
                ),
                0
            )

            ImageDraw.Draw(
                mask
            ).ellipse(
                (
                    0,
                    0,
                    250,
                    250
                ),
                fill=255
            )

            avatar_rgba = Image.new(
                "RGBA",
                (
                    250,
                    250
                ),
                (0, 0, 0, 0)
            )

            avatar_rgba.paste(
                avatar,
                (0, 0),
                mask
            )

            canvas.paste(
                avatar_rgba,
                (
                    125,
                    390
                ),
                avatar_rgba
            )

            draw.ellipse(
                (
                    115,
                    380,
                    385,
                    650
                ),
                outline=(6, 8, 14),
                width=14
            )

            draw.ellipse(
                (
                    115,
                    380,
                    385,
                    650
                ),
                outline=(124, 92, 255),
                width=5
            )

        else:

            draw.ellipse(
                (
                    125,
                    390,
                    375,
                    640
                ),
                fill=(24, 28, 40),
                outline=(124, 92, 255),
                width=5
            )

            self.draw_center(
                draw,
                250,
                460,
                "F",
                self.get_font(
                    80,
                    True
                ),
                (154, 132, 255)
            )

        # ====================================================
        # PROFILE
        # ====================================================

        draw.text(
            (435, 405),
            "FIME",
            font=self.get_font(
                52,
                True
            ),
            fill=(247, 248, 252)
        )

        draw.text(
            (438, 472),
            "Official Community Message",
            font=self.get_font(
                23
            ),
            fill=(151, 158, 176)
        )

        draw.rounded_rectangle(
            (
                435,
                520,
                735,
                565
            ),
            radius=22,
            fill=(124, 92, 255, 35),
            outline=(124, 92, 255, 100)
        )

        draw.text(
            (460, 532),
            "OFFICIAL PROFILE",
            font=self.get_font(
                15,
                True
            ),
            fill=(166, 147, 255)
        )

        # ====================================================
        # DEFINITION
        # ====================================================

        if room_definition:

            text = self.prepare_text(
                room_definition
            )

            words = text.split()

            lines = []

            current = ""

            font = self.get_font(
                20
            )

            for word in words:

                candidate = (
                    f"{current} {word}".strip()
                )

                bbox = draw.textbbox(
                    (0, 0),
                    candidate,
                    font=font
                )

                if (
                    bbox[2] -
                    bbox[0]
                ) <= 830:

                    current = candidate

                else:

                    if current:
                        lines.append(
                            current
                        )

                    current = word

            if current:
                lines.append(
                    current
                )

            lines = lines[:3]

            draw.rounded_rectangle(
                (
                    435,
                    595,
                    1500,
                    770
                ),
                radius=28,
                fill=(14, 17, 27, 240),
                outline=(124, 92, 255, 70),
                width=2
            )

            draw.text(
                (470, 620),
                self.prepare_text(
                    "📖 تعريف الروم"
                ),
                font=self.get_font(
                    18,
                    True
                ),
                fill=(154, 132, 255)
            )

            for index, line in enumerate(
                lines
            ):

                draw.text(
                    (
                        470,
                        658 +
                        index * 31
                    ),
                    line,
                    font=font,
                    fill=(190, 195, 207)
                )

        else:

            draw.rounded_rectangle(
                (
                    435,
                    595,
                    1500,
                    735
                ),
                radius=28,
                fill=(14, 17, 27, 240),
                outline=(48, 53, 70),
                width=2
            )

            draw.text(
                (470, 630),
                "FIME COMMUNITY",
                font=self.get_font(
                    18,
                    True
                ),
                fill=(124, 92, 255)
            )

            draw.text(
                (470, 670),
                "Official message • Team Fime",
                font=self.get_font(
                    22
                ),
                fill=(175, 181, 194)
            )

        # ====================================================
        # FOOTER
        # ====================================================

        draw.rounded_rectangle(
            (
                95,
                815,
                1505,
                848
            ),
            radius=16,
            fill=(124, 92, 255)
        )

        draw.text(
            (115, 821),
            "FIME",
            font=self.get_font(
                14,
                True
            ),
            fill="white"
        )

        draw.text(
            (1335, 821),
            "TEAM FIME",
            font=self.get_font(
                14,
                True
            ),
            fill=(235, 236, 242)
        )

        return self.image_to_jpeg(
            canvas,
            quality=88
        )

    # ========================================================
    # SERVER INFORMATION
    # ========================================================

    def build_server_embed(
        self,
        guild
    ):

        owner = guild.owner

        embed = discord.Embed(
            title=f"🛰️ {guild.name}",
            description=(
                "معلومات السيرفر الذي يستخدم فيه البوت حاليًا."
            ),
            color=discord.Color.blurple()
        )

        if guild.icon:

            embed.set_thumbnail(
                url=guild.icon.url
            )

        embed.add_field(
            name="🆔 Server ID",
            value=f"`{guild.id}`",
            inline=False
        )

        embed.add_field(
            name="👥 الأعضاء",
            value=f"`{guild.member_count:,}`",
            inline=True
        )

        embed.add_field(
            name="💬 القنوات",
            value=f"`{len(guild.channels):,}`",
            inline=True
        )

        embed.add_field(
            name="🎭 الرتب",
            value=f"`{len(guild.roles):,}`",
            inline=True
        )

        embed.add_field(
            name="👑 المالك",
            value=(
                owner.mention
                if owner
                else
                "غير معروف"
            ),
            inline=True
        )

        embed.add_field(
            name="📅 إنشاء السيرفر",
            value=discord.utils.format_dt(
                guild.created_at,
                "F"
            ),
            inline=False
        )

        embed.set_footer(
            text=(
                f"Team Fime • البوت موجود في "
                f"{len(self.bot.guilds)} سيرفر"
            )
        )

        return embed

    @app_commands.command(
        name="server",
        description="معلومات السيرفرات التي يستخدم فيها البوت"
    )
    async def server_command(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        current = interaction.guild

        if not current:
            return

        embed = self.build_server_embed(
            current
        )

        embed.title = (
            "🛰️ معلومات البوت والسيرفر"
        )

        embed.description = (
            f"**البوت موجود حاليًا في "
            f"`{len(self.bot.guilds)}` سيرفر.**\n\n"
            f"السيرفر الحالي: **{current.name}**"
        )

        embed.add_field(
            name="🌐 إجمالي السيرفرات",
            value=f"`{len(self.bot.guilds):,}`",
            inline=True
        )

        total_members = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )

        embed.add_field(
            name="👥 إجمالي الأعضاء",
            value=f"`{total_members:,}`",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @app_commands.command(
        name="سيرفر",
        description="معلومات السيرفرات التي يستخدم فيها البوت"
    )
    async def arabic_server_command(
        self,
        interaction
    ):

        await self.server_command.callback(
            self,
            interaction
        )

    # ========================================================
    # EDIT BOT MESSAGE
    # ========================================================

    @app_commands.command(
        name="تعديل-رسالة",
        description="تعديل رسالة أرسلها البوت"
    )
    @app_commands.describe(
        channel="الروم الذي توجد فيه الرسالة",
        message_id="ID الرسالة",
        new_message="النص الجديد"
    )
    async def edit_bot_message(
        self,
        interaction,
        channel: discord.TextChannel,
        message_id: str,
        new_message: str
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not message_id.isdigit():

            await interaction.response.send_message(
                "❌ Message ID غير صحيح.",
                ephemeral=True
            )
            return

        if len(new_message) > 2000:

            await interaction.response.send_message(
                "❌ الرسالة تتجاوز 2000 حرف.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:

            message = await channel.fetch_message(
                int(message_id)
            )

        except discord.NotFound:

            await interaction.followup.send(
                "❌ ما لقيت الرسالة.",
                ephemeral=True
            )
            return

        except discord.Forbidden:

            await interaction.followup.send(
                "❌ ما أقدر أوصل للروم أو الرسالة.",
                ephemeral=True
            )
            return

        if (
            not self.bot.user
            or
            message.author.id !=
            self.bot.user.id
        ):

            await interaction.followup.send(
                "❌ تقدر تعدل رسائل البوت فقط.",
                ephemeral=True
            )
            return

        try:

            await message.edit(
                content=new_message,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            await interaction.followup.send(
                f"❌ فشل تعديل الرسالة: `{type(error).__name__}`",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            (
                "✅ **تم تعديل رسالة البوت.**\n"
                f"📍 {channel.mention}\n"
                f"🆔 `{message.id}`"
            ),
            ephemeral=True
        )

    # ========================================================
    # SUGGESTIONS
    # ========================================================

    def get_suggestion_id(
        self
    ):

        numbers = []

        for key in self.suggestions.keys():

            if str(key).isdigit():

                numbers.append(
                    int(key)
                )

        return str(
            max(
                numbers,
                default=0
            ) + 1
        )

    def suggestion_embed(
        self,
        suggestion
    ):

        status = suggestion.get(
            "status",
            "قيد المراجعة"
        )

        colors = {
            "قيد المراجعة": discord.Color.blurple(),
            "قيد التنفيذ": discord.Color.orange(),
            "مقبول": discord.Color.green(),
            "مرفوض": discord.Color.red(),
            "مكتمل": discord.Color.teal()
        }

        status_emojis = {
            "قيد المراجعة": "🕐",
            "قيد التنفيذ": "🔧",
            "مقبول": "✅",
            "مرفوض": "❌",
            "مكتمل": "🏁"
        }

        embed = discord.Embed(
            title=(
                f"💡 اقتراح #{suggestion['id']}"
            ),
            description=suggestion[
                "text"
            ],
            color=colors.get(
                status,
                discord.Color.blurple()
            )
        )

        embed.add_field(
            name="📌 الحالة",
            value=(
                f"{status_emojis.get(status, '📌')} "
                f"**{status}**"
            ),
            inline=True
        )

        embed.add_field(
            name="👤 صاحب الاقتراح",
            value=(
                f"<@{suggestion['user_id']}>"
            ),
            inline=True
        )

        created_at = suggestion.get(
            "created_at"
        )

        if created_at:

            try:

                dt = datetime.fromisoformat(
                    created_at
                )

                embed.add_field(
                    name="🕐 التاريخ",
                    value=discord.utils.format_dt(
                        dt,
                        "R"
                    ),
                    inline=True
                )

            except Exception:
                pass

        if suggestion.get(
            "admin_reply"
        ):

            embed.add_field(
                name="💬 رد الإدارة",
                value=suggestion[
                    "admin_reply"
                ][:1024],
                inline=False
            )

        embed.set_footer(
            text=(
                "Team Fime • Suggestions "
                "• استخدم الأزرار أسفل الرسالة"
            )
        )

        return embed

    async def create_suggestion_data(
        self,
        guild,
        channel,
        user,
        text
    ):

        sid = self.get_suggestion_id()

        data = {
            "id": sid,
            "guild_id": guild.id,
            "channel_id": channel.id,
            "message_id": None,
            "user_id": user.id,
            "text": text,
            "status": "قيد المراجعة",
            "admin_reply": "",
            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        message = await channel.send(
            embed=self.suggestion_embed(
                data
            ),
            view=SuggestionView(
                self,
                sid
            ),
            allowed_mentions=discord.AllowedMentions.none()
        )

        data[
            "message_id"
        ] = message.id

        self.suggestions[sid] = data

        save_suggestions(
            self.suggestions
        )

        await self.send_suggestion_log(
            data,
            guild
        )

        return data

    async def send_suggestion_log(
        self,
        data,
        guild
    ):

        cfg = self.get_config(
            guild.id
        )

        log_id = cfg.get(
            "suggestions_log_channel_id"
        )

        if not log_id:
            return

        channel = guild.get_channel(
            int(log_id)
        )

        if not channel:
            return

        embed = discord.Embed(
            title="📝 اقتراح جديد",
            description=data["text"],
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="🔢 الرقم",
            value=f"`#{data['id']}`",
            inline=True
        )

        embed.add_field(
            name="👤 العضو",
            value=f"<@{data['user_id']}>",
            inline=True
        )

        try:

            await channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            print(
                "⚠️ Suggestion log error:",
                error
            )

    # ========================================================
    # MANUAL SUGGESTION
    # ========================================================

    @app_commands.command(
        name="اقتراح",
        description="إرسال اقتراح للسيرفر"
    )
    @app_commands.describe(
        suggestion="اكتب اقتراحك"
    )
    async def create_suggestion(
        self,
        interaction,
        suggestion: str
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "❌ هذا الأمر داخل السيرفر فقط.",
                ephemeral=True
            )
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel_id = cfg.get(
            "suggestions_channel_id"
        )

        if not channel_id:

            await interaction.response.send_message(
                "❌ ما تم تحديد روم الاقتراحات.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(
            int(channel_id)
        )

        if not channel:

            await interaction.response.send_message(
                "❌ روم الاقتراحات غير موجود.",
                ephemeral=True
            )
            return

        if len(suggestion) < 5:

            await interaction.response.send_message(
                "❌ الاقتراح قصير جدًا.",
                ephemeral=True
            )
            return

        if len(suggestion) > 1500:

            await interaction.response.send_message(
                "❌ الاقتراح طويل جدًا.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:

            data = await self.create_suggestion_data(
                interaction.guild,
                channel,
                interaction.user,
                suggestion
            )

            await interaction.followup.send(
                (
                    f"✅ تم إرسال اقتراحك برقم "
                    f"**#{data['id']}**."
                ),
                ephemeral=True
            )

        except Exception as error:

            print(
                "❌ Suggestion create error:",
                error
            )

            await interaction.followup.send(
                "❌ تعذر إرسال الاقتراح.",
                ephemeral=True
            )

    # ========================================================
    # AUTO SUGGESTION ROOM
    # ========================================================

    async def handle_suggestion_message(
        self,
        message,
        cfg
    ):

        channel_id = cfg.get(
            "suggestions_channel_id"
        )

        if not channel_id:
            return False

        if (
            message.channel.id !=
            int(channel_id)
        ):
            return False

        text = (
            message.content or ""
        ).strip()

        if not text and not message.attachments:

            try:

                await message.delete()

            except Exception:
                pass

            return True

        if len(text) < 5 and not message.attachments:

            try:

                await message.delete()

            except Exception:
                pass

            return True

        if len(text) > 1500:

            text = text[:1500] + "…"

        # ====================================================
        # ATTACHMENT SUPPORT
        # ====================================================

        image_url = None

        for attachment in message.attachments:

            if self.is_supported_image(
                attachment
            ):

                image_url = attachment.url
                break

        if image_url:

            if text:

                text += (
                    f"\n\n🖼️ [الصورة المرفقة]"
                    f"({image_url})"
                )

            else:

                text = (
                    f"🖼️ [الصورة المرفقة]"
                    f"({image_url})"
                )

        try:

            await message.delete()

        except discord.Forbidden:

            print(
                "❌ ما أقدر أحذف رسالة الاقتراح."
            )

            return True

        except Exception as error:

            print(
                "⚠️ Suggestion delete error:",
                error
            )

        try:

            await self.create_suggestion_data(
                message.guild,
                message.channel,
                message.author,
                text
            )

        except Exception as error:

            print(
                "❌ Auto suggestion error:",
                error
            )

            try:

                await message.channel.send(
                    (
                        "❌ تعذر تحويل الاقتراح "
                        "إلى رسالة البوت."
                    ),
                    delete_after=6
                )

            except Exception:
                pass

        return True

    # ========================================================
    # SET SUGGESTION CHANNEL
    # ========================================================

    @app_commands.command(
        name="اقتراح-روم",
        description="تحديد روم الاقتراحات"
    )
    async def suggestion_channel(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "suggestions_channel_id"
        ] = channel.id

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ تم تحديد روم الاقتراحات: "
                f"{channel.mention}\n\n"
                "💡 الآن أي عضو يكتب داخل الروم "
                "سيتم تحويل رسالته تلقائيًا إلى اقتراح من البوت."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="اقتراح-سجل",
        description="تحديد روم سجل الاقتراحات"
    )
    async def suggestion_log_channel(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "suggestions_log_channel_id"
        ] = channel.id

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ روم سجل الاقتراحات: "
                f"{channel.mention}"
            ),
            ephemeral=True
        )

    # ========================================================
    # SUGGESTION STATUS
    # ========================================================

    @app_commands.command(
        name="اقتراح-حالة",
        description="تغيير حالة اقتراح"
    )
    @app_commands.describe(
        suggestion_id="رقم الاقتراح",
        status="الحالة الجديدة"
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(
                name="قيد المراجعة",
                value="قيد المراجعة"
            ),
            app_commands.Choice(
                name="قيد التنفيذ",
                value="قيد التنفيذ"
            ),
            app_commands.Choice(
                name="مقبول",
                value="مقبول"
            ),
            app_commands.Choice(
                name="مرفوض",
                value="مرفوض"
            ),
            app_commands.Choice(
                name="مكتمل",
                value="مكتمل"
            )
        ]
    )
    async def suggestion_status(
        self,
        interaction,
        suggestion_id: str,
        status: app_commands.Choice[str]
    ):

        if await self.owner_only(
            interaction
        ):
            return

        data = self.suggestions.get(
            suggestion_id
        )

        if not data:

            await interaction.response.send_message(
                "❌ الاقتراح غير موجود.",
                ephemeral=True
            )
            return

        data[
            "status"
        ] = status.value

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data
        )

        await interaction.response.send_message(
            (
                f"✅ تم تغيير الحالة إلى "
                f"**{status.value}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # ADMIN REPLY
    # ========================================================

    @app_commands.command(
        name="اقتراح-رد",
        description="إضافة رد الإدارة على اقتراح"
    )
    async def suggestion_reply(
        self,
        interaction,
        suggestion_id: str,
        reply: str
    ):

        if await self.owner_only(
            interaction
        ):
            return

        data = self.suggestions.get(
            suggestion_id
        )

        if not data:

            await interaction.response.send_message(
                "❌ الاقتراح غير موجود.",
                ephemeral=True
            )
            return

        data[
            "admin_reply"
        ] = reply[:1024]

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data
        )

        await interaction.response.send_message(
            "✅ تم إضافة رد الإدارة.",
            ephemeral=True
        )

    # ========================================================
    # ACCEPT / REJECT
    # ========================================================

    async def change_suggestion_status(
        self,
        interaction,
        suggestion_id,
        status
    ):

        if interaction.user.id != OWNER_ID:

            await interaction.response.send_message(
                "❌ هذا الزر للإدارة فقط.",
                ephemeral=True
            )
            return

        data = self.suggestions.get(
            str(suggestion_id)
        )

        if not data:

            await interaction.response.send_message(
                "❌ الاقتراح غير موجود.",
                ephemeral=True
            )
            return

        if data.get(
            "status"
        ) in (
            "مقبول",
            "مرفوض"
        ):

            await interaction.response.send_message(
                (
                    f"ℹ️ الاقتراح بالفعل "
                    f"**{data['status']}**."
                ),
                ephemeral=True
            )
            return

        data[
            "status"
        ] = status

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data,
            disable_buttons=True
        )

        await interaction.response.send_message(
            (
                f"{'✅' if status == 'مقبول' else '❌'} "
                f"تم تسجيل الاقتراح كـ **{status}**."
            ),
            ephemeral=True
        )

    # ========================================================
    # REFRESH SUGGESTION
    # ========================================================

    async def refresh_suggestion(
        self,
        data,
        disable_buttons=False
    ):

        guild = self.bot.get_guild(
            int(
                data["guild_id"]
            )
        )

        if not guild:
            return

        channel = guild.get_channel(
            int(
                data["channel_id"]
            )
        )

        if not channel:
            return

        try:

            message = await channel.fetch_message(
                int(
                    data["message_id"]
                )
            )

            view = None

            if not disable_buttons:

                view = SuggestionView(
                    self,
                    data["id"]
                )

            await message.edit(
                embed=self.suggestion_embed(
                    data
                ),
                view=view,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            print(
                "⚠️ Suggestion refresh error:",
                error
            )

    # ========================================================
    # TOP / FIME / LINE / SUGGESTIONS LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message
    ):

        if message.author.bot:
            return

        if not message.guild:
            return

        cfg = self.get_config(
            message.guild.id
        )

        # ====================================================
        # SUGGESTIONS FIRST
        # ====================================================

        suggestion_handled = (
            await self.handle_suggestion_message(
                message,
                cfg
            )
        )

        if suggestion_handled:
            return

        # ====================================================
        # TOP
        # ====================================================

        self.add_top_point(
            message.guild.id,
            message.author.id
        )

        period = self.top_period(
            message.content
        )

        if (
            period
            and
            self.can_use_top(
                message,
                cfg
            )
        ):

            try:

                await message.channel.send(
                    embed=self.build_top_embed(
                        message.guild,
                        period
                    ),
                    view=TopSelectView(
                        self,
                        message.guild.id
                    ),
                    allowed_mentions=discord.AllowedMentions.none()
                )

            except Exception as error:

                print(
                    "❌ TOP error:",
                    error
                )

            return

        # ====================================================
        # FIME
        # ====================================================

        normalized = (
            " ".join(
                message.content.strip().split()
            ).casefold()
        )

        if cfg.get(
            "fime_word_enabled",
            True
        ):

            if (
                normalized == "فيم"
                or
                (
                    cfg.get(
                        "fime_word_accept_fimi",
                        False
                    )
                    and
                    normalized == "فيمي"
                )
            ):

                try:

                    await message.channel.send(
                        cfg.get(
                            "fime_word_response",
                            "هلا؟ وش تبي يا فايم؟"
                        ),
                        allowed_mentions=discord.AllowedMentions.none()
                    )

                except Exception as error:

                    print(
                        "❌ Fime error:",
                        error
                    )

        # ====================================================
        # LINE
        # ====================================================

        if not cfg.get(
            "enabled"
        ):
            return

        image_url = cfg.get(
            "image_url"
        )

        if not image_url:
            return

        channel_id = cfg.get(
            "channel_id"
        )

        if (
            channel_id
            and
            message.channel.id !=
            int(channel_id)
        ):
            return

        me = message.guild.me

        if not me:
            return

        permissions = (
            message.channel.permissions_for(
                me
            )
        )

        if not permissions.send_messages:
            return

        try:

            await message.channel.send(
                image_url,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            print(
                "⚠️ Line error:",
                error
            )

    # ========================================================
    # JOIN
    # ========================================================

    async def send_join_mention(
        self,
        member
    ):

        cfg = self.get_config(
            member.guild.id
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

        channel = member.guild.get_channel(
            int(channel_id)
        )

        if not channel:
            return

        try:

            sent = await channel.send(
                member.mention,
                allowed_mentions=discord.AllowedMentions(
                    users=True
                )
            )

            duration = cfg.get(
                "join_mention_duration",
                2
            )

            try:
                duration = float(
                    duration
                )
            except Exception:
                duration = 2

            await asyncio.sleep(
                max(
                    0.1,
                    min(
                        duration,
                        30
                    )
                )
            )

            await sent.delete()

        except Exception as error:

            print(
                "❌ Join mention error:",
                error
            )

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member
    ):

        if member.bot:
            return

        await asyncio.sleep(
            0.5
        )

        await self.send_join_mention(
            member
        )

    @app_commands.command(
        name="منشن-روم",
        description="تحديد روم منشن الأعضاء الجدد"
    )
    async def mention_channel(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "join_mention_channel_id"
        ] = channel.id

        cfg[
            "join_mention_enabled"
        ] = True

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ تم تشغيل منشن الدخول "
                f"في {channel.mention}."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="منشن-إيقاف",
        description="إيقاف منشن الدخول"
    )
    async def mention_off(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "join_mention_enabled"
        ] = False

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🛑 تم إيقاف منشن الدخول.",
            ephemeral=True
        )

    @app_commands.command(
        name="منشن-حالة",
        description="حالة منشن الدخول"
    )
    async def mention_status(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel = None

        if cfg.get(
            "join_mention_channel_id"
        ):

            channel = interaction.guild.get_channel(
                int(
                    cfg[
                        "join_mention_channel_id"
                    ]
                )
            )

        await interaction.response.send_message(
            (
                "## 👋 حالة منشن الدخول\n\n"
                f"الحالة: **"
                f"{'🟢 مفعل' if cfg['join_mention_enabled'] else '🔴 متوقف'}"
                f"**\n"
                f"الروم: "
                f"{channel.mention if channel else 'غير محدد'}"
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="منشن-روم-إلغاء",
        description="إلغاء روم منشن الدخول"
    )
    async def mention_channel_clear(
        self,
        interaction
    ):

        if await self.owner_only(
            interaction
        ):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg[
            "join_mention_enabled"
        ] = False

        cfg[
            "join_mention_channel_id"
        ] = None

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "✅ تم إلغاء نظام منشن الدخول.",
            ephemeral=True
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):

    existing = bot.get_cog(
        "AutomaticLineSystem"
    )

    if existing:

        print(
            "⚠️ bot5 موجود مسبقًا."
        )

        return

    cog = AutomaticLineSystem(
        bot
    )

    await bot.add_cog(
        cog
    )

    # ========================================================
    # RESTORE PERSISTENT SUGGESTION BUTTONS
    # ========================================================

    for suggestion in (
        cog.suggestions.values()
    ):

        try:

            # الاقتراح المقبول/المرفوض لا يحتاج أزرار
            if suggestion.get(
                "status"
            ) in (
                "مقبول",
                "مرفوض"
            ):
                continue

            bot.add_view(
                SuggestionView(
                    cog,
                    suggestion["id"]
                )
            )

        except Exception as error:

            print(
                "⚠️ Suggestion persistent view error:",
                error
            )

    print(
        "✅ Team Fime bot5 loaded successfully."
    )