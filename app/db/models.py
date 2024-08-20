from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(AsyncAttrs, DeclarativeBase):
    pass

class MusicPlayer(Base):
    __tablename__ = 'music_players'

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)

class MusicPlayerQueue(Base):
    __tablename__ = 'music_player_queues'

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(MusicPlayer.guild_id), primary_key=True)

class MusicPlayerQueueItem(Base):
    __tablename__ = 'music_player_queue_items'

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey(MusicPlayerQueue.guild_id), primary_key=True)
    position: Mapped[int] = mapped_column(primary_key=True)

    url: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    author: Mapped[str] = mapped_column()
    duration: Mapped[int] = mapped_column()
    thumbnail: Mapped[str] = mapped_column()

