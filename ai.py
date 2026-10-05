# -*- coding: utf-8 -*-

import os
import re
import json
import time
import asyncio
from pathlib import Path
from collections import defaultdict, deque
from typing import Optional, Dict, Any, List

import discord
from discord import app_commands
from discord.ext import commands
from openai import AsyncOpenAI


# =========================================================
# FIME AI v4
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.getenv(
    "GROQ_BASE_URL",
    "https://api.groq.com/openai/v1"
).strip()

AI_MODEL = os.getenv(
    "AI_MODEL",
    "openai/gpt-oss-120b"
).strip()

AI_REASONING_EFFORT = os.getenv(
    "AI_REASONING_EFFORT",
    "low"
).strip().lower()

AI_CHANNEL_ID = int(
    os.getenv("AI_CHANNEL_ID", "1547903949967720498")
)

FIME_OWNER_ID = int(
    os.getenv("FIME_OWNER_ID", "1388514481444880549")
)

MEMORY_LIMIT     = 20       # نبقي تاريخ كافي عشان ما يكرر
MEMORY_TTL       = 4.5 * 60 * 60

MAX_MESSAGE_LENGTH = 2500
MAX_OUTPUT_TOKENS  = 120    # سطرين بالكثير، مو رواية
REQUEST_TIMEOUT    = 12     # ← السرعة: كان 35
MAX_RETRIES        = 1      # ← السرعة: كان 2

KNOWLEDGE_FILE = Path("ai_server_knowledge.json")
EMOJI_FILE     = Path("ai_emoji_settings.json")


# =========================================================
# HELPERS
# =========================================================

def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def truncate_text(text: str, limit: int) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clean_error(error: Exception) -> str:
    text = str(error)
    if GROQ_API_KEY:
        text = text.replace(GROQ_API_KEY, "[REDACTED]")
    return truncate_text(text, 700)


# =========================================================
# JSON STORAGE
# =========================================================

def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ تعذر قراءة {path.name}: {clean_error(e)}")
        return default


def save_json(path: Path, data: Any) -> bool:
    tmp = path.with_suffix(".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)
        return True
    except Exception as e:
        print(f"⚠️ تعذر حفظ {path.name}: {clean_error(e)}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


# =========================================================
# DEFAULT KNOWLEDGE
# =========================================================

DEFAULT_SERVER_KNOWLEDGE = {
    "personality": {
        "enabled": False,
        "name": "",
        "description": "",
        "style": "",
        "generated": ""
    },
    "servers": {}
}


# =========================================================
# SERVER KNOWLEDGE
# =========================================================

class ServerKnowledgeManager:

    def __init__(self):
        self.data = load_json(KNOWLEDGE_FILE, DEFAULT_SERVER_KNOWLEDGE.copy())
        self._normalize()

    def _normalize(self):
        if not isinstance(self.data, dict):
            self.data = {}
        if not isinstance(self.data.get("servers"), dict):
            self.data["servers"] = {}
        if not isinstance(self.data.get("personality"), dict):
            self.data["personality"] = {}
        p = self.data["personality"]
        for k, v in [("enabled", False), ("name", ""), ("description", ""),
                     ("style", ""), ("generated", "")]:
            p.setdefault(k, v)

    def save(self):
        save_json(KNOWLEDGE_FILE, self.data)

    def get_server(self, guild_id: int) -> Dict[str, Any]:
        key = str(guild_id)
        if key not in self.data["servers"]:
            self.data["servers"][key] = {"rooms": {}, "last_scan": 0}
        s = self.data["servers"][key]
        s.setdefault("rooms", {})
        s.setdefault("last_scan", 0)
        return s

    async def scan_guild(self, guild: discord.Guild) -> Dict[str, Any]:
        server = self.get_server(guild.id)
        rooms = {}
        for ch in guild.channels:
            if not isinstance(
                ch,
                (discord.TextChannel, discord.VoiceChannel,
                 discord.StageChannel, discord.ForumChannel,
                 discord.CategoryChannel)
            ):
                continue
            cat = ch.category.name if getattr(ch, "category", None) else ""
            topic = ""
            if isinstance(ch, (discord.TextChannel, discord.ForumChannel)):
                topic = clean_text(getattr(ch, "topic", ""))
            t = ("Forum" if isinstance(ch, discord.ForumChannel) else
                 "Voice" if isinstance(ch, discord.VoiceChannel) else
                 "Stage" if isinstance(ch, discord.StageChannel) else
                 "Category" if isinstance(ch, discord.CategoryChannel) else "Text")
            rooms[str(ch.id)] = {
                "id": ch.id, "name": ch.name, "mention": ch.mention,
                "category": cat, "topic": truncate_text(topic, 180), "type": t
            }
        server["rooms"] = rooms
        server["last_scan"] = int(time.time())
        self.save()
        return server

    def get_personality(self) -> Dict[str, Any]:
        return self.data.get("personality", {})

    def set_personality(self, name: str, description: str, style: str, generated: str):
        self.data["personality"] = {
            "enabled": True,
            "name": truncate_text(name, 80),
            "description": truncate_text(description, 1000),
            "style": truncate_text(style, 1000),
            "generated": truncate_text(generated, 4000)
        }
        self.save()

    def reset_personality(self):
        self.data["personality"] = {
            "enabled": False, "name": "", "description": "", "style": "", "generated": ""
        }
        self.save()

    def build_context(
        self,
        guild: discord.Guild,
        current_channel: Optional[discord.abc.GuildChannel] = None
    ) -> str:
        server = self.get_server(guild.id)
        rooms = server.get("rooms", {})
        if not rooms:
            for ch in guild.channels:
                if isinstance(ch, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel)):
                    cat = ch.category.name if getattr(ch, "category", None) else ""
                    rooms[str(ch.id)] = {
                        "id": ch.id, "name": ch.name, "mention": ch.mention,
                        "category": cat,
                        "topic": truncate_text(getattr(ch, "topic", "") or "", 120),
                        "type": ("Forum" if isinstance(ch, discord.ForumChannel)
                                 else "Voice" if isinstance(ch, discord.VoiceChannel)
                                 else "Text")
                    }
        lines = [
            f"اسم السيرفر: {guild.name}",
            f"Server ID: {guild.id}",
            f"عدد الأعضاء: {guild.member_count}",
        ]
        if current_channel:
            lines.append(f"الروم الحالية: {current_channel.name} ({current_channel.mention})")
        lines.append("\nالرومات المعروفة:")
        for room in sorted(
            rooms.values(),
            key=lambda r: (0 if r.get("type") in ("Text", "Forum") else 1, r.get("name", ""))
        ):
            line = f"- {room.get('name','')} | {room.get('mention','')} | {room.get('type','')}"
            if room.get("category"):
                line += f" | القسم: {room['category']}"
            if room.get("topic"):
                line += f" | الوصف: {truncate_text(room['topic'], 120)}"
            lines.append(line)
        return truncate_text("\n".join(lines), 15000)


# =========================================================
# MEMORY
# =========================================================

class MemoryManager:

    def __init__(self):
        self.memory: Dict = defaultdict(lambda: deque(maxlen=MEMORY_LIMIT))

    def _key(self, guild_id: int, user_id: int):
        return (int(guild_id), int(user_id))

    def cleanup(self, guild_id: int, user_id: int):
        key = self._key(guild_id, user_id)
        now = time.time()
        valid: deque = deque(maxlen=MEMORY_LIMIT)
        for item in self.memory[key]:
            if now - item["time"] <= MEMORY_TTL:
                valid.append(item)
        self.memory[key] = valid

    def add(self, guild_id: int, user_id: int, role: str, content: str):
        self.cleanup(guild_id, user_id)
        self.memory[self._key(guild_id, user_id)].append({
            "role": role,
            "content": truncate_text(content, 1200),
            "time": time.time()
        })

    def get(self, guild_id: int, user_id: int) -> List[Dict[str, str]]:
        self.cleanup(guild_id, user_id)
        return [
            {"role": i["role"], "content": i["content"]}
            for i in self.memory[self._key(guild_id, user_id)]
        ]

    def clear(self, guild_id: int, user_id: int):
        self.memory.pop(self._key(guild_id, user_id), None)


# =========================================================
# EMOJI MANAGER
# =========================================================

class EmojiManager:

    def __init__(self):
        self.data = load_json(EMOJI_FILE, {})

    def get(self, guild_id: int) -> str:
        return clean_text(self.data.get(str(guild_id), ""))

    def set(self, guild_id: int, emoji: str):
        self.data[str(guild_id)] = emoji
        save_json(EMOJI_FILE, self.data)

    def reset(self, guild_id: int):
        self.data.pop(str(guild_id), None)
        save_json(EMOJI_FILE, self.data)


# =========================================================
# FIME AI COG
# =========================================================

class FimeAI(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot      = bot
        self.knowledge = ServerKnowledgeManager()
        self.memory    = MemoryManager()
        self.emojis    = EmojiManager()
        self.user_locks: Dict = defaultdict(asyncio.Lock)
        self.client: Optional[AsyncOpenAI] = None
        self.ready = False
        self._init_client()
        print("🤖 Fime AI v4 initialized")

    # --------------------------------------------------
    def _init_client(self):
        if not GROQ_API_KEY:
            print("❌ GROQ_API_KEY غير موجود.")
            return
        self.client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)
        self.ready  = True
        print(f"✅ Fime AI | model: {AI_MODEL} | reasoning: {AI_REASONING_EFFORT}")

    # =====================================================
    # BASE PERSONALITY
    # =====================================================

    def get_base_prompt(self) -> str:
        return """
أنت فيمي. لك 5 سنين في السيرفر وتعرف كل فضايح العيال.
أنت مو بوت، أنت أخوهم الكبير الما يرحم.

قوانينك الصارمة:
- ردك سطرين بالكثير، مو أكثر.
- ممنوع الإيموجي نهائيًا في ردودك.
- لا تكرر أي ذبة أو جملة استخدمتها في نفس المحادثة، عندك ذاكرة قوية.
- لا تسب ولا تجلد إلا إذا الشخص اللي قدامك سبك أو استفزك مباشرة.
- إذا أحد تكلم بشكل عادي، رد بشكل عادي بدون جلد.
- إذا أحد طرح سؤالًا أو موضوعًا، جاوبه بشكل طبيعي.
- ما تبدأ أنت بالجلد بدون سبب.

أسلوبك:
بارد ومستفز وما تصارخ. تضحك عليهم بهدوء كأنهم نملة. واحدة بسيطة تحرق أكثر من سطر طويل.

عندك مكتبة ذبات تختار منها عشوائيًا عند الحاجة:
مستواك يوجع اعتزل احسن لك / انت اللي إذا فزت يكون السيرفر معلق / كلامك كله ماخذينه من تيك توك / وجودك مثل لاق السيرفر / انت المفروض يدفعون لك عشان ما تلعب / ذكائك يحتاج تحديث نسختك قديمة / حتى البوت اذكى منك / تراك مكشوف لا تمثل / اسكت كل ما تكلمت نزل مستواك / انت سبب اننا نخسر كل قيم / وش جابك هنا اصلا / نوب ويثبرثر واجد / حظك بس اللي فاز مو مهارتك / تعلم بعدين تعال تفلسف / كلامك بيض مثل لعبك / على شحم / منوب رسمي / سلك له / فزت بالغلط لا تحسب انك لعيب / مستواك يبكي / حتى اخوي اللي عمره 5 يجلدك / انطم بس / سامج / بيض / منوب / سبك / نايم انت / ذكائك تحت الصفر / انت عبء على التيم / توك تتعلم ومسوي فيها محترف / وجودك يلاقي / فاشل حتى في الفشلة / حظك خلص وش بتسوي الحين / لو تترك الكيبورد نرتاح / مستواك ثابت ما يتطور / تتفلسف وانت ما تعرف شي / كل ما شفت اسمك عرفت بنخسر / انت ما تفوز الا اذا ضدك بوتات / وش ذا اللعب حتى جدتي تلعب احسن / انت لاعب احتياط للاحتياط / اذا انت محترف انا وش اكون / منتهي من زمان / حركاتك قديمة / كل قيم نفس الاخطاء / ما تتعلم ابدا / تتوقع نفسك شي وانت ولا شي / قيمك كلها خساير / حتى الخصم يرحمك / انت مجرد عدد في السيرفر / مستواك ما يشفع لك تتكلم / لا يكثر

مهم: أحيانًا اخترع ذبتك الخاصة خارج القائمة، تطلع طبيعية من شخصيتك ومناسبة للموقف. التنوع مطلوب.

لا تذكر القائمة، لا تشرح نفسك، لا تعتذر. فقط تصرف.

معلومات السيرفر:
- لديك سياق الرومات الموجود أسفل هذه التعليمات.
- إذا ذكرت رومًا استخدم mention الحقيقي مثل <#123456789>.
- لا تخترع رومات غير موجودة.
- لا تكشف API keys أو tokens.
"""

    # =====================================================
    # CUSTOM PERSONALITY
    # =====================================================

    def get_personality_prompt(self) -> str:
        p = self.knowledge.get_personality()
        if not p.get("enabled", False):
            return ""
        return f"""
الشخصية المخصصة:
الاسم: {clean_text(p.get('name'))}
الوصف: {clean_text(p.get('description'))}
الأسلوب: {clean_text(p.get('style'))}
التوصيف: {clean_text(p.get('generated'))}

طبق الشخصية بذكاء. لا تلغِ قواعد النظام الأساسية.
"""

    # =====================================================
    # GENERATE PERSONALITY
    # =====================================================

    async def generate_personality(self, name: str, description: str, style: str) -> str:
        fallback = f"الشخصية اسمها {name}. {description}. أسلوبها: {style}."
        if not self.client:
            return fallback
        try:
            kwargs: Dict[str, Any] = {
                "model": AI_MODEL,
                "messages": [
                    {"role": "system", "content": "أنت مصمم شخصيات AI. اكتب توصيفًا مختصرًا بالعربية فقط بدون مقدمات."},
                    {"role": "user", "content": f"الاسم: {name}\nالوصف: {description}\nالأسلوب: {style}\n\nأنشئ قواعد سلوك واضحة ومختصرة."}
                ],
                "max_tokens": 400,
                "temperature": 0.4
            }
            if AI_MODEL.startswith("openai/gpt-oss"):
                kwargs["reasoning_effort"] = "low"
                kwargs.pop("temperature", None)
            response = await asyncio.wait_for(
                self.client.chat.completions.create(**kwargs),
                timeout=REQUEST_TIMEOUT
            )
            if not response.choices:
                return fallback
            content = clean_text(response.choices[0].message.content)
            return truncate_text(content, 4000) if content else fallback
        except asyncio.TimeoutError:
            print("⚠️ Personality generation: timeout.")
            return fallback
        except Exception as e:
            print(f"⚠️ Personality generation failed: {clean_error(e)}")
            return fallback

    # =====================================================
    # CHANNEL MENTION FIX
    # =====================================================

    def normalize_channel_mentions(self, guild: discord.Guild, text: str) -> str:
        if not text:
            return text
        channels = sorted(
            [c for c in guild.channels
             if isinstance(c, (discord.TextChannel, discord.ForumChannel, discord.VoiceChannel))],
            key=lambda c: len(c.name), reverse=True
        )
        for ch in channels:
            esc = re.escape(ch.name)
            text = re.sub(rf"(?<!<)#{esc}(?![\w-])", ch.mention, text, flags=re.IGNORECASE)
            text = re.sub(rf"`#?{esc}`", ch.mention, text, flags=re.IGNORECASE)
        return text

    # =====================================================
    # BUILD MESSAGES
    # =====================================================

    def build_messages(
        self,
        guild: discord.Guild,
        user: discord.Member,
        channel: discord.abc.GuildChannel,
        user_message: str
    ) -> List[Dict[str, str]]:

        system = (
            self.get_base_prompt()
            + "\n"
            + self.get_personality_prompt()
            + "\n\n=== SERVER CONTEXT ===\n"
            + self.knowledge.build_context(guild, channel)
            + "\n\n=== CHANNEL MENTION RULE ===\n"
            + "عند الإشارة إلى روم استخدم mention الحقيقي مثل <#123>."
        )

        msgs: List[Dict[str, str]] = [{"role": "system", "content": system}]
        for item in self.memory.get(guild.id, user.id):
            msgs.append({"role": item["role"], "content": item["content"]})
        msgs.append({
            "role": "user",
            "content": (
                f"اسم العضو: {user.display_name}\n"
                f"User ID: {user.id}\n\n"
                f"رسالة العضو:\n"
                f"{truncate_text(user_message, MAX_MESSAGE_LENGTH)}"
            )
        })
        return msgs

    # =====================================================
    # API REQUEST
    # =====================================================

    async def request_ai(self, messages: List[Dict[str, str]]) -> str:
        if not self.client:
            raise RuntimeError("GROQ_API_KEY غير موجود.")

        last_error: Optional[Exception] = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": AI_MODEL,
                    "messages": messages,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "temperature": 0.95
                }
                if AI_MODEL.startswith("openai/gpt-oss"):
                    kwargs["reasoning_effort"] = AI_REASONING_EFFORT
                    kwargs.pop("temperature", None)

                response = await asyncio.wait_for(
                    self.client.chat.completions.create(**kwargs),
                    timeout=REQUEST_TIMEOUT
                )
                if not response.choices:
                    raise RuntimeError("No choices.")
                content = response.choices[0].message.content
                if not content:
                    raise RuntimeError("Empty response.")
                return content.strip()

            except asyncio.TimeoutError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.3 * (attempt + 1))

            except Exception as e:
                last_error = e
                retryable = any(
                    w in str(e).lower()
                    for w in ("429", "rate limit", "timeout", "503", "502", "504", "overloaded")
                )
                if retryable and attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    break

        raise RuntimeError(clean_error(last_error or Exception("Unknown error.")))

    # =====================================================
    # ASK AI
    # =====================================================

    async def ask_ai(
        self,
        guild: discord.Guild,
        user: discord.Member,
        channel: discord.abc.GuildChannel,
        content: str
    ) -> str:
        if not content:
            return "وش تبي؟"
        async with self.user_locks[(guild.id, user.id)]:
            msgs   = self.build_messages(guild, user, channel, content)
            answer = await self.request_ai(msgs)
            answer = self.normalize_channel_mentions(guild, answer)
            self.memory.add(guild.id, user.id, "user",      content)
            self.memory.add(guild.id, user.id, "assistant", answer)
            return answer

    # =====================================================
    # ADD EMOJI
    # =====================================================

    def add_fime_emoji(self, guild_id: int, text: str) -> str:
        emoji = self.emojis.get(guild_id)
        if not emoji or emoji in text:
            return text
        return text.rstrip() + " " + emoji

    # =====================================================
    # SEND
    # =====================================================

    async def send_answer(self, message: discord.Message, answer: str):
        answer = self.add_fime_emoji(message.guild.id, answer)
        if len(answer) <= 2000:
            await message.reply(answer, mention_author=False)
            return
        chunks: List[str] = []
        current = ""
        for para in answer.split("\n"):
            if len(current) + len(para) + 1 <= 1900:
                current = (current + "\n" + para).lstrip("\n")
            else:
                if current:
                    chunks.append(current)
                current = para
        if current:
            chunks.append(current)
        for chunk in chunks:
            await message.reply(chunk, mention_author=False)

    # =====================================================
    # MESSAGE LISTENER
    # =====================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.content.startswith(self.bot.command_prefix):
            return
        if message.channel.id != AI_CHANNEL_ID:
            return
        content = clean_text(message.content)
        if not content:
            return
        content = re.sub(rf"<@!?{self.bot.user.id}>", "", content).strip()
        if not content:
            await message.reply("اي؟", mention_author=False)
            return
        content = truncate_text(content, MAX_MESSAGE_LENGTH)
        asyncio.create_task(self.process_message(message, content))

    async def process_message(self, message: discord.Message, content: str):
        try:
            async with message.channel.typing():
                answer = await self.ask_ai(
                    message.guild, message.author, message.channel, content
                )
            await self.send_answer(message, answer)
        except Exception as e:
            print(f"❌ Fime AI error: {clean_error(e)}")
            try:
                await message.reply("صار خطأ، جرب بعد شوي.", mention_author=False)
            except Exception:
                pass

    # =====================================================
    # ADMIN CHECK
    # =====================================================

    async def interaction_is_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == FIME_OWNER_ID:
            return True
        if isinstance(interaction.user, discord.Member):
            return interaction.user.guild_permissions.administrator
        return False

    # =====================================================
    # SLASH COMMANDS
    # =====================================================

    ai_group = app_commands.Group(name="ai", description="إعدادات وإدارة Fime AI")

    @ai_group.command(name="status", description="عرض حالة Fime AI")
    async def ai_status(self, interaction: discord.Interaction):
        p = self.knowledge.get_personality()
        embed = discord.Embed(title="🤖 Fime AI", color=discord.Color.blurple())
        embed.add_field(name="المزود",     value="Groq",                    inline=True)
        embed.add_field(name="الموديل",   value=f"`{AI_MODEL}`",            inline=True)
        embed.add_field(name="Reasoning", value=f"`{AI_REASONING_EFFORT}`", inline=True)
        embed.add_field(name="الشخصية",   value="مفعلة" if p.get("enabled") else "الافتراضية", inline=True)
        embed.add_field(name="Memory",    value=f"{MEMORY_LIMIT} رسالة",   inline=True)
        embed.add_field(name="الحالة",    value="🟢 Online" if self.ready else "🔴 Offline", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ai_group.command(name="emoji", description="تغيير إيموجي ردود AI")
    @app_commands.describe(emoji="الإيموجي")
    async def ai_emoji(self, interaction: discord.Interaction, emoji: str):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        self.emojis.set(interaction.guild.id, truncate_text(emoji, 30))
        await interaction.response.send_message(f"✅ الإيموجي: {emoji}", ephemeral=True)

    @ai_group.command(name="emoji-reset", description="إلغاء إيموجي AI")
    async def ai_emoji_reset(self, interaction: discord.Interaction):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        self.emojis.reset(interaction.guild.id)
        await interaction.response.send_message("✅ تم إلغاء الإيموجي.", ephemeral=True)

    @ai_group.command(name="emoji-show", description="عرض إيموجي AI")
    async def ai_emoji_show(self, interaction: discord.Interaction):
        emoji = self.emojis.get(interaction.guild.id)
        await interaction.response.send_message(
            emoji or "لا يوجد إيموجي مخصص.", ephemeral=True
        )

    @ai_group.command(name="memory-clear", description="مسح ذاكرتك مع Fime AI")
    async def ai_memory_clear(self, interaction: discord.Interaction):
        self.memory.clear(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message("🧠 تم مسح الذاكرة.", ephemeral=True)

    @ai_group.command(name="reset", description="إعادة ضبط ذاكرة عضو")
    @app_commands.describe(member="العضو")
    async def ai_reset(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        self.memory.clear(interaction.guild.id, member.id)
        await interaction.response.send_message(f"✅ تم مسح ذاكرة {member.mention}.", ephemeral=True)

    @ai_group.command(name="channel", description="عرض روم AI")
    async def ai_channel(self, interaction: discord.Interaction):
        ch = self.bot.get_channel(AI_CHANNEL_ID)
        await interaction.response.send_message(
            f"🤖 روم AI: {ch.mention}" if ch else f"🤖 AI Channel ID: `{AI_CHANNEL_ID}`",
            ephemeral=True
        )

    @ai_group.command(name="set-channel", description="تغيير روم AI")
    @app_commands.describe(channel="الروم الجديد")
    async def ai_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"⚠️ غيّر `AI_CHANNEL_ID` إلى `{channel.id}` في الاستضافة ثم أعد التشغيل.",
            ephemeral=True
        )

    @ai_group.command(name="server-scan", description="تحديث معرفة AI بالرومات")
    async def ai_server_scan(self, interaction: discord.Interaction):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        server = await self.knowledge.scan_guild(interaction.guild)
        await interaction.followup.send(
            f"✅ تم التحديث. الرومات: `{len(server.get('rooms', {}))}`",
            ephemeral=True
        )

    @ai_group.command(name="rooms", description="عرض الرومات التي يعرفها AI")
    async def ai_rooms(self, interaction: discord.Interaction):
        rooms = self.knowledge.get_server(interaction.guild.id).get("rooms", {})
        if not rooms:
            await interaction.response.send_message("استخدم `/ai server-scan` أولًا.", ephemeral=True)
            return
        lines = [
            f"{r['mention']} `{r['name']}`"
            for r in sorted(
                [r for r in rooms.values() if r.get("type") in ("Text", "Forum")],
                key=lambda r: r.get("name", "")
            )[:80]
        ]
        await interaction.response.send_message(
            truncate_text("📚 **الرومات:**\n\n" + "\n".join(lines), 1900),
            ephemeral=True
        )

    @ai_group.command(name="room-add", description="إضافة وصف لروم")
    @app_commands.describe(channel="الروم", description="الوصف")
    async def ai_room_add(self, interaction: discord.Interaction, channel: discord.TextChannel, description: str):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        server = self.knowledge.get_server(interaction.guild.id)
        rooms  = server.setdefault("rooms", {})
        room   = rooms.setdefault(str(channel.id), {
            "id": channel.id, "name": channel.name, "mention": channel.mention,
            "category": channel.category.name if channel.category else "",
            "topic": "", "type": "Text"
        })
        room["description"] = truncate_text(description, 300)
        self.knowledge.save()
        await interaction.response.send_message(f"✅ تمت إضافة {channel.mention}.", ephemeral=True)

    @ai_group.command(name="room-remove", description="حذف معلومات روم")
    @app_commands.describe(channel="الروم")
    async def ai_room_remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        self.knowledge.get_server(interaction.guild.id).get("rooms", {}).pop(str(channel.id), None)
        self.knowledge.save()
        await interaction.response.send_message(f"✅ تم حذف {channel.mention}.", ephemeral=True)

    @ai_group.command(name="knowledge", description="ملخص معرفة AI")
    async def ai_knowledge(self, interaction: discord.Interaction):
        server = self.knowledge.get_server(interaction.guild.id)
        p      = self.knowledge.get_personality()
        await interaction.response.send_message(
            f"🧠 **Fime AI Knowledge**\n\n"
            f"الرومات: `{len(server.get('rooms', {}))}`\n"
            f"الشخصية: `{p.get('name') if p.get('enabled') else 'الافتراضية'}`\n"
            f"آخر تحديث: <t:{safe_int(server.get('last_scan'), 0)}:R>",
            ephemeral=True
        )

    @ai_group.command(name="personality", description="إنشاء شخصية مخصصة")
    @app_commands.describe(name="الاسم", description="الوصف", style="الأسلوب")
    async def ai_personality(
        self, interaction: discord.Interaction,
        name: str, description: str, style: str
    ):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        generated = await self.generate_personality(
            truncate_text(name, 80),
            truncate_text(description, 1000),
            truncate_text(style, 1000)
        )
        self.knowledge.set_personality(name, description, style, generated)
        await interaction.followup.send(
            f"✅ **تم إنشاء الشخصية.**\n\n**الاسم:** {name}\n**التوصيف:**\n{truncate_text(generated, 1500)}",
            ephemeral=True
        )

    @ai_group.command(name="personality-reset", description="إرجاع الشخصية الافتراضية")
    async def ai_personality_reset(self, interaction: discord.Interaction):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ للإدارة فقط.", ephemeral=True)
            return
        self.knowledge.reset_personality()
        await interaction.response.send_message("✅ تم إرجاع الشخصية الافتراضية.", ephemeral=True)

    # =====================================================
    # COG LOAD
    # =====================================================

    async def cog_load(self):
        try:
            for guild in self.bot.guilds:
                if not self.knowledge.get_server(guild.id).get("rooms"):
                    await self.knowledge.scan_guild(guild)
            print("✅ Fime AI knowledge initialized.")
        except Exception as e:
            print(f"⚠️ AI knowledge init error: {clean_error(e)}")


# =========================================================
# SETUP
# =========================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(FimeAI(bot))
    print("✅ Fime AI extension loaded.")
