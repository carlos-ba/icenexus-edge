"""
demo.py — Módulo de demonstração para apresentação comercial
Fornece:
  - Injeção de falhas no emulador PCT-122E (em tempo real)
  - Análise por IA (Claude API) do estado atual do instrumento
  - Reset para estado normal
"""

import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, UTC

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, desc

from src.db import AsyncSessionFactory
from src.models import Instrument, Reading, AlarmEvent, DiagnosisCase
from src.knowledge_base import build_knowledge_context
from src.emulator_client import get_state as get_emulator_state

logger = logging.getLogger("coletor.demo")

router = APIRouter(prefix="/api/v1/demo", tags=["Demo"])

EMULATOR_URL   = "http://localhost:8000"
EMULATOR_ADDR  = 10

# ── Definição das falhas simuláveis ───────────────────────────────────────────
FAULTS = {
    "high_discharge_pressure": {
        "label":       "Alta Pressão de Descarga",
        "description": "P2 acima do limite máximo — condensador sobrecarregado",
        "icon":        "🔴",
        "severity":    "critical",
        "params":      {"F36": 390.0},   # P2 setpoint → acima do alarme F79=360
        "hint":        "Causa típica: condensador sujo, falha no ventilador de condensação ou alta temperatura ambiente.",
    },
    "low_suction_pressure": {
        "label":       "Baixa Pressão de Sucção",
        "description": "P1 abaixo do limite mínimo — possível falta de gás",
        "icon":        "🔴",
        "severity":    "critical",
        "params":      {"F06": 4.0},     # P1 setpoint → abaixo do alarme F76=8
        "hint":        "Causa típica: vazamento de gás refrigerante ou restrição na linha de sucção.",
    },
    "high_superheat": {
        "label":       "Superaquecimento Excessivo",
        "description": "SH > 15K — válvula de expansão com defeito ou falta de gás",
        "icon":        "🟡",
        "severity":    "warning",
        "params":      {"F12": -8.0},    # T1 sobe → SH = T1 - Tsat_p1 ≈ 21K
        "hint":        "Causa típica: válvula de expansão travada fechada, filtro secador entupido ou carga baixa de gás.",
    },
    "high_chamber_temp": {
        "label":       "Câmara Fora de Temperatura",
        "description": "T3 acima do setpoint operacional — risco de conformidade ANVISA",
        "icon":        "🟡",
        "severity":    "warning",
        "params":      {},               # nenhum parâmetro — T3 usa override direto de sensor
        "overrides":   {"t3": -5.0},    # força T3 a -5°C via mecanismo de injeção de falha
        "hint":        "Causa típica: porta aberta por período prolongado, falha no isolamento ou compressor não acionando.",
    },
    "gas_loss_critical": {
        "label":       "Perda Crítica de Gás",
        "description": "P1 próximo de zero — perda total de carga de refrigerante",
        "icon":        "🔴",
        "severity":    "critical",
        "params":      {"F06": 1.5, "F12": 10.0},  # P1 quase zero + T1 alta
        "hint":        "Situação crítica: perda total de gás refrigerante. Sistema sem capacidade de refrigeração. Intervenção imediata necessária.",
    },
}

# Parâmetros normais para reset
NORMAL_PARAMS = {
    "F06":  15.5,    # P1 sucção normal
    "F36": 260.8,    # P2 descarga normal
    "F12": -22.3,    # T1 gás sucção normal
    "F43": -18.0,    # T3 câmara normal
    "F44": -28.0,    # T4 aletado normal
    "F41":  70.0,    # T2 descarga normal
}


# ── Helpers HTTP emulador ─────────────────────────────────────────────────────

def _patch_param(code: str, value: float) -> dict:
    url = f"{EMULATOR_URL}/api/v1/controllers/{EMULATOR_ADDR}/parameters/{code}?value={value}"
    req = urllib.request.Request(url, method="PATCH")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _inject_sensor_override(field: str, value: float) -> dict:
    url = f"{EMULATOR_URL}/api/v1/controllers/{EMULATOR_ADDR}/fault?field={field}&value={value}"
    req = urllib.request.Request(url, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _clear_sensor_override(field: str) -> dict:
    url = f"{EMULATOR_URL}/api/v1/controllers/{EMULATOR_ADDR}/fault/{field}"
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _get_emulator_state() -> dict:
    url = f"{EMULATOR_URL}/api/v1/controllers/{EMULATOR_ADDR}/state"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/faults")
async def list_faults() -> list[dict]:
    """Lista todas as falhas disponíveis para simulação."""
    return [
        {
            "id":          fault_id,
            "label":       f["label"],
            "description": f["description"],
            "icon":        f["icon"],
            "severity":    f["severity"],
        }
        for fault_id, f in FAULTS.items()
    ]


@router.post("/fault/{fault_id}")
async def inject_fault(fault_id: str) -> dict:
    """Injeta uma falha no emulador alterando parâmetros em tempo real."""
    if fault_id not in FAULTS:
        raise HTTPException(status_code=404, detail=f"Falha '{fault_id}' não encontrada")

    fault = FAULTS[fault_id]
    results = {}
    for code, value in fault["params"].items():
        try:
            results[code] = _patch_param(code, value)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao injetar parâmetro {code}: {e}")
    for field, value in fault.get("overrides", {}).items():
        try:
            results[field] = _inject_sensor_override(field, value)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Erro ao forçar sensor {field}: {e}")

    logger.warning("DEMO — Falha injetada: %s (%s)", fault["label"], fault_id)

    return {
        "ok":          True,
        "fault_id":    fault_id,
        "label":       fault["label"],
        "description": fault["description"],
        "severity":    fault["severity"],
        "hint":        fault["hint"],
        "params_set":  results,
        "message":     f"Falha '{fault['label']}' injetada. Aguarde ~30s para ver o efeito completo no dashboard.",
    }


@router.post("/reset")
async def reset_normal() -> dict:
    """Restaura todos os parâmetros para valores normais de operação."""
    results = {}
    for code, value in NORMAL_PARAMS.items():
        try:
            results[code] = _patch_param(code, value)
        except Exception as e:
            logger.error("Erro ao resetar %s: %s", code, e)
    # Limpa todos os overrides de sensor que qualquer falha possa ter injetado
    all_overrides = {field for f in FAULTS.values() for field in f.get("overrides", {})}
    for field in all_overrides:
        try:
            _clear_sensor_override(field)
        except Exception as e:
            logger.error("Erro ao limpar override %s: %s", field, e)

    logger.info("DEMO — Sistema normalizado")
    return {
        "ok":      True,
        "message": "Sistema normalizado. Aguarde ~30s para retorno aos valores normais.",
        "params_reset": list(NORMAL_PARAMS.keys()),
    }


@router.post("/cases/{case_id}/confirm")
async def confirm_diagnosis(case_id: int, payload: dict = None) -> dict:
    if payload is None:
        payload = {}
    """
    Técnico confirma ou corrige o diagnóstico da IA.
    Salva o caso confirmado para alimentar diagnósticos futuros.
    """
    async with AsyncSessionFactory() as session:
        case = await session.get(DiagnosisCase, case_id)
        if not case:
            raise HTTPException(status_code=404, detail="Caso não encontrado")

        case.confirmed       = True
        case.ai_was_correct  = payload.get("ai_was_correct", True)
        case.confirmed_cause = payload.get("confirmed_cause") or case.ai_cause
        case.resolution      = payload.get("resolution")
        case.outcome         = payload.get("outcome")
        case.confirmed_by    = payload.get("confirmed_by", "Técnico")
        case.confirmed_at    = datetime.now(UTC)

        await session.commit()
        logger.info("Caso #%d confirmado por %s — IA correta: %s",
                    case_id, case.confirmed_by, case.ai_was_correct)

    return {"ok": True, "case_id": case_id,
            "message": "Diagnóstico confirmado. Obrigado! A IA aprenderá com este caso."}


@router.get("/cases")
async def list_cases(instrument_id: int | None = None, limit: int = 20) -> list[dict]:
    """Lista casos confirmados — memória operacional da IA."""
    async with AsyncSessionFactory() as session:
        query = select(DiagnosisCase).where(DiagnosisCase.confirmed.is_(True))
        if instrument_id:
            query = query.where(DiagnosisCase.instrument_id == instrument_id)
        query = query.order_by(desc(DiagnosisCase.confirmed_at)).limit(limit)
        result = await session.execute(query)
        cases = result.scalars().all()

    return [
        {
            "id":             c.id,
            "instrument":     c.instrument_name,
            "occurred_at":    c.occurred_at.strftime("%d/%m/%Y %H:%M"),
            "ai_status":      c.ai_status,
            "ai_cause":       c.ai_cause,
            "confirmed_cause": c.confirmed_cause,
            "ai_was_correct": c.ai_was_correct,
            "resolution":     c.resolution,
            "outcome":        c.outcome,
            "confirmed_by":   c.confirmed_by,
        }
        for c in cases
    ]


@router.post("/analyze/{instrument_id}")
async def analyze_with_ai(instrument_id: int) -> dict:
    """
    Envia estado atual do instrumento + histórico recente para Claude API.
    Para instrumentos do emulador: sempre lê o estado AO VIVO antes de analisar,
    garantindo que falhas recém-injetadas sejam capturadas imediatamente.
    """
    # Busca instrumento e últimas leituras
    async with AsyncSessionFactory() as session:
        instr = await session.get(Instrument, instrument_id)
        if not instr:
            raise HTTPException(status_code=404, detail="Instrumento não encontrado")

        # Últimas 10 leituras do banco (tendência histórica)
        result = await session.execute(
            select(Reading)
            .where(Reading.instrument_id == instrument_id)
            .order_by(desc(Reading.timestamp))
            .limit(10)
        )
        readings = list(reversed(result.scalars().all()))

        # Alarmes ativos
        alm_result = await session.execute(
            select(AlarmEvent)
            .where(
                AlarmEvent.instrument_id == instrument_id,
                AlarmEvent.is_active.is_(True),
            )
        )
        active_alarms = alm_result.scalars().all()

    if not readings:
        raise HTTPException(status_code=404, detail="Nenhuma leitura disponível")

    # ── Para emulador: sobrescreve "latest" com estado AO VIVO ──
    # Garante que falhas recém-injetadas sejam analisadas corretamente,
    # sem depender do ciclo de 30s do coletor
    live_state = None
    if instr.source == "emulator":
        try:
            live_state = await asyncio.to_thread(get_emulator_state, instr.address)
            logger.info("Estado ao vivo do emulador capturado para análise: addr=%d", instr.address)
        except Exception as e:
            logger.warning("Não foi possível ler estado ao vivo do emulador: %s", e)

    latest = readings[-1]

    # Carrega casos confirmados (memória operacional)
    async with AsyncSessionFactory() as session:
        cases_result = await session.execute(
            select(DiagnosisCase)
            .where(DiagnosisCase.confirmed.is_(True))
            .order_by(desc(DiagnosisCase.confirmed_at))
            .limit(10)
        )
        confirmed_cases = [
            {
                "occurred_at":    c.occurred_at.strftime("%d/%m/%Y %H:%M"),
                "instrument_name": c.instrument_name,
                "symptom_summary": c.symptom_summary,
                "ai_diagnosis":    c.ai_diagnosis,
                "confirmed_cause": c.confirmed_cause,
                "resolution":      c.resolution,
                "outcome":         c.outcome,
            }
            for c in cases_result.scalars().all()
        ]

    # Base de conhecimento técnico
    knowledge = build_knowledge_context(
        model_id=instr.model_id,
        confirmed_cases=confirmed_cases if confirmed_cases else None
    )

    # ── Monta "latest" — usa estado ao vivo se disponível ──────
    # Isso garante que a IA sempre analisa o estado ATUAL do equipamento,
    # não o último salvo no banco (que pode ter até 30s de atraso)
    if live_state:
        # Cria objeto "latest" virtual com dados ao vivo do emulador
        class LiveReading:
            pass
        latest = LiveReading()
        latest.p1        = live_state.get("p1")
        latest.p2        = live_state.get("p2")
        latest.t1        = live_state.get("t1")
        latest.t2        = live_state.get("t2")
        latest.t3        = live_state.get("t3")
        latest.t4        = live_state.get("t4")
        latest.t_sat_p1  = live_state.get("t_sat_p1")
        latest.t_sat_p2  = live_state.get("t_sat_p2")
        latest.superheat = live_state.get("superheat")
        latest.subcooling= live_state.get("subcooling")
        latest.out_refrigeration = live_state.get("out1")
        latest.out_fan           = live_state.get("out2")
        latest.out_defrost       = live_state.get("out3")
        latest.timestamp = datetime.now(UTC)
        live_label = "⚡ AO VIVO (direto do emulador)"
    else:
        latest     = readings[-1]
        live_label = "📂 Banco de dados (última leitura coletada)"

    # ── Detecta se é modo simulação (emulador com leitura ao vivo) ──
    is_simulation = instr.source == "emulator" and live_state is not None

    alarm_list = [
        f"{a.severity.upper()}: {a.description} (código {a.code})"
        for a in active_alarms
    ]

    if is_simulation:
        # Modo simulação: analisa APENAS os valores atuais como condição real estabelecida.
        # Não inclui série histórica para evitar que a IA detecte a "transição" e confunda
        # mudança abrupta com falha de sonda.
        prompt = f"""Você é um engenheiro especialista em sistemas de refrigeração industrial.
Use a base de conhecimento técnico abaixo para embasar seu diagnóstico.

{knowledge}

═══════════════════════════════════════════════════════
⚠️  MODO SIMULAÇÃO DE FALHAS  ⚠️
Este equipamento está em ambiente de TESTE/DEMONSTRAÇÃO.
Os valores abaixo representam uma CONDIÇÃO REAL SIMULADA — trate-os como se o
equipamento estivesse operando NESSE ESTADO HÁ TEMPO SUFICIENTE para ser uma
condição estabelecida (steady-state). NÃO considere transições ou variações
anteriores. Analise SOMENTE o estado atual e identifique a causa operacional
mais provável para esses valores.
═══════════════════════════════════════════════════════

INSTRUMENTO: {instr.name} | Endereço RS-485: {instr.address} | Refrigerante: R404A

ESTADO ATUAL (condição estabelecida para análise):
- P1 (sucção): {latest.p1} PSIG  |  Tsat P1: {latest.t_sat_p1} °C
- P2 (descarga): {latest.p2} PSIG  |  Tsat P2: {latest.t_sat_p2} °C
- T1 (gás de sucção): {latest.t1} °C
- T2 (gás de descarga): {latest.t2} °C
- T3 (câmara fria): {latest.t3} °C
- T4 (aletado/degelo): {latest.t4} °C
- Superaquecimento (SH): {latest.superheat} K
- Subresfriamento (SC): {latest.subcooling}
- Compressor: {"LIGADO" if latest.out_refrigeration else "DESLIGADO"}
- Ventilador: {"LIGADO" if latest.out_fan else "DESLIGADO"}
- Degelo: {"LIGADO" if latest.out_defrost else "DESLIGADO"}

ALARMES ATIVOS: {', '.join(alarm_list) if alarm_list else 'Nenhum'}

INSTRUÇÕES DE ANÁLISE:
1. Identifique qual(is) variável(is) está(ão) fora da faixa normal para R404A
2. Determine a causa operacional mais provável baseado NESSES valores (não em variações)
3. Ignore completamente o histórico de leituras — analise como snapshot de campo
4. No campo "resumo" inclua a nota: "[MODO SIMULAÇÃO — análise baseada no estado atual]"

Responda APENAS com o JSON abaixo, sem markdown:
{{
  "status_geral": "NORMAL | ATENÇÃO | CRÍTICO",
  "resumo": "1-2 frases + nota de simulação",
  "diagnostico": "Análise técnica dos valores atuais — variável(is) fora da faixa e significado físico",
  "causa_provavel": "Causa operacional mais provável para esses valores em condição estabelecida",
  "acoes_recomendadas": ["ação 1", "ação 2", "ação 3"],
  "urgencia": "Imediata | Próximas 24h | Manutenção programada",
  "risco_produto": "Alto | Médio | Baixo",
  "confianca": 0.0
}}"""

    else:
        # Modo real: inclui tendência histórica para análise de tendências
        trend_data = [
            {
                "ts": r.timestamp.strftime("%H:%M:%S"),
                "p1": r.p1, "p2": r.p2,
                "t1": r.t1, "t2": r.t2, "t3": r.t3, "t4": r.t4,
                "sh": r.superheat, "sc": r.subcooling,
            }
            for r in readings
        ]

        prompt = f"""Você é um engenheiro especialista em sistemas de refrigeração industrial.
Use a base de conhecimento técnico abaixo para embasar seu diagnóstico.

{knowledge}

═══════════════════════════════════════════════════════
INSTRUMENTO EM ANÁLISE: {instr.name} (Endereço RS-485: {instr.address})
FONTE DOS DADOS ATUAIS: {live_label}
REFRIGERANTE: R404A

ESTADO ATUAL:
- P1 (sucção): {latest.p1} PSIG  |  Tsat P1: {latest.t_sat_p1} °C
- P2 (descarga): {latest.p2} PSIG  |  Tsat P2: {latest.t_sat_p2} °C
- T1 (gás sucção): {latest.t1} °C
- T2 (gás descarga): {latest.t2} °C
- T3 (câmara fria): {latest.t3} °C
- T4 (aletado/degelo): {latest.t4} °C
- Superaquecimento (SH): {latest.superheat} K
- Subresfriamento (SC): {latest.subcooling}
- OUT1 (compressor): {"LIGADO" if latest.out_refrigeration else "DESLIGADO"}
- OUT2 (ventilador): {"LIGADO" if latest.out_fan else "DESLIGADO"}
- OUT3 (degelo): {"LIGADO" if latest.out_defrost else "DESLIGADO"}

ALARMES ATIVOS: {', '.join(alarm_list) if alarm_list else 'Nenhum'}

TENDÊNCIA (últimas {len(trend_data)} leituras):
{json.dumps(trend_data, ensure_ascii=False, indent=2)}

Forneça sua análise no seguinte formato JSON (responda APENAS com o JSON, sem markdown):
{{
  "status_geral": "NORMAL | ATENÇÃO | CRÍTICO",
  "resumo": "1-2 frases descrevendo o estado geral do sistema",
  "diagnostico": "Análise técnica detalhada do que está acontecendo",
  "causa_provavel": "A causa mais provável do estado atual",
  "acoes_recomendadas": ["ação 1", "ação 2", "ação 3"],
  "urgencia": "Imediata | Próximas 24h | Manutenção programada",
  "risco_produto": "Alto | Médio | Baixo",
  "confianca": 0.0
}}"""

    # ── Chama Claude API ou fallback local ───────────────────
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        analysis = _demo_analysis_fallback(latest, active_alarms, instr)
    else:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            analysis = json.loads(raw)
            analysis["source"] = "claude-api"
            analysis["instrument"] = instr.name
            analysis["timestamp"] = datetime.now(UTC).isoformat()
        except Exception as e:
            logger.error("Erro na chamada Claude API: %s", e)
            analysis = _demo_analysis_fallback(latest, active_alarms, instr)

    # ── Salva caso no banco para confirmação futura ───────────
    symptom = (
        f"P1={latest.p1} PSIG | P2={latest.p2} PSIG | "
        f"T3={latest.t3}°C | SH={latest.superheat}K | "
        f"Alarmes: {len(active_alarms)}"
    )
    async with AsyncSessionFactory() as session:
        case = DiagnosisCase(
            instrument_id   = instr.id,
            instrument_name = instr.name,
            ai_status       = analysis.get("status_geral"),
            ai_diagnosis    = analysis.get("diagnostico"),
            ai_cause        = analysis.get("causa_provavel"),
            symptom_summary = symptom,
            p1_at_fault     = latest.p1,
            p2_at_fault     = latest.p2,
            t3_at_fault     = latest.t3,
            sh_at_fault     = latest.superheat,
        )
        session.add(case)
        await session.commit()
        await session.refresh(case)
        analysis["case_id"] = case.id

    logger.info("Análise salva como caso #%d — status: %s",
                analysis["case_id"], analysis.get("status_geral"))
    return analysis


def _demo_analysis_fallback(reading: Reading, alarms: list, instr: "Instrument") -> dict:
    """
    Análise local baseada em regras quando API não está disponível.
    Suficiente para demo sem internet ou sem API key configurada.
    """
    issues = []   # diagnóstico: O QUE está acontecendo (valores medidos)
    causas = []   # causa_provavel: POR QUE está acontecendo (razão técnica)
    actions = []
    status = "NORMAL"
    urgency = "Manutenção programada"
    risk = "Baixo"

    p1  = reading.p1  or 0
    p2  = reading.p2  or 0
    t3  = reading.t3  or -18
    sh  = reading.superheat or 7

    # Alta pressão descarga
    if p2 > 350:
        issues.append(f"Pressão de descarga P2 em {p2:.1f} PSIG — acima do limite seguro (350 PSIG)")
        causas.append("Condensador com dissipação insuficiente: sujeira, bloqueio de ar ou ventilador com defeito")
        actions.append("Verificar limpeza do condensador (serpentina e filtros de ar)")
        actions.append("Medir temperatura ambiente na casa de máquinas")
        actions.append("Verificar funcionamento dos ventiladores do condensador")
        status = "CRÍTICO"
        urgency = "Imediata"
        risk = "Alto"

    # Baixa pressão sucção
    if p1 < 8:
        issues.append(f"Pressão de sucção P1 em {p1:.1f} PSIG — abaixo do mínimo operacional (8 PSIG)")
        causas.append("Carga de refrigerante insuficiente (vazamento) ou restrição severa na linha de sucção")
        actions.append("Verificar carga de gás refrigerante com manifold")
        actions.append("Inspecionar linha de sucção por restrições ou obstruções")
        actions.append("Checar válvula de serviço de sucção (totalmente aberta?)")
        status = "CRÍTICO"
        urgency = "Imediata"
        risk = "Alto"

    # Temperatura câmara fora do setpoint
    if t3 > -10:
        issues.append(f"Temperatura da câmara T3 em {t3:.1f}°C — acima do setpoint operacional (-18°C)")
        causas.append("Perda de capacidade de refrigeração: compressor parado, degelo excessivo ou porta com vedação comprometida")
        actions.append("Verificar integridade do isolamento e vedação de portas")
        actions.append("Confirmar se compressor está acionando normalmente")
        actions.append("Registrar desvio conforme procedimento ANVISA")
        if status != "CRÍTICO":
            status = "ATENÇÃO"
        urgency = "Próximas 24h"
        if risk == "Baixo":
            risk = "Médio"

    # Superaquecimento alto
    if sh > 14:
        issues.append(f"Superaquecimento do gás de sucção em {sh:.1f}K — acima da faixa ideal (5–10K)")
        causas.append("Válvula de expansão termostática subfechada ou filtro secador saturado impedindo fluxo adequado de refrigerante")
        actions.append("Verificar ajuste da válvula de expansão termostática (bulbo bem fixado na linha de sucção)")
        actions.append("Inspecionar filtro secador — possível saturação ou entupimento")
        actions.append("Medir pressão de sucção com manifold e comparar com tabela do R404A")
        if status == "NORMAL":
            status = "ATENÇÃO"
        if urgency == "Manutenção programada":
            urgency = "Próximas 24h"

    if not issues:
        issues.append("Todos os parâmetros dentro dos limites normais de operação")
        actions.append("Continuar monitoramento periódico")
        actions.append("Registrar leituras no plano de manutenção preventiva")
        causa = "Sistema operando normalmente com R404A — nenhuma anomalia identificada"
        resumo = f"{instr.name} operando dentro dos parâmetros normais. Nenhuma anomalia detectada."
    else:
        causa = " | ".join(causas) if causas else issues[0]
        resumo = f"{instr.name} apresenta {len(issues)} anomalia(s) detectada(s) que requerem atenção."

    return {
        "status_geral":       status,
        "resumo":             resumo,
        "diagnostico":        " | ".join(issues),
        "causa_provavel":     causa,
        "acoes_recomendadas": actions,
        "urgencia":           urgency,
        "risco_produto":      risk,
        "confianca":          0.82,
        "source":             "local-rules",
        "instrument":         instr.name,
        "timestamp":          datetime.now(UTC).isoformat(),
    }
