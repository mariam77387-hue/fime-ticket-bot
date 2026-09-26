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
# SAY SYSTEM — PROFESSIONAL PROFILE + PERSISTENT BUTTONS
# +
# SERVER INFORMATION SYSTEM
# +
# BOT MESSAGE EDIT SYSTEM
# +
# SMART SUGGESTIONS SYSTEM
# +
# AUTO TRIGGER RESPONSES
# +
# MODERATION SHORTCUTS
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
WARNINGS_FILE = Path("bot5_warnings.json")
SAY_MESSAGES_FILE = Path("bot5_say_messages.json")

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
    "say_storage_channel_id": None,

    # SUGGESTIONS
    "suggestions_channel_id": None,
    "suggestions_log_channel_id": None,
    "suggestions_allowed_role_ids": [],

    # AUTO TRIGGERS
    "auto_triggers": {},

    # MODERATION
    "moderation_enabled": True,
}


# ============================================================
# JSON
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


def load_warnings():
    return load_json(WARNINGS_FILE)


def save_warnings(data):
    save_json(WARNINGS_FILE, data)


def load_say_messages():
    return load_json(SAY_MESSAGES_FILE)


def save_say_messages(data):
    save_json(SAY_MESSAGES_FILE, data)


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

        super().__init__(timeout=None)

        self.add_item(
            TopSelect(
                cog,
                guild_id
            )
        )


# ============================================================
# SAY PROFILE VIEW
# ============================================================

class SayProfileSelect(discord.ui.Select):

    def __init__(
        self,
        cog,
        say_message_id,
        avatar_url=None,
        banner_url=None,
        profile_url=None,
        username=None,
        room_definition=None
    ):

        self.cog = cog
        self.say_message_id = str(say_message_id)
        self.avatar_url = avatar_url
        self.banner_url = banner_url
        self.profile_url = profile_url
        self.username = username or "Unknown"
        self.room_definition = room_definition or ""

        options = [
            discord.SelectOption(
                label="معلومات الحساب",
                value="info",
                emoji="📋",
                description="عرض معلومات الحساب"
            ),
            discord.SelectOption(
                label="رابط الافتار",
                value="avatar",
                emoji="👤",
                description="إرسال رابط الافتار"
            ),
            discord.SelectOption(
                label="رابط البنر",
                value="banner",
                emoji="🎨",
                description="إرسال رابط البنر"
            ),
            discord.SelectOption(
                label="البروفايل الكامل",
                value="profile",
                emoji="🪪",
                description="عرض صورة البروفايل"
            ),
            discord.SelectOption(
                label="إعادة توليد البروفايل",
                value="regenerate",
                emoji="🔄",
                description="إعادة إنشاء صورة البروفايل"
            ),
        ]

        super().__init__(
            placeholder="خيارات البروفايل...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_profile_select_{say_message_id}"
        )

    async def callback(self, interaction):

        choice = self.values[0]

        if choice == "info":
            await self.cog.send_say_profile_info(
                interaction,
                self.say_message_id
            )
            return

        if choice == "avatar":

            if not self.avatar_url:
                await interaction.response.send_message(
                    "❌ ما فيه افتار محفوظ لهذا البروفايل.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"👤 **رابط الافتار:**\n{self.avatar_url}",
                ephemeral=True
            )
            return

        if choice == "banner":

            if not self.banner_url:
                await interaction.response.send_message(
                    "❌ ما فيه بنر محفوظ لهذا البروفايل.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                f"🎨 **رابط البنر:**\n{self.banner_url}",
                ephemeral=True
            )
            return

        if choice == "profile":

            if not self.profile_url:
                await interaction.response.send_message(
                    "❌ صورة البروفايل غير متوفرة.",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                self.profile_url,
                ephemeral=True
            )
            return

        if choice == "regenerate":
            await self.cog.regenerate_say_profile(
                interaction,
                self.say_message_id
            )


class SayProfileButton(discord.ui.Button):

    def __init__(
        self,
        cog,
        say_message_id,
        label,
        emoji,
        action,
        row=1
    ):

        self.cog = cog
        self.say_message_id = str(say_message_id)
        self.action = action

        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"fime_say_button_{action}_{say_message_id}",
            row=row
        )

    async def callback(self, interaction):

        if self.action == "info":
            await self.cog.send_say_profile_info(
                interaction,
                self.say_message_id
            )

        elif self.action == "room":
            await self.cog.send_say_room_definition(
                interaction,
                self.say_message_id
            )

        elif self.action == "regenerate":
            await self.cog.regenerate_say_profile(
                interaction,
                self.say_message_id
            )


class SayProfileView(discord.ui.View):

    def __init__(
        self,
        cog,
        say_message_id,
        avatar_url=None,
        banner_url=None,
        profile_url=None,
        username=None,
        room_definition=None
    ):

        super().__init__(timeout=None)

        self.add_item(
            SayProfileSelect(
                cog,
                say_message_id,
                avatar_url=avatar_url,
                banner_url=banner_url,
                profile_url=profile_url,
                username=username,
                room_definition=room_definition
            )
        )

        self.add_item(
            SayProfileButton(
                cog,
                say_message_id,
                "معلومات",
                "📋",
                "info",
                row=1
            )
        )

        self.add_item(
            SayProfileButton(
                cog,
                say_message_id,
                "تعريف الروم",
                "📖",
                "room",
                row=1
            )
        )

        self.add_item(
            SayProfileButton(
                cog,
                say_message_id,
                "إعادة توليد",
                "🔄",
                "regenerate",
                row=2
            )


        )

        if avatar_url:
            self.add_item(
                discord.ui.Button(
                    label="رابط الافتار",
                    emoji="👤",
                    style=discord.ButtonStyle.link,
                    url=avatar_url,
                    row=2
                )
            )

        if banner_url:
            self.add_item(
                discord.ui.Button(
                    label="رابط البنر",
                    emoji="🎨",
                    style=discord.ButtonStyle.link,
                    url=banner_url,
                    row=2
                )
            )


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
        self.suggestion_id = str(suggestion_id)

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
        self.warnings = load_warnings()
        self.say_messages = load_say_messages()

        print(
            "✅ bot5 — Line + Join + Fime + TOP + SAY "
            "+ Server + Edit + Suggestions + Triggers "
            "+ Moderation loaded."
        )

    # ========================================================
    # CONFIG
    # ========================================================

    def get_config(self, guild_id):

        guild_key = str(guild_id)

        if guild_key not in self.config:
            self.config[guild_key] = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

        current = self.config[guild_key]

        if not isinstance(current, dict):
            current = deepcopy(
                DEFAULT_GUILD_CONFIG
            )
            self.config[guild_key] = current

        changed = False

        for key, default in DEFAULT_GUILD_CONFIG.items():

            if key not in current:
                current[key] = deepcopy(default)
                changed = True

        if not isinstance(
            current.get("top_allowed_role_ids"),
            list
        ):
            current["top_allowed_role_ids"] = []
            changed = True

        if not isinstance(
            current.get("suggestions_allowed_role_ids"),
            list
        ):
            current["suggestions_allowed_role_ids"] = []
            changed = True

        if not isinstance(
            current.get("auto_triggers"),
            dict
        ):
            current["auto_triggers"] = {}
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
        if not self.is_owner(interaction):
            await interaction.response.send_message(
                "❌ هذا الأمر للمالك فقط.",
                ephemeral=True
            )
            return True

        return False

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

        paths = (
            [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            ]
            if bold
            else
            [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            ]
        )

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
            new_width = int(new_height * source_ratio)
        else:
            new_width = width
            new_height = int(new_width / source_ratio)

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
        quality=88
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
    # SAY IMAGE
    # ========================================================

    def create_say_image_sync(
        self,
        avatar_image,
        banner_image,
        template_image,
        room_definition,
        message_text,
        username
    ):

        WIDTH = 1600
        HEIGHT = 900

        if template_image:

            canvas = self.crop_to_fill(
                template_image,
                (WIDTH, HEIGHT)
            )

            overlay = Image.new(
                "RGBA",
                canvas.size,
                (3, 5, 10, 85)
            )

            canvas.alpha_composite(overlay)

        else:

            canvas = Image.new(
                "RGBA",
                (WIDTH, HEIGHT),
                (5, 7, 13, 255)
            )

            glow = Image.new(
                "RGBA",
                canvas.size,
                (0, 0, 0, 0)
            )

            gd = ImageDraw.Draw(glow)

            gd.ellipse(
                (900, -350, 1800, 550),
                fill=(124, 92, 255, 75)
            )

            gd.ellipse(
                (-500, 560, 650, 1250),
                fill=(35, 110, 255, 42)
            )

            glow = glow.filter(
                ImageFilter.GaussianBlur(110)
            )

            canvas.alpha_composite(glow)

            draw = ImageDraw.Draw(canvas)

            draw.rounded_rectangle(
                (35, 35, WIDTH - 35, HEIGHT - 35),
                radius=48,
                fill=(10, 13, 22, 247),
                outline=(55, 61, 82),
                width=2
            )

        draw = ImageDraw.Draw(canvas)

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        draw.text(
            (90, 70),
            "TEAM FIME",
            font=self.get_font(35, True),
            fill=(248, 249, 252)
        )

        draw.text(
            (92, 117),
            "OFFICIAL COMMUNITY",
            font=self.get_font(16, True),
            fill=(154, 132, 255)
        )

        draw.rounded_rectangle(
            (1320, 75, 1505, 122),
            radius=22,
            fill=(124, 92, 255, 35),
            outline=(124, 92, 255, 90),
            width=1
        )

        draw.ellipse(
            (1335, 91, 1351, 107),
            fill=(76, 220, 130)
        )

        draw.text(
            (1365, 87),
            "FIME",
            font=self.get_font(15, True),
            fill=(220, 221, 230)
        )

        # ----------------------------------------------------
        # BANNER
        # ----------------------------------------------------

        if banner_image:

            banner = self.crop_to_fill(
                banner_image,
                (1410, 320)
            )

            canvas.paste(
                banner,
                (95, 170)
            )

            dark = Image.new(
                "RGBA",
                (1410, 320),
                (0, 0, 0, 0)
            )

            dd = ImageDraw.Draw(dark)

            dd.rectangle(
                (0, 185, 1410, 320),
                fill=(3, 4, 8, 165)
            )

            canvas.alpha_composite(
                dark,
                (95, 170)
            )

        else:

            draw.rounded_rectangle(
                (95, 170, 1505, 490),
                radius=32,
                fill=(15, 18, 29),
                outline=(124, 92, 255, 60),
                width=2
            )

            draw.text(
                (145, 255),
                "FIME",
                font=self.get_font(105, True),
                fill=(124, 92, 255, 65)
            )

            draw.text(
                (150, 390),
                "TEAM FIME COMMUNITY",
                font=self.get_font(18, True),
                fill=(140, 147, 165)
            )

        # ----------------------------------------------------
        # AVATAR
        # ----------------------------------------------------

        if avatar_image:

            avatar = self.crop_to_fill(
                avatar_image,
                (250, 250)
            )

            mask = Image.new(
                "L",
                (250, 250),
                0
            )

            ImageDraw.Draw(mask).ellipse(
                (0, 0, 250, 250),
                fill=255
            )

            avatar_rgba = Image.new(
                "RGBA",
                (250, 250),
                (0, 0, 0, 0)
            )

            avatar_rgba.paste(
                avatar,
                (0, 0),
                mask
            )

            canvas.paste(
                avatar_rgba,
                (125, 380),
                avatar_rgba
            )

            draw.ellipse(
                (115, 370, 385, 640),
                outline=(6, 8, 14),
                width=14
            )

            draw.ellipse(
                (115, 370, 385, 640),
                outline=(124, 92, 255),
                width=5
            )

        else:

            draw.ellipse(
                (125, 380, 375, 630),
                fill=(24, 28, 40),
                outline=(124, 92, 255),
                width=5
            )

            self.draw_center(
                draw,
                250,
                450,
                "F",
                self.get_font(80, True),
                (154, 132, 255)
            )

        # ----------------------------------------------------
        # USER
        # ----------------------------------------------------

        username_text = str(username or "Fime")

        draw.text(
            (435, 395),
            self.prepare_text(username_text[:28]),
            font=self.get_font(46, True),
            fill=(247, 248, 252)
        )

        draw.text(
            (438, 455),
            "Official Community Message",
            font=self.get_font(21),
            fill=(151, 158, 176)
        )

        # ----------------------------------------------------
        # MESSAGE CARD
        # ----------------------------------------------------

        draw.rounded_rectangle(
            (435, 505, 1505, 690),
            radius=28,
            fill=(14, 17, 27, 245),
            outline=(124, 92, 255, 75),
            width=2
        )

        draw.text(
            (470, 530),
            "MESSAGE",
            font=self.get_font(17, True),
            fill=(154, 132, 255)
        )

        text = self.prepare_text(message_text)

        font = self.get_font(24)

        words = text.split()
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

            if bbox[2] - bbox[0] <= 980:
                current = candidate
            else:

                if current:
                    lines.append(current)

                current = word

        if current:
            lines.append(current)

        lines = lines[:4]

        for index, line in enumerate(lines):

            draw.text(
                (470, 575 + index * 34),
                line,
                font=font,
                fill=(225, 228, 236)
            )

        # ----------------------------------------------------
        # ROOM DEFINITION
        # ----------------------------------------------------

        if room_definition:

            definition = self.prepare_text(
                room_definition
            )

            draw.rounded_rectangle(
                (435, 710, 1505, 785),
                radius=22,
                fill=(14, 17, 27, 235),
                outline=(48, 53, 70),
                width=2
            )

            draw.text(
                (470, 730),
                self.prepare_text(
                    "📖 تعريف الروم"
                ),
                font=self.get_font(16, True),
                fill=(154, 132, 255)
            )

            draw.text(
                (680, 730),
                definition[:85],
                font=self.get_font(17),
                fill=(190, 195, 207)
            )

        else:

            draw.rounded_rectangle(
                (435, 710, 1505, 785),
                radius=22,
                fill=(14, 17, 27, 235),
                outline=(48, 53, 70),
                width=2
            )

            draw.text(
                (470, 730),
                "FIME COMMUNITY",
                font=self.get_font(16, True),
                fill=(124, 92, 255)
            )

            draw.text(
                (680, 730),
                "Official message • Team Fime",
                font=self.get_font(17),
                fill=(175, 181, 194)
            )

        # ----------------------------------------------------
        # FOOTER
        # ----------------------------------------------------

        draw.rounded_rectangle(
            (95, 820, 1505, 850),
            radius=15,
            fill=(124, 92, 255)
        )

        draw.text(
            (115, 826),
            "FIME",
            font=self.get_font(13, True),
            fill="white"
        )

        draw.text(
            (1370, 826),
            "TEAM FIME",
            font=self.get_font(13, True),
            fill=(235, 236, 242)
        )

        return self.image_to_jpeg(
            canvas,
            quality=88
        )

    # ========================================================
    # FAST PROFILE
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

        draw = ImageDraw.Draw(canvas)

        if banner_image:

            banner = self.crop_to_fill(
                banner_image,
                (1130, 340)
            )

            canvas.paste(
                banner.convert("RGB"),
                (35, 35)
            )

            overlay = Image.new(
                "RGBA",
                (1130, 340),
                (0, 0, 0, 0)
            )

            od = ImageDraw.Draw(overlay)

            od.rectangle(
                (0, 210, 1130, 340),
                fill=(4, 5, 9, 150)
            )

            canvas.paste(
                overlay,
                (35, 35),
                overlay
            )

        else:

            draw.rounded_rectangle(
                (35, 35, width - 35, 375),
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
                (75, 300),
                avatar_rgba
            )

            draw.ellipse(
                (68, 293, 382, 607),
                outline=(124, 92, 255),
                width=7
            )

        else:

            draw.ellipse(
                (75, 300, 375, 600),
                fill=(25, 29, 42),
                outline=(124, 92, 255),
                width=6
            )

            self.draw_center(
                draw,
                225,
                385,
                "F",
                self.get_font(100, True),
                (154, 132, 255)
            )

        draw.text(
            (440, 420),
            "TEAM FIME",
            font=self.get_font(32, True),
            fill=(245, 247, 251)
        )

        draw.text(
            (440, 468),
            "Fime • Community Profile",
            font=self.get_font(22),
            fill=(150, 157, 175)
        )

        draw.rounded_rectangle(
            (440, 525, 760, 570),
            radius=20,
            fill=(124, 92, 255)
        )

        draw.text(
            (468, 536),
            "FULL PROFILE",
            font=self.get_font(16, True),
            fill="white"
        )

        draw.text(
            (850, 610),
            "TEAM FIME",
            font=self.get_font(17, True),
            fill=(130, 137, 155)
        )

        return self.image_to_jpeg(
            canvas,
            quality=88
        )

    # ========================================================
    # TOP
    # ========================================================

    def get_now(self):
        return datetime.now(SAUDI_TZ)

    def get_period_keys(self):

        now = self.get_now()

        daily_date = (
            now.date()
            if now.hour >= 22
            else now.date() - timedelta(days=1)
        )

        daily = daily_date.isoformat()

        week_start = (
            now.date()
            - timedelta(days=(now.weekday() + 2) % 7)
        )

        weekly = week_start.isoformat()

        monthly = f"{now.year}-{now.month:02d}"

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

        guild_data = self.ensure_top_guild(guild_id)

        daily, weekly, monthly = self.get_period_keys()

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

    def get_top_users(self, guild, period, limit=10):

        guild_data = self.ensure_top_guild(guild.id)

        daily, weekly, monthly = self.get_period_keys()

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

            try:
                member = guild.get_member(int(uid))
            except Exception:
                member = None

            if member:
                results.append(
                    (member, int(points))
                )

        results.sort(
            key=lambda x: x[1],
            reverse=True
        )

        return results[:limit]

    def build_top_embed(self, guild, period):

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

        channel_id = cfg.get("top_channel_id")

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
    # LINE
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

            if (
                old_channel
                and
                cfg.get("storage_message_id")
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
    # SAY STORAGE
    # ========================================================

    async def ensure_say_storage(
        self,
        guild,
        source_bytes,
        filename
    ):

        cfg = self.get_config(guild.id)

        channel = None

        if cfg.get("say_storage_channel_id"):
            channel = guild.get_channel(
                int(cfg["say_storage_channel_id"])
            )

        if not channel:
            return None

        try:

            stored = await channel.send(
                "🗃️ Fime Say Storage",
                file=discord.File(
                    io.BytesIO(source_bytes),
                    filename=filename
                )
            )

            return stored.attachments[0].url

        except Exception as error:

            print(
                "⚠️ Say storage error:",
                error
            )
            return None

    # ========================================================
    # SAY PROFILE HELPERS
    # ========================================================

    async def send_say_profile_info(
        self,
        interaction,
        say_message_id
    ):

        data = self.say_messages.get(
            str(say_message_id)
        )

        if not data:

            await interaction.response.send_message(
                "❌ بيانات هذا الـ /say غير موجودة.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 معلومات الحساب",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="👤 المستخدم",
            value=f"`{data.get('username', 'Unknown')}`",
            inline=False
        )

        embed.add_field(
            name="🖼️ الافتار",
            value=(
                "متوفر ✅"
                if data.get("avatar_url")
                else "غير متوفر ❌"
            ),
            inline=True
        )

        embed.add_field(
            name="🎨 البنر",
            value=(
                "متوفر ✅"
                if data.get("banner_url")
                else "غير متوفر ❌"
            ),
            inline=True
        )

        embed.add_field(
            name="🪪 البروفايل",
            value=(
                "متوفر ✅"
                if data.get("profile_url")
                else "غير متوفر ❌"
            ),
            inline=True
        )

        embed.set_footer(
            text="Team Fime • Say Profile"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    async def send_say_room_definition(
        self,
        interaction,
        say_message_id
    ):

        data = self.say_messages.get(
            str(say_message_id)
        )

        if not data:

            await interaction.response.send_message(
                "❌ بيانات هذا الـ /say غير موجودة.",
                ephemeral=True
            )
            return

        definition = str(
            data.get(
                "room_definition",
                ""
            )
        ).strip()

        if not definition:

            await interaction.response.send_message(
                "❌ ما فيه تعريف محفوظ لهذا الـ /say.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📖 تعريف الروم",
            description=definition,
            color=discord.Color.blurple()
        )

        embed.set_footer(
            text="Team Fime • Room Information"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    async def regenerate_say_profile(
        self,
        interaction,
        say_message_id
    ):

        data = self.say_messages.get(
            str(say_message_id)
        )

        if not data:

            await interaction.response.send_message(
                "❌ بيانات هذا الـ /say غير موجودة.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        profile_url = data.get("profile_url")

        if profile_url:

            await interaction.followup.send(
                (
                    "🔄 **البروفايل محفوظ بالفعل.**\n"
                    f"{profile_url}"
                ),
                ephemeral=True
            )
            return

        await interaction.followup.send(
            "❌ لا توجد نسخة مصدر كافية لإعادة التوليد.",
            ephemeral=True
        )

    # ========================================================
    # SAY
    # ========================================================

    @app_commands.command(
        name="say",
        description="إرسال رسالة — والبروفايل اختياري"
    )
    @app_commands.describe(
        message="الرسالة",
        channel="الروم",
        avatar="الافتار — اختياري",
        banner="البنر — اختياري",
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

        # ====================================================
        # NORMAL SAY
        # لا صورة ولا قالب إذا لم يطلب البروفايل
        # ====================================================

        profile_requested = any(
            (
                avatar,
                banner,
                template
            )
        )

        if not profile_requested:

            try:

                await target.send(
                    content=message,
                    allowed_mentions=discord.AllowedMentions.none()
                )

            except Exception as error:

                await interaction.response.send_message(
                    f"❌ فشل /say: `{type(error).__name__}`",
                    ephemeral=True
                )
                return

            await interaction.response.send_message(
                (
                    "✅ **تم إرسال الرسالة.**\n"
                    f"📍 {target.mention}"
                ),
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        try:

            # =================================================
            # تحميل الصور مرة واحدة وبشكل متزامن
            # =================================================

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

            results = []

            if tasks:
                results = await asyncio.gather(
                    *[
                        task
                        for _, task in tasks
                    ]
                )

            avatar_image = None
            banner_image = None
            template_image = None

            for index, (
                name,
                _
            ) in enumerate(tasks):

                if name == "avatar":
                    avatar_image = results[index]

                elif name == "banner":
                    banner_image = results[index]

                elif name == "template":
                    template_image = results[index]

            # =================================================
            # الملفات تستخدم للروابط/المعلومات
            # =================================================

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

            # =================================================
            # توليد البروفايل
            # =================================================

            generated_bytes = await asyncio.to_thread(
                self.create_say_image_sync,
                avatar_image,
                banner_image,
                template_image,
                definition,
                message,
                interaction.user.display_name
            )

            # =================================================
            # إرسال الصورة أولاً
            # =================================================

            sent = await target.send(
                content=message,
                file=discord.File(
                    io.BytesIO(generated_bytes),
                    filename="fime-say.jpg"
                ),
                allowed_mentions=discord.AllowedMentions.none()
            )

            profile_url = (
                sent.attachments[0].url
                if sent.attachments
                else None
            )

            # =================================================
            # حفظ بيانات الرسالة
            # =================================================

            say_id = str(sent.id)

            self.say_messages[say_id] = {
                "message_id": sent.id,
                "guild_id": interaction.guild.id,
                "channel_id": target.id,
                "username": interaction.user.display_name,
                "user_id": interaction.user.id,
                "message": message,
                "avatar_url": avatar_url,
                "banner_url": banner_url,
                "profile_url": profile_url,
                "room_definition": definition,
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }

            save_say_messages(
                self.say_messages
            )

            # =================================================
            # إضافة الأزرار إلى الرسالة
            # =================================================

            view = SayProfileView(
                self,
                sent.id,
                avatar_url=avatar_url,
                banner_url=banner_url,
                profile_url=profile_url,
                username=interaction.user.display_name,
                room_definition=definition
            )

            await sent.edit(
                view=view
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
                "✅ **تم إرسال الرسالة والبروفايل.**\n"
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
            value=(
                owner.mention
                if owner
                else "غير معروف"
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

    async def send_server_panel(
        self,
        interaction
    ):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        current = interaction.guild

        total_members = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )

        embed = self.build_server_embed(
            current
        )

        embed.title = "🛰️ معلومات البوت والسيرفر"

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

        embed.add_field(
            name="👥 إجمالي الأعضاء",
            value=f"`{total_members:,}`",
            inline=True
        )

        options = []

        for guild in self.bot.guilds[:25]:

            options.append(
                discord.SelectOption(
                    label=guild.name[:100],
                    value=str(guild.id),
                    emoji="🛰️",
                    description=f"ID: {guild.id}"
                )
            )

        view = ServerSelectView(
            self,
            options
        )

        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )

    @app_commands.command(
        name="server",
        description="معلومات السيرفرات التي يستخدم فيها البوت"
    )
    async def server_command(
        self,
        interaction
    ):
        await self.send_server_panel(interaction)

    @app_commands.command(
        name="سيرفر",
        description="معلومات السيرفرات التي يستخدم فيها البوت"
    )
    async def arabic_server_command(
        self,
        interaction
    ):
        await self.send_server_panel(interaction)

    # ========================================================
    # BOT MESSAGE EDIT
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

        if (
            not self.bot.user
            or
            message.author.id != self.bot.user.id
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

    def get_suggestion_id(self):

        numbers = []

        for key in self.suggestions.keys():

            if str(key).isdigit():
                numbers.append(int(key))

        return str(
            max(numbers, default=0) + 1
        )

    def can_manage_suggestions(
        self,
        member,
        cfg
    ):

        if member.id == OWNER_ID:
            return True

        allowed = {
            int(role_id)
            for role_id in cfg.get(
                "suggestions_allowed_role_ids",
                []
            )
            if str(role_id).isdigit()
        }

        return bool(
            allowed.intersection(
                role.id
                for role in getattr(
                    member,
                    "roles",
                    []
                )
            )
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
            title=f"💡 اقتراح #{suggestion['id']}",
            description=suggestion["text"],
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
            value=f"<@{suggestion['user_id']}>",
            inline=True
        )

        if suggestion.get("created_at"):

            try:

                dt = datetime.fromisoformat(
                    suggestion["created_at"]
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

        if suggestion.get("admin_reply"):

            embed.add_field(
                name="💬 رد الإدارة",
                value=suggestion["admin_reply"][:1024],
                inline=False
            )

        if suggestion.get("action_by"):

            embed.add_field(
                name="🛡️ آخر إجراء بواسطة",
                value=f"<@{suggestion['action_by']}>",
                inline=True
            )

        embed.set_footer(
            text=(
                "Team Fime • Suggestions "
                "• أزرار الإدارة أسفل الرسالة"
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
            "action_by": None,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

        message = await channel.send(
            embed=self.suggestion_embed(data),
            view=SuggestionView(
                self,
                sid
            ),
            allowed_mentions=discord.AllowedMentions.none()
        )

        data["message_id"] = message.id

        self.suggestions[sid] = data

        save_suggestions(
            self.suggestions
        )

        await self.send_suggestion_log(
            data,
            guild,
            "اقتراح جديد"
        )

        return data

    async def send_suggestion_log(
        self,
        data,
        guild,
        action="إجراء"
    ):

        cfg = self.get_config(guild.id)

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
            title=f"📝 {action}",
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

        embed.add_field(
            name="📌 الحالة",
            value=data.get(
                "status",
                "قيد المراجعة"
            ),
            inline=True
        )

        if data.get("action_by"):
            embed.add_field(
                name="🛡️ المنفذ",
                value=f"<@{data['action_by']}>",
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
    # AUTO SUGGESTION
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

        if message.channel.id != int(channel_id):
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

        image_url = None

        for attachment in message.attachments:

            if self.is_supported_image(attachment):
                image_url = attachment.url
                break

        if image_url:

            text += (
                f"\n\n🖼️ [الصورة المرفقة]({image_url})"
            )

        try:
            await message.delete()
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
                    "❌ تعذر تحويل الاقتراح إلى رسالة البوت.",
                    delete_after=6
                )
            except Exception:
                pass

        return True

    # ========================================================
    # SUGGESTION SETTINGS
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
            (
                f"✅ تم تحديد روم الاقتراحات: "
                f"{channel.mention}\n\n"
                "أي رسالة عضو داخل الروم تتحول تلقائيًا إلى اقتراح."
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
            (
                f"✅ روم سجل الاقتراحات: "
                f"{channel.mention}"
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="اقتراح-رتبة",
        description="إضافة رتبة مسموح لها قبول ورفض الاقتراحات"
    )
    async def suggestion_role(
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

        roles = cfg["suggestions_allowed_role_ids"]

        if role.id not in roles:
            roles.append(role.id)

        save_config(self.config)

        await interaction.response.send_message(
            (
                f"✅ تمت إضافة {role.mention} "
                "لإدارة الاقتراحات."
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="اقتراح-رتبة-إزالة",
        description="إزالة رتبة من إدارة الاقتراحات"
    )
    async def suggestion_role_remove(
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

        if role.id in cfg["suggestions_allowed_role_ids"]:
            cfg["suggestions_allowed_role_ids"].remove(
                role.id
            )

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تمت إزالة {role.mention}.",
            ephemeral=True
        )

    @app_commands.command(
        name="اقتراح-رتب",
        description="عرض رتب إدارة الاقتراحات"
    )
    async def suggestion_roles(
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

        roles = []

        for role_id in cfg[
            "suggestions_allowed_role_ids"
        ]:

            role = interaction.guild.get_role(
                int(role_id)
            )

            if role:
                roles.append(role.mention)

        await interaction.response.send_message(
            (
                "## 🛡️ رتب إدارة الاقتراحات\n\n"
                f"{', '.join(roles) if roles else 'لا توجد رتب محددة.'}"
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

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if not self.can_manage_suggestions(
            interaction.user,
            cfg
        ):

            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بإدارة الاقتراحات.",
                ephemeral=True
            )
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
        data["action_by"] = interaction.user.id

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data,
            disable_buttons=status.value in (
                "مقبول",
                "مرفوض"
            )
        )

        await self.send_suggestion_log(
            data,
            interaction.guild,
            f"تغيير حالة الاقتراح إلى {status.value}"
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

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if not self.can_manage_suggestions(
            interaction.user,
            cfg
        ):

            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بإدارة الاقتراحات.",
                ephemeral=True
            )
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
        data["action_by"] = interaction.user.id

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(data)

        await self.send_suggestion_log(
            data,
            interaction.guild,
            "تم تحديث رد الإدارة"
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

        if not interaction.guild:
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        if not self.can_manage_suggestions(
            interaction.user,
            cfg
        ):

            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بقبول أو رفض الاقتراحات.",
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

        if data.get("status") == status:

            await interaction.response.send_message(
                (
                    f"ℹ️ الاقتراح بالفعل "
                    f"**{status}**."
                ),
                ephemeral=True
            )
            return

        data["status"] = status
        data["action_by"] = interaction.user.id

        save_suggestions(
            self.suggestions
        )

        await self.refresh_suggestion(
            data,
            disable_buttons=True
        )

        await self.send_suggestion_log(
            data,
            interaction.guild,
            f"تم {status} الاقتراح"
        )

        await interaction.response.send_message(
            (
                f"{'✅' if status == 'مقبول' else '❌'} "
                f"تم تسجيل الاقتراح كـ **{status}**."
            ),
            ephemeral=True
        )

    async def refresh_suggestion(
        self,
        data,
        disable_buttons=False
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

            view = None

            if not disable_buttons:

                view = SuggestionView(
                    self,
                    data["id"]
                )

            await message.edit(
                embed=self.suggestion_embed(data),
                view=view,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:

            print(
                "⚠️ Suggestion refresh error:",
                error
            )

    # ========================================================
    # AUTO TRIGGERS
    # ========================================================

    def normalize_trigger(self, text):

        return " ".join(
            str(text or "").strip().casefold().split()
        )

    def get_triggers(self, cfg):

        triggers = cfg.get(
            "auto_triggers",
            {}
        )

        return triggers if isinstance(
            triggers,
            dict
        ) else {}

    @app_commands.command(
        name="محفز-إضافة",
        description="إضافة رد تلقائي لمحفز"
    )
    @app_commands.describe(
        trigger="الكلمة أو العبارة التي يكتبها العضو",
        response="الرد الذي يرسله البوت"
    )
    async def trigger_add(
        self,
        interaction,
        trigger: str,
        response: str
    ):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        trigger = self.normalize_trigger(trigger)

        if not trigger:
            await interaction.response.send_message(
                "❌ اكتب محفزًا صحيحًا.",
                ephemeral=True
            )
            return

        if len(response) > 2000:
            await interaction.response.send_message(
                "❌ الرد طويل جدًا.",
                ephemeral=True
            )
            return

        cfg = self.get_config(
            interaction.guild.id
        )

        triggers = self.get_triggers(cfg)

        triggers[trigger] = response

        cfg["auto_triggers"] = triggers

        save_config(self.config)

        await interaction.response.send_message(
            (
                "✅ تم حفظ المحفز.\n\n"
                f"**المحفز:** `{trigger}`\n"
                f"**الرد:** {response}"
            ),
            ephemeral=True
        )

    @app_commands.command(
        name="محفز-حذف",
        description="حذف رد تلقائي"
    )
    async def trigger_remove(
        self,
        interaction,
        trigger: str
    ):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        trigger = self.normalize_trigger(trigger)

        cfg = self.get_config(
            interaction.guild.id
        )

        triggers = self.get_triggers(cfg)

        if trigger not in triggers:

            await interaction.response.send_message(
                "❌ هذا المحفز غير موجود.",
                ephemeral=True
            )
            return

        del triggers[trigger]

        cfg["auto_triggers"] = triggers

        save_config(self.config)

        await interaction.response.send_message(
            f"🗑️ تم حذف المحفز `{trigger}`.",
            ephemeral=True
        )

    @app_commands.command(
        name="محفز-تعديل",
        description="تعديل رد محفز موجود"
    )
    async def trigger_edit(
        self,
        interaction,
        trigger: str,
        response: str
    ):

        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            return

        trigger = self.normalize_trigger(trigger)

        cfg = self.get_config(
            interaction.guild.id
        )

        triggers = self.get_triggers(cfg)

        if trigger not in triggers:

            await interaction.response.send_message(
                "❌ هذا المحفز غير موجود.",
                ephemeral=True
            )
            return

        if len(response) > 2000:

            await interaction.response.send_message(
                "❌ الرد طويل جدًا.",
                ephemeral=True
            )
            return

        triggers[trigger] = response

        cfg["auto_triggers"] = triggers

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم تعديل رد `{trigger}`.",
            ephemeral=True
        )

    @app_commands.command(
        name="محفز-قائمة",
        description="عرض المحفزات التلقائية"
    )
    async def trigger_list(
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

        triggers = self.get_triggers(cfg)

        if not triggers:

            await interaction.response.send_message(
                "📭 ما فيه محفزات محفوظة.",
                ephemeral=True
            )
            return

        lines = []

        for trigger, response in list(
            triggers.items()
        )[:40]:

            lines.append(
                f"• `{trigger}` → {response[:150]}"
            )

        await interaction.response.send_message(
            (
                "## 🤖 المحفزات التلقائية\n\n"
                + "\n".join(lines)
            ),
            ephemeral=True
        )

    # ========================================================
    # MODERATION HELPERS
    # ========================================================

    def has_moderation_permission(
        self,
        member,
        action
    ):

        if member.id == OWNER_ID:
            return True

        permissions = member.guild_permissions

        if action == "ban":
            return permissions.ban_members

        if action == "kick":
            return permissions.kick_members

        if action == "warn":
            return permissions.moderate_members or permissions.manage_messages

        if action == "delete":
            return permissions.manage_messages

        return False

    def can_act_on_member(
        self,
        actor,
        target
    ):

        if target.id == actor.id:
            return False

        if target.id == OWNER_ID:
            return False

        if actor.id == OWNER_ID:
            return True

        if target.id == actor.guild.owner_id:
            return False

        return (
            target.top_role < actor.top_role
        )

    def add_warning(
        self,
        guild_id,
        user_id,
        moderator_id,
        reason
    ):

        guild_key = str(guild_id)
        user_key = str(user_id)

        if guild_key not in self.warnings:
            self.warnings[guild_key] = {}

        self.warnings[guild_key].setdefault(
            user_key,
            []
        )

        self.warnings[guild_key][user_key].append(
            {
                "moderator_id": moderator_id,
                "reason": reason,
                "created_at": datetime.now(
                    timezone.utc
                ).isoformat()
            }
        )

        save_warnings(self.warnings)

        return len(
            self.warnings[guild_key][user_key]
        )

    # ========================================================
    # MODERATION SHORTCUTS
    # ========================================================

    async def handle_moderation_shortcut(
        self,
        message
    ):

        content = (
            message.content or ""
        ).strip()

        if not content:
            return False

        parts = content.split()

        command = parts[0]

        # ----------------------------------------------------
        # BAN
        # ----------------------------------------------------

        if command == "حظر":

            if len(parts) < 2:

                try:
                    await message.channel.send(
                        (
                            "🛡️ **طريقة الحظر:**\n"
                            "`حظر @عضو السبب`\n\n"
                            "يجب منشن العضو ثم كتابة السبب."
                        ),
                        delete_after=10
                    )
                except Exception:
                    pass

                return True

            if not message.mentions:

                try:
                    await message.channel.send(
                        (
                            "❌ لازم تمنشن العضو.\n"
                            "مثال: `حظر @عضو السبب`"
                        ),
                        delete_after=8
                    )
                except Exception:
                    pass

                return True

            target = message.mentions[0]

            if not isinstance(
                target,
                discord.Member
            ):
                return True

            if not self.has_moderation_permission(
                message.author,
                "ban"
            ):

                await message.channel.send(
                    "❌ ما عندك صلاحية الحظر.",
                    delete_after=6
                )
                return True

            if not self.can_act_on_member(
                message.author,
                target
            ):

                await message.channel.send(
                    "❌ ما تقدر تحظر هذا العضو بسبب الرتبة أو الصلاحيات.",
                    delete_after=6
                )
                return True

            reason = (
                " ".join(parts[2:]).strip()
                or "بدون سبب محدد"
            )

            try:

                await target.ban(
                    reason=f"{message.author} — {reason}"
                )

                await message.channel.send(
                    (
                        f"🔨 تم حظر **{target}**.\n"
                        f"السبب: **{reason}**"
                    ),
                    delete_after=8
                )

            except Exception as error:

                await message.channel.send(
                    f"❌ فشل الحظر: `{type(error).__name__}`",
                    delete_after=8
                )

            return True

        # ----------------------------------------------------
        # KICK — روح
        # ----------------------------------------------------

        if command == "روح":

            if len(parts) < 2 or not message.mentions:

                await message.channel.send(
                    (
                        "🦶 **طريقة الكِك:**\n"
                        "`روح @عضو السبب`"
                    ),
                    delete_after=8
                )
                return True

            target = message.mentions[0]

            if not isinstance(
                target,
                discord.Member
            ):
                return True

            if not self.has_moderation_permission(
                message.author,
                "kick"
            ):

                await message.channel.send(
                    "❌ ما عندك صلاحية الكِك.",
                    delete_after=6
                )
                return True

            if not self.can_act_on_member(
                message.author,
                target
            ):

                await message.channel.send(
                    "❌ ما تقدر تطرد هذا العضو.",
                    delete_after=6
                )
                return True

            reason = (
                " ".join(parts[2:]).strip()
                or "بدون سبب محدد"
            )

            try:

                await target.kick(
                    reason=f"{message.author} — {reason}"
                )

                await message.channel.send(
                    (
                        f"🦶 تم طرد **{target}**.\n"
                        f"السبب: **{reason}**"
                    ),
                    delete_after=8
                )

            except Exception as error:

                await message.channel.send(
                    f"❌ فشل الكِك: `{type(error).__name__}`",
                    delete_after=8
                )

            return True

        # ----------------------------------------------------
        # WARN — ت
        # ----------------------------------------------------

        if command == "ت":

            if len(parts) < 2 or not message.mentions:

                await message.channel.send(
                    (
                        "⚠️ **طريقة التحذير:**\n"
                        "`ت @عضو السبب`"
                    ),
                    delete_after=8
                )
                return True

            target = message.mentions[0]

            if not isinstance(
                target,
                discord.Member
            ):
                return True

            if not self.has_moderation_permission(
                message.author,
                "warn"
            ):

                await message.channel.send(
                    "❌ ما عندك صلاحية التحذير.",
                    delete_after=6
                )
                return True

            if not self.can_act_on_member(
                message.author,
                target
            ):

                await message.channel.send(
                    "❌ ما تقدر تحذر هذا العضو.",
                    delete_after=6
                )
                return True

            reason = (
                " ".join(parts[2:]).strip()
                or "بدون سبب محدد"
            )

            count = self.add_warning(
                message.guild.id,
                target.id,
                message.author.id,
                reason
            )

            try:

                await message.channel.send(
                    (
                        f"⚠️ تم تحذير **{target}**.\n"
                        f"السبب: **{reason}**\n"
                        f"عدد التحذيرات: **{count}**"
                    ),
                    delete_after=10
                )

            except Exception:
                pass

            return True

        # ----------------------------------------------------
        # PURGE MEMBER — مح
        # ----------------------------------------------------

        if command == "مح":

            if len(parts) < 2 or not message.mentions:

                await message.channel.send(
                    (
                        "🧹 **طريقة حذف رسائل العضو:**\n"
                        "`مح @عضو`"
                    ),
                    delete_after=8
                )
                return True

            target = message.mentions[0]

            if not isinstance(
                target,
                discord.Member
            ):
                return True

            if not self.has_moderation_permission(
                message.author,
                "delete"
            ):

                await message.channel.send(
                    "❌ ما عندك صلاحية حذف الرسائل.",
                    delete_after=6
                )
                return True

            try:

                deleted = await message.channel.purge(
                    limit=100,
                    check=lambda m: (
                        m.author.id == target.id
                    )
                )

                await message.channel.send(
                    (
                        f"🧹 تم حذف **{len(deleted)}** "
                        f"رسالة من {target.mention}."
                    ),
                    delete_after=6
                )

            except Exception as error:

                await message.channel.send(
                    f"❌ فشل الحذف: `{type(error).__name__}`",
                    delete_after=8
                )

            return True

        return False

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
                duration = float(duration)
            except Exception:
                duration = 2

            await asyncio.sleep(
                max(
                    0.1,
                    min(duration, 30)
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

        await asyncio.sleep(0.5)

        await self.send_join_mention(member)

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

    # ========================================================
    # MAIN MESSAGE LISTENER
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
        # MODERATION SHORTCUTS
        # قبل المحفزات والخط حتى لا تتعارض
        # ====================================================

        if cfg.get(
            "moderation_enabled",
            True
        ):

            moderation_handled = (
                await self.handle_moderation_shortcut(
                    message
                )
            )

            if moderation_handled:
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
        # AUTO TRIGGERS
        # مثال:
        # السلام عليكم -> وعليكم السلام
        # ====================================================

        normalized_message = self.normalize_trigger(
            message.content
        )

        triggers = self.get_triggers(cfg)

        if normalized_message in triggers:

            try:

                await message.channel.send(
                    triggers[normalized_message],
                    allowed_mentions=discord.AllowedMentions.none()
                )

            except Exception as error:

                print(
                    "❌ Auto trigger error:",
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

                return

        # ====================================================
        # LINE
        # ====================================================

        if not cfg.get("enabled"):
            return

        image_url = cfg.get("image_url")

        if not image_url:
            return

        channel_id = cfg.get("channel_id")

        if (
            channel_id
            and
            message.channel.id != int(channel_id)
        ):
            return

        me = message.guild.me

        if not me:
            return

        permissions = (
            message.channel.permissions_for(me)
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


# ============================================================
# SERVER SELECT
# ============================================================

class ServerSelect(discord.ui.Select):

    def __init__(
        self,
        cog,
        options
    ):

        self.cog = cog

        super().__init__(
            placeholder="اختر سيرفرًا...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="fime_server_selector"
        )

    async def callback(self, interaction):

        try:

            guild = self.cog.bot.get_guild(
                int(self.values[0])
            )

        except Exception:

            guild = None

        if not guild:

            await interaction.response.send_message(
                "❌ ما لقيت السيرفر.",
                ephemeral=True
            )
            return

        embed = self.cog.build_server_embed(
            guild
        )

        await interaction.response.edit_message(
            embed=embed,
            view=self.view
        )


class ServerSelectView(discord.ui.View):

    def __init__(
        self,
        cog,
        options
    ):

        super().__init__(timeout=None)

        if options:

            self.add_item(
                ServerSelect(
                    cog,
                    options
                )
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

    cog = AutomaticLineSystem(bot)

    await bot.add_cog(cog)

    # ========================================================
    # RESTORE SUGGESTION BUTTONS
    # ========================================================

    for suggestion in cog.suggestions.values():

        try:

            if suggestion.get("status") in (
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

    # ========================================================
    # RESTORE SAY BUTTONS
    # ========================================================

    for say_data in cog.say_messages.values():

        try:

            bot.add_view(
                SayProfileView(
                    cog,
                    say_data["message_id"],
                    avatar_url=say_data.get(
                        "avatar_url"
                    ),
                    banner_url=say_data.get(
                        "banner_url"
                    ),
                    profile_url=say_data.get(
                        "profile_url"
                    ),
                    username=say_data.get(
                        "username"
                    ),
                    room_definition=say_data.get(
                        "room_definition"
                    )
                )
            )

        except Exception as error:

            print(
                "⚠️ SAY persistent view error:",
                error
            )

    print(
        "✅ Team Fime bot5 loaded successfully."
    )