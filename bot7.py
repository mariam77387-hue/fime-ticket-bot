# -*- coding: utf-8 -*-
"""
bot7.py - Ticket System + Staff Applications (discord.py 2.7+)

Load from bot.py with:
    await bot.load_extension("bot7")

Features:
- Persistent ticket panels and ticket controls.
- Ticket transcripts and configurable ticket types.
- A private /staff-application setup command for the server owner only.
- Fully configurable staff application panel, button, questions, and channels.
- Persistent application buttons that continue working after restarts.
- All bot7 prefix commands are restricted to the server owner.

Data files are created automatically beside this file:
- bot7_tickets.json
- bot7_staff_applications.json
"""

from __future__ import annotations

import asyncio
import copy
import io
import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# Paths and constants
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
TICKET_DATA_FILE = BASE_DIR / "bot7_tickets.json"
APPLICATION_DATA_FILE = BASE_DIR / "bot7_staff_applications.json"

COG_NAME = "Tickets"
NO_MENTIONS = discord.AllowedMentions.none()

CLOSE_DELAY = 8
TRANSCRIPT_LIMIT = 1000
MAX_CUSTOM_TYPES = 15
SETUP_TIMEOUT = 120
CONFIRM_TIMEOUT = 60
APPLICATION_SETUP_TIMEOUT = 900
MAX_APPLICATION_QUESTIONS = 5

DEFAULT_PANEL_TITLE = "Support Center"
DEFAULT_PANEL_TEXT = (
    "Choose the option that best matches your request from the menu below. "
    "A private ticket will be opened for you."
)

BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


DEFAULT_TYPES: Dict[str, Dict[str, str]] = {
    "support": {
        "label": "General Support",
        "emoji": "🛠️",
        "description": "Questions, help, or account issues.",
    },
    "report": {
        "label": "Report a Member",
        "emoji": "🚨",
        "description": "Report rule breaking or misconduct.",
    },
    "partnership": {
        "label": "Partnership",
        "emoji": "🤝",
        "description": "Partnership and collaboration requests.",
    },
    "purchase": {
        "label": "Purchase",
        "emoji": "🛒",
        "description": "Orders, payments, and product questions.",
    },
    "appeal": {
        "label": "Appeal",
        "emoji": "⚖️",
        "description": "Appeal a warning, mute, or ban.",
    },
    "bug": {
        "label": "Bug Report",
        "emoji": "🐞",
        "description": "Report a bug or a broken feature.",
    },
    "other": {
        "label": "Other",
        "emoji": "📩",
        "description": "Anything that does not fit the options above.",
    },
}
DEFAULT_ENABLED = ["support", "report", "partnership", "purchase", "appeal", "other"]


def default_ticket_config() -> dict:
    return {
        "enabled_types": list(DEFAULT_ENABLED),
        "custom_types": [],
        "staff_role_id": None,
        "category_id": None,
        "log_channel_id": None,
        "panel_title": DEFAULT_PANEL_TITLE,
        "panel_text": DEFAULT_PANEL_TEXT,
        "counter": 0,
        "tickets": {},
    }


def default_application_config() -> dict:
    return {
        "panel_channel_id": None,
        "log_channel_id": None,
        "panel_title": "Staff Applications",
        "panel_description": "Click the button below to submit your staff application.",
        "button_label": "Apply Now",
        "button_emoji": None,
        "button_style": "primary",
        "embed_color": "5865F2",
        "questions": [],
    }


def trunc(value, limit: int) -> str:
    value = str(value or "").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json_atomic(path: Path, payload: str) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(path)
    except OSError as error:
        print(f"[BOT7] Could not save {path.name}: {error}")
        raise


def emoji_of(value) -> Optional[discord.PartialEmoji]:
    if not value:
        return None
    try:
        return discord.PartialEmoji.from_str(str(value).strip())
    except (TypeError, ValueError):
        return None


def slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:20]
    return cleaned or "member"


def parse_color(value: str) -> Optional[int]:
    raw = str(value or "").strip().replace("#", "").replace("0x", "").replace("0X", "")
    if len(raw) != 6:
        return None
    try:
        return int(raw, 16)
    except ValueError:
        return None


def color_from_config(cfg: dict) -> discord.Color:
    value = parse_color(cfg.get("embed_color", "5865F2"))
    return discord.Color(value if value is not None else 0x5865F2)


def ticket_catalog(cfg: dict) -> Dict[str, dict]:
    items = {key: {"key": key, **value} for key, value in DEFAULT_TYPES.items()}
    for custom in cfg.get("custom_types", []):
        if isinstance(custom, dict) and custom.get("key"):
            items[custom["key"]] = custom
    return items


def enabled_ticket_types(cfg: dict) -> List[dict]:
    items = ticket_catalog(cfg)
    return [items[key] for key in cfg.get("enabled_types", []) if key in items]


def ticket_type_label(cfg: dict, key: str) -> str:
    item = ticket_catalog(cfg).get(key)
    return item["label"] if item else "Unknown"


def is_server_owner(guild: Optional[discord.Guild], user) -> bool:
    return bool(guild and user and guild.owner_id == getattr(user, "id", None))


def server_owner_only():
    """Prefix-command check. Unauthorized users are ignored by the cog error handler."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is not None and is_server_owner(ctx.guild, ctx.author):
            return True
        raise commands.CheckFailure("Server owner only.")

    return commands.check(predicate)


# ============================================================
# Ticket views
# ============================================================


class ConfirmCloseView(discord.ui.View):
    def __init__(self, cog: "Tickets", channel: discord.TextChannel, requester_id: int, reason: str):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.cog = cog
        self.channel = channel
        self.requester_id = requester_id
        self.reason = reason
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Confirm Close", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who requested the close can confirm it.", ephemeral=True
            )
            return
        self.stop()
        await interaction.response.edit_message(content="🔒 Closing the ticket...", view=None)
        self.cog.spawn(self.cog.close_ticket(self.channel, interaction.user, self.reason))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return
        self.stop()
        await interaction.response.edit_message(content="Cancelled. The ticket stays open.", view=None)

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            await self.message.edit(
                content="⏰ Confirmation time has ended. The ticket stays open.",
                view=None,
            )
        except discord.HTTPException:
            pass


class TicketControlView(discord.ui.View):
    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="ticket:claim")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_claim_button(interaction)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.handle_close_button(interaction)


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "Tickets", options: List[discord.SelectOption]):
        super().__init__(timeout=None)
        self.cog = cog
        select = discord.ui.Select(
            custom_id="ticket:open",
            placeholder="Select the type of ticket you need...",
            min_values=1,
            max_values=1,
            options=options or [discord.SelectOption(label="Unavailable", value="none")],
        )
        select.callback = self._picked
        self.add_item(select)

    async def _picked(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This panel can only be used in a server.", ephemeral=True)
            return
        values = interaction.data.get("values") or []
        if not values:
            await interaction.response.send_message("Choose a ticket type first.", ephemeral=True)
            return
        await self.cog.open_ticket(interaction, values[0])


class TypeSelectView(discord.ui.View):
    """Owner setup menu for choosing which ticket types appear in a new panel."""

    def __init__(self, cog: "Tickets", guild_id: int, requester_id: int):
        super().__init__(timeout=SETUP_TIMEOUT)
        self.cog = cog
        self.guild_id = guild_id
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None

        cfg = cog.ticket_cfg(guild_id)
        enabled = set(cfg["enabled_types"])
        options = []
        for key, item in ticket_catalog(cfg).items():
            options.append(
                discord.SelectOption(
                    label=trunc(item["label"], 100),
                    value=key,
                    description=trunc(item.get("description", ""), 100) or None,
                    emoji=emoji_of(item.get("emoji")),
                    default=key in enabled,
                )
            )
        options = options[:25]
        self.select = discord.ui.Select(
            placeholder="Choose the ticket types shown in the panel",
            min_values=0,
            max_values=max(1, len(options)),
            options=options or [discord.SelectOption(label="No types available", value="none")],
        )
        self.select.callback = self._saved
        self.add_item(self.select)

    async def _saved(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id or not is_server_owner(interaction.guild, interaction.user):
            await interaction.response.send_message("This setup is only available to the server owner.", ephemeral=True)
            return
        cfg = self.cog.ticket_cfg(self.guild_id)
        valid = set(ticket_catalog(cfg))
        cfg["enabled_types"] = [value for value in self.select.values if value in valid]
        await self.cog.save_tickets()
        self.stop()
        await interaction.response.edit_message(
            content=f"Saved. {len(cfg['enabled_types'])} ticket type(s) will appear in new panels.",
            view=None,
        )

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            await self.message.edit(content="Selection time has ended. Run the ticket setup command again.", view=None)
        except discord.HTTPException:
            pass


# ============================================================
# Staff application modals
# ============================================================


class PanelContentModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", guild_id: int, setup_view: "ApplicationSetupView"):
        super().__init__(title="Edit Application Panel", timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.setup_view = setup_view
        cfg = cog.application_cfg(guild_id)
        self.panel_title = discord.ui.TextInput(
            default=cfg.get("panel_title", "Staff Applications"),
            max_length=256,
            required=True,
        )
        self.panel_description = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            default=cfg.get("panel_description", ""),
            max_length=3000,
            required=True,
        )
        self.add_item(discord.ui.Label(text="Panel title", component=self.panel_title))
        self.add_item(discord.ui.Label(text="Panel description", component=self.panel_description))

    async def on_submit(self, interaction: discord.Interaction):
        if not is_server_owner(interaction.guild, interaction.user):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return
        cfg = self.cog.application_cfg(self.guild_id)
        cfg["panel_title"] = trunc(self.panel_title.value, 256)
        cfg["panel_description"] = trunc(self.panel_description.value, 3000)
        await self.cog.save_applications()
        await interaction.response.send_message("Panel text saved.", ephemeral=True)


class ApplicationButtonModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", guild_id: int):
        super().__init__(title="Edit Application Button", timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        cfg = cog.application_cfg(guild_id)
        self.button_label = discord.ui.TextInput(
            default=cfg.get("button_label", "Apply Now"),
            max_length=80,
            required=True,
        )
        self.button_emoji = discord.ui.TextInput(
            default=cfg.get("button_emoji") or "",
            max_length=100,
            required=False,
            placeholder="Example: 📝",
        )
        self.add_item(discord.ui.Label(text="Button name", component=self.button_label))
        self.add_item(discord.ui.Label(text="Button emoji (optional)", component=self.button_emoji))

    async def on_submit(self, interaction: discord.Interaction):
        if not is_server_owner(interaction.guild, interaction.user):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return
        cfg = self.cog.application_cfg(self.guild_id)
        label = self.button_label.value.strip()
        if not label:
            await interaction.response.send_message("The button name cannot be empty.", ephemeral=True)
            return
        cfg["button_label"] = trunc(label, 80)
        emoji_value = self.button_emoji.value.strip()
        cfg["button_emoji"] = emoji_value or None
        await self.cog.save_applications()
        await interaction.response.send_message("Application button settings saved.", ephemeral=True)


class ApplicationQuestionsModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", guild_id: int):
        super().__init__(title="Edit Application Questions", timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        cfg = cog.application_cfg(guild_id)
        current = "\n".join(cfg.get("questions", []))
        self.questions_text = discord.ui.TextInput(
            style=discord.TextStyle.paragraph,
            default=current,
            max_length=1000,
            required=False,
            placeholder="Enter one question per line, with up to five questions.",
        )
        self.add_item(
            discord.ui.Label(
                text="Questions (one per line, up to 5)",
                component=self.questions_text,
            )
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not is_server_owner(interaction.guild, interaction.user):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return

        questions = [line.strip() for line in self.questions_text.value.splitlines() if line.strip()]
        if len(questions) > MAX_APPLICATION_QUESTIONS:
            await interaction.response.send_message(
                f"You can add up to {MAX_APPLICATION_QUESTIONS} questions.", ephemeral=True
            )
            return
        too_long = [question for question in questions if len(question) > 45]
        if too_long:
            await interaction.response.send_message(
                "Each question must be 45 characters or fewer because Discord uses it as a form field label.",
                ephemeral=True,
            )
            return

        cfg = self.cog.application_cfg(self.guild_id)
        cfg["questions"] = questions
        await self.cog.save_applications()
        await interaction.response.send_message(
            f"Saved {len(questions)} application question(s).", ephemeral=True
        )


class ApplicationColorModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", guild_id: int):
        super().__init__(title="Edit Panel Color", timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        cfg = cog.application_cfg(guild_id)
        self.color_text = discord.ui.TextInput(
            default=cfg.get("embed_color", "5865F2"),
            max_length=7,
            required=True,
            placeholder="5865F2 or #5865F2",
        )
        self.add_item(
            discord.ui.Label(text="Embed color in HEX format", component=self.color_text)
        )

    async def on_submit(self, interaction: discord.Interaction):
        if not is_server_owner(interaction.guild, interaction.user):
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
            return
        value = self.color_text.value.strip()
        parsed = parse_color(value)
        if parsed is None:
            await interaction.response.send_message(
                "Invalid color. Enter six hexadecimal characters, for example `5865F2`.",
                ephemeral=True,
            )
            return
        cfg = self.cog.application_cfg(self.guild_id)
        cfg["embed_color"] = f"{parsed:06X}"
        await self.cog.save_applications()
        await interaction.response.send_message("Panel color saved.", ephemeral=True)


class StaffApplicationModal(discord.ui.Modal):
    def __init__(self, cog: "Tickets", guild_id: int, questions: List[str]):
        super().__init__(title="Staff Application", timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.questions = list(questions[:MAX_APPLICATION_QUESTIONS])
        self.answer_inputs: List[discord.ui.TextInput] = []

        for index, question in enumerate(self.questions, start=1):
            answer = discord.ui.TextInput(
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=1000,
                placeholder="Write your answer here...",
            )
            self.answer_inputs.append(answer)
            self.add_item(discord.ui.Label(text=question, component=answer))

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.send_message("This application form is no longer valid.", ephemeral=True)
            return

        cfg = self.cog.application_cfg(guild.id)
        log_channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.response.send_message(
                "The application log channel is not configured. Please contact the server owner.",
                ephemeral=True,
            )
            return

        if not self.questions or len(self.answer_inputs) != len(self.questions):
            await interaction.response.send_message(
                "The application form is not configured correctly. Please contact the server owner.",
                ephemeral=True,
            )
            return

        application_id = uuid.uuid4().hex[:10].upper()
        embed = discord.Embed(
            title="New Staff Application",
            color=color_from_config(cfg),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="Applicant",
            value=f"{interaction.user.mention}\n`{interaction.user}`\n`{interaction.user.id}`",
            inline=False,
        )
        for question, answer_input in zip(self.questions, self.answer_inputs):
            embed.add_field(
                name=trunc(question, 256),
                value=trunc(answer_input.value, 1024) or "No answer provided.",
                inline=False,
            )
        embed.set_footer(text=f"Application ID: {application_id}")

        try:
            await log_channel.send(embed=embed, allowed_mentions=NO_MENTIONS)
        except discord.Forbidden:
            await interaction.response.send_message(
                "Your application could not be submitted because the bot cannot send messages in the application log channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as error:
            print(f"[STAFF APPLICATION] Could not log application: {error}")
            await interaction.response.send_message(
                "Your application could not be submitted due to a Discord error. Please try again later.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Your staff application has been submitted successfully.", ephemeral=True
        )


# ============================================================
# Staff application persistent panel and owner setup view
# ============================================================


class StaffApplicationPanelView(discord.ui.View):
    """Persistent public panel. Each server gets a unique custom_id."""

    def __init__(self, cog: "Tickets", guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        cfg = cog.application_cfg(guild_id)
        style = BUTTON_STYLES.get(cfg.get("button_style", "primary"), discord.ButtonStyle.primary)
        emoji = emoji_of(cfg.get("button_emoji"))
        button = discord.ui.Button(
            label=trunc(cfg.get("button_label", "Apply Now"), 80) or "Apply Now",
            style=style,
            emoji=emoji,
            custom_id=f"staffapp:apply:{guild_id}",
            row=0,
        )
        button.callback = self.apply
        self.add_item(button)

    async def apply(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or guild.id != self.guild_id:
            await interaction.response.send_message("This application panel is not available here.", ephemeral=True)
            return

        cfg = self.cog.application_cfg(guild.id)
        questions = cfg.get("questions", [])
        log_channel_id = cfg.get("log_channel_id")
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None

        if not questions:
            await interaction.response.send_message(
                "The staff application form has not been configured yet. Please contact the server owner.",
                ephemeral=True,
            )
            return
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.response.send_message(
                "The application system is not fully configured yet. Please contact the server owner.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(StaffApplicationModal(self.cog, guild.id, questions))


class ApplicationSetupView(discord.ui.View):
    """Ephemeral setup dashboard. Only the invoking server owner can use it."""

    def __init__(self, cog: "Tickets", guild_id: int, owner_id: int):
        super().__init__(timeout=APPLICATION_SETUP_TIMEOUT)
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id

        content_button = discord.ui.Button(
            label="Panel Text", style=discord.ButtonStyle.primary, emoji="📝", row=0
        )
        content_button.callback = self.edit_panel_text
        self.add_item(content_button)

        button_button = discord.ui.Button(
            label="Button Settings", style=discord.ButtonStyle.primary, emoji="🔘", row=0
        )
        button_button.callback = self.edit_button
        self.add_item(button_button)

        questions_button = discord.ui.Button(
            label="Form Questions", style=discord.ButtonStyle.primary, emoji="📋", row=0
        )
        questions_button.callback = self.edit_questions
        self.add_item(questions_button)

        current_style = cog.application_cfg(guild_id).get("button_style", "primary")
        self.style_select = discord.ui.Select(
            placeholder="Choose the application button style",
            min_values=1,
            max_values=1,
            row=1,
            options=[
                discord.SelectOption(label="Primary (Blurple)", value="primary", default=current_style == "primary"),
                discord.SelectOption(label="Secondary (Grey)", value="secondary", default=current_style == "secondary"),
                discord.SelectOption(label="Success (Green)", value="success", default=current_style == "success"),
                discord.SelectOption(label="Danger (Red)", value="danger", default=current_style == "danger"),
            ],
        )
        self.style_select.callback = self.change_style
        self.add_item(self.style_select)

        self.panel_channel_select = discord.ui.ChannelSelect(
            placeholder="Choose the channel where the panel will be posted",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
            row=2,
        )
        self.panel_channel_select.callback = self.set_panel_channel
        self.add_item(self.panel_channel_select)

        self.log_channel_select = discord.ui.ChannelSelect(
            placeholder="Choose the channel where applications will be logged",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1,
            max_values=1,
            row=3,
        )
        self.log_channel_select.callback = self.set_log_channel
        self.add_item(self.log_channel_select)

        color_button = discord.ui.Button(
            label="Embed Color", style=discord.ButtonStyle.secondary, emoji="🎨", row=4
        )
        color_button.callback = self.edit_color
        self.add_item(color_button)

        post_button = discord.ui.Button(
            label="Post Panel", style=discord.ButtonStyle.success, emoji="📨", row=4
        )
        post_button.callback = self.post_panel
        self.add_item(post_button)

        refresh_button = discord.ui.Button(
            label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄", row=4
        )
        refresh_button.callback = self.refresh_setup
        self.add_item(refresh_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_server_owner(interaction.guild, interaction.user):
            return True
        await interaction.response.send_message("Only the server owner can use this setup.", ephemeral=True)
        return False

    async def edit_panel_text(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelContentModal(self.cog, self.guild_id, self))

    async def edit_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationButtonModal(self.cog, self.guild_id))

    async def edit_questions(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationQuestionsModal(self.cog, self.guild_id))

    async def edit_color(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ApplicationColorModal(self.cog, self.guild_id))

    async def refresh_setup(self, interaction: discord.Interaction):
        cfg = self.cog.application_cfg(self.guild_id)
        await interaction.response.edit_message(
            embed=self.cog.application_setup_embed(interaction.guild, cfg), view=self
        )

    async def change_style(self, interaction: discord.Interaction):
        cfg = self.cog.application_cfg(self.guild_id)
        cfg["button_style"] = self.style_select.values[0]
        await self.cog.save_applications()
        await interaction.response.edit_message(
            embed=self.cog.application_setup_embed(interaction.guild, cfg), view=self
        )

    async def set_panel_channel(self, interaction: discord.Interaction):
        selected = self.panel_channel_select.values[0]
        channel = selected.resolve() if hasattr(selected, "resolve") else None
        if channel is None and interaction.guild is not None:
            channel = interaction.guild.get_channel(selected.id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Choose a text channel.", ephemeral=True)
            return
        cfg = self.cog.application_cfg(self.guild_id)
        cfg["panel_channel_id"] = channel.id
        await self.cog.save_applications()
        await interaction.response.edit_message(
            embed=self.cog.application_setup_embed(interaction.guild, cfg), view=self
        )

    async def set_log_channel(self, interaction: discord.Interaction):
        selected = self.log_channel_select.values[0]
        channel = selected.resolve() if hasattr(selected, "resolve") else None
        if channel is None and interaction.guild is not None:
            channel = interaction.guild.get_channel(selected.id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Choose a text channel.", ephemeral=True)
            return
        cfg = self.cog.application_cfg(self.guild_id)
        cfg["log_channel_id"] = channel.id
        await self.cog.save_applications()
        await interaction.response.edit_message(
            embed=self.cog.application_setup_embed(interaction.guild, cfg), view=self
        )

    async def post_panel(self, interaction: discord.Interaction):
        cfg = self.cog.application_cfg(self.guild_id)
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This setup only works inside a server.", ephemeral=True)
            return

        panel_channel_id = cfg.get("panel_channel_id")
        log_channel_id = cfg.get("log_channel_id")
        panel_channel = guild.get_channel(int(panel_channel_id)) if panel_channel_id else None
        log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None

        if not isinstance(panel_channel, discord.TextChannel):
            await interaction.response.send_message("Select a panel channel before posting.", ephemeral=True)
            return
        if not isinstance(log_channel, discord.TextChannel):
            await interaction.response.send_message("Select an application log channel before posting.", ephemeral=True)
            return

        bot_member = guild.me
        if bot_member is not None:
            log_permissions = log_channel.permissions_for(bot_member)
            if not log_permissions.send_messages or not log_permissions.embed_links:
                await interaction.response.send_message(
                    "I need Send Messages and Embed Links permissions in the application log channel before you can post the panel.",
                    ephemeral=True,
                )
                return

        if not cfg.get("questions"):
            await interaction.response.send_message("Add at least one application question before posting.", ephemeral=True)
            return
        if not str(cfg.get("button_label", "")).strip():
            await interaction.response.send_message("Set a button name before posting.", ephemeral=True)
            return

        # Acknowledge the private setup interaction, but never send a public status message.
        await interaction.response.defer(ephemeral=True, thinking=False)
        try:
            panel_embed = discord.Embed(
                title=trunc(cfg.get("panel_title", "Staff Applications"), 256),
                description=trunc(cfg.get("panel_description", ""), 4000),
                color=color_from_config(cfg),
            )
            panel_embed.set_footer(text="Staff Applications")
            panel_view = self.cog.register_application_view(guild.id, replace=True)
            await panel_channel.send(embed=panel_embed, view=panel_view, allowed_mentions=NO_MENTIONS)
        except discord.Forbidden:
            await interaction.edit_original_response(content="I cannot post in the selected panel channel. Check my View Channel, Send Messages, and Embed Links permissions.")
            return
        except discord.HTTPException as error:
            print(f"[STAFF APPLICATION] Could not post panel: {error}")
            await interaction.edit_original_response(content="Discord could not post the application panel. Check the channel and try again.")
            return

        # Do not send any extra message after posting. Keep the private setup dashboard open.
        await interaction.edit_original_response(
            embed=self.cog.application_setup_embed(guild, cfg),
            view=self,
            content=None,
        )


# ============================================================
# Main Cog
# ============================================================


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ticket_db = read_json(TICKET_DATA_FILE)
        self.application_db = read_json(APPLICATION_DATA_FILE)
        self.ticket_lock = asyncio.Lock()
        self.application_lock = asyncio.Lock()
        self.tasks: set = set()
        self.creating: set = set()
        self.closing: set = set()
        self.application_views: Dict[int, StaffApplicationPanelView] = {}

    # ---------------- lifecycle ----------------

    async def cog_load(self) -> None:
        # Ticket views use fixed custom IDs and are re-registered after every restart.
        self.bot.add_view(
            TicketPanelView(
                self,
                [discord.SelectOption(label="Unavailable", value="none")],
            )
        )
        self.bot.add_view(TicketControlView(self))

        # Application panel views are registered once per configured server.
        for guild_key in list(self.application_db.keys()):
            try:
                guild_id = int(guild_key)
                self.register_application_view(guild_id, replace=True)
            except (TypeError, ValueError):
                continue

    def cog_unload(self) -> None:
        for view in self.application_views.values():
            try:
                self.bot.remove_view(view)
            except Exception:
                pass
        self.application_views.clear()

    def spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # ---------------- storage ----------------

    async def save_tickets(self) -> None:
        payload = json.dumps(self.ticket_db, ensure_ascii=False, indent=2)
        async with self.ticket_lock:
            await asyncio.to_thread(write_json_atomic, TICKET_DATA_FILE, payload)

    async def save_applications(self) -> None:
        payload = json.dumps(self.application_db, ensure_ascii=False, indent=2)
        async with self.application_lock:
            await asyncio.to_thread(write_json_atomic, APPLICATION_DATA_FILE, payload)

    def ticket_cfg(self, guild_id: int) -> dict:
        key = str(guild_id)
        cfg = self.ticket_db.get(key)
        if not isinstance(cfg, dict):
            cfg = self.ticket_db[key] = default_ticket_config()
        for name, value in default_ticket_config().items():
            cfg.setdefault(name, copy.deepcopy(value))
        if not isinstance(cfg.get("tickets"), dict):
            cfg["tickets"] = {}
        if not isinstance(cfg.get("custom_types"), list):
            cfg["custom_types"] = []
        if not isinstance(cfg.get("enabled_types"), list):
            cfg["enabled_types"] = list(DEFAULT_ENABLED)
        return cfg

    def application_cfg(self, guild_id: int) -> dict:
        key = str(guild_id)
        cfg = self.application_db.get(key)
        if not isinstance(cfg, dict):
            cfg = self.application_db[key] = default_application_config()
        for name, value in default_application_config().items():
            cfg.setdefault(name, copy.deepcopy(value))
        if not isinstance(cfg.get("questions"), list):
            cfg["questions"] = []
        cfg["questions"] = [trunc(question, 45) for question in cfg["questions"] if str(question).strip()][:MAX_APPLICATION_QUESTIONS]
        if cfg.get("button_style") not in BUTTON_STYLES:
            cfg["button_style"] = "primary"
        if parse_color(cfg.get("embed_color", "5865F2")) is None:
            cfg["embed_color"] = "5865F2"
        return cfg

    # ---------------- owner and staff permissions ----------------

    def is_staff(self, member: discord.Member, cfg: dict) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
            return True
        role_id = cfg.get("staff_role_id")
        return bool(role_id and any(role.id == int(role_id) for role in member.roles))

    # ---------------- application setup helpers ----------------

    def application_setup_embed(self, guild: Optional[discord.Guild], cfg: dict) -> discord.Embed:
        panel_channel = guild.get_channel(int(cfg["panel_channel_id"])) if guild and cfg.get("panel_channel_id") else None
        log_channel = guild.get_channel(int(cfg["log_channel_id"])) if guild and cfg.get("log_channel_id") else None
        questions = cfg.get("questions", [])
        embed = discord.Embed(
            title="Staff Application Setup",
            description=(
                "Configure the application panel using the controls below. "
                "This setup is private and only the server owner can use it.\n\n"
                "The panel is posted without an extra public confirmation message."
            ),
            color=color_from_config(cfg),
        )
        embed.add_field(name="Panel Channel", value=panel_channel.mention if panel_channel else "Not selected", inline=True)
        embed.add_field(name="Application Log", value=log_channel.mention if log_channel else "Not selected", inline=True)
        embed.add_field(name="Button Style", value=str(cfg.get("button_style", "primary")).title(), inline=True)
        embed.add_field(name="Panel Title", value=trunc(cfg.get("panel_title", "Staff Applications"), 256), inline=False)
        embed.add_field(name="Button Name", value=trunc(cfg.get("button_label", "Apply Now"), 80), inline=True)
        embed.add_field(name="Button Emoji", value=cfg.get("button_emoji") or "None", inline=True)
        embed.add_field(name="Embed Color", value=f"#{cfg.get('embed_color', '5865F2')}", inline=True)
        if questions:
            questions_text = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))
        else:
            questions_text = "No questions configured. Add at least one question before posting."
        embed.add_field(name=f"Form Questions ({len(questions)}/{MAX_APPLICATION_QUESTIONS})", value=trunc(questions_text, 1000), inline=False)
        embed.set_footer(text="Changes are saved automatically.")
        return embed

    def register_application_view(self, guild_id: int, replace: bool = False) -> StaffApplicationPanelView:
        current = self.application_views.get(guild_id)
        if current is not None and not replace:
            return current
        if current is not None:
            try:
                self.bot.remove_view(current)
            except Exception:
                pass
        view = StaffApplicationPanelView(self, guild_id)
        self.bot.add_view(view)
        self.application_views[guild_id] = view
        return view

    # ---------------- ticket helpers ----------------

    def ticket_record(self, guild: Optional[discord.Guild], channel) -> Optional[dict]:
        if guild is None or channel is None:
            return None
        return self.ticket_cfg(guild.id)["tickets"].get(str(channel.id))

    def open_ticket_for(self, guild: discord.Guild, cfg: dict, user_id: int) -> Optional[discord.TextChannel]:
        for channel_id, record in list(cfg["tickets"].items()):
            if record.get("owner_id") != user_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                return channel
            cfg["tickets"].pop(channel_id, None)
        return None

    def ticket_log_channel(self, guild: discord.Guild, cfg: dict) -> Optional[discord.TextChannel]:
        channel_id = cfg.get("log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def build_transcript(self, channel: discord.TextChannel) -> str:
        lines = [
            f"Transcript of #{channel.name}",
            f"Generated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
        ]
        try:
            async for message in channel.history(limit=TRANSCRIPT_LIMIT, oldest_first=True):
                when = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                body = message.content or ""
                if message.embeds:
                    body += " [embed]"
                for attachment in message.attachments:
                    body += f" [attachment: {attachment.url}]"
                lines.append(f"[{when}] {message.author} ({message.author.id}): {body}")
        except discord.HTTPException as error:
            lines.append(f"[Transcript incomplete: {error}]")
        return "\n".join(lines)

    # ---------------- ticket lifecycle ----------------

    async def open_ticket(self, interaction: discord.Interaction, type_key: str) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.followup.send("This panel can only be used in a server.", ephemeral=True)
            return

        cfg = self.ticket_cfg(guild.id)
        ttype = ticket_catalog(cfg).get(type_key)
        if ttype is None or type_key not in cfg["enabled_types"]:
            await interaction.followup.send("This ticket type is no longer available.", ephemeral=True)
            return

        existing = self.open_ticket_for(guild, cfg, member.id)
        if existing is not None:
            await interaction.followup.send(f"You already have an open ticket: {existing.mention}", ephemeral=True)
            return

        creating_key = (guild.id, member.id)
        if creating_key in self.creating:
            await interaction.followup.send("Your ticket is being created. Please wait a moment.", ephemeral=True)
            return

        self.creating.add(creating_key)
        channel = None
        try:
            cfg["counter"] = int(cfg.get("counter", 0)) + 1
            number = cfg["counter"]
            await self.save_tickets()

            category = guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else None
            if not isinstance(category, discord.CategoryChannel):
                category = None

            staff_role = guild.get_role(int(cfg["staff_role_id"])) if cfg.get("staff_role_id") else None
            bot_member = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)
            if bot_member is None:
                raise RuntimeError("The bot member could not be resolved in this server.")

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                ),
                bot_member: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_channels=True,
                    manage_messages=True,
                ),
            }
            if staff_role is not None:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True,
                    manage_messages=True,
                )

            channel = await guild.create_text_channel(
                name=f"ticket-{number:04d}-{slug(member.name)}",
                category=category,
                overwrites=overwrites,
                topic=f"Ticket #{number:04d} | owner {member.id}",
                reason=f"Ticket opened by {member}",
            )

            cfg["tickets"][str(channel.id)] = {
                "owner_id": member.id,
                "type": type_key,
                "number": number,
                "claimed_by": None,
                "created_at": discord.utils.utcnow().isoformat(),
            }
            await self.save_tickets()

            embed = discord.Embed(
                title=f"{ttype.get('emoji', '🎫')} {ttype['label']} • Ticket #{number:04d}",
                description=(
                    f"Hello {member.mention}, thank you for opening a ticket.\n"
                    "Please describe your request in detail. A staff member will reply as soon as possible."
                ),
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Opened By", value=member.mention, inline=True)
            embed.add_field(name="Type", value=ttype["label"], inline=True)
            embed.add_field(name="Status", value="🟢 Open", inline=True)
            embed.set_footer(text="Use the buttons below to claim or close this ticket.")

            mentions = member.mention
            if staff_role is not None:
                mentions += f" {staff_role.mention}"
            await channel.send(
                content=mentions,
                embed=embed,
                view=TicketControlView(self),
                allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
            )

            log_channel = self.ticket_log_channel(guild, cfg)
            if log_channel is not None:
                try:
                    await log_channel.send(
                        f"Ticket {channel.mention} opened by {member.mention} ({ttype['label']}).",
                        allowed_mentions=NO_MENTIONS,
                    )
                except discord.HTTPException:
                    pass

            await interaction.followup.send(f"Your ticket has been created: {channel.mention}", ephemeral=True)

        except discord.Forbidden:
            if channel is not None:
                try:
                    await channel.delete(reason="Ticket setup failed due to missing permissions")
                except discord.HTTPException:
                    pass
            await interaction.followup.send(
                "I do not have permission to create ticket channels. Give me Manage Channels and the required channel permissions.",
                ephemeral=True,
            )
        except (discord.HTTPException, RuntimeError) as error:
            print(f"[TICKETS] Could not create ticket: {error}")
            await interaction.followup.send(
                "Something went wrong while creating your ticket. Please try again.", ephemeral=True
            )
        finally:
            self.creating.discard(creating_key)

    def claim_ticket(self, guild: discord.Guild, channel, member: discord.Member) -> Tuple[bool, str]:
        cfg = self.ticket_cfg(guild.id)
        record = cfg["tickets"].get(str(channel.id))
        if record is None:
            return False, "This channel is not an active ticket."
        if not self.is_staff(member, cfg):
            return False, "Only staff can claim tickets."
        claimed = record.get("claimed_by")
        if claimed == member.id:
            return False, "You already claimed this ticket."
        if claimed:
            return False, f"This ticket is already claimed by <@{claimed}>."
        record["claimed_by"] = member.id
        return True, f"🙋 {member.mention} claimed this ticket."

    async def handle_claim_button(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This action is only available in a server.", ephemeral=True)
            return
        ok, message = self.claim_ticket(interaction.guild, interaction.channel, interaction.user)
        if not ok:
            await interaction.response.send_message(message, ephemeral=True)
            return
        await self.save_tickets()
        await interaction.response.send_message(message, allowed_mentions=NO_MENTIONS)

    async def handle_close_button(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("This action is only available in a server.", ephemeral=True)
            return
        cfg = self.ticket_cfg(guild.id)
        record = self.ticket_record(guild, interaction.channel)
        if record is None:
            await interaction.response.send_message("This channel is not an active ticket.", ephemeral=True)
            return
        if member.id != record.get("owner_id") and not self.is_staff(member, cfg):
            await interaction.response.send_message("Only the ticket owner or staff can close this ticket.", ephemeral=True)
            return
        view = ConfirmCloseView(self, interaction.channel, member.id, "Closed with the close button")
        await interaction.response.send_message(
            "Are you sure you want to close this ticket? A transcript will be saved.",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()

    async def close_ticket(self, channel: discord.TextChannel, closer, reason: str) -> None:
        guild = channel.guild
        if channel.id in self.closing:
            return
        self.closing.add(channel.id)
        try:
            cfg = self.ticket_cfg(guild.id)
            record = cfg["tickets"].pop(str(channel.id), None)
            if record is None:
                return
            await self.save_tickets()

            transcript = await self.build_transcript(channel)
            log_channel = self.ticket_log_channel(guild, cfg)
            if log_channel is not None:
                owner = guild.get_member(record.get("owner_id", 0))
                embed = discord.Embed(
                    title="🔒 Ticket Closed",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.add_field(name="Ticket", value=f"#{channel.name}", inline=True)
                embed.add_field(
                    name="Opened By",
                    value=owner.mention if owner else f"<@{record.get('owner_id')}>",
                    inline=True,
                )
                embed.add_field(name="Type", value=ticket_type_label(cfg, record.get("type", "")), inline=True)
                embed.add_field(name="Closed By", value=getattr(closer, "mention", str(closer)), inline=True)
                embed.add_field(name="Reason", value=trunc(reason, 1000), inline=False)
                file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{channel.name}.txt")
                try:
                    await log_channel.send(embed=embed, file=file, allowed_mentions=NO_MENTIONS)
                except discord.HTTPException as error:
                    print(f"[TICKETS] Could not send transcript: {error}")

            try:
                await channel.send(
                    f"🔒 Ticket closed by {getattr(closer, 'mention', str(closer))}. "
                    f"This channel will be deleted in {CLOSE_DELAY} seconds.",
                    allowed_mentions=NO_MENTIONS,
                )
                await asyncio.sleep(CLOSE_DELAY)
                await channel.delete(reason=f"Ticket closed by {closer}")
            except discord.HTTPException as error:
                print(f"[TICKETS] Could not delete ticket channel: {error}")
        finally:
            self.closing.discard(channel.id)

    # ---------------- listeners and errors ----------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        cfg = self.ticket_cfg(channel.guild.id)
        if cfg["tickets"].pop(str(channel.id), None) is not None:
            await self.save_tickets()

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Unauthorized users must not receive a reply from bot7 commands.
        if isinstance(error, commands.CheckFailure):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            message = f"Missing argument: `{error.param.name}`. Use `!ticket help`."
        elif isinstance(error, commands.BadArgument):
            message = "I could not understand that input, or I could not find the member, role, or channel."
        else:
            original = getattr(error, "original", error)
            print(f"[TICKETS COMMAND] {type(original).__name__}: {original}")
            message = "An unexpected error happened while running that command."
        try:
            await ctx.send(message, delete_after=8)
        except discord.HTTPException:
            pass

    # ========================================================
    # Application slash command
    # ========================================================

    @app_commands.command(
        name="staff-application",
        description="Open the private staff application setup panel.",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def staff_application(self, interaction: discord.Interaction):
        # Runtime check is deliberately stricter than Discord's default permissions.
        if not is_server_owner(interaction.guild, interaction.user):
            # A slash interaction must be acknowledged. Defer ephemerally and delete
            # the response so the bot stays silent to everyone except Discord itself.
            await interaction.response.defer(ephemeral=True, thinking=False)
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            return

        cfg = self.application_cfg(interaction.guild.id)
        view = ApplicationSetupView(self, interaction.guild.id, interaction.user.id)
        await interaction.response.send_message(
            embed=self.application_setup_embed(interaction.guild, cfg),
            view=view,
            ephemeral=True,
        )

    # ========================================================
    # Prefix ticket commands (all inherited owner-only check)
    # ========================================================

    def ticket_help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎫 Ticket System",
            description="Members open tickets from the panel menu. Staff manage tickets with the buttons inside each ticket.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Server Owner",
            value=(
                "`!ticket setup` choose ticket types\n"
                "`!ticket panel [#channel]` post the ticket panel\n"
                "`!ticket staff @role` set the staff role\n"
                "`!ticket category <category>` set where tickets are created\n"
                "`!ticket logs [#channel]` set the transcript channel\n"
                "`!ticket title <text>` set the panel title\n"
                "`!ticket description <text>` set the panel description\n"
                "`!ticket typeadd Label | description | emoji` add a custom type\n"
                "`!ticket typeremove <label or key>` remove a custom type\n"
                "`!ticket list` list open tickets\n"
                "`!ticket add @member` add a member to the current ticket\n"
                "`!ticket remove @member` remove a member from the current ticket\n"
                "`!ticket close [reason]` close the current ticket"
            ),
            inline=False,
        )
        embed.add_field(
            name="Members",
            value="Choose a type from the ticket panel. Use the Close button inside your ticket to close it.",
            inline=False,
        )
        embed.set_footer(text="Only the server owner can use bot7 commands.")
        return embed

    def ticket_status_embed(self, guild: discord.Guild, cfg: dict) -> discord.Embed:
        staff = guild.get_role(int(cfg["staff_role_id"])) if cfg.get("staff_role_id") else None
        category = guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else None
        log_channel = self.ticket_log_channel(guild, cfg)
        embed = discord.Embed(title="🎫 Ticket System Setup", color=discord.Color.blurple())
        embed.add_field(name="Staff Role", value=staff.mention if staff else "Not set (staff = Manage Channels)", inline=False)
        embed.add_field(name="Ticket Category", value=category.name if isinstance(category, discord.CategoryChannel) else "Not set (channels are created at the top level)", inline=False)
        embed.add_field(name="Transcript Channel", value=log_channel.mention if log_channel else "Not set", inline=False)
        embed.add_field(name="Panel Title", value=trunc(cfg["panel_title"], 200), inline=False)
        embed.add_field(name="Ticket Types", value=f"{len(enabled_ticket_types(cfg))} enabled of {len(ticket_catalog(cfg))}", inline=True)
        embed.add_field(name="Open Tickets", value=str(len(cfg["tickets"])), inline=True)
        embed.set_footer(text="Select the ticket types to show in the next panel.")
        return embed

    @commands.group(name="ticket", invoke_without_command=True, case_insensitive=True)
    @server_owner_only()
    async def ticket(self, ctx: commands.Context):
        await ctx.send(embed=self.ticket_help_embed())

    @ticket.command(name="help")
    async def ticket_help(self, ctx: commands.Context):
        await ctx.send(embed=self.ticket_help_embed())

    @ticket.command(name="setup")
    async def ticket_setup(self, ctx: commands.Context):
        cfg = self.ticket_cfg(ctx.guild.id)
        view = TypeSelectView(self, ctx.guild.id, ctx.author.id)
        view.message = await ctx.send(embed=self.ticket_status_embed(ctx.guild, cfg), view=view)

    @ticket.command(name="panel")
    async def ticket_panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        cfg = self.ticket_cfg(ctx.guild.id)
        types = enabled_ticket_types(cfg)
        if not types:
            await ctx.send("No ticket types are enabled. Run `!ticket setup` first.", delete_after=8)
            return

        options = [
            discord.SelectOption(
                label=trunc(item["label"], 100),
                value=item["key"],
                description=trunc(item.get("description", ""), 100) or None,
                emoji=emoji_of(item.get("emoji")),
            )
            for item in types
        ][:25]
        embed = discord.Embed(
            title=trunc(cfg["panel_title"], 250),
            description=trunc(cfg["panel_text"], 4000),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Team Fime • Tickets")
        await channel.send(embed=embed, view=TicketPanelView(self, options), allowed_mentions=NO_MENTIONS)
        await ctx.send(f"Ticket panel posted in {channel.mention}.", delete_after=8)

    @ticket.command(name="staff")
    async def ticket_staff(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        cfg = self.ticket_cfg(ctx.guild.id)
        cfg["staff_role_id"] = role.id if role else None
        await self.save_tickets()
        message = f"Staff role set to {role.mention}." if role else "Staff role cleared."
        await ctx.send(message, allowed_mentions=NO_MENTIONS, delete_after=8)

    @ticket.command(name="category")
    async def ticket_category(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        cfg = self.ticket_cfg(ctx.guild.id)
        cfg["category_id"] = category.id if category else None
        await self.save_tickets()
        message = f"Tickets will be created under **{category.name}**." if category else "Ticket category cleared."
        await ctx.send(message, delete_after=8)

    @ticket.command(name="logs")
    async def ticket_logs(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        cfg = self.ticket_cfg(ctx.guild.id)
        cfg["log_channel_id"] = channel.id if channel else None
        await self.save_tickets()
        message = f"Ticket transcripts will be sent to {channel.mention}." if channel else "Ticket transcript logging disabled."
        await ctx.send(message, allowed_mentions=NO_MENTIONS, delete_after=8)

    @ticket.command(name="title")
    async def ticket_title(self, ctx: commands.Context, *, text: str):
        cfg = self.ticket_cfg(ctx.guild.id)
        cfg["panel_title"] = trunc(text, 250)
        await self.save_tickets()
        await ctx.send("Ticket panel title updated. Post a new panel to apply it.", delete_after=8)

    @ticket.command(name="description")
    async def ticket_description(self, ctx: commands.Context, *, text: str):
        cfg = self.ticket_cfg(ctx.guild.id)
        cfg["panel_text"] = trunc(text, 4000)
        await self.save_tickets()
        await ctx.send("Ticket panel description updated. Post a new panel to apply it.", delete_after=8)

    @ticket.command(name="typeadd")
    async def ticket_typeadd(self, ctx: commands.Context, *, data: str):
        parts = [part.strip() for part in data.split("|")]
        if not parts or not parts[0]:
            await ctx.send("Usage: `!ticket typeadd Label | description | emoji`", delete_after=8)
            return
        label = trunc(parts[0], 80)
        description = trunc(parts[1], 100) if len(parts) > 1 else ""
        emoji = parts[2] if len(parts) > 2 and parts[2] else "🎫"
        cfg = self.ticket_cfg(ctx.guild.id)
        if len(cfg["custom_types"]) >= MAX_CUSTOM_TYPES:
            await ctx.send(f"You can add up to {MAX_CUSTOM_TYPES} custom ticket types.", delete_after=8)
            return
        if any(item["label"].casefold() == label.casefold() for item in ticket_catalog(cfg).values()):
            await ctx.send("A ticket type with this name already exists.", delete_after=8)
            return
        key = "custom-" + uuid.uuid4().hex[:8]
        cfg["custom_types"].append({"key": key, "label": label, "description": description, "emoji": emoji})
        cfg["enabled_types"].append(key)
        await self.save_tickets()
        await ctx.send(f"Added ticket type **{label}** and enabled it. Post a new panel to show it.", delete_after=8)

    @ticket.command(name="typeremove")
    async def ticket_typeremove(self, ctx: commands.Context, *, name: str):
        cfg = self.ticket_cfg(ctx.guild.id)
        wanted = name.strip().casefold()
        match = next(
            (
                item for item in cfg["custom_types"]
                if item["key"].casefold() == wanted or item["label"].casefold() == wanted
            ),
            None,
        )
        if match is None:
            await ctx.send("No custom ticket type matches that name. Default types can only be disabled in `!ticket setup`.", delete_after=8)
            return
        cfg["custom_types"] = [item for item in cfg["custom_types"] if item["key"] != match["key"]]
        cfg["enabled_types"] = [key for key in cfg["enabled_types"] if key != match["key"]]
        await self.save_tickets()
        await ctx.send(f"Removed custom ticket type **{match['label']}**.", delete_after=8)

    @ticket.command(name="list")
    async def ticket_list(self, ctx: commands.Context):
        cfg = self.ticket_cfg(ctx.guild.id)
        lines = []
        for channel_id, record in cfg["tickets"].items():
            channel = ctx.guild.get_channel(int(channel_id))
            if channel is None:
                continue
            claimed = f"<@{record['claimed_by']}>" if record.get("claimed_by") else "Unclaimed"
            lines.append(
                f"{channel.mention} • <@{record.get('owner_id')}> • "
                f"{ticket_type_label(cfg, record.get('type', ''))} • {claimed}"
            )
        if not lines:
            await ctx.send("There are no open tickets right now.", delete_after=8)
            return
        embed = discord.Embed(
            title=f"🎫 Open Tickets ({len(lines)})",
            description=trunc("\n".join(lines), 4000),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @ticket.command(name="claim")
    async def ticket_claim(self, ctx: commands.Context):
        ok, message = self.claim_ticket(ctx.guild, ctx.channel, ctx.author)
        if ok:
            await self.save_tickets()
        await ctx.send(message, allowed_mentions=NO_MENTIONS, delete_after=8)

    @ticket.command(name="add")
    async def ticket_add(self, ctx: commands.Context, member: discord.Member):
        if self.ticket_record(ctx.guild, ctx.channel) is None:
            await ctx.send("This is not an active ticket channel.", delete_after=8)
            return
        await ctx.channel.set_permissions(
            member,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            reason=f"Added to ticket by {ctx.author}",
        )
        await ctx.send(f"{member.mention} was added to this ticket.", allowed_mentions=NO_MENTIONS, delete_after=8)

    @ticket.command(name="remove")
    async def ticket_remove(self, ctx: commands.Context, member: discord.Member):
        record = self.ticket_record(ctx.guild, ctx.channel)
        if record is None:
            await ctx.send("This is not an active ticket channel.", delete_after=8)
            return
        if member.id == record.get("owner_id"):
            await ctx.send("You cannot remove the ticket owner.", delete_after=8)
            return
        await ctx.channel.set_permissions(
            member,
            overwrite=None,
            reason=f"Removed from ticket by {ctx.author}",
        )
        await ctx.send(f"{member.mention} was removed from this ticket.", allowed_mentions=NO_MENTIONS, delete_after=8)

    @ticket.command(name="close")
    async def ticket_close(self, ctx: commands.Context, *, reason: str = "No reason given"):
        cfg = self.ticket_cfg(ctx.guild.id)
        record = self.ticket_record(ctx.guild, ctx.channel)
        if record is None:
            await ctx.send("This is not an active ticket channel.", delete_after=8)
            return
        if ctx.author.id != record.get("owner_id") and not self.is_staff(ctx.author, cfg):
            await ctx.send("Only the ticket owner or staff can close this ticket.", delete_after=8)
            return
        view = ConfirmCloseView(self, ctx.channel, ctx.author.id, trunc(reason, 300))
        view.message = await ctx.send(
            "Are you sure you want to close this ticket? A transcript will be saved.",
            view=view,
        )


# ============================================================
# Extension load point
# ============================================================


async def setup(bot: commands.Bot) -> None:
    """Called by discord.py when loading the bot7 extension."""
    cog = Tickets(bot)
    taken = set(bot.all_commands)
    kept = []
    skipped = []

    for command in cog.__cog_commands__:
        if command.parent is not None:
            kept.append(command)
            continue
        if command.name in taken:
            skipped.append(command.name)
            continue
        command.aliases = [alias for alias in command.aliases if alias not in taken]
        taken.add(command.name)
        taken.update(command.aliases)
        kept.append(command)

    cog.__cog_commands__ = tuple(kept)
    await bot.add_cog(cog)

    if skipped:
        print(f"[BOT7] Skipped conflicting prefix commands: {', '.join(skipped)}")
    print("[BOT7] Ticket system and owner-only staff application setup loaded.")