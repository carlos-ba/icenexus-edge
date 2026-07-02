"""
config_loader.py — Carrega configuração do cliente.

Modo PERSONALIZADO: lê config/client_config.json preparado no laboratório.
Modo AUTOMÁTICO:    gera grupos padrão a partir dos instrumentos no banco.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger("config_loader")

CONFIG_PATH = Path(__file__).parent.parent / "config" / "client_config.json"

TIPO_ICONE = {
    "camara":       "❄",
    "chiller":      "🌡",
    "freezer":      "🧊",
    "condicionador": "💨",
    "controlador":  "📡",
}


def load_config() -> dict:
    """
    Retorna a configuração do cliente.
    Se não existe client_config.json → modo automático (grupos gerados em runtime).
    """
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            modo = cfg.get("_modo", "personalizado")
            if modo == "automatico":
                logger.info("client_config.json encontrado — modo AUTOMÁTICO")
                return _config_automatico_base(cfg)
            logger.info("client_config.json encontrado — modo PERSONALIZADO")
            return cfg
        except Exception as e:
            logger.error("Erro ao ler client_config.json: %s — usando modo automático", e)

    logger.info("client_config.json não encontrado — modo AUTOMÁTICO")
    return _config_automatico_base({})


def _config_automatico_base(base: dict) -> dict:
    """Config mínimo para modo automático — grupos reais criados em runtime."""
    return {
        "_modo": "automatico",
        "cliente":              base.get("cliente", "IceNexus Edge"),
        "unidade":              base.get("unidade", ""),
        "instalacao":           base.get("instalacao", ""),
        "responsavel_tecnico":  base.get("responsavel_tecnico", ""),
        "grupos": [],
    }


def build_grupos_automatico(instruments: list[dict]) -> list[dict]:
    """
    Monta grupos a partir da lista de instrumentos retornada pelo /overview.
    Agrupa por modelo: PCT-122E → chiller, demais → controlador.
    """
    grupos: dict[str, dict] = {}

    for inst in instruments:
        model = (inst.get("model_name") or "").lower()
        if "pct" in model:
            tipo = "chiller"
        else:
            tipo = "controlador"

        if tipo not in grupos:
            grupos[tipo] = {
                "id":    tipo,
                "nome":  "Chillers" if tipo == "chiller" else "Controladores",
                "tipo":  tipo,
                "icone": TIPO_ICONE.get(tipo, "📡"),
                "instrumentos": [],
            }

        grupos[tipo]["instrumentos"].append({
            "sitrad_id":       inst["id"],
            "nome_exibicao":   inst["name"],
            "setpoint_ref":    inst.get("sensors", {}).get("setpoint"),
            "alarme_min":      None,
            "alarme_max":      None,
            "sensor_principal": "t1",
            "notas":           "",
        })

    return list(grupos.values())


def merge_config_com_overview(cfg: dict, overview: list[dict]) -> dict:
    """
    Combina a config com os dados ao vivo do overview.
    - Modo personalizado: usa grupos da config, enriquece com dados ao vivo.
    - Modo automático: gera grupos a partir do overview.
    """
    modo = cfg.get("_modo", "personalizado")

    # Indexa overview por id do instrumento
    by_id = {inst["id"]: inst for inst in overview}

    if modo == "automatico":
        grupos = build_grupos_automatico(overview)
    else:
        grupos = cfg.get("grupos", [])
        # Resolve sitrad_id → dados ao vivo
        for grupo in grupos:
            for item in grupo.get("instrumentos", []):
                sid = item.get("sitrad_id")
                live = by_id.get(sid, {})
                item["_live"] = live

    # Adiciona dados ao vivo nos grupos automáticos também
    for grupo in grupos:
        for item in grupo.get("instrumentos", []):
            if "_live" not in item:
                sid = item.get("sitrad_id")
                item["_live"] = by_id.get(sid, {})

    return {
        "cliente":             cfg.get("cliente", "IceNexus Edge"),
        "unidade":             cfg.get("unidade", ""),
        "instalacao":          cfg.get("instalacao", ""),
        "responsavel_tecnico": cfg.get("responsavel_tecnico", ""),
        "modo":                modo,
        "grupos":              grupos,
    }


def save_config(cfg: dict) -> None:
    """Salva configuração em disco."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    logger.info("Configuração salva em %s", CONFIG_PATH)
