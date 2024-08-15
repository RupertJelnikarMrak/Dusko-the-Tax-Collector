from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker
from app.config import DATABASE_URL

class AsyncEngineManager:
    _engine: AsyncEngine | None = None

    @classmethod
    def get_engine(cls) -> AsyncEngine:
        if cls._engine is None:
            cls._engine = create_async_engine(DATABASE_URL, echo=True)
        return cls._engine

    @classmethod
    def get_session(cls):
        async_session = async_sessionmaker(cls.get_engine(), expire_on_commit=False)
        return async_session()

    @classmethod
    async def close(cls):
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
