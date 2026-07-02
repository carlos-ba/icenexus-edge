"""
emulator_client.py — Cliente HTTP para o emulador PCT-122E Plus
URL base: http://localhost:8000
Endereço RS-485 padrão: 10

Converte o estado do emulador para o formato snapshot esperado pelo collector.
"""

import logging
import urllib.request
import json

logger = logging.getLogger("coletor.emulator")

EMULATOR_URL = "http://localhost:8000"
# PCT-122E Plus — endereços a monitorar (pode ter múltiplos controladores)
EMULATOR_ADDRESSES = [10]

# ID virtual para o emulador (não colide com IDs reais do Sitrad que são ≥ 1)
EMULATOR_SITRAD_ID_BASE = 90000   # emulador addr=10 → sitrad_id=90010


def get(path: str) -> dict | list:
    url = EMULATOR_URL + path
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


def list_controllers() -> list[dict]:
    """Retorna lista de controladores do emulador."""
    return get("/api/v1/controllers/")


def get_state(address: int) -> dict:
    """Retorna estado atual de um controlador."""
    return get(f"/api/v1/controllers/{address}/state")


def get_controller(address: int) -> dict:
    """Retorna dados estáticos de um controlador."""
    return get(f"/api/v1/controllers/{address}")


def get_active_alarms(address: int) -> list[dict]:
    """Retorna alarmes ativos do emulador para um controlador."""
    try:
        return get(f"/api/v1/controllers/{address}/alarms?active_only=true")
    except Exception:
        return []


def get_snapshot(address: int) -> dict:
    """
    Converte estado do emulador para o formato snapshot do coletor.
    Campos do emulador → campos do Reading.
    """
    state  = get_state(address)
    alarms = get_active_alarms(address)

    # Monta set de códigos de alarme ativos para lookup rápido
    active_codes = {a["code"] for a in alarms if a.get("is_active")}

    # Mapeia alarmes do emulador para campos do ALARM_MAP do coletor
    # ASHL = superaquecimento alto → alm_high_t1 (reutiliza campo de alta temp)
    # ASLL = superaquecimento baixo → retorno de líquido → severidade alarm
    # AHP2 = alta pressão descarga → alm_high_press
    # ALP1 = baixa pressão sucção  → alm_low_press
    alm_high_t1   = "ASHL" in active_codes   # SH alto → válvula/gás
    alm_low_t1    = "ASLL" in active_codes   # SH baixo → retorno de líquido
    alm_high_press = "AHP2" in active_codes  # alta pressão descarga
    alm_low_press  = "ALP1" in active_codes  # baixa pressão sucção

    # Alarmes ativos do emulador também ficam disponíveis como lista raw
    # para o endpoint /api/overview consumir diretamente
    active_alarm_list = [
        {
            "code":        a["code"],
            "description": a["description"],
            "severity":    a["severity"],
            "trigger_value": a.get("trigger_value"),
            "activated_at":  a.get("activated_at"),
        }
        for a in alarms if a.get("is_active")
    ]

    return {
        # Temperaturas
        "t1": state.get("t1"),
        "t2": state.get("t2"),
        "t3": state.get("t3"),
        "t4": state.get("t4"),

        # Pressões
        "p1": state.get("p1"),
        "p2": state.get("p2"),

        # Termodinâmica
        "t_sat_p1":   state.get("t_sat_p1"),
        "t_sat_p2":   state.get("t_sat_p2"),
        "superheat":  state.get("superheat"),
        "subcooling": state.get("subcooling"),

        # Saídas analógicas
        "an1_pct": state.get("an1_pct"),
        "an2_pct": state.get("an2_pct"),

        # Saídas digitais
        "out_refrigeration": state.get("out1"),
        "out_fan":           state.get("out2"),
        "out_defrost":       state.get("out3"),
        "out_buzzer":        None,

        # Controle
        "setpoint":       None,
        "differential":   None,
        "process_status": None,
        "process_text":   _process_text(state),

        # Alarmes mapeados do emulador → compatíveis com ALARM_MAP do coletor
        "alm_high_t1":    alm_high_t1,
        "alm_low_t1":     alm_low_t1,
        "alm_door":       None,
        "alm_high_press": alm_high_press,
        "alm_low_press":  alm_low_press,
        "err_s1": None,
        "err_s2": None,
        "err_s3": None,
        "fast_freezing": None,
        "economic_mode": None,

        # Lista raw de alarmes ativos (para o overview consumir)
        "_active_alarms": active_alarm_list,
    }


def _process_text(state: dict) -> str:
    """Determina status operacional com base nas saídas."""
    if state.get("out3"):
        return "Degelo"
    if state.get("out1"):
        return "Refrigeração"
    if state.get("out2"):
        return "Ventilador"
    return "Standby"


def build_instrument_info(address: int, controller: dict | None = None) -> dict:
    """
    Constrói o dicionário de instrumento para _upsert_instrument no coletor.
    usa sitrad_id virtual (EMULATOR_SITRAD_ID_BASE + address).
    """
    name = "PCT-122E Plus (Emulador)"
    if controller and controller.get("name"):
        name = controller["name"] + " (Emulador)"

    return {
        "id":          EMULATOR_SITRAD_ID_BASE + address,
        "name":        name,
        "address":     address,
        "modelId":     117,         # PCT-122E Plus — FullGauge model id
        "model_name":  "PCT-122E plus",
        "source":      "emulator",
        "status":      "Online",
        "converter_name": "Emulador Local",
    }
