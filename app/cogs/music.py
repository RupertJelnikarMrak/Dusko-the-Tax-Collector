import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
from sqlalchemy import select
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
        self.bot.loop.create_task(self.update_all_player_message())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        node = wavelink.Node(uri=f'http://{LAVALINK_HOST}:2333', password='')
        node._inactive_player_timeout = 30

        await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
        self.logger.info('Connected to the Lavalink node!')

    async def get_player_from_interaction(self, interaction: discord.Interaction) -> wavelink.Player | None:
        if not interaction.guild:
            self.logger.error('Guild could not determine the guild from an interaction. Probbably a network issue, safe to ignore unless it happens often.')
            return None

        return wavelink.Pool.get_node().get_player(interaction.guild.id)

    async def join_vc(self, interaction: Optional[discord.Interaction] = None, channel: Optional[discord.VoiceChannel] = None, edit_response: bool = False, force: bool = False) -> wavelink.Player | None:
        """
        Attempts to join either the specified voice channel or the voice channel of the author of the interaction if available.

        Parameters:
            interaction (Optional[discord.Interaction]): The interaction object.
            channel (Optional[discord.VoiceChannel]): The voice channel to join.
            edit_response (bool): Whether to edit the response or not, only works if interaction is passed.
            force (bool): Whether to disconnect the bot from it's current voice channel if it is in one.

        Returns:
            wavelink.Player | None: The player object if successful, None otherwise
        """
        async def raise_error(msg: str, level: int = logging.DEBUG):
            self.logger.log(level, msg)
            if interaction and edit_response:
                await interaction.edit_original_response(content=msg)

        if channel:
            player: Optional[wavelink.Player] = wavelink.Pool.get_node().get_player(channel.guild.id)
        elif interaction:
            player: Optional[wavelink.Player] = await self.get_player_from_interaction(interaction)

            if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel or not isinstance(interaction.user.voice.channel, discord.VoiceChannel):
                await raise_error('Neither the bot nor you are in a voice channel. Please join a voice channel or run the join command first.')
                return None
            channel = interaction.user.voice.channel
        else:
            self.logger.error('join_vc() called without parameters. Pass either a discord.Interaction or discord.BoiceChannel.')
            return None

        if player and player.connected:
            if player.channel == channel:
                return player
            if force or player.channel.members.count == 1:
                await player.disconnect(force=True)
                await asyncio.sleep(1)
            else:
                return player

        try:
            player = await channel.connect(cls=wavelink.Player)
            player.queue.mode = wavelink.QueueMode.normal
            player.autoplay = wavelink.AutoPlayMode.enabled
            return player
        except Exception as e:
            await raise_error(f'Error while trying to connect to voice channel: {e}', level=logging.ERROR)
            return None

    async def leave_vc(self, guild: discord.Guild) -> None:
        if guild.voice_client:
            await guild.voice_client.disconnect(force=True)

    async def add_audio_to_queue(self, interaction: discord.Interaction, url_or_search: str, prepend: bool = False) -> None:
        """
        Searches for an audio and adds it to the queue.

        Parameters:
            interaction (discord.Interaction): The interaction object.
            url_or_search (str): The url or search query.

        Returns:
            None
        """
        if interaction.response.is_done == False:
            await interaction.edit_original_response(content='Searching for the audio...')
        else:
            await interaction.response.send_message('Searching for the audio...', ephemeral=True)
        
        player = await self.get_player_from_interaction(interaction)
        if not player:
            await interaction.edit_original_response(content='Player not found. Add the bot to a voice channel to create it.') 
            return

        tracks: wavelink.Search = await wavelink.Playable.search(url_or_search)
        if not tracks:
            await interaction.edit_original_response(content='No tracks found.')
            return

        if isinstance(tracks, wavelink.Playlist):
            await interaction.edit_original_response(content='Playlists are not yet supported.')
            return

        track: wavelink.Playable = tracks[0]
        if prepend:
            player.queue.put_at(0, track)
        else:
            await player.queue.put_wait(track)

        await self.update_player_message(interaction.guild) # type: ignore # interaction.guild cannot be none since checked in get_player_from_interaction

        await interaction.edit_original_response(content=f'Added **{track.title}** by **{track.author}**to the queue!')

    async def pause_resume_audio(self, interaction: discord.Interaction, pause: int, respond_to_interaction: bool = True) -> None:
        """
        Pauses, resumes or toggles the audio.

        Parameters:
            interaction (discord.Interaction): The interaction object.
            pause (int): 1 to pause, 0 to resume, 2 to toggle.
            respond_to_interaction (bool): Whether to respond to the interaction or not with pottential errors.

        Returns:
            None
        """
        async def respond(content: str):
            if respond_to_interaction:
                if interaction.response.is_done:
                    await interaction.edit_original_response(content=content)
                else:
                    await interaction.response.send_message(content, ephemeral=True)

        player: Optional[wavelink.Player] = await self.get_player_from_interaction(interaction)
        if not player or not player.playing:
            await respond('There is no audio playing.')
            return

        if pause == 2:
            if not player.paused or player.playing:
                await player.pause(not player.paused)
            else:
                await respond('There is no audio paused.')
        elif pause == 1:
            if not player.paused:
                await player.pause(True)
            else:
                await respond('The audio is already paused.')
        elif pause == 0:
            if player.paused:
                await player.pause(False)
            else:
                await respond('The audio is not paused.')

    def get_add_song_modal(self) -> discord.ui.Modal:
        modal = discord.ui.Modal(title='Add song to queue')

        url_or_search_input = discord.ui.TextInput(
                label='Enter the url or search query for the audio',
                style=discord.TextStyle.short,
                placeholder='URL or search query',
                required=True,
                max_length=200
                )

        modal.add_item(url_or_search_input)

        async def on_submit_handler(interaction: discord.Interaction):
            url_or_search = url_or_search_input.value
            player = await self.join_vc(interaction=interaction, edit_response=True)

            await self.add_audio_to_queue(interaction, url_or_search)

            if player and not player.playing:
                await player.play(player.queue.get())

        modal.on_submit = on_submit_handler
        return modal

    def get_queue_item_selection(self, player: wavelink.Player, placeholder: str = 'Select a song') -> discord.ui.Select:
        options = []
        for i in range(0, player.queue.count):
            track = player.queue.get_at(i)
            options.append(discord.SelectOption(label=f'{i}. {track.title}', value=str(i)))

        select = discord.ui.Select(
                placeholder=placeholder,
                options=options
                )

        return select

    async def create_music_player_view(self, player: Optional[wavelink.Player] = None) -> discord.ui.View:
        from discord.ui import Button
        from discord.enums import ButtonStyle

        view = discord.ui.View(timeout=None)

        async def play_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(self.get_add_song_modal())

        async def stop_callback(interaction: discord.Interaction):
            player = await self.get_player_from_interaction(interaction)
            if player and player.playing:
                await player.disconnect()
            await interaction.response.send_message('Stopped the audio!', ephemeral=True)
            await interaction.delete_original_response()

        async def skip_callback(interaction: discord.Interaction):
            player = await self.get_player_from_interaction(interaction)
            if player and player.playing:
                await player.skip()
            await interaction.response.send_message('Skipped the song', ephemeral=True)
            await interaction.delete_original_response()

        async def add_song_callback(interaction: discord.Interaction):
            await interaction.response.send_modal(self.get_add_song_modal())

        async def resume_song_callback(interaction: discord.Interaction):
            await interaction.response.send_message('Resumed the audio!', ephemeral=True)
            await self.pause_resume_audio(interaction, 0)
            await interaction.delete_original_response()

        async def pause_song_callback(interaction: discord.Interaction):
            await interaction.response.send_message('Paused the audio!', ephemeral=True)
            await self.pause_resume_audio(interaction, 1)
            await interaction.delete_original_response()

        if not player or not player.playing:
            button = Button(label='Play', style=ButtonStyle.green)
            button.callback = play_callback
            view.add_item(button)

        if player and player.playing and not player.paused:
            button = Button(label='Pause', style=ButtonStyle.gray)
            button.callback = pause_song_callback
            view.add_item(button)

        if player and  player.playing and player.paused:
            button = Button(label='Resume', style=ButtonStyle.gray)
            button.callback = resume_song_callback
            view.add_item(button)

        button = Button(label='Stop', style=ButtonStyle.red, disabled=not player)
        button.callback = stop_callback
        view.add_item(button)

        button = Button(label='Add song', style=ButtonStyle.gray, row=1, disabled=not player)
        button.callback = add_song_callback
        view.add_item(button)

        button = Button(label='Skip', style=ButtonStyle.gray, row=1, disabled=not player or not player.playing)
        button.callback = skip_callback
        view.add_item(button)

        # view.add_item(Button(label='Remove song', style=ButtonStyle.gray, row=1, disabled=not player or player.queue.is_empty))
        view.add_item(Button(label='Remove', style=ButtonStyle.gray, row=1, disabled=True))

        view.add_item(Button(label='Swap', style=ButtonStyle.gray, row=1, disabled=True))

        view.add_item(Button(label='Clear queue', style=ButtonStyle.red, row=1, disabled=not player or player.queue.is_empty))

        return view

    def create_mp_embeds(self, player: Optional[wavelink.Player] = None) -> List[discord.Embed]:
        from discord import Embed
        if not player:
            return [
                    Embed(title='Queue', color=discord.Color.purple()),
                    Embed(title='Currently playing', color=discord.Color.red(), description='No audio playing. Add some to the queue!')
                    ]

        embeds = []

        queue_content = ''
        if not player.queue.is_empty:
            for i in range(player.queue.count - 1, 0, -1):
                track = player.queue.get_at(i)
                queue_content += f'{i + 1}. [{track.title}]({track.uri})\n'
        else:
            queue_content = 'No audio in the queue.'

        embeds.append(Embed(title='Queue', description=queue_content, color=discord.Color.purple()))

        if player.current:
            current_embed = Embed(title=player.current.title, url=player.current.uri, color=discord.Color.brand_red())
            current_embed.set_author(name=player.current.author)
            current_embed.set_image(url=player.current.artwork)
        else:
            current_embed = Embed(title='Currently playing', color=discord.Color.red(), description='No audio playing. Add some to the queue!')
        embeds.append(current_embed)

        return embeds

    async def update_player_message(self, guild: discord.Guild) -> None:
        self.logger.debug(f'Updating player message in guild {guild.id}...')
        async with AsyncEngineManager.get_session() as session:
            db_player_message = await session.get(MusicPlayer, guild.id)
            if not db_player_message:
                return

            player_channel = await guild.fetch_channel(db_player_message.channel_id)
            if not player_channel:
                await session.delete(db_player_message)
                await session.commit()
                return

            if not isinstance(player_channel, discord.TextChannel):
                self.logger.error(f'Channel {player_channel.id} is not a text channel. This should not happen, check how the id if a non-text channel got into the database.'
                                  f'DB info: [guild_id: {db_player_message.guild_id}, channel_id: {db_player_message.channel_id}, message_id: {db_player_message.message_id}]'
                                  f'Deleting the false player message from the database.')
                await session.delete(db_player_message)
                await session.commit()
                return

            player_message = await player_channel.fetch_message(db_player_message.message_id)
            if not player_message:
                await session.delete(db_player_message)
                await session.commit()
                return

        player: Optional[wavelink.Player] = wavelink.Pool.get_node().get_player(guild.id)
        player_embeds = self.create_mp_embeds(player)
        if not player_embeds:
            self.logger.error(f'Could not create embeds for the music player in the guild(id: {guild.id}).')
            return

        player_view = await self.create_music_player_view(player)

        await player_message.edit(embeds=player_embeds, view=player_view)

    async def update_all_player_message(self) -> None:
        async with AsyncEngineManager.get_session() as session:
            players = (await session.execute(select(MusicPlayer))).scalars().all()
            for player in players:
                guild = self.bot.get_guild(player.guild_id)
                if not guild:
                    await session.delete(player)
                    continue

                await self.update_player_message(guild)
            
            await session.commit()


    @commands.Cog.listener()
    async def on_wavelink_player_update(self, payload: wavelink.PlayerUpdateEventPayload) -> None:
        if not payload.player or not payload.player.guild:
            return
        await self.update_player_message(payload.player.guild)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackEndEventPayload) -> None:
        if not payload.player or not payload.player.guild:
            return
        await self.update_player_message(payload.player.guild)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        if player.guild:
            await self.update_player_message(player.guild)

        await player.disconnect()


    @app_commands.command(name='create_player', description='Creates a music player. Owner only!')
    @commands.is_owner()
    async def create_player(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):

        async def make_player(channel: discord.TextChannel, session: AsyncSession) -> int:
            playerEmbeds = self.create_mp_embeds()
            if not playerEmbeds:
                return 1

            view = await self.create_music_player_view(player=None)
            playerMessage = await channel.send(embeds=playerEmbeds, view=view)

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

    @app_commands.command(name='quick-play', description='Adds an audio to the end of the queue.')
    async def quick_play(self, interaction: discord.Interaction, url_or_search: str):
        player = await self.join_vc(interaction=interaction, edit_response=True)
        if not player:
            return

        await self.add_audio_to_queue(interaction, url_or_search)

        if not player.playing:
            await player.play(player.queue.get())

    @app_commands.command(name='pause', description='Pauses the current audio.')
    async def pause(self, interaction: discord.Interaction):
        await interaction.response.send_message('Pausing the audio...', ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(content='Could not determine the guild from the interaction. If the issue persists check how to open an issue in the bot\'s about me.')
            self.logger.error('Could not determine the guild from the interaction. Likely a network issue as I see no other way of how it would happen.')
            return

        player = wavelink.Pool.get_node().get_player(guild.id)
        if not player or not player.playing:
            await interaction.edit_original_response(content='There is no audio playing.')
            return

        await player.pause(True)

        await interaction.edit_original_response(content='Paused the audio!')

    @app_commands.command(name='resume', description='Resumes the current audio.')
    async def resume(self, interaction: discord.Interaction):
        await interaction.response.send_message('Resuming the audio...', ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(content='Could not determine the guild from the interaction. If the issue persists check how to open an issue in the bot\'s about me.')
            self.logger.error('Could not determine the guild from the interaction. Likely a network issue as I see no other way of how it would happen.')
            return

        player = wavelink.Pool.get_node().get_player(guild.id)
        if not player or not player.paused:
            await interaction.edit_original_response(content='There is no audio paused.')
            return

        await player.pause(False)

        await interaction.edit_original_response(content='Resumed the audio!')

    @app_commands.command(name='skip', description='Skips the current audio.')
    async def skip(self, interaction: discord.Interaction):
        await interaction.response.send_message('Skipping the audio...', ephemeral=True)
        guild = interaction.guild
        if not guild:
            await interaction.edit_original_response(content='Could not determine the guild from the interaction. If the issue persists check how to open an issue in the bot\'s about me.')
            self.logger.error('Could not determine the guild from the interaction. Likely a network issue as I see no other way of how it would happen.')
            return

        player = wavelink.Pool.get_node().get_player(guild.id)
        if not player or not player.playing:
            await interaction.edit_original_response(content='There is no audio playing.')
            return

        await player.skip()

        await interaction.edit_original_response(content='Skipped the audio!')

    @app_commands.command(name='join', description='Joins the specified discord call')
    async def join(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        await interaction.response.send_message(f'Joining {channel.mention}...', ephemeral=True)
        
        await self.join_vc(channel=channel, edit_response=True, force=True)

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
