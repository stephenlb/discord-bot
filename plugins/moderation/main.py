import discord
from discord.ext import commands
from main import Bot

class Moderation(commands.Cog):
    """
    A commands.Cog module that provides moderation commands.
    """
    def __init__(self, bot: Bot):
        self.bot = bot
#in testing should work
    @commands.hybrid_command(
            name="stephen_unban", 
            description="Unbans someone"
    )
    @commands.has_permissions(ban_members=True) # Added permission check for safety
    async def unban(self, ctx: commands.Context[Bot], user: discord.User): # Changed to discord.User to allow preventive bans
        if user == ctx.author:
            return await ctx.reply("You can't unban yourself!", mention_author=False)

        try:
            await ctx.guild.unban(user) # Using guild.unban() instead of member.unban()
    
            await ctx.send(f"🔨 Unbanned {user}", ephemeral=True) 
        except discord.Forbidden:
            await ctx.reply("I don't have permission to unban that user.", mention_author=False, ephemeral=True)
        except Exception as e:
            await ctx.reply(f"Error: {e}", mention_author=False)
    
    @commands.hybrid_command(
        name="stephen_ban", 
        description="Bans someone"
    )
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context[Bot], member: discord.Member, *, reason: str = "No reason provided"):
        if member == ctx.author:
            return await ctx.reply("You can't ban yourself!", mention_author=False)
            
        try:
            await member.ban(reason=reason)
            #no else needed gets handled by hybrid command
            await ctx.send(f"🔨 Banned {member} — **Reason:** {reason}", ephemeral=True)
        except discord.Forbidden:
            await ctx.reply("I don't have permission to ban that user.", mention_author=False, ephemeral=True)
        except Exception as e:
            await ctx.reply(f"Error: {e}", mention_author=False)
         
    @ban.error
    async def ban_error(self, ctx: commands.Context[Bot], error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You need `Ban Members` permission to use this command.", mention_author=False)

async def setup(bot: Bot):
    """
    Required async setup function to load the Status cog when the extension is initialized.
    """
    await bot.add_cog(Moderation(bot))
