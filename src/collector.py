"""
collector.py — Serviço de coleta periódica (30s) da API Sitrad PRO + Emulador PCT-122E
Responsabilidades:
  - Descobrir automaticamente os instrumentos ativos (Sitrad + emulador)
  - Salvar leituras no banco a cada tick
  - Detectar abertura/fechamento de alarmes
"""

import asyncio
import logging
from datetime import datetime, UTC

from sqlalchemy import select

from src.db import AsyncSessionFactory
from src.models import AlarmEvent, Instrument, Reading
from src import sitrad_client as sitrad
from src import emulator_client as emu
from src import modbus_client as modbus

logger = logging.getLogger("coletor")

# Mapeamento: campo do snapshot → (código alarme, descrição, severidade)
ALARM_MAP = {
    "alm_high_t1":    ("ALH_T1",    "Alta temperatura S1",    "alarm"),
    "alm_low_t1":     ("ALL_T1",    "Baixa temperatura S1",   "alarm"),
    "alm_door":       ("ALM_DOOR",  "Porta aberta",           "warning"),
    "alm_high_press": ("ALH_PRESS", "Alta pressão",           "alarm"),
    "alm_low_press":  ("ALL_PRESS", "Baixa pressão",          "alarm"),
    "err_s1":         ("ERR_S1",    "Erro sonda 1 (S1)",      "alarm"),
    "err_s2":         ("ERR_S2",    "Erro sonda 2 (S2)",      "alarm"),
    "err_s3":         ("ERR_S3",    "Erro sonda 3 (S3)",      "warning"),
}


async def _upsert_instrument(instrument_info: dict) -> int:
    """
    Garante que o instrumento existe no banco; retorna o id interno.
    Funciona tanto para instrumentos reais (Sitrad) quanto emulados.
    """
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Instrument).where(Instrument.sitrad_id == instrument_info["id"])
        )
        instr = result.scalar_one_or_none()

        if instr is None:
            instr = Instrument(
                sitrad_id=instrument_info["id"],
                name=instrument_info["name"],
                address=instrument_info["address"],
                converter_name=instrument_info.get("converter_name"),
                model_id=instrument_info.get("modelId"),
                model_name=instrument_info.get("model_name"),
                source=instrument_info.get("source", "sitrad"),
                status=instrument_info.get("status", "Unknown"),
            )
            session.add(instr)
            logger.info(
                "Novo instrumento registrado: %s (sitrad_id=%d, source=%s)",
                instr.name, instr.sitrad_id, instr.source,
            )
        else:
            instr.status    = instrument_info.get("status", instr.status)
            instr.last_seen = datetime.now(UTC)

        await session.commit()
        await session.refresh(instr)
        return instr.id


async def _save_reading(instrument_db_id: int, snap: dict) -> None:
    """Salva a leitura atual e verifica alarmes."""
    async with AsyncSessionFactory() as session:
        reading = Reading(
            instrument_id=instrument_db_id,
            # Temperaturas
            t1=snap.get("t1"),
            t2=snap.get("t2"),
            t3=snap.get("t3"),
            t4=snap.get("t4"),
            # Pressões
            p1=snap.get("p1"),
            p2=snap.get("p2"),
            # Termodinâmica
            t_sat_p1=snap.get("t_sat_p1"),
            t_sat_p2=snap.get("t_sat_p2"),
            superheat=snap.get("superheat"),
            subcooling=snap.get("subcooling"),
            # Analógicas
            an1_pct=snap.get("an1_pct"),
            an2_pct=snap.get("an2_pct"),
            # Controle
            setpoint=snap.get("setpoint"),
            differential=snap.get("differential"),
            process_status=snap.get("process_status"),
            process_text=snap.get("process_text"),
            # Saídas digitais
            out_refrigeration=snap.get("out_refrigeration"),
            out_fan=snap.get("out_fan"),
            out_defrost=snap.get("out_defrost"),
            out_buzzer=snap.get("out_buzzer"),
            # Alarmes
            alm_high_t1=snap.get("alm_high_t1"),
            alm_low_t1=snap.get("alm_low_t1"),
            alm_door=snap.get("alm_door"),
            alm_high_press=snap.get("alm_high_press"),
            alm_low_press=snap.get("alm_low_press"),
            # Erros de sonda
            err_s1=snap.get("err_s1"),
            err_s2=snap.get("err_s2"),
            err_s3=snap.get("err_s3"),
            # Modos
            fast_freezing=snap.get("fast_freezing"),
            economic_mode=snap.get("economic_mode"),
        )
        session.add(reading)

        # ── Alarmes via lista raw do emulador (_active_alarms) ──────────────────
        # Quando o snapshot inclui _active_alarms (emulador PCT-122E),
        # usamos os códigos e descrições reais do emulador em vez do ALARM_MAP.
        raw_alarms: list[dict] = snap.get("_active_alarms") or []
        if raw_alarms is not None and snap.get("_active_alarms") is not None:
            active_codes_now = {a["code"] for a in raw_alarms}

            # Busca todos os alarmes ativos deste instrumento no banco
            all_active_result = await session.execute(
                select(AlarmEvent).where(
                    AlarmEvent.instrument_id == instrument_db_id,
                    AlarmEvent.is_active.is_(True),
                )
            )
            all_active = {a.code: a for a in all_active_result.scalars().all()}

            # Abre novos alarmes
            for a in raw_alarms:
                code = a["code"]
                if code not in all_active:
                    session.add(AlarmEvent(
                        instrument_id=instrument_db_id,
                        code=code,
                        description=a["description"],
                        severity=a["severity"],
                        is_active=True,
                    ))
                    logger.warning("ALARME ABERTO [%s] — %s", code, a["description"])

            # Fecha alarmes que não estão mais ativos
            for code, existing in all_active.items():
                if code not in active_codes_now:
                    existing.is_active = False
                    existing.cleared_at = datetime.now(UTC)
                    logger.info("Alarme resolvido [%s]", code)

        else:
            # ── Alarmes via ALARM_MAP (instrumentos Sitrad PRO) ──────────────────
            for field, (code, desc, sev) in ALARM_MAP.items():
                val = snap.get(field)
                if val is None:
                    continue
                triggered = bool(val)

                result = await session.execute(
                    select(AlarmEvent).where(
                        AlarmEvent.instrument_id == instrument_db_id,
                        AlarmEvent.code == code,
                        AlarmEvent.is_active.is_(True),
                    )
                )
                existing = result.scalar_one_or_none()

                if triggered and existing is None:
                    session.add(AlarmEvent(
                        instrument_id=instrument_db_id,
                        code=code,
                        description=desc,
                        severity=sev,
                        is_active=True,
                    ))
                    logger.warning("ALARME ABERTO [%s] — %s", code, desc)

                elif not triggered and existing is not None:
                    existing.is_active = False
                    existing.cleared_at = datetime.now(UTC)
                    logger.info("Alarme resolvido [%s]", code)

        await session.commit()


def run_collect() -> None:
    """
    Função síncrona chamada pelo APScheduler a cada 30s.
    Coleta de todas as fontes: Sitrad PRO + emulador(es).
    """
    asyncio.run(_collect_all())


async def _collect_all() -> None:
    # ── 1. Sitrad PRO ─────────────────────────────────────────────────────────
    try:
        sitrad_instruments = await asyncio.to_thread(sitrad.list_instruments)
    except Exception as exc:
        logger.error("Erro ao listar instrumentos Sitrad: %s", exc)
        sitrad_instruments = []

    for instr_info in sitrad_instruments:
        sitrad_id = instr_info["id"]
        # Adiciona source ao dict
        instr_info.setdefault("source", "sitrad")
        try:
            db_id = await _upsert_instrument(instr_info)
            snap  = await asyncio.to_thread(sitrad.get_snapshot, sitrad_id)
            await _save_reading(db_id, snap)
            logger.debug(
                "Sitrad — coletado %s: T1=%.1f T3=%.1f status=%s",
                instr_info["name"],
                snap.get("t1") or 0,
                snap.get("t3") or 0,
                snap.get("process_text", "?"),
            )
        except Exception as exc:
            logger.exception("Erro ao coletar Sitrad id=%d: %s", sitrad_id, exc)

    # ── 2. Emulador PCT-122E Plus ─────────────────────────────────────────────
    for addr in emu.EMULATOR_ADDRESSES:
        try:
            ctrl_info = await asyncio.to_thread(emu.get_controller, addr)
        except Exception:
            ctrl_info = None

        try:
            instr_info = emu.build_instrument_info(addr, ctrl_info)
            db_id  = await _upsert_instrument(instr_info)
            snap   = await asyncio.to_thread(emu.get_snapshot, addr)
            await _save_reading(db_id, snap)
            logger.debug(
                "Emulador addr=%d — T1=%.1f T3=%.1f P1=%.1f P2=%.1f SH=%s status=%s",
                addr,
                snap.get("t1") or 0,
                snap.get("t3") or 0,
                snap.get("p1") or 0,
                snap.get("p2") or 0,
                snap.get("superheat"),
                snap.get("process_text", "?"),
            )
        except Exception as exc:
            logger.exception("Erro ao coletar emulador addr=%d: %s", addr, exc)

    # ── 3. TC-900E Log via Modbus RTU (Waveshare COM3) ────────────────────────
    try:
        instr_info = modbus.get_instrument_info()
        db_id      = await _upsert_instrument(instr_info)
        snap       = await asyncio.to_thread(modbus.get_snapshot)
        await _save_reading(db_id, snap)
        logger.debug(
            "Modbus TC-900E — T1=%.1f T2=%.1f SP=%s status=%s",
            snap.get("t1") or 0,
            snap.get("t2") or 0,
            snap.get("setpoint"),
            snap.get("process_text", "?"),
        )
    except Exception as exc:
        logger.warning("TC-900E Modbus indisponivel: %s", exc)
