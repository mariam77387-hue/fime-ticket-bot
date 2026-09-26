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
# SUGGESTIONS SYSTEM
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
    save_json(TOP_FILE, data)


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
            TopSelect(cog, guild_id)
        )


# ============================================================
# SAY PROFILE MENU
# ============================================================

class SayProfileSelect(discord.ui.Select):

    def __init__(
        self,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None
    ):
        self.avatar_bytes = avatar_bytes
        self.banner_bytes = banner_bytes
        self.full_profile_bytes = full_profile_bytes

        options = [
            discord.SelectOption(
                label="أخذ الافتار",
                value="avatar",
                emoji="👤",
                description="تحميل الافتار بسرعة"
            ),
            discord.SelectOption(
                label="أخذ البنر",
                value="banner",
                emoji="🎨",
                description="تحميل البنر بسرعة"
            ),
            discord.SelectOption(
                label="البروفايل كامل",
                value="profile",
                emoji="🪪",
                description="البنر والافتار في صورة واحدة"
            ),
        ]

        super().__init__(
            placeholder="خيارات البروفايل...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_profile_{id(self)}"
        )

    async def callback(self, interaction):

        choice = self.values[0]

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

        if choice == "profile":

            if not self.full_profile_bytes:
                await interaction.response.send_message(
                    "❌ تعذر تجهيز البروفايل الكامل.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                "🪪 **البروفايل الكامل — البنر + الافتار**",
                file=discord.File(
                    io.BytesIO(self.full_profile_bytes),
                    filename="fime-full-profile.jpg"
                ),
                ephemeral=True
            )


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


class SayProfileView(discord.ui.View):

    def __init__(
        self,
        avatar_bytes=None,
        banner_bytes=None,
        full_profile_bytes=None,
        room_definition=None
    ):
        super().__init__(timeout=1800)

        self.add_item(
            SayProfileSelect(
                avatar_bytes,
                banner_bytes,
                full_profile_bytes
            )
        )

        self.add_item(
            SayRoomDefinitionButton(
                room_definition
            )
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ============================================================
# SUGGESTIONS SYSTEM
# ============================================================

class SuggestionView(discord.ui.View):

    def __init__(self, cog, suggestion_id):
        super().__init__(timeout=None)

        self.cog = cog
        self.suggestion_id = str(suggestion_id)

        up = discord.ui.Button(
            label="0",
            emoji="👍",
            style=discord.ButtonStyle.success,
            custom_id=f"fime_suggest_up_{suggestion_id}"
        )

        down = discord.ui.Button(
            label="0",
            emoji="👎",
            style=discord.ButtonStyle.danger,
            custom_id=f"fime_suggest_down_{suggestion_id}"
        )

        up.callback = self.vote_up
        down.callback = self.vote_down

        self.add_item(up)
        self.add_item(down)

    async def vote_up(self, interaction):
        await self.cog.vote_suggestion(
            interaction,
            self.suggestion_id,
            True
        )

    async def vote_down(self, interaction):
        await self.cog.vote_suggestion(
            interaction,
            self.suggestion_id,
            False
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
            current = deepcopy(DEFAULT_GUILD_CONFIG)
            self.config[key] = current

        changed = False

        for key_name, default in DEFAULT_GUILD_CONFIG.items():

            if key_name not in current:
                current[key_name] = deepcopy(default)
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

        if self.is_owner(interaction):
            return False

        return True

    # ========================================================
    # IMAGE
    # ========================================================

    def is_supported_image(self, attachment):

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

        if not self.is_supported_image(attachment):
            raise ValueError("صيغة الصورة غير مدعومة.")

        data = await attachment.read()

        if not data:
            raise ValueError("الصورة فارغة.")

        try:
            image = Image.open(
                io.BytesIO(data)
            )

            image.seek(0)

            return image.convert("RGBA")

        except Exception as error:
            raise ValueError(
                "تعذر قراءة الصورة."
            ) from error

    def get_font(self, size, bold=False):

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

        text = str(text or "")

        if ARABIC_SUPPORT:
            try:
                return get_display(
                    arabic_reshaper.reshape(text)
                )
            except Exception:
                pass

        return text

    def crop_to_fill(self, image, size):

        width, height = size

        image = image.convert("RGBA")

        if image.width <= 0 or image.height <= 0:
            return Image.new(
                "RGBA",
                size,
                (10, 12, 18, 255)
            )

        source_ratio = image.width / image.height
        target_ratio = width / height

        if source_ratio > target_ratio:
            new_height = height
            new_width = int(
                new_height * source_ratio
            )
        else:
            new_width = width
            new_height = int(
                new_width / source_ratio
            )

        image = image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )

        left = (new_width - width) // 2
        top = (new_height - height) // 2

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

        image.convert("RGB").save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True
        )

        return output.getvalue()

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

        draw = ImageDraw.Draw(canvas)

        # Banner
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
                (0, 230, width, 360),
                fill=(4, 5, 9, 150)
            )

            canvas.paste(
                overlay,
                (35, 35),
                overlay
            )

        else:
            draw.rounded_rectangle(
                (35, 35, width - 35, 395),
                radius=30,
                fill=(15, 18, 28)
            )

        # Avatar
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

            ImageDraw.Draw(mask).ellipse(
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

            font = self.get_font(
                100,
                True
            )

            self.draw_center(
                draw,
                225,
                395,
                "F",
                font,
                (154, 132, 255)
            )

        # Text
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
            (440, 530, 750, 575),
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

        width = bbox[2] - bbox[0]

        draw.text(
            (
                x - width / 2,
                y
            ),
            text,
            font=font,
            fill=fill
        )

    # ========================================================
    # PROFESSIONAL SAY TEMPLATE
    # ========================================================

    async def create_say_image(
        self,
        avatar_attachment=None,
        banner_attachment=None,
        template_attachment=None,
        room_definition=None
    ):

        WIDTH = 1600
        HEIGHT = 900

        if template_attachment:

            template = await self.read_image_attachment(
                template_attachment
            )

            canvas = self.crop_to_fill(
                template,
                (WIDTH, HEIGHT)
            )

            overlay = Image.new(
                "RGBA",
                canvas.size,
                (3, 5, 10, 105)
            )

            canvas.alpha_composite(overlay)

        else:

            canvas = Image.new(
                "RGBA",
                (WIDTH, HEIGHT),
                (5, 7, 13, 255)
            )

            # Background glow
            glow = Image.new(
                "RGBA",
                canvas.size,
                (0, 0, 0, 0)
            )

            gd = ImageDraw.Draw(glow)

            gd.ellipse(
                (900, -250, 1750, 500),
                fill=(124, 92, 255, 80)
            )

            gd.ellipse(
                (-350, 550, 650, 1200),
                fill=(50, 100, 255, 45)
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(120)
            )

            canvas.alpha_composite(glow)

            draw = ImageDraw.Draw(canvas)

            draw.rounded_rectangle(
                (35, 35, WIDTH - 35, HEIGHT - 35),
                radius=55,
                fill=(11, 14, 23, 245),
                outline=(55, 60, 80),
                width=2
            )

        draw = ImageDraw.Draw(canvas)

        # ====================================================
        # TOP BRAND
        # ====================================================

        draw.text(
            (90, 80),
            "TEAM FIME",
            font=self.get_font(
                34,
                True
            ),
            fill=(248, 249, 252)
        )

        draw.text(
            (92, 125),
            "OFFICIAL COMMUNITY",
            font=self.get_font(
                17,
                True
            ),
            fill=(154, 132, 255)
        )

        # ====================================================
        # BANNER
        # ====================================================

        if banner_attachment:

            banner_image = await self.read_image_attachment(
                banner_attachment
            )

            banner = self.crop_to_fill(
                banner_image,
                (1410, 330)
            )

            canvas.paste(
                banner,
                (95, 180)
            )

            dark = Image.new(
                "RGBA",
                (1410, 330),
                (0, 0, 0, 0)
            )

            dd = ImageDraw.Draw(dark)

            dd.rectangle(
                (0, 240, 1410, 330),
                fill=(4, 5, 9, 150)
            )

            canvas.alpha_composite(
                dark,
                (95, 180)
            )

        else:

            draw.rounded_rectangle(
                (95, 180, 1505, 510),
                radius=35,
                fill=(15, 18, 29),
                outline=(124, 92, 255, 65),
                width=2
            )

            draw.text(
                (145, 325),
                "FIME",
                font=self.get_font(
                    90,
                    True
                ),
                fill=(124, 92, 255, 80)
            )

        # ====================================================
        # AVATAR
        # ====================================================

        if avatar_attachment:

            avatar_image = await self.read_image_attachment(
                avatar_attachment
            )

            avatar = self.crop_to_fill(
                avatar_image,
                (245, 245)
            )

            mask = Image.new(
                "L",
                (245, 245),
                0
            )

            ImageDraw.Draw(mask).ellipse(
                (0, 0, 245, 245),
                fill=255
            )

            avatar_rgba = Image.new(
                "RGBA",
                (245, 245),
                (0, 0, 0, 0)
            )

            avatar_rgba.paste(
                avatar,
                (0, 0),
                mask
            )

            canvas.paste(
                avatar_rgba,
                (140, 395),
                avatar_rgba
            )

            draw.ellipse(
                (130, 385, 395, 650),
                outline=(7, 8, 13),
                width=12
            )

            draw.ellipse(
                (130, 385, 395, 650),
                outline=(124, 92, 255),
                width=5
            )

        else:

            draw.ellipse(
                (140, 395, 385, 640),
                fill=(24, 28, 40),
                outline=(124, 92, 255),
                width=5
            )

            self.draw_center(
                draw,
                262,
                465,
                "F",
                self.get_font(80, True),
                (154, 132, 255)
            )

        # ====================================================
        # PROFILE INFO
        # ====================================================

        draw.text(
            (455, 425),
            "Fime",
            font=self.get_font(
                52,
                True
            ),
            fill=(247, 248, 252)
        )

        draw.text(
            (458, 490),
            "Team Fime • Official Message",
            font=self.get_font(
                24
            ),
            fill=(151, 158, 176)
        )

        draw.rounded_rectangle(
            (455, 545, 730, 592),
            radius=23,
            fill=(124, 92, 255, 50),
            outline=(124, 92, 255, 120)
        )

        draw.text(
            (480, 557),
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
                21
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

                if bbox[2] - bbox[0] <= 780:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    current = word

            if current:
                lines.append(current)

            lines = lines[:3]

            draw.rounded_rectangle(
                (455, 620, 1480, 790),
                radius=30,
                fill=(14, 17, 27, 235),
                outline=(124, 92, 255, 70),
                width=2
            )

            draw.text(
                (490, 645),
                self.prepare_text(
                    "📖 تعريف الروم"
                ),
                font=self.get_font(
                    18,
                    True
                ),
                fill=(154, 132, 255)
            )

            for index, line in enumerate(lines):

                draw.text(
                    (
                        490,
                        685 + index * 30
                    ),
                    line,
                    font=font,
                    fill=(190, 195, 207)
                )

        else:

            draw.rounded_rectangle(
                (455, 620, 1480, 750),
                radius=30,
                fill=(14, 17, 27, 235),
                outline=(48, 53, 70),
                width=2
            )

            draw.text(
                (490, 660),
                "FIME COMMUNITY",
                font=self.get_font(
                    18,
                    True
                ),
                fill=(124, 92, 255)
            )

            draw.text(
                (490, 700),
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
            (95, 820, 1505, 850),
            radius=15,
            fill=(124, 92, 255)
        )

        draw.text(
            (110, 824),
            "FIME",
            font=self.get_font(
                14,
                True
            ),
            fill="white"
        )

        draw.text(
            (1320, 824),
            "TEAM FIME",
            font=self.get_font(
                14,
                True
            ),
            fill=(225, 227, 235)
        )

        return self.image_to_jpeg(
            canvas,
            quality=88
        )

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
            daily_date = now.date() - timedelta(days=1)

        daily = daily_date.isoformat()

        week_start = (
            now.date()
            - timedelta(
                days=(now.weekday() + 2) % 7
            )
        )

        weekly = week_start.isoformat()

        monthly = (
            f"{now.year}-{now.month:02d}"
        )

        return daily, weekly, monthly

    def ensure_top_guild(self, guild_id):

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

    def add_top_point(self, guild_id, user_id):

        guild_data = self.ensure_top_guild(
            guild_id
        )

        daily, weekly, monthly = (
            self.get_period_keys()
        )

        if guild_data["day"].get("_period") != daily:
            guild_data["day"] = {"_period": daily}

        if guild_data["week"].get("_period") != weekly:
            guild_data["week"] = {"_period": weekly}

        if guild_data["month"].get("_period") != monthly:
            guild_data["month"] = {"_period": monthly}

        uid = str(user_id)

        for period in (
            "day",
            "week",
            "month",
            "all"
        ):
            guild_data[period][uid] = (
                guild_data[period].get(uid, 0) + 1
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

        daily, weekly, monthly = (
            self.get_period_keys()
        )

        if period == "day":

            if guild_data["day"].get("_period") != daily:
                guild_data["day"] = {"_period": daily}

            source = guild_data["day"]

        elif period == "week":

            if guild_data["week"].get("_period") != weekly:
                guild_data["week"] = {"_period": weekly}

            source = guild_data["week"]

        elif period == "month":

            if guild_data["month"].get("_period") != monthly:
                guild_data["month"] = {"_period": monthly}

            source = guild_data["month"]

        else:
            source = guild_data["all"]

        results = []

        for uid, points in source.items():

            if uid == "_period":
                continue

            member = guild.get_member(
                int(uid)
            )

            if member:
                results.append(
                    (member, int(points))
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

        for index, (member, points) in enumerate(
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
            description="\n".join(lines),
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Team Fime • Top System"
        )

        return embed

    def normalize_top(self, content):

        return " ".join(
            str(content or "").split()
        ).casefold()

    def top_period(self, content):

        return {
            "day": "day",
            "week": "week",
            "month": "month",
            "all": "all"
        }.get(
            self.normalize_top(content)
        )

    def can_use_top(self, message, cfg):

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
            and message.channel.id == int(channel_id)
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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["top_channel_id"] = (
            channel.id if channel else None
        )

        save_config(self.config)

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        roles = cfg["top_allowed_role_ids"]

        if role.id not in roles:
            roles.append(role.id)

        save_config(self.config)

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if role.id in cfg["top_allowed_role_ids"]:
            cfg["top_allowed_role_ids"].remove(role.id)

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تمت إزالة {role.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="توب-حالة",
        description="عرض حالة التوب"
    )
    async def top_status(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel = None

        if cfg.get("top_channel_id"):
            channel = interaction.guild.get_channel(
                int(cfg["top_channel_id"])
            )

        roles = []

        for rid in cfg["top_allowed_role_ids"]:
            role = interaction.guild.get_role(
                int(rid)
            )

            if role:
                roles.append(role.mention)

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        if not self.is_supported_image(image):
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

            storage = channel or interaction.channel

            if not isinstance(
                storage,
                discord.TextChannel
            ):
                raise RuntimeError(
                    "ما لقيت روم تخزين."
                )

            old_channel = None

            if cfg.get("storage_channel_id"):
                old_channel = interaction.guild.get_channel(
                    int(cfg["storage_channel_id"])
                )

            if old_channel and cfg.get(
                "storage_message_id"
            ):
                try:
                    old = await old_channel.fetch_message(
                        int(cfg["storage_message_id"])
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

            cfg["image_url"] = stored.attachments[0].url
            cfg["storage_channel_id"] = storage.id
            cfg["storage_message_id"] = stored.id
            cfg["channel_id"] = (
                channel.id if channel else None
            )
            cfg["enabled"] = True

            save_config(self.config)

            await interaction.followup.send(
                "✅ **تم تشغيل نظام الخط.**",
                ephemeral=True
            )

        except Exception as error:

            print("❌ Line error:", error)

            await interaction.followup.send(
                f"❌ فشل تشغيل الخط: `{type(error).__name__}`",
                ephemeral=True
            )

    @app_commands.command(
        name="خط-إيقاف",
        description="إيقاف نظام الخط"
    )
    async def line_off(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["enabled"] = False
        save_config(self.config)

        await interaction.response.send_message(
            "🛑 تم إيقاف الخط.",
            ephemeral=True
        )

    @app_commands.command(
        name="خط-حالة",
        description="حالة الخط"
    )
    async def line_status(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        channel = None

        if cfg.get("channel_id"):
            channel = interaction.guild.get_channel(
                int(cfg["channel_id"])
            )

        await interaction.response.send_message(
            (
                "## 🖼️ حالة الخط\n\n"
                f"الحالة: **{'🟢 مفعل' if cfg['enabled'] else '🔴 متوقف'}**\n"
                f"الروم: {channel.mention if channel else 'كل الرومات'}"
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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["channel_id"] = (
            channel.id if channel else None
        )

        save_config(self.config)

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
    # FIME SYSTEM
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

        if await self.owner_only(interaction):
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

        cfg["fime_word_response"] = message
        cfg["fime_word_enabled"] = True

        save_config(self.config)

        await interaction.response.send_message(
            "✅ تم تحديث رد فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-تشغيل",
        description="تشغيل نظام فيم"
    )
    async def fime_enable(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["fime_word_enabled"] = True
        save_config(self.config)

        await interaction.response.send_message(
            "🟢 تم تشغيل نظام فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-إيقاف",
        description="إيقاف نظام فيم"
    )
    async def fime_disable(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["fime_word_enabled"] = False
        save_config(self.config)

        await interaction.response.send_message(
            "🔴 تم إيقاف نظام فيم.",
            ephemeral=True
        )

    @app_commands.command(
        name="فيم-حالة",
        description="حالة نظام فيم"
    )
    async def fime_status(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        await interaction.response.send_message(
            (
                "## 🌀 حالة فيم\n\n"
                f"الحالة: **{'🟢 مفعل' if cfg['fime_word_enabled'] else '🔴 متوقف'}**\n\n"
                f"**الرد:**\n{cfg['fime_word_response']}"
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

        if await self.owner_only(interaction):
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

        cfg["say_room_definition"] = definition
        save_config(self.config)

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["say_room_definition"] = ""
        save_config(self.config)

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        if len(message) > 2000:
            await interaction.response.send_message(
                "❌ الرسالة لا تتجاوز 2000 حرف.",
                ephemeral=True
            )
            return

        target = channel or interaction.channel

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
            if attachment and not self.is_supported_image(
                attachment
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

                avatar_image = (
                    await self.read_image_attachment(
                        avatar
                    )
                    if avatar
                    else None
                )

                banner_image = (
                    await self.read_image_attachment(
                        banner
                    )
                    if banner
                    else None
                )

                # ==========================================
                # ملفات سريعة جدًا للتحميل
                # ==========================================

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

                # ==========================================
                # البروفايل الكامل مستقل عن قالب /say
                # ==========================================

                full_profile_bytes = (
                    self.create_fast_profile(
                        avatar_image,
                        banner_image
                    )
                    if avatar_image or banner_image
                    else None
                )

                generated_bytes = (
                    await self.create_say_image(
                        avatar_attachment=avatar,
                        banner_attachment=banner,
                        template_attachment=template,
                        room_definition=definition
                    )
                )

                view = SayProfileView(
                    avatar_bytes=avatar_bytes,
                    banner_bytes=banner_bytes,
                    full_profile_bytes=full_profile_bytes,
                    room_definition=definition
                )

                await target.send(
                    content=message,
                    file=discord.File(
                        io.BytesIO(generated_bytes),
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

            print("❌ SAY error:", error)

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
            value=owner.mention if owner else "غير معروف",
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
            text=f"Team Fime • البوت موجود في {len(self.bot.guilds)} سيرفر"
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

        if await self.owner_only(interaction):
            return

        current = interaction.guild

        embed = self.build_server_embed(
            current
        )

        embed.title = "🛰️ معلومات البوت والسيرفر"

        embed.description = (
            f"**البوت موجود حاليًا في `{len(self.bot.guilds)}` سيرفر.**\n\n"
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

        if await self.owner_only(interaction):
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

        if not self.bot.user or message.author.id != self.bot.user.id:

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

    def get_suggestion_id(self):

        numbers = []

        for key in self.suggestions.keys():
            if str(key).isdigit():
                numbers.append(
                    int(key)
                )

        return str(
            max(numbers, default=0) + 1
        )

    def suggestion_embed(
        self,
        suggestion
    ):

        up = len(
            suggestion.get(
                "upvotes",
                []
            )
        )

        down = len(
            suggestion.get(
                "downvotes",
                []
            )
        )

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

        embed = discord.Embed(
            title=f"💡 اقتراح #{suggestion['id']}",
            description=suggestion["text"],
            color=colors.get(
                status,
                discord.Color.blurple()
            )
        )

        embed.add_field(
            name="📌 الحالة",
            value=f"**{status}**",
            inline=True
        )

        embed.add_field(
            name="👍 مؤيد",
            value=f"`{up}`",
            inline=True
        )

        embed.add_field(
            name="👎 معارض",
            value=f"`{down}`",
            inline=True
        )

        embed.add_field(
            name="👤 صاحب الاقتراح",
            value=f"<@{suggestion['user_id']}>",
            inline=False
        )

        if suggestion.get("admin_reply"):
            embed.add_field(
                name="💬 رد الإدارة",
                value=suggestion["admin_reply"][:1024],
                inline=False
            )

        embed.set_footer(
            text="Team Fime • Suggestions"
        )

        return embed

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

        sid = self.get_suggestion_id()

        data = {
            "id": sid,
            "guild_id": interaction.guild.id,
            "channel_id": channel.id,
            "message_id": None,
            "user_id": interaction.user.id,
            "text": suggestion,
            "status": "قيد المراجعة",
            "admin_reply": "",
            "upvotes": [],
            "downvotes": [],
            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        message = await channel.send(
            embed=self.suggestion_embed(data),
            view=SuggestionView(
                self,
                sid
            )
        )

        data["message_id"] = message.id

        self.suggestions[sid] = data

        save_suggestions(
            self.suggestions
        )

        await interaction.followup.send(
            f"✅ تم إرسال اقتراحك برقم **#{sid}**.",
            ephemeral=True
        )

    @app_commands.command(
        name="اقتراح-روم",
        description="تحديد روم الاقتراحات"
    )
    async def suggestion_channel(
        self,
        interaction,
        channel: discord.TextChannel
    ):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["suggestions_channel_id"] = channel.id

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ روم الاقتراحات: {channel.mention}",
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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["suggestions_log_channel_id"] = channel.id

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ روم سجل الاقتراحات: {channel.mention}",
            ephemeral=True
        )

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

        if await self.owner_only(interaction):
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

        data["status"] = status.value

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data
        )

        await interaction.response.send_message(
            f"✅ تم تغيير الحالة إلى **{status.value}**.",
            ephemeral=True
        )

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

        if await self.owner_only(interaction):
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

        data["admin_reply"] = reply[:1024]

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

    async def refresh_suggestion(
        self,
        data
    ):

        guild = self.bot.get_guild(
            int(data["guild_id"])
        )

        if not guild:
            return

        channel = guild.get_channel(
            int(data["channel_id"])
        )

        if not channel:
            return

        try:
            message = await channel.fetch_message(
                int(data["message_id"])
            )

            await message.edit(
                embed=self.suggestion_embed(data),
                view=SuggestionView(
                    self,
                    data["id"]
                )
            )

        except Exception as error:
            print(
                "⚠️ Suggestion refresh error:",
                error
            )

    async def vote_suggestion(
        self,
        interaction,
        suggestion_id,
        positive
    ):

        data = self.suggestions.get(
            str(suggestion_id)
        )

        if not data:
            await interaction.response.send_message(
                "❌ الاقتراح غير موجود.",
                ephemeral=True
            )
            return

        if data.get("status") == "مكتمل":
            await interaction.response.send_message(
                "ℹ️ هذا الاقتراح مكتمل.",
                ephemeral=True
            )
            return

        uid = str(
            interaction.user.id
        )

        up = data.setdefault(
            "upvotes",
            []
        )

        down = data.setdefault(
            "downvotes",
            []
        )

        if uid in up:
            up.remove(uid)

        if uid in down:
            down.remove(uid)

        if positive:
            up.append(uid)
        else:
            down.append(uid)

        save_suggestions(
            self.suggestions
        )

        await interaction.response.edit_message(
            embed=self.suggestion_embed(data),
            view=SuggestionView(
                self,
                suggestion_id
            )
        )

    # ========================================================
    # TOP / FIME / LINE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if not message.guild:
            return

        cfg = self.get_config(
            message.guild.id
        )

        self.add_top_point(
            message.guild.id,
            message.author.id
        )

        # TOP
        period = self.top_period(
            message.content
        )

        if period and self.can_use_top(
            message,
            cfg
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
                    )
                )
            except Exception as error:
                print(
                    "❌ TOP error:",
                    error
                )

            return

        # FIME
        normalized = (
            " ".join(
                message.content.strip().split()
            ).casefold()
        )

        if cfg.get(
            "fime_word_enabled",
            True
        ):

            if normalized == "فيم" or (
                cfg.get(
                    "fime_word_accept_fimi",
                    False
                )
                and normalized == "فيمي"
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

        # LINE
        if not cfg.get("enabled"):
            return

        image_url = cfg.get(
            "image_url"
        )

        if not image_url:
            return

        channel_id = cfg.get(
            "channel_id"
        )

        if channel_id and (
            message.channel.id != int(channel_id)
        ):
            return

        me = message.guild.me

        if not me:
            return

        permissions = message.channel.permissions_for(
            me
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

    async def send_join_mention(self, member):

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

            await asyncio.sleep(
                2
            )

            await sent.delete()

        except Exception as error:
            print(
                "❌ Join mention error:",
                error
            )

    @commands.Cog.listener()
    async def on_member_join(self, member):

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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["join_mention_channel_id"] = channel.id
        cfg["join_mention_enabled"] = True

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم تشغيل منشن الدخول في {channel.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="منشن-إيقاف",
        description="إيقاف منشن الدخول"
    )
    async def mention_off(self, interaction):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["join_mention_enabled"] = False

        save_config(self.config)

        await interaction.response.send_message(
            "🛑 تم إيقاف منشن الدخول.",
            ephemeral=True
        )

    @app_commands.command(
        name="منشن-حالة",
        description="حالة منشن الدخول"
    )
    async def mention_status(self, interaction):

        if await self.owner_only(interaction):
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
                    cfg["join_mention_channel_id"]
                )
            )

        await interaction.response.send_message(
            (
                "## 👋 حالة منشن الدخول\n\n"
                f"الحالة: **{'🟢 مفعل' if cfg['join_mention_enabled'] else '🔴 متوقف'}**\n"
                f"الروم: {channel.mention if channel else 'غير محدد'}"
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

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        cfg["join_mention_enabled"] = False
        cfg["join_mention_channel_id"] = None

        save_config(self.config)

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

    # إعادة تفعيل أزرار الاقتراحات بعد إعادة تشغيل البوت
    for suggestion in cog.suggestions.values():

        try:

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