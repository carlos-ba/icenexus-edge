"""
fault_scenarios.py — Cenários de falha para demonstração.

Cada cenário força sensores do EMULADOR a valores que reproduzem uma falha
real de refrigeração. Os limites de alarme do PCT-122E emulado (câmara -18°C,
R404A) detectam a anomalia e o dashboard exibe o diagnóstico.

Valores calibrados contra os parâmetros default do emulador:
  F76=12 (baixa P1) F77=58 (alta P1) F79=380 (alta P2)
  F69=4  (SH baixo) F70=15 (SH alto) F83=-35 (baixa T1) F88=-10 (alta T3)
"""

FAULT_SCENARIOS: dict[str, dict] = {
    "vazamento_gas": {
        "nome": "Vazamento de refrigerante",
        "descricao": "Pressão de sucção cai e superaquecimento dispara — pouca massa de gás no circuito",
        "campos": {"p1": 10.5, "t1": -12.0},   # ALP1 (P1<12) + ASHL (SH≈19K)
    },
    "retorno_liquido": {
        "nome": "Retorno de líquido ao compressor",
        "descricao": "Superaquecimento quase nulo — válvula de expansão superalimentando o evaporador",
        "campos": {"t1": -18.5},               # ASLL (SH≈1K < 4)
    },
    "condensador_sujo": {
        "nome": "Condensador sujo / ventilador inoperante",
        "descricao": "Pressão de descarga sobe além do limite — condensação deficiente",
        "campos": {"p2": 395.0},               # AHP2 (P2>380)
    },
    "compressor_ineficiente": {
        "nome": "Compressor sem rendimento",
        "descricao": "Pressão de sucção alta mesmo com capacidade máxima — compressão deficiente",
        "campos": {"p1": 60.0},                # AHP1 (P1>58), demanda 100%
    },
    "sensor_defeituoso": {
        "nome": "Sensor de temperatura defeituoso",
        "descricao": "Sonda T1 lendo valor fora da faixa física — sensor rompido ou em curto",
        "campos": {"t1": -55.0},               # ALt1 (T1<-35) + ASLL
    },
    "porta_aberta": {
        "nome": "Porta aberta / carga térmica excessiva",
        "descricao": "Temperatura da câmara sobe a nível de risco para o produto",
        "campos": {"t3": -8.0},                # AHt3 (T3>-10) — produto em risco
    },
}
