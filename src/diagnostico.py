"""
diagnostico.py — Base de conhecimento de diagnóstico de refrigeração.

Mapeia códigos de alarme (do emulador PCT-122E e dos instrumentos Sitrad)
para: problema, causas prováveis e ações recomendadas. Exibido no painel
de ocorrências do dashboard.
"""

DIAGNOSTICOS: dict[str, dict] = {
    # ── Pressão de sucção ────────────────────────────────────────────────
    "ALP1": {
        "problema": "Pressão de sucção abaixo do limite operacional",
        "causas": [
            "Vazamento de refrigerante no circuito",
            "Filtro secador ou linha de líquido obstruída",
            "Válvula de expansão subalimentando o evaporador",
            "Baixa carga térmica na câmara",
        ],
        "acoes": [
            "Inspecionar vazamentos com detector eletrônico ou espuma",
            "Conferir carga de refrigerante pelo visor de líquido",
            "Verificar perda de carga no filtro secador",
        ],
    },
    "AHP1": {
        "problema": "Pressão de sucção acima do esperado",
        "causas": [
            "Compressor sem rendimento (válvulas internas desgastadas)",
            "Carga térmica excessiva para a capacidade instalada",
            "Retorno recente de degelo",
        ],
        "acoes": [
            "Avaliar capacidade real do compressor (teste de bombeamento)",
            "Verificar demanda térmica e dimensionamento",
        ],
    },
    # ── Pressão de descarga ──────────────────────────────────────────────
    "ALP2": {
        "problema": "Pressão de descarga abaixo do normal",
        "causas": [
            "Temperatura ambiente muito baixa (condensação flutuante)",
            "Falta severa de refrigerante",
        ],
        "acoes": [
            "Verificar controle de condensação flutuante",
            "Conferir carga de refrigerante",
        ],
    },
    "AHP2": {
        "problema": "Pressão de descarga acima do limite — condensação deficiente",
        "causas": [
            "Condensador sujo ou obstruído",
            "Ventilador do condensador inoperante",
            "Recirculação de ar quente no condensador",
            "Excesso de carga de refrigerante ou ar no circuito",
        ],
        "acoes": [
            "Limpar o condensador (serpentina e aletas)",
            "Verificar funcionamento dos ventiladores",
            "Purgar incondensáveis se houver suspeita de ar no circuito",
        ],
    },
    # ── Temperaturas ─────────────────────────────────────────────────────
    "ALt1": {
        "problema": "Temperatura de sucção anormalmente baixa",
        "causas": [
            "Sensor rompido, em curto ou mau contato",
            "Retorno de líquido pela linha de sucção",
        ],
        "acoes": [
            "Verificar integridade da sonda e conexões",
            "Conferir superaquecimento do sistema",
        ],
    },
    "AHt1": {
        "problema": "Temperatura de sucção alta",
        "causas": [
            "Falta de refrigerante",
            "Superaquecimento excessivo na válvula de expansão",
        ],
        "acoes": ["Conferir carga de gás e ajuste da válvula de expansão"],
    },
    "ALt2": {
        "problema": "Temperatura de descarga/linha de líquido baixa",
        "causas": ["Condensação excessiva", "Sensor com defeito"],
        "acoes": ["Verificar controle de condensação e sonda"],
    },
    "AHt2": {
        "problema": "Temperatura de descarga alta — compressor sob estresse",
        "causas": [
            "Relação de compressão elevada (P2 alta ou P1 baixa)",
            "Superaquecimento de sucção excessivo",
            "Falha de resfriamento do compressor",
        ],
        "acoes": [
            "Reduzir pressão de condensação (limpar condensador)",
            "Conferir superaquecimento e carga de gás",
        ],
    },
    "ALt3": {
        "problema": "Câmara mais fria que o necessário",
        "causas": ["Setpoint incorreto", "Sensor deslocado do ponto de medição"],
        "acoes": ["Conferir setpoint e posição da sonda"],
    },
    "AHt3": {
        "problema": "Temperatura da câmara alta — PRODUTO EM RISCO",
        "causas": [
            "Porta aberta ou vedação deficiente",
            "Degelo travado ou excessivo",
            "Carga quente inserida recentemente",
            "Evaporador bloqueado por gelo",
            "Falta de refrigerante",
        ],
        "acoes": [
            "Verificar porta, cortina de ar e vedações",
            "Inspecionar evaporador (bloco de gelo, ventiladores)",
            "Conferir ciclo de degelo",
        ],
    },
    # ── Superaquecimento / Subresfriamento ───────────────────────────────
    "ASHL": {
        "problema": "Superaquecimento excessivo — evaporador subalimentado",
        "causas": [
            "Falta de refrigerante (vazamento)",
            "Válvula de expansão subdimensionada ou travada",
            "Filtro secador obstruído",
            "Perda de carga do bulbo da válvula termostática",
        ],
        "acoes": [
            "Conferir carga de refrigerante",
            "Ajustar/inspecionar válvula de expansão",
            "Medir perda de carga no filtro secador",
        ],
    },
    "ASLL": {
        "problema": "Superaquecimento baixo — risco de golpe de líquido no compressor",
        "causas": [
            "Válvula de expansão superalimentando",
            "Bulbo da válvula mal fixado ou sem isolamento",
            "Carga térmica muito baixa",
        ],
        "acoes": [
            "Fechar ajuste da válvula de expansão (aumentar SH)",
            "Verificar fixação e isolamento do bulbo",
            "URGENTE: risco de dano mecânico ao compressor",
        ],
    },
    "ASCL": {
        "problema": "Subresfriamento excessivo",
        "causas": ["Excesso de carga de refrigerante", "Incondensáveis no circuito"],
        "acoes": ["Conferir carga de gás", "Avaliar purga de incondensáveis"],
    },
    "ASCLL": {
        "problema": "Subresfriamento insuficiente — risco de flash gas",
        "causas": [
            "Falta de refrigerante",
            "Condensação insuficiente",
        ],
        "acoes": [
            "Conferir carga pelo visor de líquido (bolhas = falta de gás)",
            "Verificar condensador",
        ],
    },
    # ── Códigos dos instrumentos Sitrad (ALARM_MAP do coletor) ───────────
    "ALH_T1": {
        "problema": "Alta temperatura no sensor S1",
        "causas": [
            "Porta aberta ou vedação deficiente",
            "Degelo em andamento ou travado",
            "Carga quente inserida",
            "Falta de refrigerante",
        ],
        "acoes": ["Verificar porta e vedações", "Conferir ciclo de degelo"],
    },
    "ALL_T1": {
        "problema": "Baixa temperatura no sensor S1",
        "causas": ["Setpoint incorreto", "Termostato/controlador descalibrado"],
        "acoes": ["Conferir setpoint e calibração"],
    },
    "ALM_DOOR": {
        "problema": "Porta aberta",
        "causas": ["Porta aberta por tempo excessivo", "Sensor de porta desalinhado"],
        "acoes": ["Fechar a porta", "Verificar alinhamento do sensor magnético"],
    },
    "ALH_PRESS": {
        "problema": "Alta pressão no circuito",
        "causas": [
            "Condensador sujo ou ventilador parado",
            "Excesso de carga ou incondensáveis",
        ],
        "acoes": ["Limpar condensador", "Verificar ventiladores"],
    },
    "ALL_PRESS": {
        "problema": "Baixa pressão no circuito",
        "causas": ["Vazamento de refrigerante", "Obstrução na linha de líquido"],
        "acoes": ["Inspecionar vazamentos", "Verificar filtro secador"],
    },
    "ERR_S1": {
        "problema": "Falha na sonda 1",
        "causas": ["Sonda rompida ou em curto", "Mau contato na conexão"],
        "acoes": ["Substituir/reconectar a sonda S1"],
    },
    "ERR_S2": {
        "problema": "Falha na sonda 2",
        "causas": ["Sonda rompida ou em curto", "Mau contato na conexão"],
        "acoes": ["Substituir/reconectar a sonda S2"],
    },
    "ERR_S3": {
        "problema": "Falha na sonda 3",
        "causas": ["Sonda rompida ou em curto", "Mau contato na conexão"],
        "acoes": ["Substituir/reconectar a sonda S3"],
    },
}


def diagnostico_para(code: str) -> dict | None:
    """Retorna {problema, causas, acoes} para um código de alarme, ou None."""
    return DIAGNOSTICOS.get(code)
