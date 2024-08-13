import discord
from discord import app_commands
from discord.ext import commands
import logging

class AdminCog(commands.GroupCog, name='admin'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')

    @app_commands.command(name='give_role', description='Gives a role to a user')
    @commands.is_owner()
    async def give_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.send_message('Giving role...', ephemeral=True)
        await user.add_roles(role)
        await interaction.edit_original_response(content='Role given!')

    @app_commands.command(name='remove_role', description='Removes a role from a user')
    @commands.is_owner()
    async def remove_role(self, interaction: discord.Interaction, user: discord.Member, role: discord.Role):
        await interaction.response.send_message('Removeing role...', ephemeral=True)
        await user.remove_roles(role)
        await interaction.edit_original_response(content='Role removed!')

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
