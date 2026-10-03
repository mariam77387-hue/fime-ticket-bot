# ============================================================
# Team Fime — bot5.py (النسخة المصححة)
# Line / Join Mention / Fime Word / TOP / SAY / Server Info /
# Bot Message Edit / Suggestions / Auto Triggers / Moderation
# ============================================================

from __future__ import annotations

import os
import io
import json
import asyncio
import re
import random
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from discord import app_commands

from PIL import Image, ImageDraw, ImageFont

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
TEMP_BANS_FILE = Path("bot5_temp_bans.json")
ROLE_PANEL_FILE = Path("bot5_role_panel.json")

SAUDI_TZ = timezone(timedelta(hours=3))

MOD_ACTIONS = {"حظر", "روح", "فارق", "ت", "مح"}

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
    "suggestions_allowed_role_ids": [],
    "suggestion_options": [],
    "suggestions_mention_role_id": None,

    # AUTO TRIGGERS
    "auto_triggers": {
        "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته"
    },

    # GAME INFO
    "game_info_enabled": False,
    "game_info_channel_id": None,

    # MODERATION
    "moderation_enabled": True,
    "moderation_aliases": {},
    "blocked_words": [],
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
            json.dump(data, file, ensure_ascii=False, indent=2)
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


def load_warnings():
    return load_json(WARNINGS_FILE)


def save_warnings(data):
    save_json(WARNINGS_FILE, data)


def load_temp_bans():
    return load_json(TEMP_BANS_FILE)


def save_temp_bans(data):
    save_json(TEMP_BANS_FILE, data)


def load_role_panels():
    return load_json(ROLE_PANEL_FILE)


def save_role_panels(data):
    save_json(ROLE_PANEL_FILE, data)


# ============================================================
# TOP SELECT
# ============================================================

class TopSelect(discord.ui.Select):

    def __init__(self, cog, guild_id):
        self.cog = cog

        options = [
            discord.SelectOption(label="توب اليوم", value="day", emoji="📅"),
            discord.SelectOption(label="توب الأسبوع", value="week", emoji="📊"),
            discord.SelectOption(label="توب الشهر", value="month", emoji="🗓️"),
            discord.SelectOption(label="توب الكل", value="all", emoji="🏆"),
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

        embed = self.cog.build_top_embed(interaction.guild, self.values[0])
        await interaction.response.edit_message(embed=embed, view=self.view)


class TopSelectView(discord.ui.View):

    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.add_item(TopSelect(cog, guild_id))


# ============================================================
# ROLE PANEL
# ============================================================

class RolePanelButton(discord.ui.Button):
    def __init__(self, cog, guild_id, role_id, label, emoji=None, row=0):
        self.cog = cog
        self.guild_id = int(guild_id)
        self.role_id = int(role_id)
        super().__init__(
            label=str(label)[:80],
            emoji=emoji or None,
            style=discord.ButtonStyle.secondary,
            custom_id=f"fime_role_panel_{guild_id}_{role_id}",
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or interaction.guild.id != self.guild_id:
            await interaction.response.send_message("❌ هذه اللوحة ليست لهذا السيرفر.", ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ تعذر التحقق من عضويتك.", ephemeral=True)
            return

        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("❌ هذه الرتبة لم تعد موجودة.", ephemeral=True)
            return

        me = interaction.guild.me
        if me and role >= me.top_role:
            await interaction.response.send_message("❌ البوت لا يستطيع إدارة هذه الرتبة. ارفع رتبة البوت فوقها.", ephemeral=True)
            return

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Team Fime Role Panel")
                await interaction.response.send_message(f"➖ تمت إزالة {role.mention}.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Team Fime Role Panel")
                await interaction.response.send_message(f"➕ تمت إضافة {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("❌ البوت لا يملك صلاحية إدارة هذه الرتبة.", ephemeral=True)
        except Exception as error:
            print("❌ Role panel button error:", error)
            await interaction.response.send_message("❌ تعذر تعديل الرتبة.", ephemeral=True)


class RolePanelView(discord.ui.View):
    def __init__(self, cog, guild_id, roles):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = int(guild_id)
        for index, item in enumerate(roles[:25]):
            role_id = int(item.get("role_id"))
            label = item.get("label") or item.get("name") or "رتبة"
            emoji = item.get("emoji")
            self.add_item(RolePanelButton(cog, guild_id, role_id, label, emoji, row=index // 5))


# ============================================================
# SUGGESTIONS VIEW
# ============================================================

class SuggestionView(discord.ui.View):

    def __init__(self, cog, suggestion_id):
        super().__init__(timeout=None)

        self.cog = cog
        self.suggestion_id = str(suggestion_id)

        approve = discord.ui.Button(
            label="قبول", emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"fime_suggest_approve_{suggestion_id}", row=0
        )
        reject = discord.ui.Button(
            label="رفض", emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"fime_suggest_reject_{suggestion_id}", row=0
        )
        up = discord.ui.Button(
            label="0", emoji="👍",
            style=discord.ButtonStyle.secondary,
            custom_id=f"fime_suggest_up_{suggestion_id}", row=1
        )
        down = discord.ui.Button(
            label="0", emoji="👎",
            style=discord.ButtonStyle.secondary,
            custom_id=f"fime_suggest_down_{suggestion_id}", row=1
        )

        approve.callback = self.approve
        reject.callback = self.reject
        up.callback = self.upvote
        down.callback = self.downvote

        self.add_item(approve)
        self.add_item(reject)
        self.add_item(up)
        self.add_item(down)

        data = cog.suggestions.get(str(suggestion_id), {})
        up.label = str(len(data.get("upvotes", [])))
        down.label = str(len(data.get("downvotes", [])))

        if data.get("status") in ("مقبول", "مرفوض"):
            approve.disabled = True
            reject.disabled = True

    async def approve(self, interaction):
        await self.cog.change_suggestion_status(interaction, self.suggestion_id, "مقبول")

    async def reject(self, interaction):
        await self.cog.change_suggestion_status(interaction, self.suggestion_id, "مرفوض")

    async def upvote(self, interaction):
        await self.cog.vote_suggestion(interaction, self.suggestion_id, True)

    async def downvote(self, interaction):
        await self.cog.vote_suggestion(interaction, self.suggestion_id, False)


# ============================================================
# MODERATION SHORTCUT MENU
# ============================================================

class ModerationShortcutSelect(discord.ui.Select):

    def __init__(self, shortcuts):
        options = [
            discord.SelectOption(label="حظر", value="حظر", emoji="🔨", description="حظر عضو بشكل دائم أو بمدة"),
            discord.SelectOption(label="روح", value="روح", emoji="🦶", description="طرد عضو من السيرفر"),
            discord.SelectOption(label="فارق", value="فارق", emoji="🔓", description="فك حظر عضو باستخدام الـ ID"),
            discord.SelectOption(label="ت", value="ت", emoji="⚠️", description="تحذير عضو"),
            discord.SelectOption(label="مح", value="مح", emoji="🧹", description="حذف رسائل عضو"),
        ]

        for alias, action in list(shortcuts.items())[:20]:
            if alias and action in MOD_ACTIONS:
                options.append(
                    discord.SelectOption(
                        label=str(alias)[:100],
                        value=f"alias:{alias}"[:100],
                        emoji="⌨️",
                        description=f"اختصار لـ {action}"[:100]
                    )
                )

        super().__init__(
            placeholder="اختر الاختصار الذي تبي تعرف طريقته...",
            min_values=1,
            max_values=1,
            options=options[:25]
        )

        self.shortcuts = shortcuts

    async def callback(self, interaction):
        selected = self.values[0]
        action = selected

        if selected.startswith("alias:"):
            alias = selected[6:]
            action = self.shortcuts.get(alias, alias)

        usages = {
            "حظر": "`حظر @عضو` أو `حظر @عضو 7d السبب`",
            "روح": "`روح @عضو`",
            "فارق": "`فارق USER_ID`",
            "ت": "`ت @عضو السبب`",
            "مح": "`مح @عضو`"
        }

        await interaction.response.send_message(
            f"📌 **طريقة الاستخدام:**\n{usages.get(action, 'استخدم الاختصار المضاف من المالك.')}",
            ephemeral=True
        )


class ModerationShortcutView(discord.ui.View):

    def __init__(self, shortcuts):
        super().__init__(timeout=90)
        self.add_item(ModerationShortcutSelect(shortcuts))


# ============================================================
# SERVER SELECT
# ============================================================

class ServerSelect(discord.ui.Select):

    def __init__(self, cog, options):
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
            guild = self.cog.bot.get_guild(int(self.values[0]))
        except Exception:
            guild = None

        if not guild:
            await interaction.response.send_message("❌ ما لقيت السيرفر.", ephemeral=True)
            return

        await interaction.response.edit_message(
            embed=self.cog.build_server_embed(guild),
            view=self.view
        )


class ServerSelectView(discord.ui.View):

    def __init__(self, cog, options):
        super().__init__(timeout=None)
        if options:
            self.add_item(ServerSelect(cog, options))


# ============================================================
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    top_group = app_commands.Group(name="توب", description="أوامر نظام التوب (الأكثر تفاعلاً)")
    line_group = app_commands.Group(name="خط", description="أوامر نظام الخط (الصورة التلقائية)")
    fime_group = app_commands.Group(name="فيم", description="أوامر نظام رد كلمة فيم")
    room_group = app_commands.Group(name="روم", description="أوامر تعريف الروم")
    control_group = app_commands.Group(name="بوت", description="أوامر معلومات البوت والتحكم برسائله")
    suggest_group = app_commands.Group(name="اقتراحات", description="أوامر نظام الاقتراحات")
    trigger_group = app_commands.Group(name="محفزات", description="أوامر المحفزات التلقائية (رد تلقائي على كلمة)")
    shortcut_group = app_commands.Group(name="اختصارات", description="أوامر اختصارات أوامر الإدارة النصية")
    filter_group = app_commands.Group(name="فلتر", description="أوامر فلتر الكلمات المحظورة")
    mention_group = app_commands.Group(name="منشن", description="أوامر منشن الأعضاء الجدد")
    roles_group = app_commands.Group(name="رتب", description="لوحة الرتب التفاعلية")

    def __init__(self, bot):
        self.bot = bot

        self.config = load_config()
        self.top_data = load_top()
        self.suggestions = load_suggestions()
        self.warnings = load_warnings()
        self.temp_bans = load_temp_bans()
        self.role_panels = load_role_panels()
        self.temp_ban_tasks = {}

        print("✅ bot5 — Line + Join + Fime + TOP + SAY + Server + Edit + Suggestions + Triggers + Moderation loaded.")

    def cog_unload(self):
        try:
            self.game_info_loop.cancel()
        except Exception:
            pass

        for task in list(self.temp_ban_tasks.values()):
            if not task.done():
                task.cancel()

    # ========================================================
    # CONFIG
    # ========================================================

    def get_config(self, guild_id):
        guild_key = str(guild_id)

        if guild_key not in self.config or not isinstance(self.config[guild_key], dict):
            self.config[guild_key] = deepcopy(DEFAULT_GUILD_CONFIG)

        current = self.config[guild_key]
        changed = False

        for key, default in DEFAULT_GUILD_CONFIG.items():
            if key not in current:
                current[key] = deepcopy(default)
                changed = True

        for key in ("top_allowed_role_ids", "suggestions_allowed_role_ids", "blocked_words"):
            if not isinstance(current.get(key), list):
                current[key] = []
                changed = True

        for key in ("auto_triggers", "moderation_aliases"):
            if not isinstance(current.get(key), dict):
                current[key] = {}
                changed = True

        if not current["auto_triggers"]:
            current["auto_triggers"] = {
                "السلام عليكم": "وعليكم السلام ورحمة الله وبركاته"
            }
            changed = True

        if changed:
            save_config(self.config)

        return current

    # ========================================================
    # OWNER
    # ========================================================

    def is_owner(self, interaction):
        return interaction.user.id == OWNER_ID

    async def interaction_check(self, interaction: discord.Interaction):
        """حماية مركزية: كل أوامر هذا الملف للمالك، باستثناء إرسال الاقتراح للمستخدمين."""
        if interaction.user.id == OWNER_ID:
            return True

        command = interaction.command
        qualified = getattr(command, "qualified_name", "") if command else ""
        if qualified == "اقتراحات ارسال":
            return True

        if not interaction.response.is_done():
            await interaction.response.send_message("❌ هذا الأمر للمالك فقط.", ephemeral=True)
        return False

    async def owner_only(self, interaction):
        """يرجع True إذا تم منع المستخدم (ليس المالك أو خارج السيرفر)."""
        if not self.is_owner(interaction):
            await interaction.response.send_message("❌ هذا الأمر للمالك فقط.", ephemeral=True)
            return True

        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر يعمل داخل السيرفر فقط.", ephemeral=True)
            return True

        return False

    # ========================================================
    # IMAGE
    # ========================================================

    def is_supported_image(self, attachment):
        if not attachment:
            return False

        content_type = (attachment.content_type or "").lower().split(";")[0]
        filename = (attachment.filename or "").lower()

        return (
            content_type in {
                "image/png", "image/jpeg", "image/jpg",
                "image/webp", "image/gif", "image/apng"
            }
            or filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".apng"))
        )

    async def read_image_attachment(self, attachment):
        if not self.is_supported_image(attachment):
            raise ValueError("صيغة الصورة غير مدعومة.")

        data = await attachment.read()

        if not data:
            raise ValueError("الصورة فارغة.")

        try:
            image = Image.open(io.BytesIO(data))
            image.seek(0)
            return image.convert("RGBA")
        except Exception as error:
            raise ValueError("تعذر قراءة الصورة.") from error

    def get_font(self, size, bold=False):
        paths = (
            [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Bold.ttf",
            ]
            if bold else
            [
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
            ]
        )

        for path in paths:
            try:
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)
            except Exception:
                pass

        return ImageFont.load_default()

    def prepare_text(self, text):
        text = str(text or "")

        if ARABIC_SUPPORT:
            try:
                return get_display(arabic_reshaper.reshape(text))
            except Exception:
                pass

        return text

    def crop_to_fill(self, image, size):
        width, height = size
        image = image.convert("RGBA")

        if image.width <= 0 or image.height <= 0:
            return Image.new("RGBA", size, (10, 12, 18, 255))

        source_ratio = image.width / image.height
        target_ratio = width / height

        if source_ratio > target_ratio:
            new_height = height
            new_width = int(new_height * source_ratio)
        else:
            new_width = width
            new_height = int(new_width / source_ratio)

        image = image.resize((max(1, new_width), max(1, new_height)), Image.Resampling.LANCZOS)

        left = (image.width - width) // 2
        top = (image.height - height) // 2

        return image.crop((left, top, left + width, top + height))

    def image_to_jpeg(self, image, size=None, quality=88):
        if size:
            image = self.crop_to_fill(image, size)

        output = io.BytesIO()
        image.convert("RGB").save(
            output,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True
        )
        return output.getvalue()

    def draw_center(self, draw, x, y, text, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        width = bbox[2] - bbox[0]
        draw.text((x - width / 2, y), text, font=font, fill=fill)

    # ========================================================
    # TOP
    # ========================================================

    def get_now(self):
        return datetime.now(SAUDI_TZ)

    def get_period_keys(self):
        now = self.get_now()

        daily_date = now.date() if now.hour >= 22 else now.date() - timedelta(days=1)
        daily = daily_date.isoformat()

        week_start = now.date() - timedelta(days=(now.weekday() + 2) % 7)
        weekly = week_start.isoformat()

        monthly = f"{now.year}-{now.month:02d}"

        return daily, weekly, monthly

    def ensure_top_guild(self, guild_id):
        key = str(guild_id)

        if key not in self.top_data:
            self.top_data[key] = {"day": {}, "week": {}, "month": {}, "all": {}}

        for period in ("day", "week", "month", "all"):
            self.top_data[key].setdefault(period, {})

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

        for period in ("day", "week", "month", "all"):
            guild_data[period][uid] = guild_data[period].get(uid, 0) + 1

        save_top(self.top_data)

    def get_top_users(self, guild, period, limit=10):
        guild_data = self.ensure_top_guild(guild.id)
        daily, weekly, monthly = self.get_period_keys()

        expected = {"day": daily, "week": weekly, "month": monthly}

        if period in expected:
            if guild_data[period].get("_period") != expected[period]:
                guild_data[period] = {"_period": expected[period]}
            source = guild_data[period]
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
                results.append((member, int(points)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def build_top_embed(self, guild, period):
        names = {
            "day": "توب اليوم",
            "week": "توب الأسبوع",
            "month": "توب الشهر",
            "all": "توب الكل"
        }

        results = self.get_top_users(guild, period)

        if not results:
            return discord.Embed(
                title=f"🏆 {names[period]}",
                description="ما فيه بيانات كافية للحين.",
                color=discord.Color.blurple()
            )

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []

        for index, (member, points) in enumerate(results, 1):
            medal = medals.get(index, f"`#{index}`")
            lines.append(f"{medal} {member.mention} — **{points} نقطة**")

        embed = discord.Embed(
            title=f"🏆 {names[period]}",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Team Fime • Top System")
        return embed

    def normalize_top(self, content):
        return " ".join(str(content or "").split()).casefold()

    def top_period(self, content):
        value = self.normalize_top(content)

        aliases = {
            "day": "day", "daily": "day", "توب اليوم": "day", "اليوم": "day",
            "week": "week", "weekly": "week", "توب الأسبوع": "week",
            "توب الاسبوع": "week", "الأسبوع": "week", "الاسبوع": "week",
            "month": "month", "monthly": "month", "توب الشهر": "month", "الشهر": "month",
            "all": "all", "total": "all", "توب الكل": "all", "الكل": "all",
        }

        return aliases.get(value)

    def can_use_top(self, message, cfg):
        if message.author.id == OWNER_ID:
            return True

        roles = {
            int(x)
            for x in cfg.get("top_allowed_role_ids", [])
            if str(x).isdigit()
        }

        if roles.intersection(role.id for role in getattr(message.author, "roles", [])):
            return True

        channel_id = cfg.get("top_channel_id")

        return bool(channel_id and message.channel.id == int(channel_id))

    # ========================================================
    # TOP COMMANDS
    # ========================================================

    @top_group.command(name="روم", description="تحديد روم التوب")
    async def top_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["top_channel_id"] = channel.id if channel else None
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم تحديد روم التوب: {channel.mention}" if channel else "✅ تم إلغاء تحديد روم التوب.",
            ephemeral=True
        )

    @top_group.command(name="رتبة-اضافة", description="إضافة رتبة للتوب")
    async def top_role(self, interaction: discord.Interaction, role: discord.Role):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        if role.id not in cfg["top_allowed_role_ids"]:
            cfg["top_allowed_role_ids"].append(role.id)

        save_config(self.config)

        await interaction.response.send_message(f"✅ تمت إضافة {role.mention} للتوب.", ephemeral=True)

    @top_group.command(name="رتبة-حذف", description="إزالة رتبة من التوب")
    async def top_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        if role.id in cfg["top_allowed_role_ids"]:
            cfg["top_allowed_role_ids"].remove(role.id)

        save_config(self.config)

        await interaction.response.send_message(f"✅ تمت إزالة {role.mention}.", ephemeral=True)

    @top_group.command(name="حالة", description="عرض حالة التوب")
    async def top_status(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        channel = None
        if cfg.get("top_channel_id"):
            channel = interaction.guild.get_channel(int(cfg["top_channel_id"]))

        roles = []
        for rid in cfg["top_allowed_role_ids"]:
            role = interaction.guild.get_role(int(rid))
            if role:
                roles.append(role.mention)

        await interaction.response.send_message(
            (
                "## 🏆 حالة التوب\n\n"
                f"📍 **الروم:** {channel.mention if channel else 'غير محدد'}\n\n"
                f"🎖️ **الرتب:** {', '.join(roles) if roles else 'لا توجد'}"
            ),
            ephemeral=True
        )

    # ========================================================
    # LINE
    # ========================================================

    @line_group.command(name="تشغيل", description="تشغيل نظام الخط")
    async def line_setup(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        channel: discord.TextChannel = None
    ):
        if await self.owner_only(interaction):
            return

        if not self.is_supported_image(image):
            await interaction.response.send_message("❌ صيغة الصورة غير مدعومة.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        cfg = self.get_config(interaction.guild.id)

        try:
            data = await image.read()

            storage = channel or interaction.channel

            if not isinstance(storage, discord.TextChannel):
                raise RuntimeError("ما لقيت روم تخزين.")

            old_channel = None
            if cfg.get("storage_channel_id"):
                old_channel = interaction.guild.get_channel(int(cfg["storage_channel_id"]))

            if old_channel and cfg.get("storage_message_id"):
                try:
                    old = await old_channel.fetch_message(int(cfg["storage_message_id"]))
                    await old.delete()
                except Exception:
                    pass

            stored = await storage.send(
                "🖼️ **Fime Line Storage**",
                file=discord.File(io.BytesIO(data), filename=image.filename)
            )

            cfg["image_url"] = stored.attachments[0].url
            cfg["storage_channel_id"] = storage.id
            cfg["storage_message_id"] = stored.id
            cfg["channel_id"] = channel.id if channel else None
            cfg["enabled"] = True

            save_config(self.config)

            await interaction.followup.send("✅ **تم تشغيل نظام الخط.**", ephemeral=True)

        except Exception as error:
            print("❌ Line error:", error)
            await interaction.followup.send(
                f"❌ فشل تشغيل الخط: `{type(error).__name__}`",
                ephemeral=True
            )

    @line_group.command(name="ايقاف", description="إيقاف نظام الخط")
    async def line_off(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["enabled"] = False
        save_config(self.config)

        await interaction.response.send_message("🛑 تم إيقاف الخط.", ephemeral=True)

    @line_group.command(name="حالة", description="حالة الخط")
    async def line_status(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        channel = None
        if cfg.get("channel_id"):
            channel = interaction.guild.get_channel(int(cfg["channel_id"]))

        await interaction.response.send_message(
            (
                "## 🖼️ حالة الخط\n\n"
                f"الحالة: **{'🟢 مفعل' if cfg['enabled'] else '🔴 متوقف'}**\n"
                f"الروم: {channel.mention if channel else 'كل الرومات'}"
            ),
            ephemeral=True
        )

    @line_group.command(name="روم", description="تغيير روم الخط")
    async def line_channel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["channel_id"] = channel.id if channel else None
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ الخط يعمل الآن في {channel.mention}." if channel else "✅ الخط يعمل الآن في جميع الرومات.",
            ephemeral=True
        )

    # ========================================================
    # FIME
    # ========================================================

    @fime_group.command(name="رسالة", description="تغيير رد كلمة فيم")
    async def fime_message(self, interaction: discord.Interaction, message: str):
        if await self.owner_only(interaction):
            return

        if len(message) > 2000:
            await interaction.response.send_message("❌ الرسالة طويلة جدًا.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["fime_word_response"] = message
        cfg["fime_word_enabled"] = True
        save_config(self.config)

        await interaction.response.send_message("✅ تم تحديث رد فيم.", ephemeral=True)

    @fime_group.command(name="تشغيل", description="تشغيل نظام فيم")
    async def fime_enable(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["fime_word_enabled"] = True
        save_config(self.config)

        await interaction.response.send_message("🟢 تم تشغيل نظام فيم.", ephemeral=True)

    @fime_group.command(name="ايقاف", description="إيقاف نظام فيم")
    async def fime_disable(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["fime_word_enabled"] = False
        save_config(self.config)

        await interaction.response.send_message("🔴 تم إيقاف نظام فيم.", ephemeral=True)

    @fime_group.command(name="حالة", description="حالة نظام فيم")
    async def fime_status(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

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

    @room_group.command(name="تعريف", description="حفظ تعريف الروم")
    async def set_room_definition(self, interaction: discord.Interaction, definition: str):
        if await self.owner_only(interaction):
            return

        if len(definition) > 800:
            await interaction.response.send_message("❌ التعريف طويل جدًا.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["say_room_definition"] = definition
        save_config(self.config)

        await interaction.response.send_message("✅ تم حفظ تعريف الروم.", ephemeral=True)

    @room_group.command(name="تعريف-حذف", description="حذف تعريف الروم")
    async def delete_room_definition(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["say_room_definition"] = ""
        save_config(self.config)

        await interaction.response.send_message("🗑️ تم حذف تعريف الروم.", ephemeral=True)

    # ========================================================
    # SAY
    # ========================================================

    @app_commands.command(name="say", description="إرسال رسالة باسم البوت")
    @app_commands.describe(
        message="الرسالة التي تريد إرسالها",
        channel="الروم الذي سترسل فيه الرسالة — اختياري"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None
    ):
        if await self.owner_only(interaction):
            return

        if len(message) > 2000:
            await interaction.response.send_message("❌ الرسالة لا تتجاوز 2000 حرف.", ephemeral=True)
            return

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("❌ اختر رومًا نصيًا.", ephemeral=True)
            return

        try:
            sent = await target.send(
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
            f"✅ تم إرسال الرسالة باسم البوت.\n📍 {target.mention}\n🆔 `{sent.id}`",
            ephemeral=True
        )

    # ========================================================
    # GAME INFORMATION SYSTEM

    # ========================================================

    GAME_INFO_DATABASE = [
        {"name": "Hollow Knight", "difficulty": "متوسطة إلى صعبة", "suitable": "مناسب لمحبي الاستكشاف والتحدي", "best_mode": "القصة والاستكشاف", "genre": "Metroidvania"},
        {"name": "Minecraft", "difficulty": "سهلة إلى متوسطة", "suitable": "مناسب لمعظم اللاعبين", "best_mode": "Survival", "genre": "Sandbox / Survival"},
        {"name": "Terraria", "difficulty": "متوسطة", "suitable": "مناسب لمحبي البناء والاستكشاف والقتال", "best_mode": "Classic", "genre": "Sandbox / Adventure"},
        {"name": "Stardew Valley", "difficulty": "سهلة", "suitable": "مناسب لمن يفضل اللعب الهادئ والتقدم التدريجي", "best_mode": "Single Player", "genre": "Farming / Life Sim"},
        {"name": "Elden Ring", "difficulty": "صعبة", "suitable": "مناسب لمحبي التحدي والقتال والاستكشاف", "best_mode": "القصة والاستكشاف", "genre": "Action RPG"},
        {"name": "Rocket League", "difficulty": "سهلة في البداية وصعبة للاحتراف", "suitable": "مناسب للعب السريع والمنافسة", "best_mode": "Competitive", "genre": "Sports / Action"},
        {"name": "Fortnite", "difficulty": "متوسطة", "suitable": "مناسب لمحبي المنافسة واللعب الجماعي", "best_mode": "Battle Royale", "genre": "Battle Royale"},
        {"name": "Valorant", "difficulty": "متوسطة إلى صعبة", "suitable": "مناسب لمحبي التصويب التكتيكي", "best_mode": "Competitive", "genre": "Tactical FPS"},
        {"name": "Brawl Stars", "difficulty": "سهلة إلى متوسطة", "suitable": "مناسب للجلسات القصيرة واللعب الجماعي", "best_mode": "3v3", "genre": "Action"},
        {"name": "Roblox", "difficulty": "تختلف حسب التجربة", "suitable": "مناسب لمعظم اللاعبين مع اختلاف التجربة", "best_mode": "حسب التجربة", "genre": "Platform"},
        {"name": "Celeste", "difficulty": "صعبة", "suitable": "مناسب لمحبي تحديات المنصات", "best_mode": "القصة", "genre": "Platformer"},
        {"name": "Among Us", "difficulty": "سهلة", "suitable": "مناسب للعب الجماعي مع الأصدقاء", "best_mode": "Online", "genre": "Social Deduction"},
    ]

    @tasks.loop(minutes=5)
    async def game_info_loop(self):
        for guild in self.bot.guilds:
            cfg = self.get_config(guild.id)

            if not cfg.get("game_info_enabled"):
                continue

            channel_id = cfg.get("game_info_channel_id")
            if not channel_id:
                continue

            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                await channel.send(embed=self.build_random_game_info_embed(guild))
            except Exception as error:
                print("⚠️ Game info loop error:", error)

    @game_info_loop.before_loop
    async def before_game_info_loop(self):
        await self.bot.wait_until_ready()

    def build_random_game_info_embed(self, guild):
        game = random.choice(self.GAME_INFO_DATABASE)

        embed = discord.Embed(
            title=f"🎮 {game['name']}",
            description="معلومة عشوائية عن لعبة مناسبة لجلسة اليوم.",
            color=discord.Color.dark_grey()
        )
        embed.add_field(name="🎯 النوع", value=game["genre"], inline=True)
        embed.add_field(name="📊 مستوى الصعوبة", value=game["difficulty"], inline=True)
        embed.add_field(name="👥 تناسب", value=game["suitable"], inline=False)
        embed.add_field(name="⭐ أفضل طور", value=game["best_mode"], inline=True)
        embed.set_footer(text="Team Fime • تتجدد معلومات الألعاب كل 5 دقائق")
        return embed

    @app_commands.command(
        name="معلومات-العاب",
        description="تشغيل أو إيقاف معلومات الألعاب في روم محدد"
    )
    @app_commands.describe(
        action="تشغيل أو إيقاف النظام",
        channel="الروم الذي ينشر فيه النظام"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="تشغيل", value="on"),
            app_commands.Choice(name="إيقاف", value="off"),
        ]
    )
    async def game_info_command(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        channel: discord.TextChannel = None
    ):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        if action.value == "off":
            cfg["game_info_enabled"] = False
            save_config(self.config)
            await interaction.response.send_message("⏹️ تم إيقاف نظام معلومات الألعاب.", ephemeral=True)
            return

        if channel is None:
            await interaction.response.send_message("❌ عند التشغيل لازم تحدد الروم.", ephemeral=True)
            return

        try:
            await channel.send(embed=self.build_random_game_info_embed(interaction.guild))
        except Exception as error:
            await interaction.response.send_message(
                f"❌ ما قدرت أرسل في الروم: `{type(error).__name__}`",
                ephemeral=True
            )
            return

        cfg["game_info_enabled"] = True
        cfg["game_info_channel_id"] = channel.id
        save_config(self.config)

        await interaction.response.send_message(
            (
                f"✅ تم تشغيل **معلومات الألعاب** في {channel.mention}.\n"
                "🔄 سيتم نشر لعبة عشوائية جديدة كل 5 دقائق."
            ),
            ephemeral=True
        )

    # ========================================================
    # SERVER INFORMATION
    # ========================================================

    def build_server_embed(self, guild):
        owner = guild.owner

        embed = discord.Embed(
            title=f"🛰️ {guild.name}",
            description="معلومات السيرفر الذي يستخدم فيه البوت حاليًا.",
            color=discord.Color.blurple()
        )

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="🆔 Server ID", value=f"`{guild.id}`", inline=False)
        embed.add_field(name="👥 الأعضاء", value=f"`{guild.member_count or 0:,}`", inline=True)
        embed.add_field(name="💬 القنوات", value=f"`{len(guild.channels):,}`", inline=True)
        embed.add_field(name="🎭 الرتب", value=f"`{len(guild.roles):,}`", inline=True)
        embed.add_field(name="👑 المالك", value=owner.mention if owner else "غير معروف", inline=True)
        embed.add_field(
            name="📅 إنشاء السيرفر",
            value=discord.utils.format_dt(guild.created_at, "F"),
            inline=False
        )
        embed.set_footer(text=f"Team Fime • البوت موجود في {len(self.bot.guilds)} سيرفر")

        return embed

    async def send_server_panel(self, interaction):
        if await self.owner_only(interaction):
            return

        current = interaction.guild

        total_members = sum(guild.member_count or 0 for guild in self.bot.guilds)

        embed = self.build_server_embed(current)
        embed.title = "🛰️ معلومات البوت والسيرفر"
        embed.description = (
            f"**البوت موجود حاليًا في `{len(self.bot.guilds)}` سيرفر.**\n\n"
            f"السيرفر الحالي: **{current.name}**"
        )

        embed.add_field(name="🌐 إجمالي السيرفرات", value=f"`{len(self.bot.guilds):,}`", inline=True)
        embed.add_field(name="👥 إجمالي الأعضاء", value=f"`{total_members:,}`", inline=True)

        options = [
            discord.SelectOption(
                label=guild.name[:100],
                value=str(guild.id),
                emoji="🛰️",
                description=f"ID: {guild.id}"
            )
            for guild in self.bot.guilds[:25]
        ]

        await interaction.response.send_message(
            embed=embed,
            view=ServerSelectView(self, options),
            ephemeral=True
        )

    @control_group.command(name="معلومات", description="معلومات السيرفرات التي يستخدم فيها البوت")
    async def server_command(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        await self.send_server_panel(interaction)

    # ========================================================
    # BOT MESSAGE EDIT
    # ========================================================

    @control_group.command(name="تعديل-رسالة", description="تعديل رسالة أرسلها البوت")
    @app_commands.describe(
        channel="الروم الذي توجد فيه الرسالة",
        message_id="ID الرسالة",
        new_message="النص الجديد"
    )
    async def edit_bot_message(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message_id: str,
        new_message: str
    ):
        if await self.owner_only(interaction):
            return

        if not message_id.isdigit():
            await interaction.response.send_message("❌ Message ID غير صحيح.", ephemeral=True)
            return

        if len(new_message) > 2000:
            await interaction.response.send_message("❌ الرسالة تتجاوز 2000 حرف.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            message = await channel.fetch_message(int(message_id))
        except discord.NotFound:
            await interaction.followup.send("❌ ما لقيت الرسالة.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.followup.send("❌ ما أقدر أوصل للروم أو الرسالة.", ephemeral=True)
            return
        except Exception as error:
            await interaction.followup.send(f"❌ فشل جلب الرسالة: `{type(error).__name__}`", ephemeral=True)
            return

        if not self.bot.user or message.author.id != self.bot.user.id:
            await interaction.followup.send("❌ تقدر تعدل رسائل البوت فقط.", ephemeral=True)
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
            f"✅ **تم تعديل رسالة البوت.**\n📍 {channel.mention}\n🆔 `{message.id}`",
            ephemeral=True
        )

    # ========================================================
    # SUGGESTIONS
    # ========================================================

    def get_suggestion_id(self):
        numbers = [int(key) for key in self.suggestions.keys() if str(key).isdigit()]
        return str(max(numbers, default=0) + 1)

    def can_manage_suggestions(self, member, cfg):
        if member.id == OWNER_ID:
            return True

        allowed = {
            int(role_id)
            for role_id in cfg.get("suggestions_allowed_role_ids", [])
            if str(role_id).isdigit()
        }

        return bool(allowed.intersection(role.id for role in getattr(member, "roles", [])))

    def suggestion_embed(self, suggestion):
        status = suggestion.get("status", "قيد المراجعة")

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
            color=colors.get(status, discord.Color.blurple())
        )

        embed.add_field(
            name="📌 الحالة",
            value=f"{status_emojis.get(status, '📌')} **{status}**",
            inline=True
        )
        embed.add_field(name="🏷️ النوع", value=str(suggestion.get("option", "عام"))[:1024], inline=True)
        embed.add_field(name="👤 صاحب الاقتراح", value=f"<@{suggestion['user_id']}>", inline=True)

        if suggestion.get("created_at"):
            try:
                dt = datetime.fromisoformat(suggestion["created_at"])
                embed.add_field(name="🕐 التاريخ", value=discord.utils.format_dt(dt, "R"), inline=True)
            except Exception:
                pass

        if suggestion.get("admin_reply"):
            embed.add_field(name="💬 رد الإدارة", value=suggestion["admin_reply"][:1024], inline=False)

        if suggestion.get("image_url"):
            try:
                embed.set_image(url=suggestion["image_url"])
            except Exception:
                pass

        embed.add_field(name="👍 مؤيد", value=f"`{len(suggestion.get('upvotes', []))}`", inline=True)
        embed.add_field(name="👎 غير مؤيد", value=f"`{len(suggestion.get('downvotes', []))}`", inline=True)

        if suggestion.get("action_by"):
            embed.add_field(name="🛡️ آخر إجراء بواسطة", value=f"<@{suggestion['action_by']}>", inline=True)

        embed.set_footer(text="Team Fime • Suggestions • أزرار الإدارة أسفل الرسالة")

        return embed

    async def create_suggestion_data(self, guild, channel, user, text, image_url=None, option="عام"):
        sid = self.get_suggestion_id()

        data = {
            "id": sid,
            "guild_id": guild.id,
            "channel_id": channel.id,
            "message_id": None,
            "user_id": user.id,
            "text": text,
            "option": option or "عام",
            "image_url": image_url,
            "status": "قيد المراجعة",
            "admin_reply": "",
            "action_by": None,
            "upvotes": [],
            "downvotes": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # نحفظ الاقتراح أولًا حتى يقرأ SuggestionView الأصوات الصحيحة.
        self.suggestions[sid] = data

        try:
            cfg = self.get_config(guild.id)
            mention_role_id = cfg.get("suggestions_mention_role_id")
            mention_role = guild.get_role(int(mention_role_id)) if str(mention_role_id).isdigit() else None
            content = mention_role.mention if mention_role else None
            allowed = discord.AllowedMentions(roles=True) if mention_role else discord.AllowedMentions.none()
            message = await channel.send(
                content=content,
                embed=self.suggestion_embed(data),
                view=SuggestionView(self, sid),
                allowed_mentions=allowed
            )
        except Exception:
            self.suggestions.pop(sid, None)
            raise

        data["message_id"] = message.id
        save_suggestions(self.suggestions)

        await self.send_suggestion_log(data, guild, "اقتراح جديد")

        return data

    async def send_suggestion_log(self, data, guild, action="إجراء"):
        cfg = self.get_config(guild.id)

        log_id = cfg.get("suggestions_log_channel_id")
        if not log_id:
            return

        channel = guild.get_channel(int(log_id))
        if not channel:
            return

        embed = discord.Embed(
            title=f"📝 {action}",
            description=data["text"],
            color=discord.Color.blurple()
        )
        embed.add_field(name="🔢 الرقم", value=f"`#{data['id']}`", inline=True)
        embed.add_field(name="👤 العضو", value=f"<@{data['user_id']}>", inline=True)
        embed.add_field(name="📌 الحالة", value=data.get("status", "قيد المراجعة"), inline=True)

        if data.get("action_by"):
            embed.add_field(name="🛡️ المنفذ", value=f"<@{data['action_by']}>", inline=True)

        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception as error:
            print("⚠️ Suggestion log error:", error)

    # ========================================================
    # MANUAL SUGGESTION
    # ========================================================

    async def suggestion_option_autocomplete(self, interaction: discord.Interaction, current: str):
        cfg = self.get_config(interaction.guild.id) if interaction.guild else {}
        options = cfg.get("suggestion_options", [])
        current = (current or "").casefold()
        result = []
        for option in options:
            option = str(option).strip()
            if option and current in option.casefold():
                result.append(app_commands.Choice(name=option[:100], value=option[:100]))
        return result[:25]

    @suggest_group.command(name="ارسال", description="إرسال اقتراح للسيرفر")
    @app_commands.describe(option="اختر نوع الاقتراح", suggestion="اكتب اقتراحك")
    @app_commands.autocomplete(option=suggestion_option_autocomplete)
    async def create_suggestion(self, interaction: discord.Interaction, option: str, suggestion: str):
        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر داخل السيرفر فقط.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)

        channel_id = cfg.get("suggestions_channel_id")
        if not channel_id:
            await interaction.response.send_message("❌ ما تم تحديد روم الاقتراحات.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(int(channel_id))
        if not channel:
            await interaction.response.send_message("❌ روم الاقتراحات غير موجود.", ephemeral=True)
            return

        if len(suggestion) < 5:
            await interaction.response.send_message("❌ الاقتراح قصير جدًا.", ephemeral=True)
            return

        options = [str(x).strip() for x in cfg.get("suggestion_options", []) if str(x).strip()]
        option = str(option or "").strip()
        if options and option not in options:
            await interaction.response.send_message("❌ اختر نوعًا من الخيارات التي حددها المالك.", ephemeral=True)
            return
        if not options:
            option = "عام"

        if len(suggestion) > 1500:
            await interaction.response.send_message("❌ الاقتراح طويل جدًا.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            data = await self.create_suggestion_data(
                interaction.guild,
                channel,
                interaction.user,
                suggestion,
                option=option
            )

            await interaction.followup.send(
                f"✅ تم إرسال اقتراحك برقم **#{data['id']}**.",
                ephemeral=True
            )

        except Exception as error:
            print("❌ Suggestion create error:", error)
            await interaction.followup.send("❌ تعذر إرسال الاقتراح.", ephemeral=True)

    # ========================================================
    # AUTO SUGGESTION
    # ========================================================

    async def handle_suggestion_message(self, message, cfg):
        channel_id = cfg.get("suggestions_channel_id")

        if not channel_id:
            return False

        if message.channel.id != int(channel_id):
            return False

        text = (message.content or "").strip()

        if (not text and not message.attachments) or (len(text) < 5 and not message.attachments):
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

        try:
            await message.delete()
        except Exception as error:
            print("⚠️ Suggestion delete error:", error)

        try:
            await self.create_suggestion_data(
                message.guild,
                message.channel,
                message.author,
                text or "—",
                image_url=image_url,
                option="عام"
            )
        except Exception as error:
            print("❌ Auto suggestion error:", error)

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

    @suggest_group.command(name="روم", description="تحديد روم الاقتراحات")
    async def suggestion_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["suggestions_channel_id"] = channel.id
        save_config(self.config)

        await interaction.response.send_message(
            (
                f"✅ تم تحديد روم الاقتراحات: {channel.mention}\n\n"
                "أي رسالة عضو داخل الروم تتحول تلقائيًا إلى اقتراح."
            ),
            ephemeral=True
        )

    @suggest_group.command(name="سجل", description="تحديد روم سجل الاقتراحات")
    async def suggestion_log_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["suggestions_log_channel_id"] = channel.id
        save_config(self.config)

        await interaction.response.send_message(f"✅ روم سجل الاقتراحات: {channel.mention}", ephemeral=True)

    @suggest_group.command(name="رتبة-اضافة", description="إضافة رتبة مسموح لها قبول ورفض الاقتراحات")
    async def suggestion_role(self, interaction: discord.Interaction, role: discord.Role):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        if role.id not in cfg["suggestions_allowed_role_ids"]:
            cfg["suggestions_allowed_role_ids"].append(role.id)

        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تمت إضافة {role.mention} لإدارة الاقتراحات.",
            ephemeral=True
        )

    @suggest_group.command(name="رتبة-حذف", description="إزالة رتبة من إدارة الاقتراحات")
    async def suggestion_role_remove(self, interaction: discord.Interaction, role: discord.Role):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        if role.id in cfg["suggestions_allowed_role_ids"]:
            cfg["suggestions_allowed_role_ids"].remove(role.id)

        save_config(self.config)

        await interaction.response.send_message(f"✅ تمت إزالة {role.mention}.", ephemeral=True)

    @suggest_group.command(name="رتب", description="عرض رتب إدارة الاقتراحات")
    async def suggestion_roles(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        roles = []
        for role_id in cfg["suggestions_allowed_role_ids"]:
            role = interaction.guild.get_role(int(role_id))
            if role:
                roles.append(role.mention)

        await interaction.response.send_message(
            (
                "## 🛡️ رتب إدارة الاقتراحات\n\n"
                f"{', '.join(roles) if roles else 'لا توجد رتب محددة.'}"
            ),
            ephemeral=True
        )

    @suggest_group.command(name="خيار-اضافة", description="إضافة خيار يظهر للمستخدم قبل إرسال الاقتراح")
    async def suggestion_option_add(self, interaction: discord.Interaction, option: str):
        if await self.owner_only(interaction):
            return
        option = option.strip()
        if not option or len(option) > 100:
            await interaction.response.send_message("❌ الخيار يجب أن يكون بين 1 و100 حرف.", ephemeral=True)
            return
        cfg = self.get_config(interaction.guild.id)
        options = [str(x) for x in cfg.get("suggestion_options", []) if str(x).strip()]
        if option.casefold() in {x.casefold() for x in options}:
            await interaction.response.send_message("ℹ️ هذا الخيار موجود أصلًا.", ephemeral=True)
            return
        if len(options) >= 25:
            await interaction.response.send_message("❌ الحد الأقصى 25 خيارًا.", ephemeral=True)
            return
        options.append(option)
        cfg["suggestion_options"] = options
        save_config(self.config)
        await interaction.response.send_message(f"✅ تمت إضافة خيار **{option}**.", ephemeral=True)

    @suggest_group.command(name="خيار-حذف", description="حذف خيار من الاقتراحات")
    async def suggestion_option_remove(self, interaction: discord.Interaction, option: str):
        if await self.owner_only(interaction):
            return
        cfg = self.get_config(interaction.guild.id)
        options = [str(x) for x in cfg.get("suggestion_options", [])]
        match = next((x for x in options if x.casefold() == option.strip().casefold()), None)
        if not match:
            await interaction.response.send_message("❌ الخيار غير موجود.", ephemeral=True)
            return
        options.remove(match)
        cfg["suggestion_options"] = options
        save_config(self.config)
        await interaction.response.send_message(f"🗑️ تم حذف **{match}**.", ephemeral=True)

    @suggest_group.command(name="خيارات", description="عرض خيارات الاقتراحات")
    async def suggestion_option_list(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return
        cfg = self.get_config(interaction.guild.id)
        options = [str(x) for x in cfg.get("suggestion_options", []) if str(x).strip()]
        await interaction.response.send_message(
            "## 🏷️ خيارات الاقتراحات\n\n" + ("\n".join(f"• `{x}`" for x in options) if options else "لا توجد خيارات؛ سيظهر النوع كـ `عام`."),
            ephemeral=True
        )

    @suggest_group.command(name="منشن", description="تحديد رتبة يتم منشنها عند وصول اقتراح جديد")
    async def suggestion_mention_role(self, interaction: discord.Interaction, role: discord.Role = None):
        if await self.owner_only(interaction):
            return
        cfg = self.get_config(interaction.guild.id)
        cfg["suggestions_mention_role_id"] = role.id if role else None
        save_config(self.config)
        await interaction.response.send_message(
            f"✅ تاق الاقتراحات: {role.mention}" if role else "🛑 تم إلغاء تاق الاقتراحات.",
            ephemeral=True
        )

    # ========================================================
    # SUGGESTION STATUS
    # ========================================================

    @suggest_group.command(name="حالة", description="تغيير حالة اقتراح")
    @app_commands.describe(suggestion_id="رقم الاقتراح", status="الحالة الجديدة")
    @app_commands.choices(
        status=[
            app_commands.Choice(name="قيد المراجعة", value="قيد المراجعة"),
            app_commands.Choice(name="قيد التنفيذ", value="قيد التنفيذ"),
            app_commands.Choice(name="مقبول", value="مقبول"),
            app_commands.Choice(name="مرفوض", value="مرفوض"),
            app_commands.Choice(name="مكتمل", value="مكتمل"),
        ]
    )
    async def suggestion_status(
        self,
        interaction: discord.Interaction,
        suggestion_id: str,
        status: app_commands.Choice[str]
    ):
        if await self.owner_only(interaction):
            return
        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر داخل السيرفر فقط.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)

        if not self.can_manage_suggestions(interaction.user, cfg):
            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بإدارة الاقتراحات.",
                ephemeral=True
            )
            return

        data = self.suggestions.get(suggestion_id.strip().lstrip("#"))

        if not data:
            await interaction.response.send_message("❌ الاقتراح غير موجود.", ephemeral=True)
            return

        data["status"] = status.value
        data["action_by"] = interaction.user.id
        save_suggestions(self.suggestions)

        await self.refresh_suggestion(
            data,
            disable_buttons=status.value in ("مقبول", "مرفوض")
        )

        await self.send_suggestion_log(
            data,
            interaction.guild,
            f"تغيير حالة الاقتراح إلى {status.value}"
        )

        await interaction.response.send_message(
            f"✅ تم تغيير الحالة إلى **{status.value}**.",
            ephemeral=True
        )

    # ========================================================
    # ADMIN REPLY
    # ========================================================

    @suggest_group.command(name="رد", description="إضافة رد الإدارة على اقتراح")
    async def suggestion_reply(self, interaction: discord.Interaction, suggestion_id: str, reply: str):
        if await self.owner_only(interaction):
            return

        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر داخل السيرفر فقط.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)

        if not self.can_manage_suggestions(interaction.user, cfg):
            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بإدارة الاقتراحات.",
                ephemeral=True
            )
            return

        data = self.suggestions.get(suggestion_id.strip().lstrip("#"))

        if not data:
            await interaction.response.send_message("❌ الاقتراح غير موجود.", ephemeral=True)
            return

        data["admin_reply"] = reply[:1024]
        data["action_by"] = interaction.user.id
        save_suggestions(self.suggestions)

        await self.refresh_suggestion(
            data,
            disable_buttons=data.get("status") in ("مقبول", "مرفوض")
        )

        await self.send_suggestion_log(data, interaction.guild, "تم تحديث رد الإدارة")

        await interaction.response.send_message("✅ تم إضافة رد الإدارة.", ephemeral=True)

    # ========================================================
    # ACCEPT / REJECT / VOTE
    # ========================================================

    async def change_suggestion_status(self, interaction, suggestion_id, status):
        if not interaction.guild:
            await interaction.response.send_message("❌ هذا الأمر داخل السيرفر فقط.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)

        if not self.can_manage_suggestions(interaction.user, cfg):
            await interaction.response.send_message(
                "❌ ما عندك رتبة مسموح لها بقبول أو رفض الاقتراحات.",
                ephemeral=True
            )
            return

        data = self.suggestions.get(str(suggestion_id))

        if not data:
            await interaction.response.send_message("❌ الاقتراح غير موجود.", ephemeral=True)
            return

        if data.get("status") == status:
            await interaction.response.send_message(f"ℹ️ الاقتراح بالفعل **{status}**.", ephemeral=True)
            return

        data["status"] = status
        data["action_by"] = interaction.user.id
        save_suggestions(self.suggestions)

        # نرد أولًا على التفاعل قبل أي عمليات ثقيلة حتى لا ينتهي وقته.
        await interaction.response.send_message(
            f"{'✅' if status == 'مقبول' else '❌'} تم تسجيل الاقتراح كـ **{status}**.",
            ephemeral=True
        )

        await self.refresh_suggestion(data, disable_buttons=True)
        await self.send_suggestion_log(data, interaction.guild, f"تم {status} الاقتراح")

    async def vote_suggestion(self, interaction, suggestion_id, upvote):
        data = self.suggestions.get(str(suggestion_id))

        if not data:
            await interaction.response.send_message("❌ الاقتراح غير موجود.", ephemeral=True)
            return

        data.setdefault("upvotes", [])
        data.setdefault("downvotes", [])

        uid = str(interaction.user.id)
        upvotes = set(str(x) for x in data["upvotes"])
        downvotes = set(str(x) for x in data["downvotes"])

        if upvote:
            if uid in upvotes:
                upvotes.remove(uid)
                state = "تم إلغاء تصويتك."
            else:
                upvotes.add(uid)
                downvotes.discard(uid)
                state = "تم تسجيل تصويتك 👍."
        else:
            if uid in downvotes:
                downvotes.remove(uid)
                state = "تم إلغاء تصويتك."
            else:
                downvotes.add(uid)
                upvotes.discard(uid)
                state = "تم تسجيل تصويتك 👎."

        data["upvotes"] = list(upvotes)
        data["downvotes"] = list(downvotes)
        save_suggestions(self.suggestions)

        await interaction.response.send_message(
            f"{state}\n👍 `{len(upvotes)}`  •  👎 `{len(downvotes)}`",
            ephemeral=True
        )

        await self.refresh_suggestion(data)

    async def refresh_suggestion(self, data, disable_buttons=False):
        guild = self.bot.get_guild(int(data["guild_id"]))
        if not guild:
            return

        channel = guild.get_channel(int(data["channel_id"]))
        if not channel:
            return

        try:
            message = await channel.fetch_message(int(data["message_id"]))

            view = None if disable_buttons else SuggestionView(self, data["id"])

            await message.edit(
                embed=self.suggestion_embed(data),
                view=view,
                allowed_mentions=discord.AllowedMentions.none()
            )

        except Exception as error:
            print("⚠️ Suggestion refresh error:", error)

    # ========================================================
    # AUTO TRIGGERS
    # ========================================================

    def normalize_trigger(self, text):
        return " ".join(str(text or "").strip().casefold().split())

    def get_triggers(self, cfg):
        triggers = cfg.get("auto_triggers", {})
        return triggers if isinstance(triggers, dict) else {}

    @trigger_group.command(name="اضافة", description="إضافة رد تلقائي لمحفز")
    @app_commands.describe(
        trigger="الكلمة أو العبارة التي يكتبها العضو",
        response="الرد الذي يرسله البوت"
    )
    async def trigger_add(self, interaction: discord.Interaction, trigger: str, response: str):
        if await self.owner_only(interaction):
            return

        trigger = self.normalize_trigger(trigger)

        if not trigger:
            await interaction.response.send_message("❌ اكتب محفزًا صحيحًا.", ephemeral=True)
            return

        if len(response) > 2000:
            await interaction.response.send_message("❌ الرد طويل جدًا.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)
        triggers = self.get_triggers(cfg)
        triggers[trigger] = response
        cfg["auto_triggers"] = triggers
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم حفظ المحفز.\n\n**المحفز:** `{trigger}`\n**الرد:** {response}",
            ephemeral=True
        )

    @trigger_group.command(name="حذف", description="حذف رد تلقائي")
    async def trigger_remove(self, interaction: discord.Interaction, trigger: str):
        if await self.owner_only(interaction):
            return

        trigger = self.normalize_trigger(trigger)

        cfg = self.get_config(interaction.guild.id)
        triggers = self.get_triggers(cfg)

        if trigger not in triggers:
            await interaction.response.send_message("❌ هذا المحفز غير موجود.", ephemeral=True)
            return

        del triggers[trigger]
        cfg["auto_triggers"] = triggers
        save_config(self.config)

        await interaction.response.send_message(f"🗑️ تم حذف المحفز `{trigger}`.", ephemeral=True)

    @trigger_group.command(name="تعديل", description="تعديل رد محفز موجود")
    async def trigger_edit(self, interaction: discord.Interaction, trigger: str, response: str):
        if await self.owner_only(interaction):
            return

        trigger = self.normalize_trigger(trigger)

        cfg = self.get_config(interaction.guild.id)
        triggers = self.get_triggers(cfg)

        if trigger not in triggers:
            await interaction.response.send_message("❌ هذا المحفز غير موجود.", ephemeral=True)
            return

        if len(response) > 2000:
            await interaction.response.send_message("❌ الرد طويل جدًا.", ephemeral=True)
            return

        triggers[trigger] = response
        cfg["auto_triggers"] = triggers
        save_config(self.config)

        await interaction.response.send_message(f"✅ تم تعديل رد `{trigger}`.", ephemeral=True)

    @trigger_group.command(name="قائمة", description="عرض المحفزات التلقائية")
    async def trigger_list(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        triggers = self.get_triggers(cfg)

        if not triggers:
            await interaction.response.send_message("📭 ما فيه محفزات محفوظة.", ephemeral=True)
            return

        lines = [
            f"• `{trigger}` → {response[:150]}"
            for trigger, response in list(triggers.items())[:40]
        ]

        text = "## 🤖 المحفزات التلقائية\n\n" + "\n".join(lines)

        await interaction.response.send_message(text[:2000], ephemeral=True)

    # ========================================================
    # MODERATION HELPERS
    # ========================================================

    def has_moderation_permission(self, member, action):
        if member.id == OWNER_ID:
            return True

        permissions = member.guild_permissions

        if permissions.administrator:
            return True

        if action in ("ban", "unban"):
            return permissions.ban_members

        if action == "kick":
            return permissions.kick_members

        if action == "warn":
            return permissions.moderate_members or permissions.manage_messages

        if action == "delete":
            return permissions.manage_messages

        return False

    def is_moderator(self, member):
        """هل العضو يملك أي صلاحية إدارية؟ (لتجاهل رسائل الأعضاء العاديين)"""
        if member.id == OWNER_ID:
            return True

        p = member.guild_permissions

        return bool(
            p.administrator or p.ban_members or p.kick_members
            or p.moderate_members or p.manage_messages
        )

    def can_act_on_member(self, actor, target):
        if target.id == actor.id:
            return False

        if target.id == OWNER_ID:
            return False

        if actor.id == OWNER_ID:
            return True

        if target.id == actor.guild.owner_id:
            return False

        return target.top_role < actor.top_role

    def add_warning(self, guild_id, user_id, moderator_id, reason):
        guild_key = str(guild_id)
        user_key = str(user_id)

        self.warnings.setdefault(guild_key, {})
        self.warnings[guild_key].setdefault(user_key, [])

        self.warnings[guild_key][user_key].append(
            {
                "moderator_id": moderator_id,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        )

        save_warnings(self.warnings)

        return len(self.warnings[guild_key][user_key])

    def normalize_filter_text(self, text):
        text = str(text or "").casefold()
        for char in "ًٌٍَُِّْـ":
            text = text.replace(char, "")
        return " ".join(text.split())

    def get_blocked_words(self, cfg):
        words = cfg.get("blocked_words", [])

        if not isinstance(words, list):
            return []

        return [
            self.normalize_filter_text(word)
            for word in words
            if self.normalize_filter_text(word)
        ]

    def get_moderation_aliases(self, cfg):
        aliases = cfg.get("moderation_aliases", {})

        if not isinstance(aliases, dict):
            return {}

        return {
            str(alias).strip(): action
            for alias, action in aliases.items()
            if str(alias).strip() and action in MOD_ACTIONS
        }

    def resolve_moderation_command(self, command, cfg):
        return self.get_moderation_aliases(cfg).get(command, command)

    def parse_duration(self, value):
        if not value:
            return None

        text = str(value).strip().casefold()
        match = re.fullmatch(
            r"(\d+(?:\.\d+)?)\s*(ثانية|دقيقة|ساعة|أسبوع|اسبوع|يوم|ث|s|m|د|h|س|d|ي|w)",
            text
        )

        if not match:
            return None

        amount = float(match.group(1))
        unit = match.group(2)

        multipliers = {
            "ث": 1, "ثانية": 1, "s": 1,
            "m": 60, "د": 60, "دقيقة": 60,
            "h": 3600, "س": 3600, "ساعة": 3600,
            "d": 86400, "ي": 86400, "يوم": 86400,
            "w": 604800, "أسبوع": 604800, "اسبوع": 604800,
        }

        return max(1, int(amount * multipliers[unit]))

    def format_duration(self, seconds):
        seconds = int(seconds)
        parts = []

        for amount, label in (
            (604800, "أسبوع"),
            (86400, "يوم"),
            (3600, "ساعة"),
            (60, "دقيقة"),
            (1, "ثانية"),
        ):
            if seconds >= amount:
                value, seconds = divmod(seconds, amount)
                parts.append(f"{value} {label}")

            if len(parts) >= 2:
                break

        return " و ".join(parts) or "ثانية"

    async def schedule_temp_unban(self, guild_id, user_id, unban_at):
        key = f"{guild_id}:{user_id}"

        old = self.temp_ban_tasks.get(key)
        if old and not old.done():
            old.cancel()

        async def worker():
            try:
                wait_for = max(0, float(unban_at) - datetime.now(timezone.utc).timestamp())

                if wait_for:
                    await asyncio.sleep(wait_for)

                guild = self.bot.get_guild(int(guild_id))

                if guild:
                    try:
                        await guild.unban(
                            discord.Object(id=int(user_id)),
                            reason="انتهاء مدة الحظر المؤقت"
                        )
                    except discord.NotFound:
                        pass
                    except discord.Forbidden:
                        print(f"❌ لا أستطيع فك الحظر المؤقت عن {user_id}.")

                self.temp_bans.pop(key, None)
                save_temp_bans(self.temp_bans)

            except asyncio.CancelledError:
                return
            except Exception as error:
                print("❌ Temp ban worker error:", error)
            finally:
                # لا نحذف المهمة إلا إذا كانت هي المهمة الحالية (لا مهمة جديدة حلّت مكانها).
                if self.temp_ban_tasks.get(key) is asyncio.current_task():
                    self.temp_ban_tasks.pop(key, None)

        self.temp_ban_tasks[key] = asyncio.create_task(worker())

    async def restore_temp_bans(self):
        if not isinstance(self.temp_bans, dict):
            self.temp_bans = {}

        for key, data in list(self.temp_bans.items()):
            try:
                await self.schedule_temp_unban(
                    int(data["guild_id"]),
                    int(data["user_id"]),
                    float(data["unban_at"])
                )
            except Exception:
                self.temp_bans.pop(key, None)

        save_temp_bans(self.temp_bans)

    async def handle_blocked_words(self, message, cfg):
        if message.author.id == OWNER_ID:
            return False

        if isinstance(message.author, discord.Member):
            permissions = message.author.guild_permissions
            if permissions.manage_messages or permissions.administrator:
                return False

        words = self.get_blocked_words(cfg)
        if not words:
            return False

        normalized = self.normalize_filter_text(message.content)

        for word in words:
            if word and word in normalized:
                try:
                    await message.delete()
                except Exception:
                    pass

                try:
                    await message.channel.send(
                        "🚫 تم حذف الرسالة لأنها تحتوي على كلمة محظورة.",
                        delete_after=5
                    )
                except Exception:
                    pass

                return True

        return False

    # ========================================================
    # MODERATION SETTINGS — ALIASES
    # ========================================================

    @shortcut_group.command(name="اضافة", description="إضافة اختصار مخصص لأوامر الإدارة")
    @app_commands.describe(
        shortcut="الاختصار الذي سيكتبه العضو",
        action="الأمر الذي سينفذه الاختصار"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="حظر", value="حظر"),
            app_commands.Choice(name="روح", value="روح"),
            app_commands.Choice(name="فارق", value="فارق"),
            app_commands.Choice(name="تحذير", value="ت"),
            app_commands.Choice(name="حذف رسائل", value="مح"),
        ]
    )
    async def moderation_alias_add(
        self,
        interaction: discord.Interaction,
        shortcut: str,
        action: app_commands.Choice[str]
    ):
        if await self.owner_only(interaction):
            return

        shortcut = shortcut.strip()

        if not shortcut or len(shortcut) > 32 or " " in shortcut:
            await interaction.response.send_message(
                "❌ اكتب اختصارًا من كلمة واحدة (1 إلى 32 حرفًا).",
                ephemeral=True
            )
            return

        cfg = self.get_config(interaction.guild.id)
        aliases = self.get_moderation_aliases(cfg)
        aliases[shortcut] = action.value
        cfg["moderation_aliases"] = aliases
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم حفظ `{shortcut}` كاختصار لـ **{action.name}**.",
            ephemeral=True
        )

    @shortcut_group.command(name="حذف", description="حذف اختصار مخصص")
    @app_commands.describe(shortcut="الاختصار")
    async def moderation_alias_remove(self, interaction: discord.Interaction, shortcut: str):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        aliases = self.get_moderation_aliases(cfg)

        if shortcut not in aliases:
            await interaction.response.send_message("❌ هذا الاختصار غير موجود.", ephemeral=True)
            return

        aliases.pop(shortcut, None)
        cfg["moderation_aliases"] = aliases
        save_config(self.config)

        await interaction.response.send_message(f"🗑️ تم حذف الاختصار `{shortcut}`.", ephemeral=True)

    @shortcut_group.command(name="قائمة", description="عرض اختصارات الإدارة المخصصة")
    async def moderation_alias_list(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        aliases = self.get_moderation_aliases(cfg)

        lines = [f"• `{alias}` → **{action}**" for alias, action in aliases.items()]

        await interaction.response.send_message(
            "## ⌨️ اختصارات الإدارة\n\n"
            + ("\n".join(lines) if lines else "لا توجد اختصارات مخصصة."),
            ephemeral=True
        )

    # ========================================================
    # BLOCKED WORDS
    # ========================================================

    @filter_group.command(name="اضافة", description="إضافة كلمة إلى فلتر الكلمات المحظورة")
    @app_commands.describe(word="الكلمة أو العبارة")
    async def blocked_word_add(self, interaction: discord.Interaction, word: str):
        if await self.owner_only(interaction):
            return

        word = self.normalize_filter_text(word)

        if not word or len(word) > 100:
            await interaction.response.send_message("❌ الكلمة غير صالحة.", ephemeral=True)
            return

        cfg = self.get_config(interaction.guild.id)
        words = self.get_blocked_words(cfg)

        if word not in words:
            words.append(word)

        cfg["blocked_words"] = words[:200]
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تمت إضافة `{word}` إلى الكلمات المحظورة.",
            ephemeral=True
        )

    @filter_group.command(name="حذف", description="حذف كلمة من فلتر الكلمات المحظورة")
    @app_commands.describe(word="الكلمة أو العبارة")
    async def blocked_word_remove(self, interaction: discord.Interaction, word: str):
        if await self.owner_only(interaction):
            return

        word = self.normalize_filter_text(word)

        cfg = self.get_config(interaction.guild.id)
        words = self.get_blocked_words(cfg)

        if word not in words:
            await interaction.response.send_message("❌ الكلمة غير موجودة.", ephemeral=True)
            return

        words.remove(word)
        cfg["blocked_words"] = words
        save_config(self.config)

        await interaction.response.send_message(f"🗑️ تمت إزالة `{word}`.", ephemeral=True)

    @filter_group.command(name="قائمة", description="عرض الكلمات المحظورة")
    async def blocked_word_list(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        words = self.get_blocked_words(cfg)

        text = (
            "## 🚫 الكلمات المحظورة\n\n"
            + ("\n".join(f"• `{word}`" for word in words) if words else "لا توجد كلمات.")
        )

        await interaction.response.send_message(text[:2000], ephemeral=True)

    # ========================================================
    # MODERATION SHORTCUTS (TEXT)
    # ========================================================

    async def handle_moderation_shortcut(self, message):
        content = (message.content or "").strip()

        if not content:
            return False

        parts = content.split()

        cfg = self.get_config(message.guild.id)
        command = self.resolve_moderation_command(parts[0], cfg)

        # ليست كلمة أمر إدارة أصلًا.
        if command not in MOD_ACTIONS:
            return False

        # الأعضاء العاديون يمرون كأي رسالة عادية (لا يتم استهلاك كلمة مثل "ت").
        if not isinstance(message.author, discord.Member) or not self.is_moderator(message.author):
            return False

        # حظر بدون أي شيء = قائمة الاختصارات.
        if command == "حظر" and len(parts) == 1:
            try:
                await message.channel.send(
                    "🛡️ **اختصارات الإدارة**\nاختر الأمر الذي تبي تعرف طريقته:",
                    view=ModerationShortcutView(self.get_moderation_aliases(cfg)),
                    delete_after=90
                )
            except Exception:
                pass
            return True

        # ----------------------------------------------------
        # BAN — حظر دائم أو مؤقت، والسبب اختياري
        # ----------------------------------------------------
        if command == "حظر":
            if not message.mentions:
                return False

            target = message.mentions[0]

            if not isinstance(target, discord.Member):
                return True

            if not self.has_moderation_permission(message.author, "ban"):
                await message.channel.send("❌ ما عندك صلاحية الحظر.", delete_after=6)
                return True

            if not self.can_act_on_member(message.author, target):
                await message.channel.send(
                    "❌ ما تقدر تحظر هذا العضو بسبب الرتبة أو الصلاحيات.",
                    delete_after=6
                )
                return True

            remaining = parts[2:]
            duration_seconds = None
            reason = "بدون سبب محدد"

            if remaining:
                parsed = self.parse_duration(remaining[0])

                if parsed is not None:
                    duration_seconds = parsed
                    if len(remaining) > 1:
                        reason = " ".join(remaining[1:]).strip() or reason
                else:
                    reason = " ".join(remaining).strip() or reason

            try:
                try:
                    await target.send(
                        f"🔨 تم حظرك من **{message.guild.name}**.\nالسبب: **{reason}**"
                        + (
                            f"\nالمدة: **{self.format_duration(duration_seconds)}**"
                            if duration_seconds else "\nالمدة: **دائم**"
                        )
                    )
                except Exception:
                    pass

                await target.ban(reason=f"{message.author} — {reason}"[:512])

                if duration_seconds:
                    unban_at = datetime.now(timezone.utc).timestamp() + duration_seconds
                    key = f"{message.guild.id}:{target.id}"

                    self.temp_bans[key] = {
                        "guild_id": message.guild.id,
                        "user_id": target.id,
                        "unban_at": unban_at,
                        "reason": reason,
                    }
                    save_temp_bans(self.temp_bans)

                    await self.schedule_temp_unban(message.guild.id, target.id, unban_at)

                    text = (
                        f"🔨 تم حظر **{target}** لمدة "
                        f"**{self.format_duration(duration_seconds)}**."
                    )
                else:
                    text = f"🔨 تم حظر **{target}** بشكل دائم."

                await message.channel.send(f"{text}\nالسبب: **{reason}**", delete_after=8)

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
            if not message.mentions:
                if len(parts) == 1:
                    await message.channel.send("`روح @عضو`", delete_after=8)
                    return True
                return False

            target = message.mentions[0]

            if not isinstance(target, discord.Member):
                return True

            if not self.has_moderation_permission(message.author, "kick"):
                await message.channel.send("❌ ما عندك صلاحية الطرد.", delete_after=6)
                return True

            if not self.can_act_on_member(message.author, target):
                await message.channel.send("❌ ما تقدر تطرد هذا العضو.", delete_after=6)
                return True

            reason = " ".join(parts[2:]).strip() or "بدون سبب محدد"

            try:
                await target.kick(reason=f"{message.author} — {reason}"[:512])
                await message.channel.send(
                    f"🦶 تم طرد **{target}**.\nالسبب: **{reason}**",
                    delete_after=8
                )
            except Exception as error:
                await message.channel.send(
                    f"❌ فشل الطرد: `{type(error).__name__}`",
                    delete_after=8
                )

            return True

        # ----------------------------------------------------
        # UNBAN — فارق
        # ----------------------------------------------------
        if command == "فارق":
            if len(parts) < 2:
                await message.channel.send("`فارق USER_ID` لفك حظر عضو.", delete_after=8)
                return True

            if not self.has_moderation_permission(message.author, "unban"):
                await message.channel.send("❌ ما عندك صلاحية فك الحظر.", delete_after=6)
                return True

            raw_id = re.sub(r"[^0-9]", "", parts[1])

            if not raw_id:
                await message.channel.send("❌ اكتب ID العضو المحظور.", delete_after=6)
                return True

            reason = " ".join(parts[2:]).strip() or "بدون سبب محدد"

            try:
                await message.guild.unban(
                    discord.Object(id=int(raw_id)),
                    reason=f"{message.author} — {reason}"[:512]
                )

                key = f"{message.guild.id}:{int(raw_id)}"
                self.temp_bans.pop(key, None)
                save_temp_bans(self.temp_bans)

                task = self.temp_ban_tasks.pop(key, None)
                if task and not task.done():
                    task.cancel()

                await message.channel.send(f"🔓 تم فك حظر `{raw_id}`.", delete_after=8)

            except discord.NotFound:
                await message.channel.send("❌ هذا العضو غير موجود في قائمة المحظورين.", delete_after=7)
            except Exception as error:
                await message.channel.send(
                    f"❌ فشل فك الحظر: `{type(error).__name__}`",
                    delete_after=8
                )

            return True

        # ----------------------------------------------------
        # WARN — ت
        # ----------------------------------------------------
        if command == "ت":
            if not message.mentions:
                if len(parts) == 1:
                    await message.channel.send("`ت @عضو السبب`", delete_after=8)
                    return True
                return False

            target = message.mentions[0]

            if not isinstance(target, discord.Member):
                return True

            if not self.has_moderation_permission(message.author, "warn"):
                await message.channel.send("❌ ما عندك صلاحية التحذير.", delete_after=6)
                return True

            if not self.can_act_on_member(message.author, target):
                await message.channel.send("❌ ما تقدر تحذر هذا العضو.", delete_after=6)
                return True

            reason = " ".join(parts[2:]).strip() or "بدون سبب محدد"

            count = self.add_warning(
                message.guild.id,
                target.id,
                message.author.id,
                reason
            )

            await message.channel.send(
                (
                    f"⚠️ تم تحذير **{target}**.\n"
                    f"السبب: **{reason}**\n"
                    f"عدد التحذيرات: **{count}**"
                ),
                delete_after=10
            )
            return True

        # ----------------------------------------------------
        # PURGE MEMBER — مح
        # ----------------------------------------------------
        if command == "مح":
            if not message.mentions:
                if len(parts) == 1:
                    await message.channel.send("`مح @عضو`", delete_after=8)
                    return True
                return False

            target = message.mentions[0]

            if not isinstance(target, discord.Member):
                return True

            if not self.has_moderation_permission(message.author, "delete"):
                await message.channel.send("❌ ما عندك صلاحية حذف الرسائل.", delete_after=6)
                return True

            try:
                deleted = await message.channel.purge(
                    limit=100,
                    check=lambda m: m.author.id == target.id
                )
                await message.channel.send(
                    f"🧹 تم حذف **{len(deleted)}** رسالة من {target.mention}.",
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
    # ROLE PANEL COMMANDS
    # ========================================================

    def get_role_panel(self, guild_id):
        key = str(guild_id)
        data = self.role_panels.setdefault(key, {})
        data.setdefault("channel_id", None)
        data.setdefault("message_id", None)
        data.setdefault("roles", [])
        return data

    def build_role_panel_embed(self, guild):
        panel = self.get_role_panel(guild.id)
        roles = []
        for item in panel.get("roles", [])[:25]:
            role = guild.get_role(int(item.get("role_id", 0)))
            if role:
                roles.append((role, item.get("label") or role.name, item.get("emoji") or "•"))
        if not roles:
            description = "لا توجد رتب مضافة حاليًا.\n\nيستطيع المالك إضافة الرتب من أوامر `/رتب`."
        else:
            description = "\n".join(f"{emoji} {role.mention} — **{label}**" for role, label, emoji in roles)
        embed = discord.Embed(title="🎖️ لوحة الرتب", description=description, color=discord.Color.blurple())
        embed.set_footer(text="اضغط على الرتبة لإضافتها أو إزالتها")
        return embed

    async def refresh_role_panel(self, guild):
        panel = self.get_role_panel(guild.id)
        channel_id = panel.get("channel_id")
        message_id = panel.get("message_id")
        if not channel_id or not message_id:
            return False
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return False
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(
                embed=self.build_role_panel_embed(guild),
                view=RolePanelView(self, guild.id, panel.get("roles", [])),
                allowed_mentions=discord.AllowedMentions.none()
            )
            return True
        except Exception as error:
            print("⚠️ Role panel refresh error:", error)
            return False

    @roles_group.command(name="لوحة", description="إنشاء أو استعادة لوحة الرتب في روم محدد")
    async def role_panel_create(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        if await self.owner_only(interaction):
            return
        panel = self.get_role_panel(interaction.guild.id)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message("❌ اختر رومًا نصيًا.", ephemeral=True)
            return

        panel["channel_id"] = target.id
        save_role_panels(self.role_panels)
        if await self.refresh_role_panel(interaction.guild):
            await interaction.response.send_message("✅ تم تحديث لوحة الرتب القديمة بدون حذف إعداداتها.", ephemeral=True)
            return

        message = await target.send(
            embed=self.build_role_panel_embed(interaction.guild),
            view=RolePanelView(self, interaction.guild.id, panel.get("roles", [])),
            allowed_mentions=discord.AllowedMentions.none()
        )
        panel["message_id"] = message.id
        save_role_panels(self.role_panels)
        await interaction.response.send_message(f"✅ تم إنشاء لوحة الرتب في {target.mention}.", ephemeral=True)

    @roles_group.command(name="اضافة", description="إضافة رتبة إلى لوحة الرتب")
    async def role_panel_add(self, interaction: discord.Interaction, role: discord.Role, label: str = None, emoji: str = None):
        if await self.owner_only(interaction):
            return
        panel = self.get_role_panel(interaction.guild.id)
        roles = panel.setdefault("roles", [])
        if any(int(x.get("role_id", 0)) == role.id for x in roles):
            await interaction.response.send_message("ℹ️ هذه الرتبة موجودة في اللوحة أصلًا.", ephemeral=True)
            return
        if len(roles) >= 25:
            await interaction.response.send_message("❌ الحد الأقصى 25 رتبة في اللوحة.", ephemeral=True)
            return
        roles.append({"role_id": role.id, "label": (label or role.name)[:80], "emoji": (emoji or "•")[:2]})
        save_role_panels(self.role_panels)
        updated = await self.refresh_role_panel(interaction.guild)
        await interaction.response.send_message(
            f"✅ تمت إضافة {role.mention} إلى اللوحة." + ("" if updated else " استخدم `/رتب لوحة` لإنشائها أو ربطها."),
            ephemeral=True
        )

    @roles_group.command(name="حذف", description="حذف رتبة من لوحة الرتب")
    async def role_panel_remove(self, interaction: discord.Interaction, role: discord.Role):
        if await self.owner_only(interaction):
            return
        panel = self.get_role_panel(interaction.guild.id)
        old = len(panel.get("roles", []))
        panel["roles"] = [x for x in panel.get("roles", []) if int(x.get("role_id", 0)) != role.id]
        if len(panel["roles"]) == old:
            await interaction.response.send_message("❌ هذه الرتبة ليست في اللوحة.", ephemeral=True)
            return
        save_role_panels(self.role_panels)
        await self.refresh_role_panel(interaction.guild)
        await interaction.response.send_message(f"🗑️ تمت إزالة {role.mention} من اللوحة.", ephemeral=True)

    @roles_group.command(name="تحديث", description="تحديث لوحة الرتب مع الحفاظ على الرتب المحفوظة")
    async def role_panel_refresh(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return
        if await self.refresh_role_panel(interaction.guild):
            await interaction.response.send_message("✅ تم تحديث لوحة الرتب بدون إعادة إضافة الرتب.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ ما لقيت لوحة محفوظة. استخدم `/رتب لوحة` أولًا.", ephemeral=True)

    @roles_group.command(name="حالة", description="عرض إعدادات لوحة الرتب")
    async def role_panel_status(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return
        panel = self.get_role_panel(interaction.guild.id)
        channel = interaction.guild.get_channel(int(panel["channel_id"])) if panel.get("channel_id") else None
        roles = [interaction.guild.get_role(int(x.get("role_id", 0))) for x in panel.get("roles", [])]
        roles = [r.mention for r in roles if r]
        await interaction.response.send_message(
            f"## 🎖️ حالة لوحة الرتب\n\n📍 الروم: {channel.mention if channel else 'غير محدد'}\n🆔 الرسالة: `{panel.get('message_id') or 'غير محددة'}`\n🎖️ الرتب: {', '.join(roles) if roles else 'لا توجد'}",
            ephemeral=True
        )

    # ========================================================
    # JOIN
    # ========================================================

    async def send_join_mention(self, member):
        cfg = self.get_config(member.guild.id)

        if not cfg.get("join_mention_enabled"):
            return

        channel_id = cfg.get("join_mention_channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return

        try:
            sent = await channel.send(
                member.mention,
                allowed_mentions=discord.AllowedMentions(users=True)
            )

            duration = cfg.get("join_mention_duration", 2)

            try:
                duration = float(duration)
            except Exception:
                duration = 2

            await asyncio.sleep(max(0.1, min(duration, 30)))
            await sent.delete()

        except Exception as error:
            print("❌ Join mention error:", error)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return

        await asyncio.sleep(0.5)
        await self.send_join_mention(member)

    @mention_group.command(name="روم", description="تحديد روم منشن الأعضاء الجدد")
    async def mention_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["join_mention_channel_id"] = channel.id
        cfg["join_mention_enabled"] = True
        save_config(self.config)

        await interaction.response.send_message(
            f"✅ تم تشغيل منشن الدخول في {channel.mention}.",
            ephemeral=True
        )

    @mention_group.command(name="ايقاف", description="إيقاف منشن الدخول")
    async def mention_off(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["join_mention_enabled"] = False
        save_config(self.config)

        await interaction.response.send_message("🛑 تم إيقاف منشن الدخول.", ephemeral=True)

    @mention_group.command(name="حالة", description="حالة منشن الدخول")
    async def mention_status(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)

        channel = None
        if cfg.get("join_mention_channel_id"):
            channel = interaction.guild.get_channel(int(cfg["join_mention_channel_id"]))

        await interaction.response.send_message(
            (
                "## 👋 حالة منشن الدخول\n\n"
                f"الحالة: **{'🟢 مفعل' if cfg['join_mention_enabled'] else '🔴 متوقف'}**\n"
                f"الروم: {channel.mention if channel else 'غير محدد'}"
            ),
            ephemeral=True
        )

    @mention_group.command(name="الغاء", description="إلغاء روم منشن الدخول")
    async def mention_channel_clear(self, interaction: discord.Interaction):
        if await self.owner_only(interaction):
            return

        cfg = self.get_config(interaction.guild.id)
        cfg["join_mention_enabled"] = False
        cfg["join_mention_channel_id"] = None
        save_config(self.config)

        await interaction.response.send_message("✅ تم إلغاء نظام منشن الدخول.", ephemeral=True)

    # ========================================================
    # MAIN MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.guild:
            return

        cfg = self.get_config(message.guild.id)

        # SUGGESTIONS FIRST
        if await self.handle_suggestion_message(message, cfg):
            return

        # MODERATION SHORTCUTS
        if cfg.get("moderation_enabled", True):
            if await self.handle_moderation_shortcut(message):
                return

        # BLOCKED WORDS
        if await self.handle_blocked_words(message, cfg):
            return

        # TOP
        self.add_top_point(message.guild.id, message.author.id)

        period = self.top_period(message.content)

        if period and self.can_use_top(message, cfg):
            try:
                await message.channel.send(
                    embed=self.build_top_embed(message.guild, period),
                    view=TopSelectView(self, message.guild.id),
                    allowed_mentions=discord.AllowedMentions.none()
                )
            except Exception as error:
                print("❌ TOP error:", error)

            return

        # AUTO TRIGGERS
        normalized_message = self.normalize_trigger(message.content)
        triggers = self.get_triggers(cfg)

        if normalized_message in triggers:
            try:
                await message.channel.send(
                    triggers[normalized_message],
                    allowed_mentions=discord.AllowedMentions.none()
                )
            except Exception as error:
                print("❌ Auto trigger error:", error)

            return

        # FIME
        normalized = " ".join(message.content.strip().split()).casefold()

        if cfg.get("fime_word_enabled", True):
            if (
                normalized == "فيم"
                or (cfg.get("fime_word_accept_fimi", False) and normalized == "فيمي")
            ):
                try:
                    await message.channel.send(
                        cfg.get("fime_word_response", "هلا؟ وش تبي يا فايم؟"),
                        allowed_mentions=discord.AllowedMentions.none()
                    )
                except Exception as error:
                    print("❌ Fime error:", error)

                return

        # LINE
        if not cfg.get("enabled"):
            return

        image_url = cfg.get("image_url")
        if not image_url:
            return

        channel_id = cfg.get("channel_id")

        if channel_id and message.channel.id != int(channel_id):
            return

        me = message.guild.me
        if not me:
            return

        if not message.channel.permissions_for(me).send_messages:
            return

        try:
            await message.channel.send(
                image_url,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception as error:
            print("⚠️ Line error:", error)


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    existing = bot.get_cog("AutomaticLineSystem")

    if existing:
        print("⚠️ bot5 موجود مسبقًا.")
        return

    cog = AutomaticLineSystem(bot)

    await bot.add_cog(cog)

    try:
        if not cog.game_info_loop.is_running():
            cog.game_info_loop.start()
    except Exception as error:
        print("⚠️ Game info task start error:", error)

    try:
        await cog.restore_temp_bans()
    except Exception as error:
        print("⚠️ Temp ban restore error:", error)

    # RESTORE ROLE PANEL
    for guild_id, panel in cog.role_panels.items():
        try:
            roles = panel.get("roles", []) if isinstance(panel, dict) else []
            if panel.get("message_id") and roles:
                bot.add_view(RolePanelView(cog, int(guild_id), roles))
        except Exception as error:
            print("⚠️ Role panel persistent view error:", error)

    # RESTORE SUGGESTION BUTTONS
    for suggestion in cog.suggestions.values():
        try:
            if suggestion.get("status") in ("مقبول", "مرفوض"):
                continue

            bot.add_view(SuggestionView(cog, suggestion["id"]))

        except Exception as error:
            print("⚠️ Suggestion persistent view error:", error)

    print("✅ Team Fime bot5 loaded successfully.")