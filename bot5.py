# ============================================================
# Team Fime
# bot5.py
# Automatic Divider / Line Image System
# +
# Temporary Join Mention System
# +
# Fime Keyword Response System
# ============================================================

from __future__ import annotations

import os
import io
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

    # هل نظام كلمة "فيم" مفعل؟
    "fime_word_enabled": True,

    # الرسالة التي يرسلها البوت عند كتابة "فيم"
    "fime_word_response": "هلا؟ وش تبي يا فايم؟",

    # هل نسمح بكلمة "فيمي" أيضًا؟
    # False = فقط "فيم"
    "fime_word_accept_fimi": False,
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
# COG
# ============================================================

class AutomaticLineSystem(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.config = load_config()

        print(
            "✅ bot5 — Automatic Line + Join Mention + Fime Keyword loaded."
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

        storage_channel = None

        # ----------------------------------------------------
        # Configured storage channel
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Fallback to line channel
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # System channel
        # ----------------------------------------------------

        if storage_channel is None:

            storage_channel = guild.system_channel

        # ----------------------------------------------------
        # Any usable text channel
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Download image
        # ----------------------------------------------------

        image_bytes = await image_attachment.read()

        if not image_bytes:

            raise RuntimeError(
                "الصورة المرفوعة فارغة."
            )

        # ----------------------------------------------------
        # Upload permanent storage copy
        # ----------------------------------------------------

        file = discord.File(
            fp=io.BytesIO(
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
                    "أو `WEBP` أو `GIF`."
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

            cfg["channel_id"] = (
                channel.id
            )

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

        value = str(content or "").strip()

        # إزالة المسافات الزائدة فقط
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

        except discord.Forbidden as error:

            print(
                "⚠️ bot5 Fime keyword permission error:",
                error
            )

        except discord.HTTPException as error:

            print(
                "⚠️ bot5 Fime keyword HTTP error:",
                error
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
    # LINE MESSAGE LISTENER
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

        # ----------------------------------------------------
        # Channel filter
        # ----------------------------------------------------

        configured_channel_id = (
            cfg.get("channel_id")
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
        # Send divider
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

        # ----------------------------------------------------
        # Bot permissions
        # ----------------------------------------------------

        me = guild.me

        if me is None:
            return

        permissions = (
            channel.permissions_for(me)
        )

        if not permissions.view_channel:

            print(
                f"⚠️ Join mention: "
                f"لا أستطيع رؤية {channel}."
            )

            return

        if not permissions.send_messages:

            print(
                f"⚠️ Join mention: "
                f"لا أستطيع الإرسال في {channel}."
            )

            return

        # ----------------------------------------------------
        # Duration
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Send actual mention
        # ----------------------------------------------------

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

        except discord.Forbidden as error:

            print(
                "⚠️ Join mention permission error:",
                error
            )

            return

        except discord.HTTPException as error:

            print(
                "⚠️ Join mention HTTP error:",
                error
            )

            return

        except Exception as error:

            print(
                "❌ Join mention error:",
                error
            )

            return

        # ----------------------------------------------------
        # Wait then delete
        # ----------------------------------------------------

        try:

            await asyncio.sleep(
                duration
            )

            await sent_message.delete()

        except discord.NotFound:

            pass

        except discord.Forbidden:

            print(
                "⚠️ Join mention: "
                "البوت لا يستطيع حذف رسالة المنشن."
            )

        except discord.HTTPException as error:

            print(
                "⚠️ Join mention delete error:",
                error
            )

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

        if enabled:

            status = "🟢 مفعل"

        else:

            status = "🔴 متوقف"

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
        "Automatic Line + Join Mention + Fime Keyword loaded."
    )