import discord
from discord import app_commands
from discord.ext import commands
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional, List

from app.db.models import MusicPlayer
from app.db.engine import AsyncEngineManager

def create_player_embeds() -> List[discord.Embed]:
    from discord import Embed
    return [
        Embed(title='Queue', color=discord.Color.purple()),
        Embed(title='Currently playing', color=discord.Color.red()),
    ]

class MusicCog(commands.GroupCog, name='music'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')

    @app_commands.command(name='create_player', description='Creates a music player. Owner only!')
    @commands.is_owner()
    async def create_player(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):

        async def make_player(channel: discord.TextChannel, session: AsyncSession):
            playerEmbeds = create_player_embeds()
            playerMessage = await channel.send(embeds=playerEmbeds)

            session.add(MusicPlayer(guild_id=interaction.guild_id, channel_id=channel.id, message_id=playerMessage.id))

        class MoveConfirmationView(discord.ui.View):
            def __init__(self, interaction: discord.Interaction, session: AsyncSession, oldPlayerMessage: discord.Message, destinationChannel: discord.TextChannel, oldMusicPlayer: MusicPlayer):
                super().__init__()
                self.interaction = interaction
                self.session = session
                self.oldPlayerMessage = oldPlayerMessage
                self.destinationChannel = destinationChannel
                self.oldMusicPlayer = oldMusicPlayer

            @discord.ui.button(style=discord.ButtonStyle.gray, label='Keep')
            async def keep(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.interaction.edit_original_response(content='Player creation cancelled.', view=None)

            @discord.ui.button(style=discord.ButtonStyle.danger, label='Move')
            async def move(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.interaction.edit_original_response(content=f'Moving the player from <#{self.oldPlayerMessage.channel.id}> to {self.destinationChannel.mention}...', view=None)

                await session.delete(self.oldMusicPlayer)
                await self.oldPlayerMessage.delete()

                await make_player(self.destinationChannel, self.session)

                await session.commit()

                await self.interaction.edit_original_response(content=f'Player moved from <#{self.oldPlayerMessage.channel.id}> to {self.destinationChannel.mention}!', view=None)

        if channel is None:
            if isinstance(interaction.channel, discord.TextChannel):
                channel = interaction.channel
            else: 
                await interaction.response.send_message('The channel could not be determined from the context. You can prevent this by specifying a channel when running this command.', ephemeral=True)
                return

        await interaction.response.send_message(f'Creating a music player in {channel.mention}...', ephemeral=True)

        async with AsyncEngineManager.get_session() as session:
            existingMusicPlayer = await session.get(MusicPlayer, interaction.guild_id)
            
            # If there is no player in the guild, make it
            if not existingMusicPlayer:
                await make_player(channel, session)
                await session.commit()
                return

            # Try to get the guild from the interaction
            guild: Optional[discord.Guild] = interaction.guild
            if not guild:
                await interaction.edit_original_response(content='CRITICAL: The guild could not be determined from the context. Try again, if the issue persists see how to oppen an issue in bot\'s about me!', view=None)
                self.logger.warning(
                    f'Guild could not be determined from the interaction. '
                    f'This is most likely Discord\'s fault and should not cause concern except if it is happening often check the bot\'s internet connection.'
                )
                return

            # If there is a player in the guild already, check if it still exists, if it doesn't create a new one and update the database.
            try:
                existingPlayerChannel =  await guild.fetch_channel(existingMusicPlayer.channel_id)
                if isinstance(existingPlayerChannel, discord.TextChannel) or isinstance(existingPlayerChannel, discord.Thread):
                    try:
                        existingPlayerMessage = await existingPlayerChannel.fetch_message(existingMusicPlayer.message_id)
                        # Prompt the user to move the player to the new channel
                        # Moving the player will delete the old player message and create a new one as well as update the database.
                        await interaction.edit_original_response(
                                content=f'A player already exists in this guild! Do you wish to move it from {existingPlayerChannel.mention} to {channel.mention}?',
                                view=MoveConfirmationView(interaction, session, existingPlayerMessage, channel, existingMusicPlayer)
                                )
                        return
                    except discord.NotFound:
                        await session.delete(existingMusicPlayer)
                else:
                    self.logger.error(
                        f'Channel {existingPlayerChannel.id} is not a text channel or thread. '
                        f'This should not happen, check how the id if a non-text channel got into the database.\n'
                        f'DB info: [guild_id: {existingMusicPlayer.guild_id}, channel_id: {existingMusicPlayer.channel_id}, message_id: {existingMusicPlayer.message_id}]'
                    )
            except discord.NotFound:
                await session.delete(existingMusicPlayer)

            await make_player(channel, session)

            await session.commit()

        await interaction.edit_original_response(content=f'Player created in {channel.mention}!')


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
