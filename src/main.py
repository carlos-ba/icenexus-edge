"""
main.py — Entrypoint do SitradColetor
  - Inicializa banco de dados
  - Agenda coleta a cada 30s
  - Serve dashboard estático + API REST
"""

import logging
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.db import init_db
from src.api import router
from src.demo import router as demo_router
from src.collector import run_collect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

COLLECT_INTERVAL_SECONDS = 3
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializa banco
    logger.info("Inicializando banco de dados...")
    await init_db()

    # Faz uma coleta imediata ao iniciar
    logger.info("Coleta inicial...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_collect)

    # Agenda coleta periódica
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        run_collect,
        trigger="interval",
        seconds=COLLECT_INTERVAL_SECONDS,
        id="collect",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Scheduler iniciado — coleta a cada %ds", COLLECT_INTERVAL_SECONDS)

    yield

    scheduler.shutdown(wait=False)
    logger.info("Scheduler encerrado.")


app = FastAPI(
    title="Sitrad Coletor Dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# API REST
app.include_router(router)
app.include_router(demo_router)

# Arquivos estáticos
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")
