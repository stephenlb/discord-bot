import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import io
import json
import os
from main import Bot
#config
DATA_FILE = "ticket_forums.json"

def load_forums():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_forums(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

class TicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        forums_data = load_forums()
        forum_id = str(interaction.message.id)
        
        if forum_id not in forums_data:
            return await interaction.response.send_message("❌ This ticket forum is no longer active.", ephemeral=True)
            
        guild = interaction.guild
        allowed_role_ids = forums_data[forum_id]["roles"]
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True)
        }
        
        for role_id in allowed_role_ids:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            overwrites=overwrites,
            category=interaction.channel.category,
            topic=f"Ticket created by {interaction.user.id}"
        )

        await interaction.response.send_message(f"Your ticket has been created: {ticket_channel.mention}", ephemeral=True)
        await ticket_channel.send(f"Welcome {interaction.user.mention}! Please describe your issue. Our team will be with you shortly.")


class TicketSystem(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    forum_group = app_commands.Group(name="forum", description="Manage ticket forums")

    @forum_group.command(name="create", description="Create a ticket forum in a designated channel")
    @app_commands.describe(
        message="The message displayed on the ticket forum",
        role1="First role allowed to see tickets",
        target_channel="Channel to create the forum in (Defaults to current channel)",
        role2="Second role allowed to see tickets (optional)",
        role3="Third role allowed to see tickets (optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def create_ticket_forum(
        self, 
        interaction: discord.Interaction, 
        message: str, 
        role1: discord.Role, 
        target_channel: discord.TextChannel = None,
        role2: discord.Role = None, 
        role3: discord.Role = None
    ):
      
        forum_channel = target_channel or interaction.channel
        embed = discord.Embed(title="Support Tickets", description=message, color=discord.Color.blue())
        forum_msg = await forum_channel.send(embed=embed, view=TicketButton())
        
        #Save Role + Channela
        forums_data = load_forums()
        allowed_roles = [role1.id]
        if role2: allowed_roles.append(role2.id)
        if role3: allowed_roles.append(role3.id)
        
        forums_data[str(forum_msg.id)] = {
            "roles": allowed_roles,
            "channel_id": forum_channel.id
        }
        save_forums(forums_data)

        #ID
        admin_overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        
        admin_channel = await interaction.guild.create_text_channel(
            name=f"forum-info-{forum_msg.id}",
            overwrites=admin_overwrites,
            category=interaction.channel.category
        )
        
        await admin_channel.send(
            f"**Private Forum Info**\n"
            f"The ticket forum in {forum_channel.mention} has been created.\n"
            f"**Forum ID:** `{forum_msg.id}`\n\n"
            f"*You can delete this channel once you have noted the ID.*"
        )
        
        await interaction.response.send_message(
            f"Ticket forum created in {forum_channel.mention}! Admin details sent to {admin_channel.mention}", 
            ephemeral=True
        )

    @forum_group.command(name="delete", description="Delete an active ticket forum by ID")
    @app_commands.default_permissions(administrator=True)
    async def delete_forum(self, interaction: discord.Interaction, forum_id: str):
        forums_data = load_forums()
        
        if forum_id not in forums_data:
            return await interaction.response.send_message("Forum ID not database.", ephemeral=True)
            
        forum_info = forums_data[forum_id]
        channel_id = forum_info.get("channel_id")
      
        if channel_id:
            try:
                channel = self.bot.get_channel(channel_id) or await self.bot.fetch_channel(channel_id)
                if channel:
                    msg = await channel.fetch_message(int(forum_id))
                    await msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass

        #Remove from database
        del forums_data[forum_id]
        save_forums(forums_data)
        
        await interaction.response.send_message(f"✅ Ticket forum message successfully deleted and deactivated.", ephemeral=True)

    @app_commands.command(name="close", description="Close the current ticket, create a transcript, and delete instantly")
    @app_commands.describe(title="Optional custom title for the transcript file")
    async def close_ticket(self, interaction: discord.Interaction, title: str = None):
        if not interaction.channel.name.startswith("ticket-"):
            return await interaction.response.send_message("❌ This command can only be used inside a ticket channel.", ephemeral=True)
            
        await interaction.response.defer()
        
        #generate transcript name for sorting/appeals
        transcript_title = title if title else interaction.channel.name
        
        #Transcript
        transcript = f"Transcript for {transcript_title}\n"
        transcript += "=" * 40 + "\n\n"        
        participants = set()         
        messages = [msg async for msg in interaction.channel.history(limit=None, oldest_first=True)]
        for msg in messages:
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
            transcript += f"[{timestamp}] {msg.author.name}: {msg.clean_content}\n"
            if msg.attachments:
                transcript += f"    [Attachments: {', '.join([a.url for a in msg.attachments])}]\n"
            if not msg.author.bot:
                participants.add(msg.author)
        try:
            topic = interaction.channel.topic
            if topic:
                user_id_str = topic.split(" ")[-1]
                if user_id_str.isdigit():
                    ticket_user = await interaction.guild.fetch_member(int(user_id_str))
                    if ticket_user and not ticket_user.bot:
                        participants.add(ticket_user)
        except Exception:
            pass 
        transcript_bytes = transcript.encode('utf-8')
        safe_filename = transcript_title.replace("/", "-") 
        #avoid possible naming exploit
        for user in participants:
            try:
                transcript_file = discord.File(io.BytesIO(transcript_bytes), filename=f"{safe_filename}.txt")
                await user.send(
                    content=f"Here is the transcript of the closed ticket in **{interaction.guild.name}**:", 
                    file=transcript_file
                )
            except discord.Forbidden:
                #Dms closed
                pass
            except Exception as e:
                print(f"Failed to send transcript to {user.name}: {e}")
        await interaction.followup.send("Ticket closed and transcript sent to participants.")
        try:
            await interaction.channel.delete(reason="Ticket closed.")
        except discord.NotFound:
            pass

async def setup(bot: Bot):
    await bot.add_cog(TicketSystem(bot))
