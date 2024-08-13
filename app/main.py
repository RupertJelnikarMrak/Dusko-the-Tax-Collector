# pyright: reportUnusedFunction=false
import os
import logging
import discord
from discord.ext import commands

from app.config import setup_logging, BOT_PREFIX, DISCORD_AUTH_TOKEN

def main(debug: bool = False):
    setup_logging()
    logger = logging.getLogger('bot')
    intents = discord.Intents.all()
    bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)

    async def load_cogs():
        for filename in os.listdir('./app/cogs'):
            if filename.endswith('.py'):
                await bot.load_extension(f'app.cogs.{filename[:-3]}')
                logger.info(f'Loaded cog: {filename[:-3]}')

    async def unload_cogs():
        for filename in os.listdir('./app/cogs'):
            if filename.endswith('.py'):
                await bot.unload_extension(f'app.cogs.{filename[:-3]}')
                logger.info(f'Unloaded cog: {filename[:-3]}')

    @bot.event
    async def on_ready():
        logger.info(f'Logged in as {bot.user.name} ID: {bot.user.id}') # pyright: ignore[reportOptionalMemberAccess]

        await load_cogs()

        await bot.tree.sync()

    @bot.tree.command(name='reload', description='Reloads all cogs')
    @commands.is_owner()
    async def reload_cogs(interaction: discord.Interaction):
        await interaction.response.send_message('Reloading all cogs...', ephemeral=True)
        await unload_cogs()
        await load_cogs()
        await interaction.edit_original_response(content='Reloaded all cogs!')

    try:
        bot.run(DISCORD_AUTH_TOKEN, log_handler=None)
    except (SystemExit, KeyboardInterrupt):
        bot.loop.run_until_complete(bot.close())
        logger.info('Bot closed successfully')

if __name__ == '__main__':
    main()
