# -*- coding: utf-8 -*-
"""
bot7.py - نظام الأفتارات (discord.py 2.x)

التحميل من bot.py:
    await bot.load_extension("bot7")

الأمر الوحيد (للمالك فقط):
    !avatars  + مرفق الصور

- صورة اسمها يبدأ بـ banner = البنر (اختياري)
- باقي الصور = الأفتارات (كل أفتار = بروفايل)
- مع البنر: القوالب تنرسل كبروفايلات، الحد 7 أفتارات
- بدون البنر: الأفتارات تنرسل مباشرة بدون قالب، بدون حد للعدد
  (حد ديسكورد 10 مرفقات بالرسالة الواحدة، والأكثر يرسل بأمر ثاني)
- الرسالة عامة ودائمة، وزر "تحميل" يرسل الصور الأصلية في الخاص
- الزر يعمل بعد إعادة تشغيل البوت بدون إعادة رفع الصور

المكتبات المطلوبة:
    pip install -U discord.py pillow
"""

from __future__ import annotations

import asyncio
import io
import json
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps


# ============================================================
# الإعدادات
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "bot7_avatars.json"
ASSETS_DIR = BASE_DIR / "bot7_avatar_assets"

PROFILE_DISPLAY_NAME = "1zja"
PROFILE_USERNAME = "1zja"
PROFILE_BIO = "MCCl SERVER"

MAX_WITH_BANNER = 7
DISCORD_FILES_PER_MESSAGE = 10
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
NO_MENTIONS = discord.AllowedMentions.none()

# ألوان وأبعاد القالب (شكل بروفايل ديسكورد)
CARD_W = 735
CARD_H = 660
BANNER_H = 260
AVATAR_D = 150
RING = 6
AV_X = 28
PAD = 28
CARD_BG = (232, 238, 245)
TEXT_MAIN = (20, 22, 26)
TEXT_SUB = (92, 98, 108)
DIVIDER = (200, 206, 214)
STATUS_GREY = (116, 122, 130)


# ============================================================
# أدوات مساعدة
# ============================================================

def owner_only():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is not None and ctx.guild.owner_id == ctx.author.id:
            return True
        raise commands.CheckFailure("owner only")

    return commands.check(predicate)


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: Path, payload: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)


@lru_cache(maxsize=32)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica-Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttf"]
    )
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def load_image(data: bytes, mode: str) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.seek(0)
    return img.convert(mode)


def circle_mask(diameter: int) -> Image.Image:
    big = Image.new("L", (diameter * 4, diameter * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, diameter * 4 - 1, diameter * 4 - 1), fill=255)
    return big.resize((diameter, diameter), Image.LANCZOS)


def draw_badges(draw: ImageDraw.ImageDraw, x: int, cy: int) -> None:
    width = 3 * 36 + 20
    draw.rounded_rectangle(
        (x, cy - 20, x + width, cy + 20),
        radius=20,
        fill=(255, 255, 255),
        outline=(210, 214, 222),
        width=1,
    )
    colors = [(115, 82, 230), (170, 190, 255), (71, 139, 255)]
    for i, color in enumerate(colors):
        cx = x + 22 + i * 36
        draw.ellipse((cx - 13, cy - 13, cx + 13, cy + 13), fill=color)
        draw.ellipse((cx - 5, cy - 5, cx + 5, cy + 5), fill=(255, 255, 255))


def render_card(banner_bytes: bytes, avatar_bytes: bytes) -> bytes:
    """يرسم قالب البروفايل بالبنر والأفتار المعطى، ويرجع PNG كبايتات."""
    banner = ImageOps.fit(load_image(banner_bytes, "RGB"), (CARD_W, BANNER_H), Image.LANCZOS)
    card = Image.new("RGB", (CARD_W, CARD_H), CARD_BG)
    card.paste(banner, (0, 0))
    draw = ImageDraw.Draw(card)

    # الأفتار مع الحلقة البيضاء فوق البنر
    av_x = AV_X
    av_y = BANNER_H - AVATAR_D // 2
    cx, cy = av_x + AVATAR_D // 2, av_y + AVATAR_D // 2
    ring_r = AVATAR_D // 2 + RING
    draw.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r), fill=CARD_BG)
    avatar = ImageOps.fit(load_image(avatar_bytes, "RGBA"), (AVATAR_D, AVATAR_D), Image.LANCZOS)
    card.paste(avatar, (av_x, av_y), circle_mask(AVATAR_D))

    # نقطة الحالة أسفل الأفتار
    sx, sy = av_x + AVATAR_D - 22, av_y + AVATAR_D - 22
    draw.ellipse((sx - 20, sy - 20, sx + 20, sy + 20), fill=CARD_BG)
    draw.ellipse((sx - 14, sy - 14, sx + 14, sy + 14), fill=STATUS_GREY)
    draw.ellipse((sx - 8, sy - 8, sx + 8, sy + 8), fill=CARD_BG)

    # الاسم واسم المستخدم والشارات
    y0 = BANNER_H + AVATAR_D // 2 + 18
    draw.text((PAD, y0), PROFILE_DISPLAY_NAME, font=load_font(40, True), fill=TEXT_MAIN)

    y1 = y0 + 56
    user_font = load_font(24)
    draw.text((PAD, y1), PROFILE_USERNAME, font=user_font, fill=TEXT_SUB)
    ux = PAD + draw.textlength(PROFILE_USERNAME, font=user_font) + 14
    draw_badges(draw, int(ux), y1 + 14)

    # التبويبات
    y2 = y1 + 62
    tab_font = load_font(24, True)
    draw.text((PAD, y2), "Principal", font=tab_font, fill=TEXT_MAIN)
    tab_w = draw.textlength("Principal", font=tab_font)
    draw.rounded_rectangle((PAD, y2 + 42, PAD + tab_w, y2 + 46), radius=2, fill=TEXT_MAIN)
    draw.line((PAD, y2 + 52, CARD_W - PAD, y2 + 52), fill=DIVIDER, width=2)

    # البايو
    y3 = y2 + 80
    draw.text((PAD, y3), "Bio", font=load_font(22), fill=TEXT_SUB)
    draw.text((PAD, y3 + 34), PROFILE_BIO, font=load_font(28, True), fill=TEXT_MAIN)

    # زوايا مدورة للقالب كاملاً
    mask = Image.new("L", (CARD_W * 2, CARD_H * 2), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, CARD_W * 2 - 1, CARD_H * 2 - 1), radius=56, fill=255
    )
    mask = mask.resize((CARD_W, CARD_H), Image.LANCZOS)
    out = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    out.paste(card, (0, 0), mask)

    buffer = io.BytesIO()
    out.save(buffer, format="PNG")
    return buffer.getvalue()


def chunked(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


# ============================================================
# زر التحميل (دائم، يعمل بعد إعادة التشغيل)
# ============================================================

class AvatarDownloadView(discord.ui.View):
    def __init__(self, cog: "AvatarCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="تحميل",
        style=discord.ButtonStyle.success,
        emoji="⬇️",
        custom_id="avatars:download",
    )
    async def download(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.send_raw_files(interaction)


# ============================================================
# الكوج
# ============================================================

class AvatarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Dict[str, dict] = read_json(DATA_FILE)
        self.lock = asyncio.Lock()

    async def cog_load(self) -> None:
        self.bot.add_view(AvatarDownloadView(self))

    async def save_db(self) -> None:
        payload = json.dumps(self.db, ensure_ascii=False, indent=2)
        async with self.lock:
            await asyncio.to_thread(write_json_atomic, DATA_FILE, payload)

    # ---------------- الأمر الوحيد ----------------

    @commands.command(name="avatars")
    @owner_only()
    async def avatars(self, ctx: commands.Context):
        images = [a for a in ctx.message.attachments if a.filename.lower().endswith(IMAGE_EXTS)]
        if not images:
            await ctx.send(
                "أرفق الصور مع الأمر. صورة اسمها `banner` للبنر (اختياري)، والباقي أفتارات.",
                delete_after=12,
            )
            return

        banner_att = next(
            (a for a in images if Path(a.filename).stem.lower().startswith("banner")), None
        )
        avatar_atts = [a for a in images if a is not banner_att]

        if not avatar_atts:
            await ctx.send("لازم ترفق أفتار واحد على الأقل.", delete_after=12)
            return
        if banner_att is not None and len(avatar_atts) > MAX_WITH_BANNER:
            await ctx.send(
                f"مع البنر الحد {MAX_WITH_BANNER} أفتارات. احذف البنر أو قلل الأفتارات.",
                delete_after=12,
            )
            return

        batch_dir = ASSETS_DIR / uuid.uuid4().hex[:12]
        batch_dir.mkdir(parents=True, exist_ok=True)

        try:
            raw_paths: List[str] = []
            avatar_blobs: List[tuple] = []

            banner_bytes = None
            if banner_att is not None:
                banner_bytes = await banner_att.read()
                path = batch_dir / f"banner{Path(banner_att.filename).suffix.lower()}"
                await asyncio.to_thread(path.write_bytes, banner_bytes)
                raw_paths.append(str(path))

            for index, att in enumerate(avatar_atts, start=1):
                data = await att.read()
                path = batch_dir / f"avatar_{index:02d}{Path(att.filename).suffix.lower()}"
                await asyncio.to_thread(path.write_bytes, data)
                raw_paths.append(str(path))
                avatar_blobs.append((index, data))

            # القوالب أو الأفتارات الخام للنشر العام
            public_files: List[discord.File] = []
            if banner_bytes is not None:
                for index, data in avatar_blobs:
                    card = await asyncio.to_thread(render_card, banner_bytes, data)
                    public_files.append(
                        discord.File(io.BytesIO(card), filename=f"profile_{index:02d}.png")
                    )
            else:
                for index, data in avatar_blobs:
                    suffix = Path(avatar_atts[index - 1].filename).suffix.lower()
                    public_files.append(
                        discord.File(io.BytesIO(data), filename=f"avatar_{index:02d}{suffix}")
                    )

            groups = list(chunked(public_files, DISCORD_FILES_PER_MESSAGE))
            last_message: Optional[discord.Message] = None
            for position, group in enumerate(groups):
                kwargs = {"files": group, "allowed_mentions": NO_MENTIONS}
                is_last = position == len(groups) - 1
                if is_last:
                    kwargs["view"] = AvatarDownloadView(self)
                last_message = await ctx.channel.send(**kwargs)

            self.db[str(last_message.id)] = {
                "guild_id": ctx.guild.id if ctx.guild else None,
                "channel_id": ctx.channel.id,
                "raw": raw_paths,
            }
            await self.save_db()

        except discord.Forbidden:
            await ctx.send("ما عندي صلاحية أرسل الصور في هذا الروم.", delete_after=12)
            await asyncio.to_thread(self._cleanup, batch_dir)
        except discord.HTTPException as error:
            print(f"[AVATARS] Discord error: {error}")
            await ctx.send("صار خطأ من ديسكورد وما انرسلت الصور. جرب مرة ثانية.", delete_after=12)
            await asyncio.to_thread(self._cleanup, batch_dir)
        except Exception as error:
            print(f"[AVATARS] Processing error: {type(error).__name__}: {error}")
            await ctx.send("صار خطأ أثناء معالجة الصور. تأكد أن الملفات صور صالحة.", delete_after=12)
            await asyncio.to_thread(self._cleanup, batch_dir)

    @staticmethod
    def _cleanup(folder: Path) -> None:
        for item in folder.glob("*"):
            try:
                item.unlink()
            except OSError:
                pass
        try:
            folder.rmdir()
        except OSError:
            pass

    # ---------------- إرسال الملفات الخام في الخاص ----------------

    async def send_raw_files(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=False)

        message_id = interaction.message.id if interaction.message else None
        record = self.db.get(str(message_id)) if message_id else None
        paths = [Path(p) for p in (record or {}).get("raw", []) if Path(p).exists()]

        if not paths:
            await interaction.followup.send(
                "الملفات مو موجودة. اطلب من المالك ينزل الأفتارات من جديد.", ephemeral=True
            )
            return

        try:
            for group in chunked(paths, DISCORD_FILES_PER_MESSAGE):
                files = [
                    discord.File(io.BytesIO(p.read_bytes()), filename=p.name) for p in group
                ]
                await interaction.user.send(files=files)
        except discord.Forbidden:
            await interaction.followup.send(
                "ما قدرت أرسل لك في الخاص. افتح الرسائل الخاصة من أعضاء السيرفر وجرب مرة ثانية.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            print(f"[AVATARS] Could not DM files: {error}")
            await interaction.followup.send(
                "صار خطأ من ديسكورد أثناء الإرسال. جرب مرة ثانية.", ephemeral=True
            )
            return

        await interaction.followup.send("تم ارسال الصور في الخاص ✅", ephemeral=True)

    # ---------------- الأخطاء ----------------

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            return  # غير المالك ما يحصل رد
        original = getattr(error, "original", error)
        print(f"[AVATARS COMMAND] {type(original).__name__}: {original}")
        try:
            await ctx.send("صار خطأ غير متوقع.", delete_after=8)
        except discord.HTTPException:
            pass


# ============================================================
# نقطة التحميل
# ============================================================

async def setup(bot: commands.Bot) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    await bot.add_cog(AvatarCog(bot))
    print("[BOT7] Avatar system loaded.")