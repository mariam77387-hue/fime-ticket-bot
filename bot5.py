# ============================================================
# Team Fime
# bot5.py
# Automatic Divider / Line Image System
# ============================================================

from __future__ import annotations

import os
import json
import asyncio
from copy import deepcopy
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

OWNER_ID = 1388514481444880549

CONFIG_FILE = Path("bot5_config.json")

DEFAULT_GUILD_CONFIG = {
    "enabled": False,
    "channel_id": None,
    "image_url": None,
    "storage_channel_id": None,
    "storage_message_id": None,
    "delete_after": 0
}


# ============================================================
# JSON
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

    temp_file = CONFIG_FILE.with_suffix(
        ".tmp"
    )

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
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.config = load_config()

        print(
            "✅ bot5 — Automatic Line System loaded."
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

        if changed:
            save_config(
                self.config
            )

        return current


    def is_owner(
        self,
        interaction: discord.Interaction
    ):

        if interaction.user.id == OWNER_ID:
            return True

        return False


    # ========================================================
    # PERMISSION
    # ========================================================

    async def silently_ignore_if_not_owner(
        self,
        interaction
    ):

        if self.is_owner(interaction):
            return False

        # مهم جدًا:
        # لا رسالة خطأ.
        # لا رد.
        # فقط تجاهل.
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
        ).lower()

        filename = (
            attachment.filename
            or ""
        ).lower()

        supported_types = {
            "image/png",
            "image/jpeg",
            "image/jpg",
            "image/webp",
            "image/gif"
        }

        supported_extensions = (
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif"
        )

        return (
            content_type in supported_types
            or filename.endswith(
                supported_extensions
            )
        )


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

        # ----------------------------------------------------
        # Pick storage channel
        # ----------------------------------------------------

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
                f"البوت لا يستطيع رؤية {storage_channel.mention}."
            )

        if not permissions.send_messages:

            raise RuntimeError(
                f"البوت لا يستطيع الإرسال في {storage_channel.mention}."
            )

        if not permissions.attach_files:

            raise RuntimeError(
                f"البوت يحتاج صلاحية Attach Files في {storage_channel.mention}."
            )

        # ----------------------------------------------------
        # Download image
        # ----------------------------------------------------

        image_bytes = await image_attachment.read()

        if not image_bytes:

            raise RuntimeError(
                "الصورة المرفوعة فارغة."
            )

        # ----------------------------------------------------
        # Send permanent storage copy
        # ----------------------------------------------------

        file = discord.File(
            fp=__import__("io").BytesIO(
                image_bytes
            ),
            filename=(
                image_attachment.filename
                or "fime-line.png"
            )
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

        # ----------------------------------------------------
        # OWNER ONLY — SILENT
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Image check
        # ----------------------------------------------------

        if not self.is_supported_image(
            image
        ):

            await interaction.response.send_message(
                (
                    "❌ أرسل صورة بصيغة "
                    "`PNG` أو `JPG` أو `JPEG` أو `WEBP` أو `GIF`."
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

        # ----------------------------------------------------
        # Target channel
        # ----------------------------------------------------

        if channel is None:

            # إذا ما حدد روم:
            # نستخدم كل الرومات النصية التي يستطيع
            # البوت الكتابة فيها.
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

            cfg["channel_id"] = (
                channel.id
            )

        # ----------------------------------------------------
        # Delete previous storage
        # ----------------------------------------------------

        await self.delete_old_storage(
            guild
        )

        # ----------------------------------------------------
        # Create new storage
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Result
        # ----------------------------------------------------

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
                f"🗄️ التخزين: {storage_channel.mention}\n\n"
                "العضو العادي إذا كتب `/خط` "
                "لن يحصل على أي رد أو تنفيذ."
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
                f"الحالة: **مفعل**\n"
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

        save_config(
            self.config
        )

        await interaction.response.send_message(
            f"✅ صار الخط يعمل فقط في {channel.mention}.",
            ephemeral=True
        )


    # ========================================================
    # MESSAGE LISTENER
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        # ----------------------------------------------------
        # Ignore bots
        # ----------------------------------------------------

        if message.author.bot:
            return

        if message.guild is None:
            return

        cfg = self.get_config(
            message.guild.id
        )

        if not cfg.get("enabled"):
            return

        image_url = cfg.get(
            "image_url"
        )

        if not image_url:
            return

        # ----------------------------------------------------
        # Channel filter
        # ----------------------------------------------------

        configured_channel_id = (
            cfg.get(
                "channel_id"
            )
        )

        if configured_channel_id:

            if message.channel.id != int(
                configured_channel_id
            ):
                return

        # ----------------------------------------------------
        # Bot permissions
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Send divider image
        # ----------------------------------------------------

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
        "✅ Team Fime bot5 — Automatic Line System loaded."
    )