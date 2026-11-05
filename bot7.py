# -*- coding: utf-8 -*-
"""Team Fime bot7 - Avatar card publisher (discord.py 2.x).

Load from bot.py with: await bot.load_extension('bot7')
Slash command: /avatars
IMPORTANT: This extension deliberately does NOT sync the command tree.
The main bot should sync once after login / in setup_hook with an application_id.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

log = logging.getLogger("team_fime.bot7")
BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "bot7_avatars.json"
ASSETS_DIR = BASE_DIR / "bot7_avatar_assets"

PROFILE_DISPLAY_NAME = "1zja"
PROFILE_USERNAME = "1zja"
PROFILE_BIO = "MCCl SERVER"
MAX_WITH_BANNER = 7
MAX_AVATARS = 10
MAX_IMAGE_BYTES = 8 * 1024 * 1024
FILES_PER_MESSAGE = 10
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
NO_MENTIONS = discord.AllowedMentions.none()

CARD_W, CARD_H, BANNER_H = 735, 660, 260
AVATAR_D, RING, AV_X, PAD = 150, 6, 28, 28
CARD_BG = (232, 238, 245)
TEXT_MAIN = (20, 22, 26)
TEXT_SUB = (92, 98, 108)
DIVIDER = (200, 206, 214)
STATUS_GREY = (116, 122, 130)


def read_db() -> Dict[str, dict]:
    try:
        value = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_db(payload: Dict[str, dict]) -> None:
    temp = DATA_FILE.with_suffix(DATA_FILE.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_FILE)


def load_font(size: int, bold: bool = False):
    choices = (["DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold
               else ["DejaVuSans.ttf", "arial.ttf"])
    for name in choices:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def read_valid_image(data: bytes, *, mode: str) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image is empty or larger than 8 MB")
    with Image.open(io.BytesIO(data)) as source:
        source.seek(0)
        if source.width < 16 or source.height < 16 or source.width > 12000 or source.height > 12000:
            raise ValueError("Unsupported image dimensions")
        source.load()
        return source.convert(mode)


def circle_mask(diameter: int) -> Image.Image:
    scale = 4
    mask = Image.new("L", (diameter * scale, diameter * scale), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter * scale - 1, diameter * scale - 1), fill=255)
    return mask.resize((diameter, diameter), Image.Resampling.LANCZOS)


def render_card(banner_bytes: bytes, avatar_bytes: bytes) -> bytes:
    banner = ImageOps.fit(read_valid_image(banner_bytes, mode="RGB"),
                          (CARD_W, BANNER_H), Image.Resampling.LANCZOS)
    avatar = ImageOps.fit(read_valid_image(avatar_bytes, mode="RGBA"),
                          (AVATAR_D, AVATAR_D), Image.Resampling.LANCZOS)
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    card.paste(banner, (0, 0))
    draw = ImageDraw.Draw(card)

    ax, ay = AV_X, BANNER_H - AVATAR_D // 2
    cx, cy = ax + AVATAR_D // 2, ay + AVATAR_D // 2
    rr = AVATAR_D // 2 + RING
    draw.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=CARD_BG)
    card.paste(avatar, (ax, ay), circle_mask(AVATAR_D))

    sx, sy = ax + AVATAR_D - 22, ay + AVATAR_D - 22
    draw.ellipse((sx - 20, sy - 20, sx + 20, sy + 20), fill=CARD_BG)
    draw.ellipse((sx - 14, sy - 14, sx + 14, sy + 14), fill=STATUS_GREY)
    draw.ellipse((sx - 8, sy - 8, sx + 8, sy + 8), fill=CARD_BG)

    y0 = BANNER_H + AVATAR_D // 2 + 18
    draw.text((PAD, y0), PROFILE_DISPLAY_NAME, font=load_font(40, True), fill=TEXT_MAIN)
    y1 = y0 + 56
    user_font = load_font(24)
    draw.text((PAD, y1), PROFILE_USERNAME, font=user_font, fill=TEXT_SUB)
    badge_x = int(PAD + draw.textlength(PROFILE_USERNAME, font=user_font) + 14)
    draw.rounded_rectangle((badge_x, y1 - 5, badge_x + 128, y1 + 35), radius=20,
                           fill=(255, 255, 255), outline=(210, 214, 222), width=1)
    for index, color in enumerate(((115, 82, 230), (170, 190, 255), (71, 139, 255))):
        bx = badge_x + 22 + index * 36
        draw.ellipse((bx - 13, y1 + 1, bx + 13, y1 + 27), fill=color)
        draw.ellipse((bx - 5, y1 + 9, bx + 5, y1 + 19), fill=(255, 255, 255))

    y2 = y1 + 62
    tab_font = load_font(24, True)
    draw.text((PAD, y2), "Principal", font=tab_font, fill=TEXT_MAIN)
    tab_w = draw.textlength("Principal", font=tab_font)
    draw.rounded_rectangle((PAD, y2 + 42, PAD + tab_w, y2 + 46), radius=2, fill=TEXT_MAIN)
    draw.line((PAD, y2 + 52, CARD_W - PAD, y2 + 52), fill=DIVIDER, width=2)
    y3 = y2 + 80
    draw.text((PAD, y3), "Bio", font=load_font(22), fill=TEXT_SUB)
    draw.text((PAD, y3 + 34), PROFILE_BIO, font=load_font(28, True), fill=TEXT_MAIN)

    mask = Image.new("L", (CARD_W * 2, CARD_H * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, CARD_W * 2 - 1, CARD_H * 2 - 1),
                                           radius=56, fill=255)
    mask = mask.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)
    buffer = io.BytesIO()
    out.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def is_image(attachment: discord.Attachment) -> bool:
    suffix = Path(attachment.filename).suffix.lower()
    return suffix in IMAGE_EXTS or (attachment.content_type or "").startswith("image/")


def chunks(items: List, size: int):
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


class AvatarDownloadView(discord.ui.View):
    def __init__(self, cog: "AvatarCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="تحميل", style=discord.ButtonStyle.success,
                       emoji="⬇️", custom_id="avatars:download")
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.send_raw_files(interaction)


class AvatarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = read_db()
        self.db_lock = asyncio.Lock()

    async def cog_load(self) -> None:
        # Persistent view registration is safe before on_ready; it does not sync commands.
        self.bot.add_view(AvatarDownloadView(self))
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    async def save_record(self, message_id: int, record: dict) -> None:
        async with self.db_lock:
            self.db[str(message_id)] = record
            payload = json.loads(json.dumps(self.db, ensure_ascii=False))
            await asyncio.to_thread(write_db, payload)

    @app_commands.command(name="avatars", description="ينشئ قوالب بروفايل من الصور")
    @app_commands.guild_only()
    @app_commands.describe(
        banner="بنر اختياري. عند إرفاقه تُنشأ قوالب بروفايل",
        avatar1="الأفتار الأول", avatar2="الأفتار الثاني", avatar3="الأفتار الثالث",
        avatar4="الأفتار الرابع", avatar5="الأفتار الخامس", avatar6="الأفتار السادس",
        avatar7="الأفتار السابع", avatar8="الأفتار الثامن", avatar9="الأفتار التاسع",
        avatar10="الأفتار العاشر",
    )
    async def avatars(
        self, interaction: discord.Interaction,
        banner: Optional[discord.Attachment] = None,
        avatar1: Optional[discord.Attachment] = None,
        avatar2: Optional[discord.Attachment] = None,
        avatar3: Optional[discord.Attachment] = None,
        avatar4: Optional[discord.Attachment] = None,
        avatar5: Optional[discord.Attachment] = None,
        avatar6: Optional[discord.Attachment] = None,
        avatar7: Optional[discord.Attachment] = None,
        avatar8: Optional[discord.Attachment] = None,
        avatar9: Optional[discord.Attachment] = None,
        avatar10: Optional[discord.Attachment] = None,
    ) -> None:
        guild = interaction.guild
        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message("هذا الأمر لمالك السيرفر فقط.", ephemeral=True)
            return

        avatars = [item for item in (avatar1, avatar2, avatar3, avatar4, avatar5,
                                     avatar6, avatar7, avatar8, avatar9, avatar10) if item]
        if not avatars:
            await interaction.response.send_message("أرفق أفتاراً واحداً على الأقل.", ephemeral=True)
            return
        if banner and not is_image(banner):
            await interaction.response.send_message("ملف البنر لازم يكون صورة.", ephemeral=True)
            return
        if any(not is_image(item) for item in avatars):
            await interaction.response.send_message("كل المرفقات لازم تكون صوراً.", ephemeral=True)
            return
        if banner and len(avatars) > MAX_WITH_BANNER:
            await interaction.response.send_message(
                f"مع البنر الحد الأقصى {MAX_WITH_BANNER} أفتارات.", ephemeral=True)
            return
        if len(avatars) > MAX_AVATARS:
            await interaction.response.send_message("الحد الأقصى 10 أفتارات.", ephemeral=True)
            return
        if any(item.size > MAX_IMAGE_BYTES for item in avatars) or (banner and banner.size > MAX_IMAGE_BYTES):
            await interaction.response.send_message("حجم الصورة الواحدة لازم يكون 8MB أو أقل.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        batch_dir = ASSETS_DIR / uuid.uuid4().hex[:16]
        batch_dir.mkdir(parents=True, exist_ok=True)
        raw_paths: List[str] = []
        public_files: List[discord.File] = []
        channel = interaction.channel

        try:
            banner_bytes = await banner.read() if banner else None
            if banner_bytes is not None:
                read_valid_image(banner_bytes, mode="RGB")
                banner_path = batch_dir / ("banner" + (Path(banner.filename).suffix.lower() or ".png"))
                await asyncio.to_thread(banner_path.write_bytes, banner_bytes)
                raw_paths.append(str(banner_path))

            for index, attachment in enumerate(avatars, start=1):
                data = await attachment.read()
                # Decode now so broken images fail before anything is published.
                read_valid_image(data, mode="RGBA")
                suffix = Path(attachment.filename).suffix.lower() or ".png"
                path = batch_dir / f"avatar_{index:02d}{suffix}"
                await asyncio.to_thread(path.write_bytes, data)
                raw_paths.append(str(path))
                if banner_bytes is not None:
                    rendered = await asyncio.to_thread(render_card, banner_bytes, data)
                    public_files.append(discord.File(io.BytesIO(rendered), filename=f"profile_{index:02d}.png"))
                else:
                    public_files.append(discord.File(io.BytesIO(data), filename=f"avatar_{index:02d}{suffix}"))

            if channel is None:
                raise RuntimeError("Interaction channel is unavailable")
            last_message = None
            batches = list(chunks(public_files, FILES_PER_MESSAGE))
            for position, batch in enumerate(batches):
                kwargs = {"files": batch, "allowed_mentions": NO_MENTIONS}
                if position == len(batches) - 1:
                    kwargs["view"] = AvatarDownloadView(self)
                last_message = await channel.send(**kwargs)
            if last_message is None:
                raise RuntimeError("No output message was created")

            await self.save_record(last_message.id, {
                "guild_id": guild.id,
                "channel_id": channel.id,
                "raw": raw_paths,
                "owner_id": guild.owner_id,
            })
            await interaction.followup.send(
                f"تم نشر {len(public_files)} صورة بنجاح في {channel.mention} ✅",
                ephemeral=True,
            )
        except discord.Forbidden:
            await self.cleanup(batch_dir)
            await interaction.followup.send("ما عندي صلاحية إرسال الصور في هذا الروم.", ephemeral=True)
        except (ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            await self.cleanup(batch_dir)
            log.warning("Avatar image rejected: %s", exc)
            await interaction.followup.send("إحدى الصور تالفة أو غير مدعومة أو حجمها/أبعادها غير مناسبة.", ephemeral=True)
        except discord.HTTPException as exc:
            await self.cleanup(batch_dir)
            log.exception("Discord error while publishing avatars")
            await interaction.followup.send("ديسكورد رفض إرسال الملفات. تحقق من حجمها وصلاحيات البوت.", ephemeral=True)
        except Exception:
            await self.cleanup(batch_dir)
            log.exception("Unexpected avatar processing error")
            await interaction.followup.send("حدث خطأ أثناء تجهيز الصور. راجع سجل الاستضافة للتفاصيل.", ephemeral=True)

    @staticmethod
    async def cleanup(folder: Path) -> None:
        def remove():
            for item in folder.glob("*"):
                try:
                    item.unlink()
                except OSError:
                    pass
            try:
                folder.rmdir()
            except OSError:
                pass
        await asyncio.to_thread(remove)

    async def send_raw_files(self, interaction: discord.Interaction) -> None:
        message = interaction.message
        record = self.db.get(str(message.id)) if message else None
        if not record:
            await interaction.response.send_message("ما لقيت ملفات هذه الرسالة. اطلب من المالك إعادة نشرها.", ephemeral=True)
            return
        paths = [Path(value) for value in record.get("raw", [])]
        existing = [path for path in paths if path.is_file()]
        if not existing:
            await interaction.response.send_message("الصور الأصلية غير موجودة على الاستضافة حالياً.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            for group in chunks(existing, FILES_PER_MESSAGE):
                files = [discord.File(io.BytesIO(await asyncio.to_thread(path.read_bytes)), filename=path.name)
                         for path in group]
                await interaction.user.send(files=files, allowed_mentions=NO_MENTIONS)
            await interaction.followup.send("تم إرسال الصور الأصلية في الخاص ✅", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("افتح استقبال الرسائل الخاصة من أعضاء السيرفر ثم أعد المحاولة.", ephemeral=True)
        except discord.HTTPException:
            log.exception("Could not DM avatar files")
            await interaction.followup.send("حدث خطأ من ديسكورد أثناء إرسال الصور.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AvatarCog(bot))
    log.info("[BOT7] Avatar system loaded. Slash sync is managed by the main bot.")
