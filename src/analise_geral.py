"""
analise_geral.py — Análise geral do sistema com IA.

Coleta o estado consolidado de todos os instrumentos (últimas leituras,
tendências de 60 min, alarmes ativos e casos de diagnóstico validados)
e envia para o Claude com um prompt de engenheiro de refrigeração.

Fallback offline: se a API não estiver acessível (sem internet ou sem
chave), gera um parecer por regras usando a base de diagnóstico local.

Configuração da chave em client_config.json:
    "ia": { "api_key": "sk-ant-...", "model": "claude-opus-4-8" }
"""

import json
import logging
from datetime import datetime, timedelta, UTC

from sqlalchemy import select, desc

from src.db import AsyncSessionFactory
from src.models import AlarmEvent, DiagnosisCase, Instrument, Reading
from src.diagnostico import diagnostico_para

logger = logging.getLogger("analise")

_CAMPOS_TENDENCIA = ("t1", "t2", "t3", "p1", "p2", "superheat", "subcooling")

SYSTEM_PROMPT = """\
Você é um engenheiro sênior especialista em refrigeração industrial, \
responsável pela análise técnica da plataforma de monitoramento IceNexus IAR.

Você receberá um JSON com o estado consolidado de todos os instrumentos de \
uma planta de refrigeração: últimas leituras, tendências dos últimos 60 \
minutos (mínimo, máximo, média e variação), alarmes ativos e o histórico de \
diagnósticos validados pelos técnicos da planta.

Regras:
- Baseie TODA a análise exclusivamente nos dados fornecidos. Nunca invente \
valores. Se um dado não existir, diga que não está disponível.
- Considere tendências, não só valores instantâneos: uma pressão subindo \
consistentemente é um risco mesmo dentro dos limites.
- Se houver casos validados anteriores no mesmo equipamento, use-os: \
"em ocorrência anterior neste equipamento, a causa confirmada foi X".
- Unidades: pressões em PSI, temperaturas em °C, SH/SC em Kelvin (°C de diferença).
- Regra específica para racks RCK-862: avalie a temperatura de saturação da \
DESCARGA (t_sat_p2 = condensação). Acima de ~48°C o sistema está saindo da \
faixa ideal de condensação — sinalize SEMPRE como ponto a ser avaliado \
(status geral no mínimo 🟡 amarelo, item em Riscos Potenciais), recomendando \
verificação do condensador (limpeza, ventiladores, recirculação de ar) e da \
carga térmica. Acima de ~55°C trate como problema ativo (🔴). Aplique o mesmo \
raciocínio à tendência: condensação subindo consistentemente merece alerta \
mesmo abaixo do limite.
- Responda em português do Brasil, em markdown, no formato EXATO:

## 🟢/🟡/🔴 Status Geral
(uma frase objetiva sobre o estado da planta — escolha UM emoji)

## Situação por Equipamento
(um bullet por instrumento: nome — estado em uma linha)

## Problemas Detectados
(apenas se houver; para cada um: equipamento, problema, evidência numérica)

## Riscos Potenciais
(tendências que ainda não geraram alarme mas merecem atenção; se não houver, diga "Nenhum risco emergente identificado.")

## Recomendações
(lista priorizada, começando pela mais urgente; ações concretas de manutenção)

Seja conciso: gestor de manutenção lê isso em 1 minuto.\
"""


def _load_ia_config() -> dict:
    from src.auth import _load_config
    cfg = _load_config()
    return cfg.get("ia", {})


async def coletar_estado_consolidado() -> dict:
    """Monta o retrato completo da planta para análise."""
    agora = datetime.now(UTC)
    inicio_janela = agora - timedelta(minutes=60)

    async with AsyncSessionFactory() as session:
        instrumentos = (await session.execute(
            select(Instrument).where(Instrument.enabled.is_(True))
        )).scalars().all()

        estado: dict = {
            "gerado_em": agora.isoformat(),
            "janela_tendencia_min": 60,
            "instrumentos": [],
            "casos_validados": [],
        }

        for instr in instrumentos:
            leituras = (await session.execute(
                select(Reading)
                .where(
                    Reading.instrument_id == instr.id,
                    Reading.timestamp >= inicio_janela,
                )
                .order_by(Reading.timestamp)
            )).scalars().all()

            atual = leituras[-1] if leituras else None
            online = False
            if atual:
                idade = (agora - atual.timestamp.replace(tzinfo=UTC)).total_seconds()
                online = idade < 90

            tendencias = {}
            for campo in _CAMPOS_TENDENCIA:
                valores = [getattr(r, campo) for r in leituras if getattr(r, campo) is not None]
                if len(valores) >= 2:
                    tendencias[campo] = {
                        "atual":    round(valores[-1], 1),
                        "min":      round(min(valores), 1),
                        "max":      round(max(valores), 1),
                        "media":    round(sum(valores) / len(valores), 1),
                        "variacao": round(valores[-1] - valores[0], 1),
                    }

            alarmes = (await session.execute(
                select(AlarmEvent).where(
                    AlarmEvent.instrument_id == instr.id,
                    AlarmEvent.is_active.is_(True),
                )
            )).scalars().all()

            estado["instrumentos"].append({
                "nome":      instr.name,
                "modelo":    instr.model_name,
                "fonte":     "emulado" if instr.source == "emulator" else "real",
                "online":    online,
                "tendencias_60min": tendencias,
                "alarmes_ativos": [
                    {
                        "codigo":    a.code,
                        "descricao": a.description,
                        "severidade": a.severity,
                        "desde":     a.started_at.isoformat() if a.started_at else None,
                        "responsavel": a.assumed_by,
                    }
                    for a in alarmes
                ],
            })

        # Memória de aprendizado: casos já validados pelos técnicos
        casos = (await session.execute(
            select(DiagnosisCase)
            .where(DiagnosisCase.confirmed.is_(True))
            .order_by(desc(DiagnosisCase.confirmed_at))
            .limit(10)
        )).scalars().all()

        for c in casos:
            estado["casos_validados"].append({
                "equipamento":     c.instrument_name,
                "diagnostico_ia":  c.ai_diagnosis,
                "ia_acertou":      c.ai_was_correct,
                "causa_real":      c.confirmed_cause,
                "validado_por":    c.confirmed_by,
            })

        return estado


def _chamar_ia(estado: dict) -> str:
    """Envia o estado à API do Claude e retorna o parecer em markdown."""
    import anthropic

    ia_cfg = _load_ia_config()
    api_key = ia_cfg.get("api_key")
    if not api_key:
        raise RuntimeError("Chave da API não configurada (client_config.json → 'ia' → 'api_key')")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=ia_cfg.get("model", "claude-opus-4-8"),
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Analise o estado atual da planta de refrigeração:\n\n"
                + json.dumps(estado, ensure_ascii=False, indent=2)
            ),
        }],
    )
    return next(b.text for b in response.content if b.type == "text")


def _analise_por_regras(estado: dict) -> str:
    """Fallback offline: parecer simplificado pela base de diagnóstico local."""
    linhas: list[str] = []
    problemas: list[str] = []
    recomendacoes: list[str] = []
    offline: list[str] = []

    for inst in estado["instrumentos"]:
        nome = inst["nome"]
        if not inst["online"]:
            offline.append(nome)
        for a in inst["alarmes_ativos"]:
            diag = diagnostico_para(a["codigo"]) or {}
            problema = diag.get("problema", a["descricao"])
            problemas.append(f"**{nome}** — {problema} (código {a['codigo']})")
            for acao in diag.get("acoes", [])[:2]:
                recomendacoes.append(f"{nome}: {acao}")

    total = len(estado["instrumentos"])
    n_alarm = len(problemas)
    if n_alarm == 0 and not offline:
        emoji, frase = "🟢", f"Todos os {total} instrumentos operando normalmente, sem alarmes ativos."
    elif any("alarm" in str(p).lower() for p in problemas) or n_alarm >= 2:
        emoji, frase = "🔴", f"{n_alarm} problema(s) ativo(s) exigindo atenção."
    else:
        emoji, frase = "🟡", f"{n_alarm} alerta(s) ativo(s); {len(offline)} instrumento(s) sem comunicação."

    linhas.append(f"## {emoji} Status Geral")
    linhas.append(frase)
    linhas.append("")
    linhas.append("## Situação por Equipamento")
    for inst in estado["instrumentos"]:
        st = "🔴 em alarme" if inst["alarmes_ativos"] else ("🟢 normal" if inst["online"] else "⚪ sem comunicação")
        linhas.append(f"- **{inst['nome']}** ({inst['modelo'] or '?'}) — {st}")
    linhas.append("")
    linhas.append("## Problemas Detectados")
    linhas.extend([f"- {p}" for p in problemas] or ["Nenhum problema ativo."])
    linhas.append("")
    linhas.append("## Recomendações")
    linhas.extend([f"1. {r}" for r in recomendacoes] or ["Manter monitoramento de rotina."])
    linhas.append("")
    linhas.append("*Análise gerada localmente por regras (IA indisponível neste momento).*")
    return "\n".join(linhas)


async def executar_analise() -> dict:
    """Ponto de entrada: coleta, analisa (IA com fallback) e retorna o parecer."""
    import asyncio

    estado = await coletar_estado_consolidado()
    try:
        texto = await asyncio.to_thread(_chamar_ia, estado)
        fonte = "ia"
    except Exception as exc:
        logger.warning("IA indisponível (%s) — usando análise por regras", exc)
        texto = _analise_por_regras(estado)
        fonte = "regras"

    return {
        "analise":   texto,
        "fonte":     fonte,
        "gerado_em": estado["gerado_em"],
        "instrumentos_analisados": len(estado["instrumentos"]),
    }
