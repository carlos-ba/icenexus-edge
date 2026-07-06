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
    """Cria as tabelas se não existirem e aplica migrações leves."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)


async def _migrate(conn) -> None:
    """
    Migrações aditivas para bancos existentes (create_all não altera
    tabelas já criadas). Cada ALTER é idempotente via try/except.
    """
    from sqlalchemy import text
    migracoes = [
        "ALTER TABLE alarm_events ADD COLUMN diagnostico_correto BOOLEAN",
        "ALTER TABLE alarm_events ADD COLUMN causa_real VARCHAR",
        "ALTER TABLE alarm_events ADD COLUMN avaliado_em DATETIME",
    ]
    for sql in migracoes:
        try:
            await conn.execute(text(sql))
        except Exception:
            pass  # coluna já existe
