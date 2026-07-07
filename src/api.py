"""
api.py — Endpoints FastAPI para o dashboard
Suporta TC-900E (temperatura) e PCT-122E Plus (refrigeração com pressão).
"""

from datetime import datetime, UTC, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select, desc, and_, delete

from src.db import AsyncSessionFactory
from src.models import AlarmEvent, Instrument, Reading
from src.auth import require_auth, require_admin
from src.diagnostico import diagnostico_para

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

            # Valores presentes na leitura — genérico para qualquer modelo:
            # o card/modal exibem o que existir (pressões só aparecem se o
            # instrumento tiver transdutores, independente do model_id).
            sensors = {}
            if reading:
                campos = (
                    "t1", "t2", "t3", "t4",
                    "p1", "p2",
                    "superheat", "subcooling",
                    "t_sat_p1", "t_sat_p2",
                    "setpoint",
                    "an1_pct", "an2_pct",
                )
                sensors = {
                    c: valor for c in campos
                    if (valor := getattr(reading, c)) is not None
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
                    {
                        "code": a.code,
                        "description": a.description,
                        "severity": a.severity,
                        **(diagnostico_para(a.code) or {}),
                    }
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


@router.get("/tecnicos")
async def list_tecnicos() -> list[str]:
    """Lista de técnicos disponíveis para atribuição (client_config.json)."""
    from src.auth import _load_config
    cfg = _load_config()
    tecnicos = cfg.get("tecnicos") or []
    if not tecnicos:
        tecnicos = ["Técnico de Plantão"]
    return tecnicos


@router.post("/alarms/{alarm_id}/validate", dependencies=[Depends(require_admin)])
async def validate_alarm_diagnosis(alarm_id: int, body: dict) -> dict:
    """
    Registra a validação do diagnóstico da IA pelo técnico responsável.
    body: {"correto": bool, "causa_real": str (obrigatória se correto=False)}
    Alimenta também a memória de aprendizado (diagnosis_cases).
    """
    correto = body.get("correto")
    causa_real = (body.get("causa_real") or "").strip() or None
    if correto is None:
        raise HTTPException(status_code=422, detail="Campo 'correto' obrigatório")
    if correto is False and not causa_real:
        raise HTTPException(status_code=422, detail="Informe a causa real quando o diagnóstico está incorreto")

    async with AsyncSessionFactory() as session:
        alarm = await session.get(AlarmEvent, alarm_id)
        if not alarm:
            raise HTTPException(status_code=404, detail="Alarme não encontrado")
        if not alarm.assumed_by:
            raise HTTPException(status_code=422, detail="Atribua um responsável antes de validar o diagnóstico")

        alarm.diagnostico_correto = bool(correto)
        alarm.causa_real = causa_real
        alarm.avaliado_em = datetime.now(UTC)

        # Memória de aprendizado — caso confirmado vira dataset
        from src.models import DiagnosisCase
        diag = diagnostico_para(alarm.code) or {}
        instr = await session.get(Instrument, alarm.instrument_id)
        session.add(DiagnosisCase(
            instrument_id=alarm.instrument_id,
            instrument_name=instr.name if instr else "?",
            ai_diagnosis=diag.get("problema") or alarm.description,
            ai_cause="; ".join(diag.get("causas", [])[:2]) or None,
            confirmed=True,
            ai_was_correct=bool(correto),
            confirmed_cause=causa_real,
            confirmed_by=alarm.assumed_by,
            confirmed_at=datetime.now(UTC),
        ))
        await session.commit()

        return {
            "id": alarm.id,
            "diagnostico_correto": alarm.diagnostico_correto,
            "causa_real": alarm.causa_real,
        }


@router.get("/alarms/recent")
async def recent_alarms(limit: int = Query(default=15, ge=1, le=100)) -> dict:
    """
    Ocorrências recentes (ativas primeiro) com estado do fluxo de atendimento
    e diagnóstico da IA, + estatística de acerto dos diagnósticos validados.
    """
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(AlarmEvent, Instrument.name)
            .join(Instrument, Instrument.id == AlarmEvent.instrument_id)
            .order_by(desc(AlarmEvent.is_active), desc(AlarmEvent.started_at))
            .limit(limit)
        )
        rows = result.all()

        # Estatística de acerto da IA (todos os alarmes já validados)
        stats_result = await session.execute(
            select(AlarmEvent.diagnostico_correto)
            .where(AlarmEvent.diagnostico_correto.is_not(None))
        )
        validados = [r[0] for r in stats_result.all()]
        total_validados = len(validados)
        acertos = sum(1 for v in validados if v)

        alarms = []
        for alarm, instr_name in rows:
            diag = diagnostico_para(alarm.code) or {}
            alarms.append({
                "id":          alarm.id,
                "instrument":  instr_name,
                "code":        alarm.code,
                "description": alarm.description,
                "severity":    alarm.severity,
                "is_active":   alarm.is_active,
                "started_at":  alarm.started_at.isoformat() if alarm.started_at else None,
                "cleared_at":  alarm.cleared_at.isoformat() if alarm.cleared_at else None,
                "assumed_by":  alarm.assumed_by,
                "diagnostico_correto": alarm.diagnostico_correto,
                "causa_real":  alarm.causa_real,
                "problema":    diag.get("problema"),
                "causas":      diag.get("causas"),
                "acoes":       diag.get("acoes"),
            })

        return {
            "alarms": alarms,
            "ia_stats": {
                "validados": total_validados,
                "acertos":   acertos,
                "pct":       round(acertos / total_validados * 100) if total_validados else None,
            },
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
# Admin — ferramentas de demonstração (somente admin)
# ---------------------------------------------------------------------------

@router.post("/admin/collect-now", dependencies=[Depends(require_admin)])
async def admin_collect_now() -> dict:
    """Dispara coleta imediata sem aguardar o próximo ciclo do scheduler."""
    import asyncio
    from src.collector import _collect_all
    asyncio.create_task(_collect_all())
    return {"status": "triggered", "timestamp": datetime.now(UTC).isoformat()}


@router.post("/admin/fault/clear", dependencies=[Depends(require_admin)])
async def admin_fault_clear() -> dict:
    """Remove todas as falhas simuladas — emulador volta à operação normal."""
    import asyncio
    from src import emulator_client as emu
    for addr in emu.EMULATOR_ADDRESSES:
        await asyncio.to_thread(emu.clear_all_faults, addr)
    return {"status": "normalizado"}


@router.post("/admin/fault/{cenario}", dependencies=[Depends(require_admin)])
async def admin_fault_scenario(cenario: str) -> dict:
    """
    Aplica um cenário de falha simulada no controlador EMULADO.
    Atua exclusivamente na API do emulador (porta 8000) — instrumentos
    reais do Sitrad são somente leitura e não podem ser afetados.
    """
    import asyncio
    from src import emulator_client as emu
    from src.fault_scenarios import FAULT_SCENARIOS

    sc = FAULT_SCENARIOS.get(cenario)
    if sc is None:
        raise HTTPException(status_code=404, detail=f"Cenário '{cenario}' não existe")

    for addr in emu.EMULATOR_ADDRESSES:
        # Limpa falhas anteriores para os cenários não se sobreporem
        await asyncio.to_thread(emu.clear_all_faults, addr)
        for campo, valor in sc["campos"].items():
            await asyncio.to_thread(emu.inject_fault, addr, campo, valor)

    return {"status": "aplicado", "cenario": sc["nome"], "descricao": sc["descricao"]}


@router.get("/admin/fault-scenarios", dependencies=[Depends(require_admin)])
async def admin_list_scenarios() -> list[dict]:
    """Lista os cenários de falha disponíveis para o painel admin."""
    from src.fault_scenarios import FAULT_SCENARIOS
    return [
        {"id": k, "nome": v["nome"], "descricao": v["descricao"]}
        for k, v in FAULT_SCENARIOS.items()
    ]


@router.post("/admin/analise-geral", dependencies=[Depends(require_admin)])
async def admin_analise_geral() -> dict:
    """
    Análise geral do sistema com IA: coleta o estado consolidado de todos
    os instrumentos (leituras, tendências 60min, alarmes, casos validados)
    e retorna um parecer técnico. Fallback por regras se a IA estiver
    indisponível.
    """
    from src.analise_geral import executar_analise
    return await executar_analise()


@router.post("/admin/clear-history", dependencies=[Depends(require_admin)])
async def admin_clear_history() -> dict:
    """Apaga readings e alarm_events; mantém a tabela de instrumentos intacta."""
    async with AsyncSessionFactory() as session:
        await session.execute(delete(AlarmEvent))
        await session.execute(delete(Reading))
        await session.commit()
    return {"status": "cleared", "timestamp": datetime.now(UTC).isoformat()}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
