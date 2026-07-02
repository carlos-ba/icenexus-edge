"""
api.py — Endpoints FastAPI para o dashboard
Suporta TC-900E (temperatura) e PCT-122E Plus (refrigeração com pressão).
"""

from datetime import datetime, UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, desc, and_

from src.db import AsyncSessionFactory
from src.models import AlarmEvent, Instrument, Reading
from src.auth import require_auth

router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Instrumentos
# ---------------------------------------------------------------------------

@router.get("/instruments")
async def list_instruments() -> list[dict]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Instrument).where(Instrument.enabled.is_(True))
            .order_by(Instrument.name)
        )
        instruments = result.scalars().all()
        return [
            {
                "id":             i.id,
                "sitrad_id":      i.sitrad_id,
                "name":           i.name,
                "address":        i.address,
                "converter_name": i.converter_name,
                "model_id":       i.model_id,
                "model_name":     i.model_name,
                "source":         i.source,
                "status":         i.status,
                "last_seen":      i.last_seen.isoformat() if i.last_seen else None,
            }
            for i in instruments
        ]


# ---------------------------------------------------------------------------
# Overview — resumo de todos os instrumentos (tela inicial)
# ---------------------------------------------------------------------------

@router.get("/overview")
async def get_overview() -> list[dict]:
    """
    Retorna resumo de todos os instrumentos para a tela inicial.
    Uma chamada só para montar todos os cards.
    """
    async with AsyncSessionFactory() as session:
        instr_result = await session.execute(
            select(Instrument).where(Instrument.enabled.is_(True)).order_by(Instrument.name)
        )
        instruments = instr_result.scalars().all()

        overview = []
        now = datetime.now(UTC)

        for instr in instruments:
            # Última leitura
            r_result = await session.execute(
                select(Reading)
                .where(Reading.instrument_id == instr.id)
                .order_by(desc(Reading.timestamp))
                .limit(1)
            )
            reading = r_result.scalar_one_or_none()

            # Alarmes ativos
            alm_result = await session.execute(
                select(AlarmEvent)
                .where(AlarmEvent.instrument_id == instr.id, AlarmEvent.is_active.is_(True))
                .order_by(AlarmEvent.started_at)
            )
            active_alarms = alm_result.scalars().all()

            # Último alarme resolvido (para tempo médio de correção)
            resolved_result = await session.execute(
                select(AlarmEvent)
                .where(
                    AlarmEvent.instrument_id == instr.id,
                    AlarmEvent.is_active.is_(False),
                    AlarmEvent.cleared_at.isnot(None),
                )
                .order_by(desc(AlarmEvent.cleared_at))
                .limit(5)
            )
            resolved_alarms = resolved_result.scalars().all()

            # Calcula métricas
            age_s  = (now - reading.timestamp.replace(tzinfo=UTC)).total_seconds() if reading else 9999
            online = age_s < 90

            # Tempo em alarme (alarme mais antigo ativo)
            alarm_duration_min = None
            if active_alarms:
                oldest = min(active_alarms, key=lambda a: a.started_at)
                alarm_duration_min = int((now - oldest.started_at.replace(tzinfo=UTC)).total_seconds() / 60)

            # Tempo médio de correção (dos últimos resolvidos)
            avg_fix_min = None
            fix_times = []
            for a in resolved_alarms:
                if a.cleared_at and a.started_at:
                    delta = (a.cleared_at.replace(tzinfo=UTC) - a.started_at.replace(tzinfo=UTC)).total_seconds() / 60
                    if delta > 0:
                        fix_times.append(delta)
            if fix_times:
                avg_fix_min = round(sum(fix_times) / len(fix_times))

            # Valores chave por modelo
            sensors = {}
            if reading:
                is_pct = (instr.model_id == 117)
                if is_pct:
                    sensors = {
                        "p1":        reading.p1,
                        "p2":        reading.p2,
                        "t1":        reading.t1,
                        "t3":        reading.t3,
                        "superheat": reading.superheat,
                        "t_sat_p1":  reading.t_sat_p1,
                    }
                else:
                    sensors = {
                        "t1":      reading.t1,
                        "t2":      reading.t2,
                        "t3":      reading.t3,
                        "setpoint": reading.setpoint,
                    }

            overview.append({
                "id":           instr.id,
                "name":         instr.name,
                "address":      instr.address,
                "model_id":     instr.model_id,
                "model_name":   instr.model_name,
                "source":       instr.source,
                "status":       instr.status,
                "online":       online,
                "age_s":        round(age_s),
                "last_seen":    reading.timestamp.isoformat() if reading else None,
                "process_text": reading.process_text if reading else None,
                "sensors":      sensors,
                "outputs": {
                    "refrigeration": reading.out_refrigeration if reading else None,
                    "fan":           reading.out_fan           if reading else None,
                    "defrost":       reading.out_defrost       if reading else None,
                } if reading else {},
                "alarm_count":        len(active_alarms),
                "alarm_duration_min": alarm_duration_min,
                "active_alarms":      [
                    {"code": a.code, "description": a.description, "severity": a.severity}
                    for a in active_alarms
                ],
                "avg_fix_min":        avg_fix_min,
                "has_data":           reading is not None,
            })

        return overview


# ---------------------------------------------------------------------------
# Leitura atual (última coletada)
# ---------------------------------------------------------------------------

@router.get("/instruments/{instrument_id}/state")
async def get_instrument_state(instrument_id: int) -> dict:
    async with AsyncSessionFactory() as session:
        instr = await session.get(Instrument, instrument_id)
        if not instr:
            raise HTTPException(status_code=404, detail="Instrumento não encontrado")

        # Última leitura
        result = await session.execute(
            select(Reading)
            .where(Reading.instrument_id == instrument_id)
            .order_by(desc(Reading.timestamp))
            .limit(1)
        )
        reading = result.scalar_one_or_none()
        if not reading:
            raise HTTPException(status_code=404, detail="Nenhuma leitura disponível")

        # Alarmes ativos
        alm_result = await session.execute(
            select(AlarmEvent)
            .where(
                AlarmEvent.instrument_id == instrument_id,
                AlarmEvent.is_active.is_(True),
            )
            .order_by(desc(AlarmEvent.started_at))
        )
        active_alarms = alm_result.scalars().all()

        # Calcula se está online (última leitura < 90s atrás)
        age_s = (datetime.now(UTC) - reading.timestamp.replace(tzinfo=UTC)).total_seconds()
        online = age_s < 90

        return {
            "instrument": {
                "id":         instr.id,
                "name":       instr.name,
                "address":    instr.address,
                "status":     instr.status,
                "online":     online,
                "model_id":   instr.model_id,
                "model_name": instr.model_name,
                "source":     instr.source,
            },
            "timestamp": reading.timestamp.isoformat(),

            # Sensores de temperatura (todos os modelos)
            "sensors": {
                "t1": reading.t1,
                "t2": reading.t2,
                "t3": reading.t3,
                "t4": reading.t4,
            },

            # Pressões e termodinâmica (PCT series)
            "refrigeration": {
                "p1":       reading.p1,
                "p2":       reading.p2,
                "t_sat_p1": reading.t_sat_p1,
                "t_sat_p2": reading.t_sat_p2,
                "superheat":  reading.superheat,
                "subcooling": reading.subcooling,
                "an1_pct":  reading.an1_pct,
                "an2_pct":  reading.an2_pct,
            },

            "control": {
                "setpoint":       reading.setpoint,
                "differential":   reading.differential,
                "process_status": reading.process_status,
                "process_text":   reading.process_text,
            },
            "outputs": {
                "refrigeration": reading.out_refrigeration,
                "fan":           reading.out_fan,
                "defrost":       reading.out_defrost,
                "buzzer":        reading.out_buzzer,
            },
            "alarms": [
                {
                    "id":          a.id,
                    "code":        a.code,
                    "description": a.description,
                    "severity":    a.severity,
                    "started_at":  a.started_at.isoformat(),
                    "assumed_by":  a.assumed_by,
                    "assumed_at":  a.assumed_at.isoformat() if a.assumed_at else None,
                }
                for a in active_alarms
            ],
            "modes": {
                "fast_freezing": reading.fast_freezing,
                "economic_mode": reading.economic_mode,
            },
            "sensor_errors": {
                "s1": reading.err_s1,
                "s2": reading.err_s2,
                "s3": reading.err_s3,
            },
        }


# ---------------------------------------------------------------------------
# Histórico de leituras (para gráficos)
# ---------------------------------------------------------------------------

@router.get("/instruments/{instrument_id}/history")
async def get_history(instrument_id: int, limit: int = 120) -> list[dict]:
    limit = min(limit, 1440)
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Reading)
            .where(Reading.instrument_id == instrument_id)
            .order_by(desc(Reading.timestamp))
            .limit(limit)
        )
        readings = list(reversed(result.scalars().all()))
        return [
            {
                "timestamp":  r.timestamp.isoformat(),
                "t1": r.t1,
                "t2": r.t2,
                "t3": r.t3,
                "t4": r.t4,
                "p1": r.p1,
                "p2": r.p2,
                "t_sat_p1": r.t_sat_p1,
                "t_sat_p2": r.t_sat_p2,
                "superheat":  r.superheat,
                "subcooling": r.subcooling,
                "setpoint": r.setpoint,
                "out_refrigeration": r.out_refrigeration,
                "out_fan":    r.out_fan,
                "out_defrost": r.out_defrost,
            }
            for r in readings
        ]


# ---------------------------------------------------------------------------
# Histórico de alarmes
# ---------------------------------------------------------------------------

@router.get("/instruments/{instrument_id}/alarms/history")
async def get_alarm_history(instrument_id: int, limit: int = 50) -> list[dict]:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(AlarmEvent)
            .where(AlarmEvent.instrument_id == instrument_id)
            .order_by(desc(AlarmEvent.started_at))
            .limit(limit)
        )
        alarms = result.scalars().all()
        return [
            {
                "id":          a.id,
                "code":        a.code,
                "description": a.description,
                "severity":    a.severity,
                "started_at":  a.started_at.isoformat(),
                "cleared_at":  a.cleared_at.isoformat() if a.cleared_at else None,
                "is_active":   a.is_active,
            }
            for a in alarms
        ]


# ---------------------------------------------------------------------------
# Log global de ocorrências (overview — painel inferior)
# ---------------------------------------------------------------------------

@router.get("/alarm-log")
async def get_alarm_log(limit: int = 30) -> list[dict]:
    """
    Retorna os últimos eventos de alarme de todos os instrumentos,
    com nome do instrumento, para o painel de ocorrências do overview.
    """
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(AlarmEvent, Instrument)
            .join(Instrument, AlarmEvent.instrument_id == Instrument.id)
            .where(Instrument.enabled.is_(True))
            .order_by(desc(AlarmEvent.started_at))
            .limit(limit)
        )
        rows = result.all()
        return [
            {
                "id":              a.id,
                "instrument_id":   a.instrument_id,
                "instrument_name": i.name,
                "code":            a.code,
                "description":     a.description,
                "severity":        a.severity,
                "is_active":       a.is_active,
                "started_at":      a.started_at.isoformat(),
                "cleared_at":      a.cleared_at.isoformat() if a.cleared_at else None,
                "assumed_by":      a.assumed_by,
                "assumed_at":      a.assumed_at.isoformat() if a.assumed_at else None,
            }
            for a, i in rows
        ]


# ---------------------------------------------------------------------------
# Aceite de atendimento
# ---------------------------------------------------------------------------

@router.post("/alarms/{alarm_id}/assume")
async def assume_alarm(alarm_id: int, body: dict) -> dict:
    """Registra que um técnico assumiu o atendimento do alarme."""
    technician = (body.get("technician") or "").strip()
    if not technician:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Nome do técnico obrigatório")

    async with AsyncSessionFactory() as session:
        alarm = await session.get(AlarmEvent, alarm_id)
        if not alarm:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Alarme não encontrado")

        alarm.assumed_by = technician
        alarm.assumed_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(alarm)

        return {
            "id":          alarm.id,
            "assumed_by":  alarm.assumed_by,
            "assumed_at":  alarm.assumed_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Relatório PDF de conformidade
# ---------------------------------------------------------------------------

@router.get("/instruments/{instrument_id}/report")
async def get_report(
    instrument_id: int,
    hours: int = Query(default=24, ge=1, le=720, description="Período em horas (1–720)"),
    company: str = Query(default="[PROPONENTE]", description="Nome da empresa"),
    operator: str = Query(default="Sistema Automático", description="Nome do operador"),
) -> Response:
    """Gera e retorna relatório PDF de conformidade para download."""
    from src.report import generate_pdf
    import asyncio

    async with AsyncSessionFactory() as session:
        instr = await session.get(Instrument, instrument_id)
        if not instr:
            raise HTTPException(status_code=404, detail="Instrumento não encontrado")

        period_end   = datetime.now(UTC)
        period_start = period_end - timedelta(hours=hours)

        # Leituras do período (máx 2880 = 24h × 2/min)
        result = await session.execute(
            select(Reading)
            .where(
                and_(
                    Reading.instrument_id == instrument_id,
                    Reading.timestamp >= period_start,
                )
            )
            .order_by(Reading.timestamp)
            .limit(2880)
        )
        readings_orm = result.scalars().all()

        # Alarmes do período
        alm_result = await session.execute(
            select(AlarmEvent)
            .where(
                and_(
                    AlarmEvent.instrument_id == instrument_id,
                    AlarmEvent.started_at >= period_start,
                )
            )
            .order_by(desc(AlarmEvent.started_at))
        )
        alarms_orm = alm_result.scalars().all()

    # Serializa para dicts simples
    readings_data = [
        {
            "timestamp":  r.timestamp.isoformat(),
            "t1": r.t1, "t2": r.t2, "t3": r.t3, "t4": r.t4,
            "p1": r.p1, "p2": r.p2,
            "t_sat_p1": r.t_sat_p1, "t_sat_p2": r.t_sat_p2,
            "superheat": r.superheat, "subcooling": r.subcooling,
            "setpoint":  r.setpoint,
            "out_refrigeration": r.out_refrigeration,
        }
        for r in readings_orm
    ]

    alarms_data = [
        {
            "code":        a.code,
            "description": a.description,
            "severity":    a.severity,
            "started_at":  a.started_at.isoformat(),
            "cleared_at":  a.cleared_at.isoformat() if a.cleared_at else None,
            "is_active":   a.is_active,
        }
        for a in alarms_orm
    ]

    instrument_data = {
        "id":         instr.id,
        "name":       instr.name,
        "address":    instr.address,
        "model_id":   instr.model_id,
        "model_name": instr.model_name,
        "source":     instr.source,
    }

    # Gera PDF em thread (matplotlib/reportlab não são async)
    pdf_bytes = await asyncio.to_thread(
        generate_pdf,
        instrument_data,
        readings_data,
        alarms_data,
        period_start,
        period_end,
        company,
        operator,
    )

    filename = (f"conformidade_{instr.name.replace(' ', '_')}_"
                f"{period_start.strftime('%Y%m%d_%H%M')}.pdf")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Dashboard configurado — combina config do cliente + overview ao vivo
# ---------------------------------------------------------------------------

@router.get("/dashboard")
async def get_dashboard() -> dict:
    """
    Retorna estrutura completa para o dashboard:
    config do cliente + grupos + dados ao vivo de cada instrumento.
    """
    from src.config_loader import load_config, merge_config_com_overview

    # Reutiliza lógica do overview
    overview = await get_overview()
    cfg = load_config()
    return merge_config_com_overview(cfg, overview)


@router.get("/client-config")
async def get_client_config() -> dict:
    from src.config_loader import load_config
    return load_config()


@router.post("/client-config")
async def save_client_config(body: dict) -> dict:
    from src.config_loader import save_config
    save_config(body)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
