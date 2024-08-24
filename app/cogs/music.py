import discord
from discord import app_commands
from discord.ext import commands
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Optional, List

import wavelink

from app.db.models import MusicPlayer
from app.db.engine import AsyncEngineManager
from app.config import LAVALINK_HOST 

class MusicCog(commands.GroupCog, name='music'):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        nodes = [wavelink.Node(uri=f'http://{LAVALINK_HOST}:2333', password='')]

        await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=None)
        self.logger.info('Connected to the Lavalink node!')

    async def join_vc(self, interaction: discord.Interaction | None = None, channel: discord.VoiceChannel | None = None) -> discord.VoiceClient | None:
        if not channel:
            if not interaction:
                self.logger.error(f'join_vc() called without parameters. Pass either a discord.Interaction or discord.BoiceChannel.')
                return None

            if isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel and isinstance(interaction.user.voice.channel, discord.VoiceChannel):
                channel = interaction.user.voice.channel
            else:
                return None

        if channel.guild.voice_client: 
            if channel.guild.voice_client.channel != channel:
                await channel.guild.voice_client.disconnect(force=True)
            else:
                if isinstance(channel.guild.voice_client, discord.VoiceClient):
                    return channel.guild.voice_client
                else:
                    return None

        try:
            return await channel.connect()
        except discord.ClientException as e:
            self.logger.error(f'Error while trying to connect to voice channel: {e}')
            return None

    async def leave_vc(self, guild: discord.Guild):
        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)

    class MPButtonPlay(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Play', style=discord.ButtonStyle.green)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonPause(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Pause', style=discord.ButtonStyle.green)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonResume(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Resume', style=discord.ButtonStyle.green)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonSkip(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Skip', style=discord.ButtonStyle.blurple)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonStop(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Stop', style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonAdd(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Add', style=discord.ButtonStyle.gray, row=1)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonMove(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Move', style=discord.ButtonStyle.gray, row=1)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonRemove(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Remove', style=discord.ButtonStyle.gray, row=1)

        async def callback(self, interaction: discord.Interaction):
            pass

    class MPButtonLoop(discord.ui.Button):
        def __init__(self):
            super().__init__(label='loop', style=discord.ButtonStyle.gray, row=1)

        async def callback(self, interaction: discord.Interaction):
            pass

    def create_music_player_view(self) -> discord.ui.View:
        view = discord.ui.View()
        view.add_item(self.MPButtonPlay())
        view.add_item(self.MPButtonStop())
        view.add_item(self.MPButtonSkip())
        view.add_item(self.MPButtonAdd())
        view.add_item(self.MPButtonRemove())
        view.add_item(self.MPButtonMove())
        view.add_item(self.MPButtonLoop())

        return view

    def create_mp_embeds(self) -> List[discord.Embed] | None:
        from discord import Embed
        return [
                Embed(title='Queue', color=discord.Color.purple()),
                Embed(title='Currently playing', color=discord.Color.red()),
                ]

    @app_commands.command(name='create_player', description='Creates a music player. Owner only!')
    @commands.is_owner()
    async def create_player(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):

        async def make_player(channel: discord.TextChannel, session: AsyncSession) -> int:
            playerEmbeds = self.create_mp_embeds()
            if playerEmbeds:
                view = self.create_music_player_view()
                playerMessage = await channel.send(embeds=playerEmbeds, view=view)
            else:
                return 1

            session.add(MusicPlayer(guild_id=interaction.guild_id, channel_id=channel.id, message_id=playerMessage.id))
            return 0

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

            # If there is a music player in the guild already, check if it still exists, if it doesn't create a new one and update the database.
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

    @app_commands.command(name='play', description='Plays audio from a youtube video or url.')
    async def play(self, interaction: discord.Interaction, query: str | None = None, url: str | None = None):
        await interaction.response.send_message('Searching for the audio...', ephemeral=True)

    @app_commands.command(name='join', description='Joins the specified discord call')
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.send_message(f'Joining {channel.mention}...', ephemeral=True)
        
        voice_client = await self.join_vc(channel=channel)

        if not voice_client:
            await interaction.edit_original_response(content='Failed to join the channel specified')

        await interaction.edit_original_response(content=f'Successfully joined {channel.mention}!')

    @app_commands.command(name='leave', description='Leaves the current discord call')
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.send_message('Leaving the voice channel...', ephemeral=True)

        if not interaction.guild:
            await interaction.edit_original_response(content='Could not determine the guild from the interaction. If the issue persists check how to open an issue in the bot\'s about me.')
            self.logger.error('Could not determine the guild from the interaction. Likely a network issue as I see no other way of how it would happen.')
            return

        await self.leave_vc(interaction.guild)

        await interaction.edit_original_response(content='Left the voice channel!')

async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
