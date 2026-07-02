"""
db.py — Configuração do banco SQLite assíncrono
"""

from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from src.models import Base

DB_PATH = Path(__file__).parent.parent / "data" / "coletor.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


async def init_db() -> None:
    """Cria as tabelas se não existirem."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
