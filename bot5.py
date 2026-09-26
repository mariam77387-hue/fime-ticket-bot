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
# SAY SYSTEM — BOT SPEAK + AVATAR/BANNER/TEMPLATE
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

from PIL import Image, ImageDraw, ImageFilter


# ============================================================
# CONFIG
# ============================================================

OWNER_ID = 1388514481444880549

CONFIG_FILE = Path("bot5_config.json")
TOP_FILE = Path("bot5_top.json")

# توقيت السعودية UTC+3
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

    # الروم الذي يستطيع أي عضو استخدام كلمات التوب فيه
    "top_channel_id": None,

    # الرتب التي تستطيع استخدام كلمات التوب في جميع الرومات
    "top_allowed_role_ids": [],
}


# ============================================================
# JSON — CONFIG
# ============================================================

def load_config():

    try:

        if not CONFIG_FILE.exists():
            return {}

        with CONFIG_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:

        print(
            "❌ bot5 config load error:",
            error
        )

        return {}


def save_config(data):

    temp_file = CONFIG_FILE.with_suffix(".tmp")

    try:

        with temp_file.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            CONFIG_FILE
        )

    except Exception as error:

        print(
            "❌ bot5 config save error:",
            error
        )

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

        with TOP_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except Exception as error:

        print(
            "❌ bot5 top load error:",
            error
        )

        return {}


def save_top(data):

    temp_file = TOP_FILE.with_suffix(".tmp")

    try:

        with temp_file.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            temp_file,
            TOP_FILE
        )

    except Exception as error:

        print(
            "❌ bot5 top save error:",
            error
        )

        try:

            if temp_file.exists():
                temp_file.unlink()

        except Exception:
            pass


# ============================================================
# TOP SELECT MENU
# ============================================================

class TopSelect(discord.ui.Select):

    def __init__(
        self,
        cog,
        guild_id
    ):

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
                description="التوب الكامل منذ بداية النظام"
            ),
        ]

        super().__init__(
            placeholder="اختر نوع التوب...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"fime_top_select_{guild_id}"
        )


    async def callback(
        self,
        interaction: discord.Interaction
    ):

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

    def __init__(
        self,
        cog,
        guild_id
    ):

        super().__init__(
            timeout=900
        )

        self.add_item(
            TopSelect(
                cog,
                guild_id
            )
        )


# ============================================================
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    def __init__(
        self,
        bot
    ):

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

    def get_config(
        self,
        guild_id
    ):

        key = str(guild_id)

        if key not in self.config:

            self.config[key] = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

            save_config(
                self.config
            )

        current = self.config[key]

        if not isinstance(current, dict):

            current = deepcopy(
                DEFAULT_GUILD_CONFIG
            )

            self.config[key] = current

        changed = False

        for name, default in DEFAULT_GUILD_CONFIG.items():

            if name not in current:

                current[name] = deepcopy(
                    default
                )

                changed = True

        if not isinstance(
            current.get("top_allowed_role_ids"),
            list
        ):

            current["top_allowed_role_ids"] = []
            changed = True

        if changed:

            save_config(
                self.config
            )

        return current


    # ========================================================
    # OWNER CHECK
    # ========================================================

    def is_owner(
        self,
        interaction: discord.Interaction
    ):

        return interaction.user.id == OWNER_ID


    async def silently_ignore_if_not_owner(
        self,
        interaction
    ):

        if self.is_owner(interaction):
            return False

        return True


    # ========================================================
    # IMAGE VALIDATION
    # ========================================================

    def is_supported_image(
        self,
        attachment: discord.Attachment
    ):

        content_type = (
            attachment.content_type
            or ""
        ).lower().split(";")[0].strip()

        filename = (
            attachment.filename
            or ""
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

    def get_storage_filename(
        self,
        attachment: discord.Attachment
    ):

        original_name = (
            attachment.filename
            or ""
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

        cfg = self.get_config(
            guild.id
        )

        storage_channel = None

        if cfg.get(
            "storage_channel_id"
        ):

            storage_channel = (
                guild.get_channel(
                    int(
                        cfg[
                            "storage_channel_id"
                        ]
                    )
                )
            )

        if storage_channel is None:

            configured_channel_id = (
                cfg.get(
                    "channel_id"
                )
            )

            if configured_channel_id:

                storage_channel = (
                    guild.get_channel(
                        int(
                            configured_channel_id
                        )
                    )
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

        permissions = (
            storage_channel.permissions_for(me)
        )

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
            fp=io.BytesIO(
                image_bytes
            ),
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

        stored_attachment = (
            message.attachments[0]
        )

        cfg["image_url"] = (
            stored_attachment.url
        )

        cfg["storage_channel_id"] = (
            storage_channel.id
        )

        cfg["storage_message_id"] = (
            message.id
        )

        save_config(
            self.config
        )

        return (
            stored_attachment.url,
            storage_channel,
            message
        )


    # ========================================================
    # DELETE OLD STORAGE
    # ========================================================

    async def delete_old_storage(
        self,
        guild
    ):

        cfg = self.get_config(
            guild.id
        )

        channel_id = cfg.get(
            "storage_channel_id"
        )

        message_id = cfg.get(
            "storage_message_id"
        )

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

        return datetime.now(
            SAUDI_TZ
        )


    def get_period_keys(self):

        now = self.get_now()

        # اليوم يتغير الساعة 10 مساءً
        if now.hour >= 22:

            daily_date = now.date()

        else:

            daily_date = (
                now.date()
                - timedelta(days=1)
            )

        daily_key = (
            daily_date.isoformat()
        )

        # الأسبوع يبدأ من السبت
        week_start = (
            now.date()
            - timedelta(
                days=(
                    now.weekday() + 2
                ) % 7
            )
        )

        weekly_key = (
            week_start.isoformat()
        )

        monthly_key = (
            f"{now.year}-{now.month:02d}"
        )

        return (
            daily_key,
            weekly_key,
            monthly_key
        )


    def ensure_top_guild(
        self,
        guild_id
    ):

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


    def add_top_point(
        self,
        guild_id,
        user_id
    ):

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

        if guild_data["day"].get(
            "_period"
        ) != daily_key:

            guild_data["day"] = {
                "_period": daily_key
            }

        if guild_data["week"].get(
            "_period"
        ) != weekly_key:

            guild_data["week"] = {
                "_period": weekly_key
            }

        if guild_data["month"].get(
            "_period"
        ) != monthly_key:

            guild_data["month"] = {
                "_period": monthly_key
            }

        user_key = str(user_id)

        guild_data["day"][user_key] = (
            guild_data["day"].get(
                user_key,
                0
            ) + 1
        )

        guild_data["week"][user_key] = (
            guild_data["week"].get(
                user_key,
                0
            ) + 1
        )

        guild_data["month"][user_key] = (
            guild_data["month"].get(
                user_key,
                0
            ) + 1
        )

        guild_data["all"][user_key] = (
            guild_data["all"].get(
                user_key,
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

        if period == "day":

            daily_key, _, _ = (
                self.get_period_keys()
            )

            if guild_data["day"].get(
                "_period"
            ) != daily_key:

                guild_data["day"] = {
                    "_period": daily_key
                }

                save_top(
                    self.top_data
                )

            source = guild_data["day"]

        elif period == "week":

            _, weekly_key, _ = (
                self.get_period_keys()
            )

            if guild_data["week"].get(
                "_period"
            ) != weekly_key:

                guild_data["week"] = {
                    "_period": weekly_key
                }

                save_top(
                    self.top_data
                )

            source = guild_data["week"]

        elif period == "month":

            _, _, monthly_key = (
                self.get_period_keys()
            )

            if guild_data["month"].get(
                "_period"
            ) != monthly_key:

                guild_data["month"] = {
                    "_period": monthly_key
                }

                save_top(
                    self.top_data
                )

            source = guild_data["month"]

        else:

            source = guild_data["all"]

        results = []

        for user_id, points in source.items():

            if user_id == "_period":
                continue

            try:

                member = guild.get_member(
                    int(user_id)
                )

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


    def get_period_title(
        self,
        period
    ):

        if period == "day":
            return "توب اليوم"

        if period == "week":
            return "توب الأسبوع"

        if period == "month":
            return "توب الشهر"

        return "توب الكل"


    def build_top_embed(
        self,
        guild,
        period
    ):

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
                description=(
                    "ما فيه بيانات كافية للحين."
                ),
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


    def normalize_top_keyword(
        self,
        content
    ):

        value = str(
            content or ""
        ).strip()

        value = " ".join(
            value.split()
        )

        return value.casefold()


    def get_top_keyword_period(
        self,
        content
    ):

        normalized = self.normalize_top_keyword(
            content
        )

        keywords = {
            "day": "day",
            "week": "week",
            "month": "month",
            "all": "all",
        }

        return keywords.get(
            normalized
        )


    def member_can_use_top_keyword(
        self,
        message,
        cfg
    ):

        if message.author.id == OWNER_ID:
            return True

        # الرتب المسموح لها تستخدم التوب في كل الرومات
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

        # باقي الأعضاء: فقط روم التوب المحدد
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

        except discord.Forbidden as error:

            print(
                "⚠️ bot5 TOP permission error:",
                error
            )

        except discord.HTTPException as error:

            print(
                "⚠️ bot5 TOP HTTP error:",
                error
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
        interaction: discord.Interaction,
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

            save_config(
                self.config
            )

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

        permissions = channel.permissions_for(
            me
        )

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

        save_config(
            self.config
        )

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
        interaction: discord.Interaction,
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
                (
                    f"ℹ️ الرتبة {role.mention} "
                    "مضافة مسبقًا."
                ),
                ephemeral=True
            )

            return

        roles.append(
            role.id
        )

        save_config(
            self.config
        )

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
        interaction: discord.Interaction,
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
                (
                    f"ℹ️ الرتبة {role.mention} "
                    "ليست ضمن رتب التوب."
                ),
                ephemeral=True
            )

            return

        roles.remove(
            role.id
        )

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                f"✅ تم إزالة {role.mention} "
                "من رتب التوب."
            ),
            ephemeral=True
        )


    @app_commands.command(
        name="توب-حالة",
        description="عرض إعدادات نظام التوب"
    )
    async def top_status(
        self,
        interaction: discord.Interaction
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

        top_channel_id = cfg.get(
            "top_channel_id"
        )

        if top_channel_id:

            try:

                top_channel = (
                    interaction.guild.get_channel(
                        int(top_channel_id)
                    )
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
                roles.append(
                    role.mention
                )

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
        interaction: discord.Interaction,
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

        if not self.is_supported_image(
            image
        ):

            await interaction.response.send_message(
                (
                    "❌ أرسل صورة بصيغة "
                    "`PNG` أو `JPG` أو `JPEG` "
                    "أو `WEBP` أو `GIF` أو `APNG`."
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        guild = interaction.guild

        cfg = self.get_config(
            guild.id
        )

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

            permissions = channel.permissions_for(
                me
            )

            if not permissions.view_channel:

                await interaction.followup.send(
                    f"❌ ما أقدر أشوف "
                    f"{channel.mention}.",
                    ephemeral=True
                )

                return

            if not permissions.send_messages:

                await interaction.followup.send(
                    f"❌ ما أقدر أرسل في "
                    f"{channel.mention}.",
                    ephemeral=True
                )

                return

            cfg["channel_id"] = channel.id

        await self.delete_old_storage(
            guild
        )

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

        save_config(
            self.config
        )

        if channel:

            target_text = channel.mention

        else:

            target_text = (
                "كل الرومات النصية التي يستطيع "
                "البوت الكتابة فيها"
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


    # ========================================================
    # /خط-إيقاف
    # ========================================================

    @app_commands.command(
        name="خط-إيقاف",
        description="إيقاف الخط التلقائي"
    )
    async def line_off(
        self,
        interaction: discord.Interaction
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

        cfg["enabled"] = False

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🛑 تم إيقاف نظام الخط.",
            ephemeral=True
        )


    # ========================================================
    # /خط-حالة
    # ========================================================

    @app_commands.command(
        name="خط-حالة",
        description="عرض حالة نظام الخط"
    )
    async def line_status(
        self,
        interaction: discord.Interaction
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

            channel = (
                interaction.guild.get_channel(
                    int(channel_id)
                )
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


    # ========================================================
    # /خط-روم
    # ========================================================

    @app_commands.command(
        name="خط-روم",
        description="تغيير نطاق الخط إلى روم محدد أو جميع الرومات"
    )
    async def line_channel(
        self,
        interaction: discord.Interaction,
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

            save_config(
                self.config
            )

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

        permissions = channel.permissions_for(
            me
        )

        if not permissions.view_channel:

            await interaction.response.send_message(
                f"❌ ما أقدر أشوف "
                f"{channel.mention}.",
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                f"❌ ما أقدر أرسل في "
                f"{channel.mention}.",
                ephemeral=True
            )

            return

        cfg["channel_id"] = channel.id

        save_config(
            self.config
        )

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

    def normalize_fime_keyword(
        self,
        content: str
    ):

        value = str(
            content or ""
        ).strip()

        value = " ".join(
            value.split()
        )

        return value.casefold()


    def is_fime_keyword(
        self,
        content: str,
        accept_fimi: bool = False
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
        message: discord.Message,
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
            )
            or ""
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


    # ========================================================
    # /فيم-رسالة
    # ========================================================

    @app_commands.command(
        name="فيم-رسالة",
        description="تغيير الرسالة التي يرسلها البوت عند كتابة فيم"
    )
    @app_commands.describe(
        message="الرسالة التي تريد أن يرسلها البوت"
    )
    async def fime_message(
        self,
        interaction: discord.Interaction,
        message: str
    ):

        if await self.silently_ignore_if_not_owner(
            interaction
        ):
            return

        if interaction.guild is None:
            return

        message = str(
            message or ""
        ).strip()

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

        save_config(
            self.config
        )

        await interaction.response.send_message(
            (
                "✅ **تم تغيير رسالة فيم.**\n\n"
                f"الرسالة الجديدة:\n{message}\n\n"
                "🟢 تم تشغيل النظام تلقائيًا."
            ),
            ephemeral=True
        )


    # ========================================================
    # /فيم-تشغيل
    # ========================================================

    @app_commands.command(
        name="فيم-تشغيل",
        description="تشغيل الرد التلقائي على كلمة فيم"
    )
    async def fime_enable(
        self,
        interaction: discord.Interaction
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

        cfg["fime_word_enabled"] = True

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🟢 تم تشغيل نظام كلمة فيم.",
            ephemeral=True
        )


    # ========================================================
    # /فيم-إيقاف
    # ========================================================

    @app_commands.command(
        name="فيم-إيقاف",
        description="إيقاف الرد التلقائي على كلمة فيم"
    )
    async def fime_disable(
        self,
        interaction: discord.Interaction
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

        cfg["fime_word_enabled"] = False

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🛑 تم إيقاف نظام كلمة فيم.",
            ephemeral=True
        )


    # ========================================================
    # /فيم-حالة
    # ========================================================

    @app_commands.command(
        name="فيم-حالة",
        description="عرض حالة نظام كلمة فيم"
    )
    async def fime_status(
        self,
        interaction: discord.Interaction
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

        enabled = cfg.get(
            "fime_word_enabled",
            True
        )

        response_text = str(
            cfg.get(
                "fime_word_response",
                ""
            )
            or ""
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

    def crop_to_fill(
        self,
        image,
        size
    ):

        target_width, target_height = size

        image = image.convert(
            "RGBA"
        )

        source_width, source_height = image.size

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


    def circle_avatar(
        self,
        image,
        size
    ):

        image = self.crop_to_fill(
            image,
            (
                size,
                size
            )
        )

        mask = Image.new(
            "L",
            (
                size,
                size
            ),
            0
        )

        draw = ImageDraw.Draw(
            mask
        )

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
            (
                size,
                size
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        result.paste(
            image,
            (
                0,
                0
            ),
            mask
        )

        return result


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

            # GIF/APNG → أول فريم فقط
            try:
                image.seek(0)
            except Exception:
                pass

            return image.convert(
                "RGBA"
            )

        except Exception as error:

            raise ValueError(
                "تعذر قراءة الصورة."
            ) from error


    async def create_say_image(
        self,
        avatar_attachment=None,
        banner_attachment=None,
        template_attachment=None
    ):

        # ====================================================
        # CANVAS
        # ====================================================

        if template_attachment:

            template_image = await self.read_image_attachment(
                template_attachment
            )

            canvas = self.crop_to_fill(
                template_image,
                (
                    1200,
                    675
                )
            )

        else:

            canvas = Image.new(
                "RGBA",
                (
                    1200,
                    675
                ),
                (
                    7,
                    8,
                    13,
                    255
                )
            )

            draw = ImageDraw.Draw(
                canvas
            )

            # خلفية ناعمة
            draw.rounded_rectangle(
                (
                    35,
                    35,
                    1165,
                    640
                ),
                radius=36,
                fill=(
                    16,
                    19,
                    28,
                    255
                )
            )

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
                    1130,
                    310
                )
            )

            # تعتيم بسيط أسفل البنر
            overlay = Image.new(
                "RGBA",
                banner.size,
                (
                    0,
                    0,
                    0,
                    35
                )
            )

            banner.alpha_composite(
                overlay
            )

            canvas.alpha_composite(
                banner,
                (
                    35,
                    35
                )
            )

        else:

            # لو ما فيه بنر، نخلي مساحة علوية احترافية
            draw = ImageDraw.Draw(
                canvas
            )

            draw.rounded_rectangle(
                (
                    35,
                    35,
                    1165,
                    345
                ),
                radius=30,
                fill=(
                    12,
                    15,
                    23,
                    255
                )
            )

        # ====================================================
        # DARK OVERLAY
        # ====================================================

        overlay = Image.new(
            "RGBA",
            (
                1200,
                675
            ),
            (
                0,
                0,
                0,
                0
            )
        )

        overlay_draw = ImageDraw.Draw(
            overlay
        )

        overlay_draw.rectangle(
            (
                35,
                280,
                1165,
                640
            ),
            fill=(
                7,
                8,
                13,
                145
            )
        )

        canvas.alpha_composite(
            overlay
        )

        # ====================================================
        # AVATAR
        # ====================================================

        if avatar_attachment:

            avatar = await self.read_image_attachment(
                avatar_attachment
            )

            avatar = self.circle_avatar(
                avatar,
                210
            )

            # ظل
            shadow = Image.new(
                "RGBA",
                (
                    230,
                    230
                ),
                (
                    0,
                    0,
                    0,
                    0
                )
            )

            shadow_draw = ImageDraw.Draw(
                shadow
            )

            shadow_draw.ellipse(
                (
                    5,
                    8,
                    225,
                    228
                ),
                fill=(
                    0,
                    0,
                    0,
                    170
                )
            )

            shadow = shadow.filter(
                ImageFilter.GaussianBlur(
                    10
                )
            )

            canvas.alpha_composite(
                shadow,
                (
                    55,
                    250
                )
            )

            canvas.alpha_composite(
                avatar,
                (
                    65,
                    260
                )
            )

        # ====================================================
        # PROFESSIONAL DETAILS
        # ====================================================

        draw = ImageDraw.Draw(
            canvas
        )

        # خط زخرفي
        draw.rounded_rectangle(
            (
                315,
                500,
                1120,
                504
            ),
            radius=2,
            fill=(
                124,
                92,
                255,
                220
            )
        )

        # شعار بسيط
        draw.text(
            (
                315,
                535
            ),
            "TEAM FIME",
            fill=(
                245,
                247,
                251,
                220
            )
        )

        draw.text(
            (
                315,
                575
            ),
            "Fime • Official Message",
            fill=(
                146,
                152,
                168,
                190
            )
        )

        # ====================================================
        # OUTPUT
        # ====================================================

        output = io.BytesIO()

        canvas.convert(
            "RGB"
        ).save(
            output,
            format="PNG",
            optimize=True
        )

        output.seek(0)

        return output


    # ========================================================
    # /say
    # ========================================================

    @app_commands.command(
        name="say",
        description="يجعل البوت يرسل رسالة في روم محدد مع قالب اختياري"
    )
    @app_commands.describe(
        message="الرسالة التي تريد أن يرسلها البوت",
        channel="الروم الذي تريد إرسال الرسالة فيه، اختياري",
        avatar="الصورة الشخصية التي تريد وضعها داخل القالب",
        banner="البنر الذي تريد وضعه داخل القالب",
        template="قالب مخصص اختياري بدل القالب الافتراضي"
    )
    async def say(
        self,
        interaction: discord.Interaction,
        message: str,
        channel: discord.TextChannel = None,
        avatar: discord.Attachment = None,
        banner: discord.Attachment = None,
        template: discord.Attachment = None
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

        permissions = target_channel.permissions_for(
            me
        )

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

        image_requested = any(
            (
                avatar,
                banner,
                template
            )
        )

        await interaction.response.defer(
            ephemeral=True
        )

        generated_file = None

        if image_requested:

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

                generated_file = (
                    await self.create_say_image(
                        avatar_attachment=avatar,
                        banner_attachment=banner,
                        template_attachment=template
                    )
                )

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
                        "❌ حصل خطأ أثناء تجهيز قالب الرسالة.\n"
                        f"الخطأ: `{type(error).__name__}`"
                    ),
                    ephemeral=True
                )

                return

        try:

            if generated_file:

                file = discord.File(
                    generated_file,
                    filename="fime-say.png"
                )

                await target_channel.send(
                    content=message,
                    file=file,
                    allowed_mentions=discord.AllowedMentions.none()
                )

            else:

                await target_channel.send(
                    message,
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

        await interaction.followup.send(
            (
                "✅ تم إرسال الرسالة بواسطة البوت.\n"
                f"📍 الروم: {target_channel.mention}"
            ),
            ephemeral=True
        )


    # ========================================================
    # LINE MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

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

        image_url = cfg.get(
            "image_url"
        )

        if not image_url:
            return

        configured_channel_id = (
            cfg.get("channel_id")
        )

        if configured_channel_id:

            if message.channel.id != int(
                configured_channel_id
            ):
                return

        me = message.guild.me

        if me is None:
            return

        permissions = (
            message.channel.permissions_for(me)
        )

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

    async def send_join_mention(
        self,
        member: discord.Member
    ):

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

        permissions = (
            channel.permissions_for(me)
        )

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

            await asyncio.sleep(
                duration
            )

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
    async def on_member_join(
        self,
        member: discord.Member
    ):

        if member.bot:
            return

        await asyncio.sleep(
            0.5
        )

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
        interaction: discord.Interaction,
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

        permissions = channel.permissions_for(
            me
        )

        if not permissions.view_channel:

            await interaction.response.send_message(
                (
                    f"❌ ما أقدر أشوف "
                    f"{channel.mention}."
                ),
                ephemeral=True
            )

            return

        if not permissions.send_messages:

            await interaction.response.send_message(
                (
                    f"❌ ما أقدر أرسل في "
                    f"{channel.mention}."
                ),
                ephemeral=True
            )

            return

        cfg = self.get_config(
            guild.id
        )

        cfg["join_mention_channel_id"] = (
            channel.id
        )

        cfg["join_mention_enabled"] = True
        cfg["join_mention_duration"] = 2

        save_config(
            self.config
        )

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


    # ========================================================
    # /منشن-إيقاف
    # ========================================================

    @app_commands.command(
        name="منشن-إيقاف",
        description="إيقاف منشن الأعضاء الجدد"
    )
    async def mention_off(
        self,
        interaction: discord.Interaction
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

        save_config(
            self.config
        )

        await interaction.response.send_message(
            "🛑 تم إيقاف منشن دخول الأعضاء.",
            ephemeral=True
        )


    # ========================================================
    # /منشن-حالة
    # ========================================================

    @app_commands.command(
        name="منشن-حالة",
        description="عرض حالة منشن الأعضاء الجدد"
    )
    async def mention_status(
        self,
        interaction: discord.Interaction
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

        enabled = cfg.get(
            "join_mention_enabled",
            False
        )

        channel_id = cfg.get(
            "join_mention_channel_id"
        )

        if channel_id:

            try:

                channel = (
                    interaction.guild.get_channel(
                        int(channel_id)
                    )
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


    # ========================================================
    # /منشن-روم-إلغاء
    # ========================================================

    @app_commands.command(
        name="منشن-روم-إلغاء",
        description="إلغاء روم منشن الأعضاء"
    )
    async def mention_channel_clear(
        self,
        interaction: discord.Interaction
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

        save_config(
            self.config
        )

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

async def setup(
    bot
):

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