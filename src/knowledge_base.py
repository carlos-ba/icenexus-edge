"""
knowledge_base.py — Base de conhecimento técnico de refrigeração
Injetada no prompt do Claude para diagnósticos mais precisos.

Conteúdo:
  - Tabela de saturação R404A (pressão PSIG × temperatura °C)
  - Faixas normais de operação por modelo FullGauge
  - Padrões de falha clássicos com causas e soluções
  - Carregamento de casos confirmados do banco de dados
"""

from __future__ import annotations
import logging
from datetime import datetime, UTC, timedelta

logger = logging.getLogger("coletor.kb")

# ══════════════════════════════════════════════════════════════
# TABELA DE SATURAÇÃO R404A  (DuPont / Chemours)
# Pressão em PSIG × Temperatura de saturação em °C
# Fonte: tabela termodinâmica R404A — ponto de bolha (líquido)
# ══════════════════════════════════════════════════════════════

R404A_SAT_TABLE = """
TABELA DE SATURAÇÃO R404A (ponto de bolha)
PSIG  |  T_sat (°C)
------|-------------
  0   |  -46.3
  2   |  -43.1
  4   |  -40.2
  6   |  -37.5
  8   |  -35.0
 10   |  -32.7
 12   |  -30.6
 14   |  -28.6
 16   |  -26.8
 18   |  -25.1
 20   |  -23.5
 25   |  -19.8
 30   |  -16.5
 35   |  -13.5
 40   |  -10.8
 50   |   -5.9
 60   |   -1.5
 70   |    2.5
 80   |    6.2
 90   |    9.6
100   |   12.8
120   |   18.6
140   |   23.8
160   |   28.5
180   |   32.8
200   |   36.7
220   |   40.3
240   |   43.7
260   |   46.8
280   |   49.7
300   |   52.5
320   |   55.1
340   |   57.6
360   |   59.9
390   |   63.4  ← LIMITE CRÍTICO P2 (acima = alta pressão)
420   |   66.7
"""

# ══════════════════════════════════════════════════════════════
# FAIXAS NORMAIS DE OPERAÇÃO — PCT-122E Plus  (câmara -18°C)
# Refrigerante R404A
# ══════════════════════════════════════════════════════════════

PCT122E_NORMAL_RANGES = """
PARÂMETROS NORMAIS DE OPERAÇÃO — PCT-122E Plus
Aplicação: câmara de congelamento -18°C | Refrigerante: R404A

PRESSÕES:
  P1 (sucção):    12–18 PSIG         ← Tsat ≈ -30 a -26°C
  P2 (descarga):  240–280 PSIG       ← Tsat ≈ 43–50°C
  Alarme baixo P1: < 8 PSIG          ← possível falta de gás
  Alarme alto P2:  > 360 PSIG        ← sobrecarga condensador

TEMPERATURAS:
  T1 (gás sucção):      -23 a -20°C  ← SH = T1 - Tsat_P1
  T2 (gás descarga):    60–80°C      ← após compressor
  T3 (câmara fria):     -19 a -16°C  ← setpoint operacional
  T4 (aletado/degelo):  -30 a -25°C  ← próximo a Tsat_P1

TERMODINÂMICA:
  Superaquecimento (SH):  5–10 K     ← ideal 6-8K
  Subresfriamento (SC):   3–8 K      ← ideal 5K
  SH > 12K:  ATENÇÃO — válvula expansão ou falta gás
  SH > 15K:  CRÍTICO — intervenção necessária
  SH < 3K:   RISCO — possível retorno de líquido ao compressor

SAÍDAS DIGITAIS:
  OUT1 (compressor):  liga quando T3 > setpoint + diferencial
  OUT2 (ventilador):  normalmente sempre ligado em refrigeração
  OUT3 (degelo):      ciclos programados (ex: 2x/dia, 20-30 min)
  Compressor ciclando < 10 min liga/desliga: possível problema de carga

CICLO TÍPICO CÂMARA -18°C:
  Pull-down (de +5°C até -18°C): 45–90 min (depende da carga)
  Ciclo estável: compressor ~70-80% do tempo ligado
  Degelo: 1–3x por dia, duração 15–35 min, T4 sobe até +5°C
"""

# ══════════════════════════════════════════════════════════════
# PADRÕES DE FALHA — diagnóstico diferencial
# ══════════════════════════════════════════════════════════════

FAULT_PATTERNS = """
DIAGNÓSTICO DIFERENCIAL — PADRÕES DE FALHA COMUNS

1. ALTA PRESSÃO DE DESCARGA (P2 > 350 PSIG)
   Sintomas: P2 elevado, T2 alta, Tsat_P2 alta, câmara pode estar quente
   Causas possíveis (em ordem de probabilidade):
     a) Condensador sujo/obstruído → mais comum (70% dos casos)
     b) Ventilador do condensador com defeito ou parado
     c) Alta temperatura ambiente na casa de máquinas
     d) Excesso de carga de gás (overcharge)
     e) Ar não-condensável no circuito
   Diferenciação:
     - Se ventilador parado → P2 sobe rapidamente, T2 muito alta (>90°C)
     - Se condensador sujo → P2 sobe gradualmente ao longo de dias/semanas
     - Se overcharge → SC muito alto (>12K) junto com P2 alto

2. BAIXA PRESSÃO DE SUCÇÃO (P1 < 8 PSIG)
   Sintomas: P1 baixa, Tsat_P1 muito negativa, câmara não atinge setpoint
   Causas possíveis:
     a) Carga de gás baixa (vazamento) → mais comum
     b) Restrição na linha de sucção (filtro secador entupido)
     c) Válvula de expansão travada fechada
     d) Restrição na linha de líquido
   Diferenciação:
     - Se vazamento → SH muito alto (>15K) + P1 cai gradualmente
     - Se filtro entupido → diferença de temperatura no filtro, pode gelar
     - Se válvula fechada → SH muito alto + P1 cai rápido ao ligar compressor

3. SUPERAQUECIMENTO EXCESSIVO (SH > 12K)
   Sintomas: T1 alta em relação a Tsat_P1, P1 normal ou baixa
   Causas possíveis:
     a) Válvula de expansão termostática mal ajustada/com defeito
     b) Filtro secador entupido (restrição de líquido)
     c) Carga de gás baixa
     d) Bulbo da VET mal posicionado ou com defeito
   Diferenciação:
     - Se P1 também baixa → provável falta de gás
     - Se P1 normal + SH alto → válvula de expansão ou filtro
     - Se SH alto só quando câmara abre (porta) → normal, temporário

4. CÂMARA NÃO ATINGE SETPOINT (T3 > setpoint + 3°C persistente)
   Sintomas: T3 elevada persistentemente, compressor ligado continuamente
   Causas possíveis:
     a) Porta com vedação danificada ou aberta frequentemente
     b) Produto quente carregado em excesso
     c) Degelo muito frequente ou longo
     d) Capacidade de refrigeração insuficiente para carga térmica
     e) Problema no compressor (perda de eficiência)
   Diferenciação:
     - Verificar logs de OUT3 (degelo) — frequência anormal?
     - Verificar P1/P2 — sistema tem capacidade?
     - Verificar T3 vs hora do dia — pior em horário de carga?

5. RETORNO DE LÍQUIDO AO COMPRESSOR (SH < 3K)
   SITUAÇÃO CRÍTICA — pode destruir o compressor
   Sintomas: SH muito baixo, T2 anormalmente baixa, compressor pode estar gelando
   Causas:
     a) Válvula de expansão muito aberta (overfeeding)
     b) Carga excessiva de gás
     c) Evaporador com defeito ou superfície muito grande
   Ação imediata: DESLIGAR compressor, não religar sem diagnóstico
"""

# ══════════════════════════════════════════════════════════════
# NORMAS RELEVANTES — ações de conformidade
# ══════════════════════════════════════════════════════════════

COMPLIANCE_RULES = """
AÇÕES DE CONFORMIDADE ANVISA/MAPA

RDC 430/2020 (ANVISA) — Boas Práticas de Distribuição e Armazenagem:
  - Desvio de temperatura DEVE ser registrado com: data/hora início, responsável,
    produto afetado, ação corretiva tomada, data/hora de restabelecimento
  - Produtos farmacêuticos: qualquer desvio acima de 2°C do limite por > 15 min
    requer avaliação de qualidade e possível descarte
  - Sistema de monitoramento deve ter calibração rastreável
  - Relatórios de temperatura devem ser mantidos por mínimo 1 ano

IN 87/2019 (MAPA) — Armazenagem de produtos veterinários:
  - Temperatura de armazenagem deve ser mantida dentro dos limites da bula
  - Desvios devem ser comunicados ao responsável técnico em até 2 horas
  - Registro contínuo obrigatório (mínimo a cada 30 minutos)

QUANDO ACIONAR PROCEDIMENTO DE DESVIO:
  - T3 fora do limite por mais de 15 minutos
  - Alarme de temperatura confirmado pelo técnico
  - Falha no sistema de monitoramento por mais de 30 minutos
"""


# ══════════════════════════════════════════════════════════════
# MONTA CONTEXTO COMPLETO PARA INJEÇÃO NO PROMPT
# ══════════════════════════════════════════════════════════════

def build_knowledge_context(model_id: int | None = None,
                            confirmed_cases: list[dict] | None = None) -> str:
    """
    Monta o bloco de conhecimento técnico para injetar no prompt do Claude.
    Inclui tabela R404A, faixas normais, padrões de falha e casos confirmados.
    """
    parts = [
        "═══════════════════════════════════════════════════════",
        "BASE DE CONHECIMENTO TÉCNICO — REFRIGERAÇÃO INDUSTRIAL",
        "═══════════════════════════════════════════════════════",
        "",
        R404A_SAT_TABLE,
    ]

    if model_id == 117:   # PCT-122E Plus
        parts += ["", PCT122E_NORMAL_RANGES]

    parts += ["", FAULT_PATTERNS, "", COMPLIANCE_RULES]

    # Casos confirmados pela equipe técnica (memória operacional)
    if confirmed_cases:
        parts.append("\n═══════════════════════════════════════")
        parts.append("CASOS CONFIRMADOS — MEMÓRIA OPERACIONAL")
        parts.append("(diagnósticos verificados pela equipe técnica nesta instalação)")
        parts.append("═══════════════════════════════════════\n")
        for i, case in enumerate(confirmed_cases, 1):
            parts.append(
                f"Caso #{i} — {case.get('occurred_at', 'data desconhecida')}\n"
                f"  Instrumento: {case.get('instrument_name', '—')}\n"
                f"  Sintoma: {case.get('symptom_summary', '—')}\n"
                f"  Diagnóstico IA: {case.get('ai_diagnosis', '—')}\n"
                f"  Causa confirmada: {case.get('confirmed_cause', '—')}\n"
                f"  Solução aplicada: {case.get('resolution', '—')}\n"
                f"  Resultado: {case.get('outcome', '—')}\n"
            )

    return "\n".join(parts)
