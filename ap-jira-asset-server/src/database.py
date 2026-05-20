import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

DB_PATH = os.getenv("DATABASE_PATH", "./assets.db")

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)

# WAL mode + foreign keys on every new connection
@event.listens_for(engine.sync_engine, "connect")
def _set_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.close()

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    async with SessionLocal() as session:
        yield session
