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
import aiohttp


# =========================================================
# FIME AI - configurable chat API
# =========================================================
# This file uses a standard Chat Completions-compatible endpoint.
# MongoDB ai.mongodb.com keys are for embeddings/reranking and do not
# provide chat completions; use a chat-generation provider key here.
# بعض لوحات الاستضافة تتيح نسخ القيمة بعلامات اقتباس؛ نزيل الاقتباس الخارجي فقط.
AI_API_KEY = os.getenv("AI_API_KEY", "").strip().strip('"\'')
AI_BASE_URL = os.getenv(
    "AI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/"
).strip().rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "gemini-2.5-flash").strip()
AI_PROVIDER_NAME = os.getenv("AI_PROVIDER_NAME", "Gemini API").strip() or "Custom AI API"

try:
    AI_CHANNEL_ID = int(os.getenv("AI_CHANNEL_ID", "1547903949967720498"))
except (TypeError, ValueError):
    AI_CHANNEL_ID = 0

try:
    FIME_OWNER_ID = int(os.getenv("FIME_OWNER_ID", "1388514481444880549"))
except (TypeError, ValueError):
    FIME_OWNER_ID = 0

MEMORY_LIMIT = 16
MEMORY_TTL = 4.5 * 60 * 60
MAX_MESSAGE_LENGTH = 2500
MAX_OUTPUT_TOKENS = 900
REQUEST_TIMEOUT = 35
MAX_RETRIES = 2
KNOWLEDGE_FILE = Path("ai_server_knowledge.json")
EMOJI_FILE = Path("ai_emoji_settings.json")
SCRIPT_KEYWORDS = ("سكربت", "سكريبت", "سكرببت", "scripts", "script", "scripting", "scriptblox", "rscripts")
SCRIPT_ROOM_LIMIT = 25


# =========================================================
# HELPERS
# =========================================================

def clean_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    value = str(value).strip()

    if not value:
        return default

    return value


def truncate_text(text: str, limit: int) -> str:
    text = clean_text(text)

    if len(text) <= limit:
        return text

    return text[:limit - 3] + "..."


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clean_error(error: Exception) -> str:
    text = str(error)
    if AI_API_KEY:
        text = text.replace(AI_API_KEY, "[REDACTED]")
    return truncate_text(text, 700)


# =========================================================
# JSON STORAGE
# =========================================================

def load_json(path: Path, default: Any) -> Any:
    try:
        if not path.exists():
            return default

        with path.open(
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        return data

    except Exception as error:
        print(
            f"⚠️ تعذر قراءة {path.name}: "
            f"{clean_error(error)}"
        )
        return default


def save_json(path: Path, data: Any) -> bool:
    temp_path = path.with_suffix(".tmp")

    try:
        with temp_path.open(
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )

        temp_path.replace(path)
        return True

    except Exception as error:
        print(
            f"⚠️ تعذر حفظ {path.name}: "
            f"{clean_error(error)}"
        )

        try:
            if temp_path.exists():
                temp_path.unlink()
        except Exception:
            pass

        return False


# =========================================================
# DEFAULT KNOWLEDGE
# =========================================================

DEFAULT_SERVER_KNOWLEDGE = {
    "servers": {}
}


# =========================================================
# SERVER KNOWLEDGE
# =========================================================

class ServerKnowledgeManager:

    def __init__(self):
        self.data = load_json(
            KNOWLEDGE_FILE,
            DEFAULT_SERVER_KNOWLEDGE.copy()
        )

        self._normalize()

    # -----------------------------------------------------

    def _normalize(self):
        if not isinstance(self.data, dict):
            self.data = {}
        if not isinstance(self.data.get("servers"), dict):
            self.data["servers"] = {}
        # Remove old custom-personality data during migration.
        self.data.pop("personality", None)

    # -----------------------------------------------------

    def save(self):
        save_json(
            KNOWLEDGE_FILE,
            self.data
        )

    # -----------------------------------------------------

    def get_server(
        self,
        guild_id: int
    ) -> Dict[str, Any]:

        key = str(guild_id)

        if key not in self.data["servers"]:
            self.data["servers"][key] = {
                "rooms": {},
                "script_rooms": {},
                "last_scan": 0,
                "ai_channel_id": AI_CHANNEL_ID
            }

        server = self.data["servers"][key]

        server.setdefault(
            "rooms",
            {}
        )

        server.setdefault(
            "last_scan",
            0
        )

        server.setdefault(
            "script_rooms",
            {}
        )
        server.setdefault("ai_channel_id", AI_CHANNEL_ID)

        return server

    # -----------------------------------------------------

    def get_ai_channel_id(self, guild_id: int) -> int:
        return safe_int(self.get_server(guild_id).get("ai_channel_id"), AI_CHANNEL_ID)

    def set_ai_channel_id(self, guild_id: int, channel_id: int) -> None:
        self.get_server(guild_id)["ai_channel_id"] = int(channel_id)
        self.save()

    # -----------------------------------------------------

    async def scan_guild(
        self,
        guild: discord.Guild
    ) -> Dict[str, Any]:

        server = self.get_server(
            guild.id
        )

        rooms = {}

        for channel in guild.channels:

            if not isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.VoiceChannel,
                    discord.StageChannel,
                    discord.ForumChannel,
                    discord.CategoryChannel
                )
            ):
                continue

            category_name = ""

            if getattr(
                channel,
                "category",
                None
            ):
                category_name = (
                    channel.category.name
                )

            topic = ""

            if isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.ForumChannel
                )
            ):
                topic = clean_text(
                    getattr(
                        channel,
                        "topic",
                        ""
                    )
                )

            room_type = "Other"

            if isinstance(
                channel,
                discord.TextChannel
            ):
                room_type = "Text"

            elif isinstance(
                channel,
                discord.ForumChannel
            ):
                room_type = "Forum"

            elif isinstance(
                channel,
                discord.VoiceChannel
            ):
                room_type = "Voice"

            elif isinstance(
                channel,
                discord.StageChannel
            ):
                room_type = "Stage"

            elif isinstance(
                channel,
                discord.CategoryChannel
            ):
                room_type = "Category"

            rooms[str(channel.id)] = {
                "id": channel.id,
                "name": channel.name,
                "mention": channel.mention,
                "category": category_name,
                "topic": truncate_text(
                    topic,
                    180
                ),
                "type": room_type
            }

        server["rooms"] = rooms
        server["last_scan"] = int(time.time())

        self.save()

        return server

    # -----------------------------------------------------

    def get_script_rooms(self, guild_id: int) -> Dict[str, Any]:
        server = self.get_server(guild_id)
        return server.setdefault("script_rooms", {})

    def add_script_room(self, guild_id: int, channel: discord.abc.GuildChannel):
        rooms = self.get_script_rooms(guild_id)
        rooms[str(channel.id)] = {
            "id": channel.id,
            "name": channel.name,
            "mention": channel.mention,
            "type": type(channel).__name__,
        }
        self.save()

    def remove_script_room(self, guild_id: int, channel_id: int) -> bool:
        rooms = self.get_script_rooms(guild_id)
        removed = rooms.pop(str(channel_id), None) is not None
        self.save()
        return removed

    # -----------------------------------------------------

    def build_context(
        self,
        guild: discord.Guild,
        current_channel: Optional[discord.abc.GuildChannel] = None
    ) -> str:

        server = self.get_server(
            guild.id
        )

        rooms = server.get(
            "rooms",
            {}
        )

        # إذا ما كان فيه بيانات، نسوي scan سريع
        if not rooms:
            rooms = {}

            for channel in guild.channels:

                if isinstance(
                    channel,
                    (
                        discord.TextChannel,
                        discord.ForumChannel,
                        discord.VoiceChannel
                    )
                ):

                    category = ""

                    if getattr(
                        channel,
                        "category",
                        None
                    ):
                        category = (
                            channel.category.name
                        )

                    rooms[str(channel.id)] = {
                        "id": channel.id,
                        "name": channel.name,
                        "mention": channel.mention,
                        "category": category,
                        "topic": truncate_text(
                            getattr(
                                channel,
                                "topic",
                                ""
                            ) or "",
                            120
                        ),
                        "type": (
                            "Forum"
                            if isinstance(
                                channel,
                                discord.ForumChannel
                            )
                            else (
                                "Voice"
                                if isinstance(
                                    channel,
                                    discord.VoiceChannel
                                )
                                else "Text"
                            )
                        )
                    }

        lines = []

        lines.append(
            f"اسم السيرفر: {guild.name}"
        )

        lines.append(
            f"Server ID: {guild.id}"
        )

        lines.append(
            f"عدد الأعضاء: {guild.member_count}"
        )

        if current_channel:

            lines.append(
                "الروم الحالية: "
                f"{current_channel.name} "
                f"({current_channel.mention})"
            )

        lines.append(
            "\nالرومات المعروفة:"
        )

        # نحط الرومات النصية والمنتديات أولاً
        ordered_rooms = sorted(
            rooms.values(),
            key=lambda room: (
                0
                if room.get("type")
                in ("Text", "Forum")
                else 1,
                room.get("name", "")
            )
        )

        for room in ordered_rooms:

            room_name = room.get(
                "name",
                ""
            )

            mention = room.get(
                "mention",
                ""
            )

            category = room.get(
                "category",
                ""
            )

            room_type = room.get(
                "type",
                "Other"
            )

            topic = room.get(
                "topic",
                ""
            )

            line = (
                f"- {room_name} | "
                f"{mention} | "
                f"{room_type}"
            )

            if category:
                line += (
                    f" | القسم: {category}"
                )

            if topic:
                line += (
                    f" | الوصف: "
                    f"{truncate_text(topic, 120)}"
                )
            description = room.get("description", "")
            if description:
                line += f" | معلومات إضافية: {truncate_text(description, 120)}"

            lines.append(
                line
            )

        return truncate_text(
            "\n".join(lines),
            15000
        )


# =========================================================
# MEMORY
# =========================================================

class MemoryManager:

    def __init__(self):
        self.memory = defaultdict(
            lambda: deque(
                maxlen=MEMORY_LIMIT
            )
        )

    # -----------------------------------------------------

    def _key(
        self,
        guild_id: int,
        user_id: int
    ):
        return (
            int(guild_id),
            int(user_id)
        )

    # -----------------------------------------------------

    def cleanup(
        self,
        guild_id: int,
        user_id: int
    ):

        key = self._key(
            guild_id,
            user_id
        )

        now = time.time()

        valid = deque(
            maxlen=MEMORY_LIMIT
        )

        for item in self.memory[key]:

            if now - item["time"] <= MEMORY_TTL:
                valid.append(item)

        self.memory[key] = valid

    # -----------------------------------------------------

    def add(
        self,
        guild_id: int,
        user_id: int,
        role: str,
        content: str
    ):

        self.cleanup(
            guild_id,
            user_id
        )

        self.memory[
            self._key(
                guild_id,
                user_id
            )
        ].append({
            "role": role,
            "content": truncate_text(
                content,
                1200
            ),
            "time": time.time()
        })

    # -----------------------------------------------------

    def get(
        self,
        guild_id: int,
        user_id: int
    ) -> List[Dict[str, str]]:

        self.cleanup(
            guild_id,
            user_id
        )

        return [
            {
                "role": item["role"],
                "content": item["content"]
            }
            for item in self.memory[
                self._key(
                    guild_id,
                    user_id
                )
            ]
        ]

    # -----------------------------------------------------

    def clear(
        self,
        guild_id: int,
        user_id: int
    ):

        self.memory.pop(
            self._key(
                guild_id,
                user_id
            ),
            None
        )


# =========================================================
# EMOJI MANAGER
# =========================================================

class EmojiManager:

    def __init__(self):
        self.data = load_json(
            EMOJI_FILE,
            {}
        )

    # -----------------------------------------------------

    def get(
        self,
        guild_id: int
    ) -> str:

        return clean_text(
            self.data.get(
                str(guild_id),
                ""
            )
        )

    # -----------------------------------------------------

    def set(
        self,
        guild_id: int,
        emoji: str
    ):

        self.data[str(guild_id)] = emoji

        save_json(
            EMOJI_FILE,
            self.data
        )

    # -----------------------------------------------------

    def reset(
        self,
        guild_id: int
    ):

        self.data.pop(
            str(guild_id),
            None
        )

        save_json(
            EMOJI_FILE,
            self.data
        )


# =========================================================
# FIME AI
# =========================================================

class FimeAI(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot
    ):

        self.bot = bot

        self.knowledge = (
            ServerKnowledgeManager()
        )

        self.memory = (
            MemoryManager()
        )

        self.emojis = (
            EmojiManager()
        )

        self.user_locks = defaultdict(
            asyncio.Lock
        )

        self.ready = False
        self._init_client()
        print("🤖 Fime AI initialized")

    # =====================================================
    # API CONFIGURATION
    # =====================================================

    def _init_client(self):
        mongo_key_on_google_endpoint = (
            (AI_API_KEY.startswith("al-") or AI_API_KEY.startswith("AQ."))
            and "generativelanguage.googleapis.com" in AI_BASE_URL
        )
        self.ready = bool(AI_API_KEY and AI_BASE_URL and AI_MODEL) and not mongo_key_on_google_endpoint
        if not AI_API_KEY:
            print("❌ AI_API_KEY غير موجود. أضف مفتاح واجهة توليد نصوص.")
            return
        if mongo_key_on_google_endpoint:
            print("❌ صيغة المفتاح لا تبدو مناسبة لواجهة Gemini المضبوطة. تأكد أنك نسخت مفتاح Gemini API من Google AI Studio، وليس مفتاح خدمة أخرى.")
            return
        print(f"✅ Fime AI endpoint: {AI_BASE_URL}")
        print(f"🧠 Fime AI model: {AI_MODEL}")

    # =====================================================
    # BASE BEHAVIOR
    # =====================================================

    def get_base_prompt(self) -> str:

        return """
أنت "فيمي" AI الخاص بسيرفر Team Fime.

هويتك:
- اسمك فيمي.
- تتكلم بأسلوب سعودي طبيعي وعفوي.
- لا تتكلم كأنك خدمة عملاء.
- لا تستخدم "عمي".
- لا تكن رسميًا بشكل مبالغ فيه.
- لا توافق المستخدم في كل شيء لمجرد إرضائه.
- إذا كان المستخدم مخطئًا، صحح له بهدوء وبوضوح.
- عند المزح، امزح بشكل طبيعي بدون مبالغة.
- لا تجعل كل رسالة مليئة بالإيموجيات.
- لا تستخدم مقدمات آلية مثل "بالتأكيد يسعدني مساعدتك".
- لا تكرر كلام المستخدم بدون سبب.
- إذا كان السؤال بسيطًا، جاوب بشكل بسيط.
- إذا احتاج السؤال شرحًا، اشرح بوضوح.
- لا تعطِ إجابات طويلة بدون حاجة.

هوية Team Fime:
- أنت جزء من Team Fime.
- افهم أن Fime / فايم هو اسم وهوية السيرفر/المالك.
- لا تدّعي أنك المالك.
- أنت مساعد السيرفر وشخصيته الذكية.

اللغة:
- العربية السعودية هي اللغة الأساسية.
- يمكنك استخدام الإنجليزية إذا كانت مناسبة.
- إذا تكلم المستخدم بالإنجليزية، افهمه ورد بالطريقة الأنسب.
- لا تترجم كل شيء للعربية بشكل إجباري.

معلومات السيرفر:
- لديك سياق الرومات الموجود أسفل هذه التعليمات.
- إذا ذكرت رومًا موجودًا في السياق، استخدم Discord mention الحقيقي له.
- مثال صحيح: <#123456789>
- لا تكتب اسم الروم فقط عندما يكون المقصود الإشارة للروم.
- لا تخترع ID.
- لا تخترع رومًا غير موجود في السياق.
- إذا كان اسم الروم معروفًا، استخدم الـ mention الموجود بجانبه.
- لا تحوّل أسماء الأقسام Category إلى mentions لأن Discord لا يستخدمها كـ text-channel mentions.

البرمجة:
- لا تكتب أو تعدل أكواد البوت للأعضاء إذا كان ذلك مخالفًا لسياسة السيرفر أو تعليماتك.
- يمكنك شرح أنظمة Team Fime الموجودة ومساعدتهم على فهمها.
- لا تكشف الأسرار أو مفاتيح API أو التوكنات أو كلمات المرور.

الخصوصية:
- لا تدّعي معرفة معلومات خاصة غير موجودة في السياق.
- لا تدّعي تنفيذ شيء لم تنفذه.
- لا تدّعي الوصول إلى ملفات أو أنظمة لم يتم إعطاؤك الوصول إليها.

الرد:
- كن واثقًا وطبيعيًا.
- لا تكرر نفس الجملة.
- لا تضع عناوين كثيرة في رد صغير.
- لا تستخدم markdown بكثرة.
- اجعل الرد مناسبًا لديسكورد.
"""

    # =====================================================
    # CHANNEL MENTION FIX
    # =====================================================

    def normalize_channel_mentions(
        self,
        guild: discord.Guild,
        text: str
    ) -> str:

        if not text:
            return text

        channels = []

        for channel in guild.channels:

            if isinstance(
                channel,
                (
                    discord.TextChannel,
                    discord.ForumChannel,
                    discord.VoiceChannel
                )
            ):
                channels.append(
                    channel
                )

        # الأطول أولًا حتى لا يحصل تعارض
        channels.sort(
            key=lambda channel: len(
                channel.name
            ),
            reverse=True
        )

        for channel in channels:

            escaped_name = re.escape(
                channel.name
            )

            mention = channel.mention

            # #channel-name
            pattern = (
                rf"(?<!<)#"
                rf"{escaped_name}"
                rf"(?![\w-])"
            )

            text = re.sub(
                pattern,
                mention,
                text,
                flags=re.IGNORECASE
            )

            # `channel-name`
            pattern_code = (
                rf"`#?{escaped_name}`"
            )

            text = re.sub(
                pattern_code,
                mention,
                text,
                flags=re.IGNORECASE
            )

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

        server_context = (
            self.knowledge.build_context(
                guild,
                channel
            )
        )

        memory = self.memory.get(
            guild.id,
            user.id
        )

        system = (
            self.get_base_prompt()
            + "\n\n"
            + "=== SERVER CONTEXT ===\n"
            + server_context
            + "\n\n"
            + "=== CHANNEL MENTION RULE ===\n"
            + (
                "عند الإشارة إلى روم، "
                "استخدم قيمة mention الموجودة "
                "بجانب الروم حرفيًا، مثل <#123>."
            )
        )

        messages = [
            {
                "role": "system",
                "content": system
            }
        ]

        for item in memory:

            messages.append({
                "role": item["role"],
                "content": item["content"]
            })

        messages.append({
            "role": "user",
            "content": (
                f"اسم العضو: {user.display_name}\n"
                f"User ID: {user.id}\n\n"
                f"رسالة العضو:\n"
                f"{truncate_text(user_message, MAX_MESSAGE_LENGTH)}"
            )
        })

        return messages

    # =====================================================
    # API REQUEST
    # =====================================================

    async def request_ai(self, messages: List[Dict[str, str]]) -> str:
        if not AI_API_KEY:
            raise RuntimeError(
                "AI_API_KEY غير موجود. مفتاح MongoDB ai.mongodb.com مخصص للتضمين النصي "
                "ولا يدعم توليد ردود المحادثة؛ أضف مفتاح Chat API متوافقًا."
            )
        if (AI_API_KEY.startswith(("al-", "AQ.")) and "generativelanguage.googleapis.com" in AI_BASE_URL):
            raise RuntimeError(
                "هذا المفتاح لا يبدو مفتاح Gemini API صالحًا لهذه الواجهة؛ احصل على مفتاح توليد محادثة "
                "أو اضبط AI_BASE_URL وAI_MODEL لمزود يدعم chat completions."
            )
        if not AI_BASE_URL or not AI_MODEL:
            raise RuntimeError("تأكد من إعداد AI_BASE_URL وAI_MODEL في Environment.")

        endpoint = f"{AI_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": AI_MODEL,
            "messages": messages,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.75,
        }
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        last_error = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(endpoint, headers=headers, json=payload) as response:
                        response_text = await response.text()
                        if response.status >= 400:
                            safe_body = response_text.replace(AI_API_KEY, "[REDACTED]")
                            last_error = RuntimeError(
                                f"Chat API HTTP {response.status}: {truncate_text(safe_body, 500)}"
                            )
                            retryable = response.status in (408, 425, 429, 500, 502, 503, 504)
                            if retryable and attempt < MAX_RETRIES:
                                await asyncio.sleep(0.8 * (attempt + 1))
                                continue
                            raise last_error

                        try:
                            data = json.loads(response_text)
                        except json.JSONDecodeError as error:
                            raise RuntimeError("واجهة الذكاء الاصطناعي أعادت استجابة غير صالحة.") from error

                        choices = data.get("choices") or []
                        if not choices:
                            raise RuntimeError("واجهة الذكاء الاصطناعي لم تُرجع أي رد.")
                        message_data = choices[0].get("message") or {}
                        content = message_data.get("content")
                        if isinstance(content, list):
                            content = "".join(
                                part.get("text", "") if isinstance(part, dict) else str(part)
                                for part in content
                            )
                        content = clean_text(content)
                        if not content:
                            raise RuntimeError("النموذج أعاد ردًا فارغًا.")
                        return content

            except asyncio.TimeoutError as error:
                last_error = error
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
            except aiohttp.ClientError as error:
                last_error = error
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.6 * (attempt + 1))
                    continue
            except Exception as error:
                if last_error is None or error is not last_error:
                    last_error = error
                error_text = str(error).lower()
                retryable = any(token in error_text for token in ("429", "rate limit", "timeout", "temporarily", "503", "502", "504", "overloaded"))
                if retryable and attempt < MAX_RETRIES:
                    await asyncio.sleep(0.8 * (attempt + 1))
                    continue
                break

        raise RuntimeError(clean_error(last_error or Exception("تعذر الاتصال بواجهة الذكاء الاصطناعي.")))

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
            return "وش تبي بالضبط؟"

        lock = self.user_locks[
            (guild.id, user.id)
        ]

        # يمنع رسائل نفس العضو من التخبط
        # لكنه لا يوقف باقي الأعضاء
        async with lock:

            messages = self.build_messages(
                guild,
                user,
                channel,
                content
            )

            answer = await self.request_ai(
                messages
            )

            answer = (
                self.normalize_channel_mentions(
                    guild,
                    answer
                )
            )

            self.memory.add(
                guild.id,
                user.id,
                "user",
                content
            )

            self.memory.add(
                guild.id,
                user.id,
                "assistant",
                answer
            )

            return answer

    # =====================================================
    # SCRIPT ROOM ROUTING
    # =====================================================

    @staticmethod
    def normalize_script_text(text: str) -> str:
        text = clean_text(text).lower()
        for old, new in {"إ": "ا", "أ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""}.items():
            text = text.replace(old, new)
        return re.sub(r"\s+", " ", text)

    def is_script_request(self, text: str) -> bool:
        normalized = self.normalize_script_text(text)
        if any(word in normalized for word in ("سكربت", "سكريبت", "سكرببت")):
            return True
        # Match actual English words, so "description" doesn't accidentally trigger "script".
        return bool(re.search(
            r"(?<![a-z0-9_])(?:script|scripts|scripting|scriptblox|rscripts)(?![a-z0-9_])",
            normalized,
            flags=re.IGNORECASE,
        ))

    def get_script_room_mentions(self, guild: discord.Guild) -> List[str]:
        configured = self.knowledge.get_script_rooms(guild.id)
        mentions = []
        stale = []
        for channel_id in list(configured):
            channel = guild.get_channel(safe_int(channel_id, 0))
            if channel is None:
                stale.append(channel_id)
            else:
                mentions.append(channel.mention)
        if stale:
            for channel_id in stale:
                configured.pop(channel_id, None)
            self.knowledge.save()
        return mentions[:SCRIPT_ROOM_LIMIT]

    async def route_script_request(self, message: discord.Message) -> bool:
        if not self.is_script_request(message.content):
            return False
        rooms = self.get_script_room_mentions(message.guild)
        if rooms:
            text = "إذا تبي السكربتات، تلقاها هنا: " + " ".join(rooms)
            text += "\nاكتب طلبك في الروم المخصصة عشان يروح للمكان الصحيح."
        else:
            text = (
                "ما فيه روم سكربتات محددة في هذا السيرفر حتى الآن. "
                "خلّ الإدارة تستخدم `/ai script-room-add` لتحديد الروم أولًا."
            )
        await message.reply(text, mention_author=False)
        return True

    # =====================================================
    # ADD EMOJI
    # =====================================================

    def add_fime_emoji(
        self,
        guild_id: int,
        text: str
    ) -> str:

        emoji = self.emojis.get(
            guild_id
        )

        if not emoji:
            return text

        # لا نضيفه إذا الرد يحتويه
        if emoji in text:
            return text

        return (
            text.rstrip()
            + " "
            + emoji
        )

    # =====================================================
    # SEND
    # =====================================================

    async def send_answer(self, message: discord.Message, answer: str):
        answer = self.add_fime_emoji(message.guild.id, clean_text(answer))
        if not answer:
            answer = "ما وصلني رد نصي من النموذج."

        # Discord message content must remain below 2,000 characters.
        chunks = []
        remaining = answer
        limit = 1900
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, limit)
            if split_at < limit // 2:
                split_at = remaining.rfind(" ", 0, limit)
            if split_at < limit // 2:
                split_at = limit
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip()

        for index, chunk in enumerate(chunks):
            if index == 0:
                await message.reply(chunk, mention_author=False)
            else:
                await message.channel.send(chunk)

    # =====================================================
    # MESSAGE LISTENER
    # =====================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Respect string, list, or callable command-prefix configurations.
        try:
            context = await self.bot.get_context(message)
            if context.valid:
                return
        except Exception:
            pass

        content = clean_text(message.content)
        if not content:
            return

        # Route script-related messages anywhere in the server, before the AI-room filter.
        if await self.route_script_request(message):
            return

        ai_channel_id = self.knowledge.get_ai_channel_id(message.guild.id)
        if ai_channel_id and message.channel.id != ai_channel_id:
            return

        if self.bot.user:
            content = re.sub(rf"<@!?{self.bot.user.id}>", "", content).strip()
        if not content:
            await message.reply("هلا، وش تبي؟", mention_author=False)
            return

        content = truncate_text(content, MAX_MESSAGE_LENGTH)
        asyncio.create_task(self.process_message(message, content))

    # =====================================================

    async def process_message(
        self,
        message: discord.Message,
        content: str
    ):

        try:

            async with message.channel.typing():

                answer = await self.ask_ai(
                    message.guild,
                    message.author,
                    message.channel,
                    content
                )

            await self.send_answer(
                message,
                answer
            )

        except Exception as error:

            print(
                "❌ Fime AI error: "
                f"{clean_error(error)}"
            )

            try:

                await message.reply(
                    "صار خطأ وأنا أحاول أجيب الرد، "
                    "جرب بعد شوي.",
                    mention_author=False
                )

            except Exception:
                pass

    # =====================================================
    # ADMIN CHECK
    # =====================================================

    async def interaction_is_admin(
        self,
        interaction: discord.Interaction
    ) -> bool:

        if interaction.user.id == FIME_OWNER_ID:
            return True

        if isinstance(
            interaction.user,
            discord.Member
        ):

            if interaction.user.guild_permissions.administrator:
                return True

        return False

    # =====================================================
    # GROUP
    # =====================================================

    ai_group = app_commands.Group(
        name="ai",
        description="إعدادات وإدارة Fime AI"
    )

    # =====================================================
    # /ai status
    # =====================================================

    @ai_group.command(
        name="status",
        description="عرض حالة Fime AI"
    )
    async def ai_status(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 Fime AI",
            description="حالة نظام الذكاء الاصطناعي",
            color=discord.Color.blurple()
        )
        embed.add_field(name="المزود", value=AI_PROVIDER_NAME, inline=True)
        embed.add_field(name="الموديل", value=f"`{AI_MODEL}`", inline=True)
        embed.add_field(name="الذاكرة", value=f"{MEMORY_LIMIT} رسالة", inline=True)
        embed.add_field(
            name="الحالة",
            value="🟢 الإعدادات مكتملة" if self.ready else "🔴 مفتاح AI_API_KEY غير موجود",
            inline=True
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # =====================================================
    # /ai emoji
    # =====================================================

    @ai_group.command(
        name="emoji",
        description="تغيير الإيموجي الخاص بردود AI"
    )
    @app_commands.describe(
        emoji="الإيموجي الذي سيضاف لنهاية الرد"
    )
    async def ai_emoji(
        self,
        interaction: discord.Interaction,
        emoji: str
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        emoji = truncate_text(
            emoji,
            30
        )

        self.emojis.set(
            interaction.guild.id,
            emoji
        )

        await interaction.response.send_message(
            f"✅ تم تغيير إيموجي Fime AI إلى {emoji}",
            ephemeral=True
        )

    # =====================================================
    # /ai emoji-reset
    # =====================================================

    @ai_group.command(
        name="emoji-reset",
        description="إرجاع إيموجي AI للوضع الافتراضي"
    )
    async def ai_emoji_reset(
        self,
        interaction: discord.Interaction
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        self.emojis.reset(
            interaction.guild.id
        )

        await interaction.response.send_message(
            "✅ تم إلغاء إيموجي AI.",
            ephemeral=True
        )

    # =====================================================
    # /ai emoji-show
    # =====================================================

    @ai_group.command(
        name="emoji-show",
        description="عرض إيموجي AI الحالي"
    )
    async def ai_emoji_show(
        self,
        interaction: discord.Interaction
    ):

        emoji = self.emojis.get(
            interaction.guild.id
        )

        await interaction.response.send_message(
            emoji
            if emoji
            else "لا يوجد إيموجي مخصص حاليًا.",
            ephemeral=True
        )

    # =====================================================
    # /ai memory-clear
    # =====================================================

    @ai_group.command(
        name="memory-clear",
        description="مسح ذاكرة محادثتك مع Fime AI"
    )
    async def ai_memory_clear(
        self,
        interaction: discord.Interaction
    ):

        self.memory.clear(
            interaction.guild.id,
            interaction.user.id
        )

        await interaction.response.send_message(
            "🧠 تم مسح ذاكرتك مع Fime AI.",
            ephemeral=True
        )

    # =====================================================
    # /ai reset
    # =====================================================

    @ai_group.command(
        name="reset",
        description="إعادة ضبط ذاكرة عضو"
    )
    @app_commands.describe(
        member="العضو"
    )
    async def ai_reset(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        self.memory.clear(
            interaction.guild.id,
            member.id
        )

        await interaction.response.send_message(
            f"✅ تم مسح ذاكرة {member.mention}.",
            ephemeral=True
        )

    # =====================================================
    # /ai channel
    # =====================================================

    @ai_group.command(
        name="channel",
        description="عرض روم AI الحالي"
    )
    async def ai_channel(self, interaction: discord.Interaction):
        channel_id = self.knowledge.get_ai_channel_id(interaction.guild.id)
        channel = interaction.guild.get_channel(channel_id) if channel_id else None
        text = f"🤖 روم AI الحالي: {channel.mention}" if channel else (
            f"لم يتم تحديد روم AI. استخدم `/ai set-channel` أو اضبط `AI_CHANNEL_ID` في الاستضافة.\n"
            f"المعرّف الحالي: `{channel_id or 0}`"
        )
        await interaction.response.send_message(text, ephemeral=True)

    # =====================================================
    # /ai set-channel
    # =====================================================

    @ai_group.command(name="set-channel", description="تحديد روم الذكاء الاصطناعي لهذا السيرفر")
    @app_commands.describe(channel="روم AI الجديدة")
    async def ai_set_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ هذا الأمر للإدارة فقط.", ephemeral=True)
            return
        self.knowledge.set_ai_channel_id(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} كروم للذكاء الاصطناعي. التغيير محفوظ ولا يحتاج تعديل Environment.",
            ephemeral=True
        )

    # =====================================================
    # /ai server-scan
    # =====================================================

    @ai_group.command(
        name="server-scan",
        description="تحديث معرفة Fime AI برومات السيرفر"
    )
    async def ai_server_scan(
        self,
        interaction: discord.Interaction
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        server = await self.knowledge.scan_guild(
            interaction.guild
        )

        count = len(
            server.get(
                "rooms",
                {}
            )
        )

        await interaction.followup.send(
            f"✅ تم تحديث معرفة AI.\n"
            f"📚 عدد الرومات: `{count}`",
            ephemeral=True
        )

    # =====================================================
    # /ai rooms
    # =====================================================

    @ai_group.command(
        name="rooms",
        description="عرض الرومات التي يعرفها AI"
    )
    async def ai_rooms(
        self,
        interaction: discord.Interaction
    ):

        server = self.knowledge.get_server(
            interaction.guild.id
        )

        rooms = server.get(
            "rooms",
            {}
        )

        if not rooms:

            await interaction.response.send_message(
                "لا توجد بيانات محفوظة. "
                "استخدم `/ai server-scan`.",
                ephemeral=True
            )

            return

        text_rooms = [
            room
            for room in rooms.values()
            if room.get("type")
            in ("Text", "Forum")
        ]

        text_rooms.sort(
            key=lambda x: x.get(
                "name",
                ""
            )
        )

        lines = [
            f"{room['mention']} "
            f"`{room['name']}`"
            for room in text_rooms[:80]
        ]

        output = (
            "📚 **الرومات التي يعرفها Fime AI:**\n\n"
            + "\n".join(lines)
        )

        await interaction.response.send_message(
            truncate_text(
                output,
                1900
            ),
            ephemeral=True
        )

    # =====================================================
    # /ai room-add
    # =====================================================

    @ai_group.command(
        name="room-add",
        description="إضافة معلومات لروم"
    )
    @app_commands.describe(
        channel="الروم",
        description="وصف مختصر للروم"
    )
    async def ai_room_add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        description: str
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        server = self.knowledge.get_server(
            interaction.guild.id
        )

        rooms = server.setdefault(
            "rooms",
            {}
        )

        room = rooms.setdefault(
            str(channel.id),
            {
                "id": channel.id,
                "name": channel.name,
                "mention": channel.mention,
                "category": (
                    channel.category.name
                    if channel.category
                    else ""
                ),
                "topic": "",
                "type": "Text"
            }
        )

        room["description"] = (
            truncate_text(
                description,
                300
            )
        )

        self.knowledge.save()

        await interaction.response.send_message(
            f"✅ تمت إضافة معلومات {channel.mention}.",
            ephemeral=True
        )

    # =====================================================
    # /ai room-remove
    # =====================================================

    @ai_group.command(
        name="room-remove",
        description="حذف معلومات روم من معرفة AI"
    )
    @app_commands.describe(
        channel="الروم"
    )
    async def ai_room_remove(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        if not await self.interaction_is_admin(
            interaction
        ):

            await interaction.response.send_message(
                "❌ هذا الأمر للإدارة فقط.",
                ephemeral=True
            )

            return

        server = self.knowledge.get_server(
            interaction.guild.id
        )

        rooms = server.get(
            "rooms",
            {}
        )

        rooms.pop(
            str(channel.id),
            None
        )

        self.knowledge.save()

        await interaction.response.send_message(
            f"✅ تم حذف معلومات {channel.mention}.",
            ephemeral=True
        )

    # =====================================================
    # /ai knowledge
    # =====================================================

    @ai_group.command(
        name="knowledge",
        description="عرض ملخص معرفة AI بالسيرفر"
    )
    async def ai_knowledge(self, interaction: discord.Interaction):
        server = self.knowledge.get_server(interaction.guild.id)
        rooms = server.get("rooms", {})
        script_rooms = server.get("script_rooms", {})
        await interaction.response.send_message(
            "🧠 **Fime AI Knowledge**\n\n"
            f"الرومات المعروفة: `{len(rooms)}`\n"
            f"رومات السكربتات: `{len(script_rooms)}`\n"
            f"آخر تحديث: <t:{safe_int(server.get('last_scan'), 0)}:R>",
            ephemeral=True
        )

    # =====================================================
    # /ai script-room-add
    # =====================================================

    @ai_group.command(
        name="script-room-add",
        description="تحديد روم مخصصة لطلبات السكربتات"
    )
    @app_commands.describe(channel="الروم التي توجه إليها طلبات السكربتات")
    async def ai_script_room_add(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ هذا الأمر للإدارة فقط.", ephemeral=True)
            return
        self.knowledge.add_script_room(interaction.guild.id, channel)
        await interaction.response.send_message(
            f"✅ تم تحديد {channel.mention} كروم للسكربتات.\n"
            "سيتم اكتشاف كلمات مثل «سكربت» و«سكريبت» و«script» داخل الرسالة.",
            ephemeral=True
        )

    # =====================================================
    # /ai script-room-remove
    # =====================================================

    @ai_group.command(
        name="script-room-remove",
        description="إزالة روم من توجيه طلبات السكربتات"
    )
    @app_commands.describe(channel="الروم التي تريد إزالتها")
    async def ai_script_room_remove(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ هذا الأمر للإدارة فقط.", ephemeral=True)
            return
        removed = self.knowledge.remove_script_room(interaction.guild.id, channel.id)
        await interaction.response.send_message(
            "✅ تمت إزالة الروم." if removed else "ℹ️ الروم ليست ضمن رومات السكربتات.",
            ephemeral=True
        )

    # =====================================================
    # /ai script-rooms
    # =====================================================

    @ai_group.command(
        name="script-rooms",
        description="عرض رومات السكربتات المحددة"
    )
    async def ai_script_rooms(self, interaction: discord.Interaction):
        if not await self.interaction_is_admin(interaction):
            await interaction.response.send_message("❌ هذا الأمر للإدارة فقط.", ephemeral=True)
            return
        rooms = self.get_script_room_mentions(interaction.guild)
        text = ("🧩 **رومات السكربتات:**\n" + "\n".join(rooms)) if rooms else (
            "لا توجد رومات سكربتات محددة. استخدم `/ai script-room-add`."
        )
        await interaction.response.send_message(text, ephemeral=True)

    # =====================================================
    # COG LOAD
    # =====================================================

    async def cog_load(self):

        try:

            # نتأكد أن معرفة السيرفر موجودة
            for guild in self.bot.guilds:

                server = (
                    self.knowledge.get_server(
                        guild.id
                    )
                )

                if not server.get(
                    "rooms"
                ):

                    await self.knowledge.scan_guild(
                        guild
                    )

            print(
                "✅ Fime AI knowledge initialized."
            )

        except Exception as error:

            print(
                "⚠️ AI knowledge init error: "
                f"{clean_error(error)}"
            )


# =========================================================
# SETUP
# =========================================================

async def setup(
    bot: commands.Bot
):

    await bot.add_cog(
        FimeAI(bot)
    )

    print(
        "✅ Fime AI extension loaded."
    )
