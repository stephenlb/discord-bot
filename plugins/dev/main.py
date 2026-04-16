from discord import Embed, Interaction
from main import Bot
from discord.ext import commands
from discord import app_commands

from plugins.dev.views.plugin import PluginView
class Dev(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot = bot

    @commands.check(lambda ctx: ctx.author.id == 865907763350601738 or ctx.bot.is_owner(ctx.author))
    @commands.hybrid_command(
        name = 'sync',
        guild_only=True
    )
    async def sync(self, ctx: commands.Context[Bot]): 
        "Syncs the bot's command tree in the current guild"
        message = await ctx.reply(f"Syncingcommands to this guild...")

        if ctx.guild is None:
            await ctx.send("This command must be used in a server.")
            return
        
        await ctx.defer()
        self.bot.tree.copy_global_to(guild=ctx.guild)
        spec = await self.bot.tree.sync(guild = ctx.guild)
        if message:
            await message.edit(content=f"Synced {len(spec)} commands to this guild.")
        else:
            await ctx.reply(f"Synced {len(spec)} commands to this guild.")

    @commands.hybrid_command(name='plugin')
    async def plugin(self, ctx: commands.Context[Bot]):
        await ctx.reply(view=PluginView(bot=self.bot))

async def setup(bot: Bot):
    """
    Required async setup function to load the Dev cog when the extension is initialized.
    """
    await bot.add_cog(Dev(bot))
