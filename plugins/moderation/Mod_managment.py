import discord
import main import Bot
from discord import app_commands
from discord.ext import commands
from googleapiclient.discovery import build
import json
import os
import re
import asyncio

from main import Bot 

# =====================================================
#                 PLUGIN CONFIGURATION
# =====================================================

MOD_ROLE_ID   = int(os.getenv("DISCORD_MOD_ROLE_ID",   "0"))
ADMIN_ROLE_ID = int(os.getenv("DISCORD_ADMIN_ROLE_ID", "0"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
DATA_FILE = os.getenv("MOD_DB_FILE", "mod_database.json")

CHANNEL_ID_REGEX = re.compile(r"(UC[\w-]{21,22})")

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_data(data: dict):
    tmp_path = f"{DATA_FILE}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp_path, DATA_FILE)

def fetch_channel(query: str, youtube_client):
    """Fetches channel info from YouTube (Blocking call)."""
    if not youtube_client:
        return None
        
    try:
        id_match = CHANNEL_ID_REGEX.search(query)
        item = None
        channel_id = None

        if id_match:
            channel_id = id_match.group(1)
            response = youtube_client.channels().list(part="snippet", id=channel_id, maxResults=1).execute()
            if response.get("items"):
                item = response["items"][0]

        if not item:
            search_term = query.rstrip("/").split("/")[-1] if "youtube.com" in query else query
            response = youtube_client.search().list(part="snippet", q=search_term, type="channel", maxResults=1).execute()
            if response.get("items"):
                item = response["items"][0]

        if not item:
            return None

        snippet = item["snippet"]
        if channel_id is None:
            channel_id = item["id"].get("channelId") if isinstance(item.get("id"), dict) else item.get("id")

        if not channel_id:
            return None

        thumbs = snippet.get("thumbnails") or {}
        thumb_url = (
            (thumbs.get("default") or {}).get("url")
            or (thumbs.get("medium") or {}).get("url")
            or (thumbs.get("high") or {}).get("url")
        )

        return {
            "title": snippet.get("title", "Unknown"),
            "id": channel_id,
            "url": f"https://www.youtube.com/channel/{channel_id}",
            "thumbnail": thumb_url,
        }

    except Exception as e:
        print(f"YouTube API error: {e}")
        return None

# Permission Check 
def mod_manager_only():
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild: return False
        member = interaction.guild.get_member(interaction.user.id)
        if not member: return False
        if member.guild_permissions.administrator: return True
        return any(role.id == ADMIN_ROLE_ID for role in member.roles)
    return app_commands.check(predicate)

# =====================================================
#                   PLUGIN COG
# =====================================================

class YouTubeModManager(commands.GroupCog, group_name="mod", group_description="Moderator management via YouTube"):
    def __init__(self, bot: Bot):
        self.bot = bot
        # Initialize the API client dynamically when the cog loads
        if YOUTUBE_API_KEY:
            self.youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        else:
            self.youtube = None
            print("WARNING: YOUTUBE_API_KEY is not set in environment variables.")

    @app_commands.command(name="add", description="Register a moderator (Auto-Role & DB)")
    @mod_manager_only()
    async def mod_add(self, interaction: discord.Interaction, user: discord.Member, yt_query: str):
        await interaction.response.defer(ephemeral=True)

        if not self.youtube:
            await interaction.followup.send("❌ YouTube API key is missing. Contact the bot developer.")
            return

        data = load_data()
        if str(user.id) in data:
            await interaction.followup.send("⚠️ This user is already registered.")
            return

        # Run blocking API call in an executor
        loop = asyncio.get_running_loop()
        channel = await loop.run_in_executor(None, lambda: fetch_channel(yt_query, self.youtube))

        if not channel:
            await interaction.followup.send("❌ YouTube channel not found.")
            return

        mod_role = interaction.guild.get_role(MOD_ROLE_ID) if interaction.guild else None
        if not mod_role:
            await interaction.followup.send("❌ Mod role does not exist (Check Config).")
            return

        me = interaction.guild.get_member(self.bot.user.id) if interaction.guild and self.bot.user else None

        if not me or not getattr(me, "top_role", None):
            await interaction.followup.send("❌ Could not determine bot role. Try again in a moment.")
            return

        if mod_role.position >= me.top_role.position:
            await interaction.followup.send("❌ Bot role hierarchy is too low. Move the Bot role above the Mod role in Server Settings.")
            return

        try:
            await user.add_roles(mod_role, reason="Moderator registered via Bot")
        except discord.Forbidden:
            await interaction.followup.send("❌ Missing Permissions to add role.")
            return

        data[str(user.id)] = {
            "discord_name": user.name,
            "yt_title": channel["title"],
            "yt_id": channel["id"],
            "yt_url": channel["url"],
            "yt_thumb": channel.get("thumbnail"),
        }
        save_data(data)

        embed = discord.Embed(title="✅ Moderator Registered", color=discord.Color.green())
        if channel.get("thumbnail"):
            embed.set_thumbnail(url=channel["thumbnail"])
        embed.add_field(name="Discord", value=user.mention)
        embed.add_field(name="YouTube", value=f"[{channel['title']}]({channel['url']})")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="remove", description="Remove a moderator (Removes Role & DB)")
    @mod_manager_only()
    async def mod_remove(self, interaction: discord.Interaction, user: discord.Member):
        data = load_data()

        if str(user.id) not in data:
            await interaction.response.send_message("⚠️ User is not registered.", ephemeral=True)
            return

        mod_role = interaction.guild.get_role(MOD_ROLE_ID) if interaction.guild else None
        if mod_role and mod_role in user.roles:
            try:
                await user.remove_roles(mod_role, reason="Moderator removed via Bot")
            except discord.Forbidden:
                await interaction.response.send_message("❌ I cannot remove the role (Hierarchy issue).", ephemeral=True)
                return

        del data[str(user.id)]
        save_data(data)

        await interaction.response.send_message(f"🗑️ {user.mention} removed from DB and Role removed.")

    @app_commands.command(name="list", description="List all moderators")
    async def mod_list(self, interaction: discord.Interaction):
        data = load_data()

        if not data:
            await interaction.response.send_message("📭 No moderators registered.", ephemeral=True)
            return

        embed = discord.Embed(title="🛡️ Moderator List", color=discord.Color.red())

        for uid, info in data.items():
            embed.add_field(
                name=info.get("discord_name", "Unknown"),
                value=f"<@{uid}>\n📺 [{info.get('yt_title','Unknown')}]({info.get('yt_url','')})",
                inline=True,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Get moderator info by User or YT Name")
    async def mod_info(self, interaction: discord.Interaction, user: discord.Member = None, yt_name: str = None):
        data = load_data()
        entry = None
        uid = None

        if user and str(user.id) in data:
            uid, entry = str(user.id), data[str(user.id)]
        elif yt_name:
            for k, v in data.items():
                if yt_name.lower() in (v.get("yt_title") or "").lower():
                    uid, entry = k, v
                    break

        if not entry:
            await interaction.response.send_message("❌ Moderator not found in database.", ephemeral=True)
            return

        embed = discord.Embed(title="🔎 Moderator Info", color=discord.Color.blue())
        if entry.get("yt_thumb"):
            embed.set_thumbnail(url=entry["yt_thumb"])
        embed.add_field(name="Discord", value=f"<@{uid}>", inline=True)
        embed.add_field(
            name="YouTube Channel",
            value=f"[{entry.get('yt_title','Unknown')}]({entry.get('yt_url','')})",
            inline=True,
        )
        if entry.get("yt_id"):
            embed.set_footer(text=f"YT ID: {entry['yt_id']}")

        await interaction.response.send_message(embed=embed)

    # Automatically handle errors specifically for the commands in this cog
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            msg = "⛔ You don't have permission to do that."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        else:
            print(f"App command error in YouTubeModManager: {error}")

async def setup(bot: Bot):
    """Required async setup function to load the cog."""
    await bot.add_cog(YouTubeModManager(bot))

