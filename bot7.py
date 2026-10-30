# -*- coding: utf-8 -*-
"""
bot7.py - Ticket system (Discord Cog, English).

Load from bot.py with:  await bot.load_extension("bot7")

Persistent: panels and ticket controls keep working after the bot restarts,
because views are registered on load and all ticket data is saved to disk.
"""

import asyncio
import io
import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord.ext import commands

DATA_FILE = Path(__file__).resolve().parent / "bot7_tickets.json"
COG_NAME = "Tickets"
NO_MENTIONS = discord.AllowedMentions.none()

CLOSE_DELAY = 8                 # seconds before a closed ticket channel is deleted
TRANSCRIPT_LIMIT = 1000         # max messages included in a transcript
MAX_CUSTOM_TYPES = 15
MAX_ACTIVE_PER_USER = 1
SETUP_TIMEOUT = 120
CONFIRM_TIMEOUT = 60
DEFAULT_PANEL_TITLE = "Support Center"
DEFAULT_PANEL_TEXT = (
    "Choose the option that best matches your request from the menu below. "
    "A private ticket will be opened for you."
)

DEFAULT_TYPES: Dict[str, Dict[str, str]] = {
    "support": {"label": "General Support", "emoji": "🛠️", "description": "Questions, help, or account issues."},
    "report": {"label": "Report a Member", "emoji": "🚨", "description": "Report rule breaking or misconduct."},
    "partnership": {"label": "Partnership", "emoji": "🤝", "description": "Partnership and collaboration requests."},
    "purchase": {"label": "Purchase", "emoji": "🛒", "description": "Orders, payments, and product questions."},
    "appeal": {"label": "Appeal", "emoji": "⚖️", "description": "Appeal a warning, mute, or ban."},
    "bug": {"label": "Bug Report", "emoji": "🐞", "description": "Report a bug or a broken feature."},
    "other": {"label": "Other", "emoji": "📩", "description": "Anything that does not fit the options above."},
}
DEFAULT_ENABLED = ["support", "report", "partnership", "purchase", "appeal", "other"]


# ============================================================
# Helpers
# ============================================================

def default_config() -> dict:
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


def trunc(text, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def catalog(cfg: dict) -> Dict[str, dict]:
    """All ticket types: defaults plus custom ones, keyed by their key."""
    items = {key: {"key": key, **value} for key, value in DEFAULT_TYPES.items()}
    for custom in cfg.get("custom_types", []):
        items[custom["key"]] = custom
    return items


def enabled_types(cfg: dict) -> List[dict]:
    items = catalog(cfg)
    return [items[key] for key in cfg.get("enabled_types", []) if key in items]


def type_label(cfg: dict, key: str) -> str:
    item = catalog(cfg).get(key)
    return item["label"] if item else "Unknown"


def emoji_of(value) -> Optional[discord.PartialEmoji]:
    if not value:
        return None
    try:
        return discord.PartialEmoji.from_str(str(value))
    except Exception:
        return None


def slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:20]
    return cleaned or "member"


def _write_file(payload: str) -> None:
    temp = DATA_FILE.with_suffix(".tmp")
    try:
        temp.write_text(payload, encoding="utf-8")
        temp.replace(DATA_FILE)
    except OSError as error:
        print(f"[TICKETS] Could not save data: {error}")


def admin_only():
    """Owner, administrators, or members with Manage Server."""
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("This command only works inside a server.")
        perms = ctx.author.guild_permissions
        if perms.administrator or perms.manage_guild:
            return True
        raise commands.CheckFailure("You need the Manage Server permission for this command.")
    return commands.check(predicate)


def staff_only():
    """Staff: the staff role, or members with Manage Channels or Administrator."""
    async def predicate(ctx: commands.Context) -> bool:
        cog = ctx.bot.get_cog(COG_NAME)
        if cog is None or ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("This command only works inside a server.")
        if cog.is_staff(ctx.author, cog.cfg(ctx.guild.id)):
            return True
        raise commands.CheckFailure("Only staff can use this command.")
    return commands.check(predicate)


# ============================================================
# Views
# ============================================================

class ConfirmCloseView(discord.ui.View):
    """Confirmation before closing a ticket. Works for buttons and for the !ticket close command."""

    def __init__(self, cog: "Tickets", channel: discord.TextChannel, requester_id: int, reason: str):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.cog = cog
        self.channel = channel
        self.requester_id = requester_id
        self.reason = reason
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Confirm close", style=discord.ButtonStyle.danger, emoji="✅")
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
            await self.message.edit(content="⏰ Confirmation time has ended. The ticket stays open.", view=None)
        except discord.HTTPException:
            pass


class TicketControlView(discord.ui.View):
    """Buttons inside each ticket channel. Persistent: custom IDs are registered on load."""

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
    """The public panel menu. Persistent: the select uses a fixed custom ID."""

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
            return
        values = interaction.data.get("values") or []
        if not values:
            return
        await self.cog.open_ticket(interaction, values[0])


class TypeSelectView(discord.ui.View):
    """Admin menu: choose which ticket types appear in the panel."""

    def __init__(self, cog: "Tickets", guild_id: int, requester_id: int):
        super().__init__(timeout=SETUP_TIMEOUT)
        self.cog = cog
        self.guild_id = guild_id
        self.requester_id = requester_id
        self.message: Optional[discord.Message] = None

        cfg = cog.cfg(guild_id)
        enabled = set(cfg["enabled_types"])
        options = []
        for key, item in catalog(cfg).items():
            options.append(discord.SelectOption(
                label=trunc(item["label"], 100),
                value=key,
                description=trunc(item.get("description", ""), 100) or None,
                emoji=emoji_of(item.get("emoji")),
                default=key in enabled,
            ))
        options = options[:25]

        self.select = discord.ui.Select(
            placeholder="Choose the ticket types shown in the panel",
            min_values=0,
            max_values=len(options),
            options=options,
        )
        self.select.callback = self._saved
        self.add_item(self.select)

    async def _saved(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the person who opened this setup can change it.", ephemeral=True
            )
            return
        cfg = self.cog.cfg(self.guild_id)
        valid = set(catalog(cfg))
        cfg["enabled_types"] = [value for value in self.select.values if value in valid]
        await self.cog.save()
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Saved. **{len(cfg['enabled_types'])}** ticket type(s) will appear in new panels.",
            view=None,
        )

    async def on_timeout(self):
        if self.message is None:
            return
        try:
            await self.message.edit(
                content="⏰ Selection time has ended. Run `!ticket setup` again to continue.",
                view=None,
            )
        except discord.HTTPException:
            pass


# ============================================================
# Cog
# ============================================================

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: dict = self._load()
        self.lock = asyncio.Lock()
        self.tasks: set = set()
        self.creating: set = set()

    # ---------------- lifecycle ----------------

    async def cog_load(self) -> None:
        # Register persistent views so buttons keep working after restarts.
        self.bot.add_view(TicketPanelView(self, [
            discord.SelectOption(label="Unavailable", value="none"),
        ]))
        self.bot.add_view(TicketControlView(self))

    def spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    # ---------------- data ----------------

    @staticmethod
    def _load() -> dict:
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    async def save(self) -> None:
        payload = json.dumps(self.db, ensure_ascii=False, indent=2)
        async with self.lock:
            await asyncio.to_thread(_write_file, payload)

    def cfg(self, guild_id: int) -> dict:
        key = str(guild_id)
        cfg = self.db.get(key)
        if not isinstance(cfg, dict):
            cfg = self.db[key] = default_config()
        for name, value in default_config().items():
            cfg.setdefault(name, value)
        return cfg

    def ticket_record(self, guild: discord.Guild, channel) -> Optional[dict]:
        if guild is None or channel is None:
            return None
        return self.cfg(guild.id)["tickets"].get(str(channel.id))

    def open_ticket_for(self, guild: discord.Guild, cfg: dict, user_id: int) -> Optional[discord.TextChannel]:
        for channel_id, record in list(cfg["tickets"].items()):
            if record.get("owner_id") != user_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if channel is not None:
                return channel
            cfg["tickets"].pop(channel_id, None)
        return None

    # ---------------- permissions ----------------

    def is_staff(self, member: discord.Member, cfg: dict) -> bool:
        if member.guild_permissions.administrator or member.guild_permissions.manage_channels:
            return True
        role_id = cfg.get("staff_role_id")
        return bool(role_id and any(role.id == int(role_id) for role in member.roles))

    # ---------------- helpers ----------------

    def log_channel(self, guild: discord.Guild, cfg: dict) -> Optional[discord.TextChannel]:
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
        guild, member = interaction.guild, interaction.user
        cfg = self.cfg(guild.id)

        ttype = catalog(cfg).get(type_key)
        if ttype is None or type_key not in cfg["enabled_types"]:
            await interaction.followup.send("❌ This ticket type is no longer available.", ephemeral=True)
            return

        existing = self.open_ticket_for(guild, cfg, member.id)
        if existing is not None:
            await interaction.followup.send(
                f"You already have an open ticket: {existing.mention}", ephemeral=True
            )
            return

        if member.id in self.creating:
            await interaction.followup.send("⏳ Your ticket is being created. Please wait a moment.", ephemeral=True)
            return

        self.creating.add(member.id)
        try:
            cfg["counter"] = int(cfg.get("counter", 0)) + 1
            number = cfg["counter"]
            await self.save()

            category = guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else None
            if not isinstance(category, discord.CategoryChannel):
                category = None

            staff_role = guild.get_role(int(cfg["staff_role_id"])) if cfg.get("staff_role_id") else None
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                member: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    attach_files=True, embed_links=True,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    manage_channels=True, manage_messages=True,
                ),
            }
            if staff_role is not None:
                overwrites[staff_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True,
                    attach_files=True, embed_links=True, manage_messages=True,
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
            await self.save()

            embed = discord.Embed(
                title=f"{ttype.get('emoji', '🎫')} {ttype['label']} • Ticket #{number:04d}",
                description=(
                    f"Hello {member.mention}, thank you for opening a ticket.\n"
                    "Please describe your request in detail. A staff member will reply as soon as possible."
                ),
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Opened by", value=member.mention, inline=True)
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

            log_channel = self.log_channel(guild, cfg)
            if log_channel is not None:
                try:
                    await log_channel.send(
                        f"📥 Ticket {channel.mention} opened by {member.mention} ({ttype['label']}).",
                        allowed_mentions=NO_MENTIONS,
                    )
                except discord.HTTPException:
                    pass

            await interaction.followup.send(f"✅ Your ticket has been created: {channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to create ticket channels. Give me Manage Channels.", ephemeral=True
            )
        except discord.HTTPException as error:
            print(f"[TICKETS] Could not create ticket: {error}")
            await interaction.followup.send("❌ Something went wrong while creating your ticket. Try again.", ephemeral=True)
        finally:
            self.creating.discard(member.id)

    def claim_ticket(self, guild: discord.Guild, channel, member: discord.Member) -> tuple:
        """Returns (success, message). Changes the record in memory; caller saves."""
        cfg = self.cfg(guild.id)
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
        ok, text = self.claim_ticket(interaction.guild, interaction.channel, interaction.user)
        if not ok:
            await interaction.response.send_message(text, ephemeral=True)
            return
        await self.save()
        await interaction.response.send_message(text, allowed_mentions=NO_MENTIONS)

    async def handle_close_button(self, interaction: discord.Interaction) -> None:
        guild, member = interaction.guild, interaction.user
        cfg = self.cfg(guild.id)
        record = self.ticket_record(guild, interaction.channel)
        if record is None:
            await interaction.response.send_message("This channel is not an active ticket.", ephemeral=True)
            return
        if member.id != record.get("owner_id") and not self.is_staff(member, cfg):
            await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.", ephemeral=True
            )
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
        cfg = self.cfg(guild.id)
        record = cfg["tickets"].pop(str(channel.id), None)
        if record is None:
            return
        await self.save()

        transcript = await self.build_transcript(channel)
        log_channel = self.log_channel(guild, cfg)
        if log_channel is not None:
            owner = guild.get_member(record.get("owner_id", 0))
            embed = discord.Embed(title="🔒 Ticket Closed", color=discord.Color.red(), timestamp=discord.utils.utcnow())
            embed.add_field(name="Ticket", value=f"#{channel.name}", inline=True)
            embed.add_field(name="Opened by", value=owner.mention if owner else f"<@{record.get('owner_id')}>", inline=True)
            embed.add_field(name="Type", value=type_label(cfg, record.get("type", "")), inline=True)
            embed.add_field(name="Closed by", value=closer.mention, inline=True)
            embed.add_field(name="Reason", value=trunc(reason, 1000), inline=False)
            file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"{channel.name}.txt")
            try:
                await log_channel.send(embed=embed, file=file, allowed_mentions=NO_MENTIONS)
            except discord.HTTPException as error:
                print(f"[TICKETS] Could not send transcript: {error}")

        try:
            await channel.send(
                f"🔒 Ticket closed by {closer.mention}. This channel will be deleted in {CLOSE_DELAY} seconds.",
                allowed_mentions=NO_MENTIONS,
            )
            await asyncio.sleep(CLOSE_DELAY)
            await channel.delete(reason=f"Ticket closed by {closer}")
        except discord.HTTPException as error:
            print(f"[TICKETS] Could not delete ticket channel: {error}")

    # ---------------- listeners ----------------

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        cfg = self.cfg(channel.guild.id)
        if cfg["tickets"].pop(str(channel.id), None) is not None:
            await self.save()

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            text = str(error) or "You don't have permission for this command."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Missing argument: `{error.param.name}`. Use `!ticket help`."
        elif isinstance(error, commands.BadArgument):
            text = "I couldn't understand that input, or I couldn't find the member, role, or channel."
        else:
            original = getattr(error, "original", error)
            print(f"[TICKETS COMMAND] {type(original).__name__}: {original}")
            text = "An unexpected error happened while running that command."
        try:
            await ctx.send(text, delete_after=8)
        except discord.HTTPException:
            pass

    # ============================================================
    # Commands: !ticket
    # ============================================================

    def help_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎫 Ticket System",
            description="Members open tickets from the panel menu. Staff manage them with these commands.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Administrators (Manage Server)",
            value=(
                "`!ticket setup` choose ticket types and view settings\n"
                "`!ticket panel [#channel]` post the ticket panel\n"
                "`!ticket staff @role` set the staff role\n"
                "`!ticket category <category>` set where tickets are created\n"
                "`!ticket logs [#channel]` set the transcript channel\n"
                "`!ticket title <text>` set the panel title\n"
                "`!ticket description <text>` set the panel text\n"
                "`!ticket typeadd Label | description | emoji` add a custom type\n"
                "`!ticket typeremove <label or key>` remove a custom type"
            ),
            inline=False,
        )
        embed.add_field(
            name="Staff",
            value=(
                "`!ticket list` show open tickets\n"
                "`!ticket claim` claim the current ticket\n"
                "`!ticket add @member` add a member to this ticket\n"
                "`!ticket remove @member` remove a member from this ticket\n"
                "`!ticket close [reason]` close this ticket (with confirmation)"
            ),
            inline=False,
        )
        embed.add_field(
            name="Members",
            value="Pick a type from the panel menu. Use the **Close** button inside your ticket to close it.",
            inline=False,
        )
        embed.set_footer(text="Team Fime • Tickets")
        return embed

    def status_embed(self, guild: discord.Guild, cfg: dict) -> discord.Embed:
        staff = guild.get_role(int(cfg["staff_role_id"])) if cfg.get("staff_role_id") else None
        category = guild.get_channel(int(cfg["category_id"])) if cfg.get("category_id") else None
        log = self.log_channel(guild, cfg)
        embed = discord.Embed(title="🎫 Ticket System Setup", color=discord.Color.blurple())
        embed.add_field(
            name="Staff role",
            value=staff.mention if staff else "Not set (staff = Manage Channels)",
            inline=False,
        )
        embed.add_field(
            name="Ticket category",
            value=category.name if category else "Not set (channels are created at the top level)",
            inline=False,
        )
        embed.add_field(name="Transcript channel", value=log.mention if log else "Not set", inline=False)
        embed.add_field(name="Panel title", value=trunc(cfg["panel_title"], 200), inline=False)
        embed.add_field(
            name="Ticket types",
            value=f"{len(enabled_types(cfg))} enabled of {len(catalog(cfg))}",
            inline=True,
        )
        embed.add_field(name="Open tickets", value=str(len(cfg["tickets"])), inline=True)
        embed.set_footer(text="Select the types to show in the panel below.")
        return embed

    @commands.group(name="ticket", invoke_without_command=True, case_insensitive=True)
    async def ticket(self, ctx: commands.Context):
        await ctx.send(embed=self.help_embed())

    @ticket.command(name="help")
    async def ticket_help(self, ctx: commands.Context):
        await ctx.send(embed=self.help_embed())

    @ticket.command(name="setup")
    @admin_only()
    async def ticket_setup(self, ctx: commands.Context):
        cfg = self.cfg(ctx.guild.id)
        view = TypeSelectView(self, ctx.guild.id, ctx.author.id)
        view.message = await ctx.send(embed=self.status_embed(ctx.guild, cfg), view=view)

    @ticket.command(name="panel")
    @admin_only()
    async def ticket_panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        cfg = self.cfg(ctx.guild.id)
        types = enabled_types(cfg)
        if not types:
            await ctx.send("❌ No ticket types are enabled. Run `!ticket setup` first.")
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
        await channel.send(embed=embed, view=TicketPanelView(self, options))
        await ctx.send(f"✅ Ticket panel posted in {channel.mention}.", delete_after=8)

    @ticket.command(name="staff")
    @admin_only()
    async def ticket_staff(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        cfg = self.cfg(ctx.guild.id)
        cfg["staff_role_id"] = role.id if role else None
        await self.save()
        text = f"✅ Staff role set to {role.mention}." if role else "✅ Staff role cleared."
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @ticket.command(name="category")
    @admin_only()
    async def ticket_category(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        cfg = self.cfg(ctx.guild.id)
        cfg["category_id"] = category.id if category else None
        await self.save()
        text = f"✅ Tickets will be created under **{category.name}**." if category else "✅ Ticket category cleared."
        await ctx.send(text)

    @ticket.command(name="logs")
    @admin_only()
    async def ticket_logs(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        cfg = self.cfg(ctx.guild.id)
        cfg["log_channel_id"] = channel.id if channel else None
        await self.save()
        text = f"✅ Transcripts will be sent to {channel.mention}." if channel else "✅ Transcript logging disabled."
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @ticket.command(name="title")
    @admin_only()
    async def ticket_title(self, ctx: commands.Context, *, text: str):
        cfg = self.cfg(ctx.guild.id)
        cfg["panel_title"] = trunc(text, 250)
        await self.save()
        await ctx.send("✅ Panel title updated. Post a new panel with `!ticket panel`.")

    @ticket.command(name="description")
    @admin_only()
    async def ticket_description(self, ctx: commands.Context, *, text: str):
        cfg = self.cfg(ctx.guild.id)
        cfg["panel_text"] = trunc(text, 4000)
        await self.save()
        await ctx.send("✅ Panel text updated. Post a new panel with `!ticket panel`.")

    @ticket.command(name="typeadd")
    @admin_only()
    async def ticket_typeadd(self, ctx: commands.Context, *, data: str):
        parts = [part.strip() for part in data.split("|")]
        if not parts or not parts[0]:
            await ctx.send("Usage: `!ticket typeadd Label | description | emoji`")
            return
        label = trunc(parts[0], 80)
        description = trunc(parts[1], 100) if len(parts) > 1 else ""
        emoji = parts[2] if len(parts) > 2 and parts[2] else "🎫"

        cfg = self.cfg(ctx.guild.id)
        if len(cfg["custom_types"]) >= MAX_CUSTOM_TYPES:
            await ctx.send(f"❌ You can add up to {MAX_CUSTOM_TYPES} custom types.")
            return
        if any(item["label"].casefold() == label.casefold() for item in catalog(cfg).values()):
            await ctx.send("❌ A ticket type with this name already exists.")
            return

        key = "custom-" + uuid.uuid4().hex[:8]
        cfg["custom_types"].append({"key": key, "label": label, "description": description, "emoji": emoji})
        cfg["enabled_types"].append(key)
        await self.save()
        await ctx.send(f"✅ Added ticket type **{label}** and enabled it. Post a new panel to show it.")

    @ticket.command(name="typeremove")
    @admin_only()
    async def ticket_typeremove(self, ctx: commands.Context, *, name: str):
        cfg = self.cfg(ctx.guild.id)
        wanted = name.strip().casefold()
        match = next(
            (item for item in cfg["custom_types"]
             if item["key"].casefold() == wanted or item["label"].casefold() == wanted),
            None,
        )
        if match is None:
            await ctx.send("❌ No custom ticket type matches that name. Default types can only be disabled in `!ticket setup`.")
            return
        cfg["custom_types"] = [item for item in cfg["custom_types"] if item["key"] != match["key"]]
        cfg["enabled_types"] = [key for key in cfg["enabled_types"] if key != match["key"]]
        await self.save()
        await ctx.send(f"✅ Removed ticket type **{match['label']}**.")

    @ticket.command(name="list")
    @staff_only()
    async def ticket_list(self, ctx: commands.Context):
        cfg = self.cfg(ctx.guild.id)
        lines = []
        for channel_id, record in cfg["tickets"].items():
            channel = ctx.guild.get_channel(int(channel_id))
            if channel is None:
                continue
            claimed = f"<@{record['claimed_by']}>" if record.get("claimed_by") else "unclaimed"
            lines.append(
                f"{channel.mention} • <@{record.get('owner_id')}> • "
                f"{type_label(cfg, record.get('type', ''))} • {claimed}"
            )
        if not lines:
            await ctx.send("There are no open tickets right now.")
            return
        embed = discord.Embed(
            title=f"🎫 Open tickets ({len(lines)})",
            description=trunc("\n".join(lines), 4000),
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed, allowed_mentions=NO_MENTIONS)

    @ticket.command(name="claim")
    @staff_only()
    async def ticket_claim(self, ctx: commands.Context):
        ok, text = self.claim_ticket(ctx.guild, ctx.channel, ctx.author)
        if not ok:
            await ctx.send(text, allowed_mentions=NO_MENTIONS)
            return
        await self.save()
        await ctx.send(text, allowed_mentions=NO_MENTIONS)

    @ticket.command(name="add")
    @staff_only()
    async def ticket_add(self, ctx: commands.Context, member: discord.Member):
        if self.ticket_record(ctx.guild, ctx.channel) is None:
            await ctx.send("This is not an active ticket channel.")
            return
        await ctx.channel.set_permissions(
            member,
            view_channel=True, send_messages=True, read_message_history=True,
            attach_files=True, embed_links=True,
            reason=f"Added to ticket by {ctx.author}",
        )
        await ctx.send(f"✅ {member.mention} was added to this ticket.", allowed_mentions=NO_MENTIONS)

    @ticket.command(name="remove")
    @staff_only()
    async def ticket_remove(self, ctx: commands.Context, member: discord.Member):
        record = self.ticket_record(ctx.guild, ctx.channel)
        if record is None:
            await ctx.send("This is not an active ticket channel.")
            return
        if member.id == record.get("owner_id"):
            await ctx.send("You can't remove the ticket owner.")
            return
        await ctx.channel.set_permissions(member, overwrite=None, reason=f"Removed from ticket by {ctx.author}")
        await ctx.send(f"✅ {member.mention} was removed from this ticket.", allowed_mentions=NO_MENTIONS)

    @ticket.command(name="close")
    async def ticket_close(self, ctx: commands.Context, *, reason: str = "No reason given"):
        cfg = self.cfg(ctx.guild.id)
        record = self.ticket_record(ctx.guild, ctx.channel)
        if record is None:
            await ctx.send("This is not an active ticket channel.")
            return
        if ctx.author.id != record.get("owner_id") and not self.is_staff(ctx.author, cfg):
            await ctx.send("Only the ticket owner or staff can close this ticket.")
            return
        view = ConfirmCloseView(self, ctx.channel, ctx.author.id, trunc(reason, 300))
        view.message = await ctx.send(
            "Are you sure you want to close this ticket? A transcript will be saved.",
            view=view,
        )


# ============================================================
# Load point
# ============================================================

async def setup(bot: commands.Bot) -> None:
    """Called by discord.py on load_extension("bot7").

    If a command name or alias already exists in bot.py or another cog, it is skipped
    instead of stopping the cog from loading.
    """
    cog = Tickets(bot)
    taken: set = set(bot.all_commands)
    kept, skipped = [], []

    for command in cog.__cog_commands__:
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
        print(f"[TICKETS] Skipped conflicting commands: {', '.join(skipped)}")
    print(f"✅ Ticket system loaded ({len(kept)} commands)")
