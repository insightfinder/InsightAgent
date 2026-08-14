import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event, inspect, text

DB_PATH = os.getenv("DATABASE_PATH", "./assets.db")

# Default pool (size=5, max_overflow=10) caps concurrent requests at 15 in-flight
# DB connections; requests beyond that queue for pool_timeout seconds. Raised to
# handle bursts of concurrent lookups (e.g. device_inventory_lookup.py's worker pool).
engine = create_async_engine(
    f"sqlite+aiosqlite:///{DB_PATH}",
    echo=False,
    pool_size=20,
    max_overflow=80,
    pool_timeout=30,
)

# WAL mode + foreign keys on every new connection
@event.listens_for(engine.sync_engine, "connect")
def _set_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def _add_missing_columns(conn):
    # create_all() only creates missing tables, not missing columns on existing
    # ones. This project has no migration tool, so new nullable columns added
    # to an existing table (e.g. Venue.abbreviation) are backfilled here.
    existing_cols = {col["name"] for col in inspect(conn).get_columns("venues")}
    for col in ("abbreviation", "abbreviation_key"):
        if col not in existing_cols:
            conn.execute(text(f"ALTER TABLE venues ADD COLUMN {col} VARCHAR(100)"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def get_session():
    async with SessionLocal() as session:
        yield session
