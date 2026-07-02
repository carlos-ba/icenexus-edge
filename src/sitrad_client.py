"""
sitrad_client.py — Cliente HTTP para a API REST do Sitrad PRO
Porta: 8002 (HTTPS, certificado auto-assinado)
Auth:  Basic (usuario:senha de um usuário no grupo API do Sitrad)
"""

import ssl
import urllib.request
import urllib.error
import json
import base64
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("sitrad.client")

# ---------------------------------------------------------------------------
# Configuração da conexão
# ---------------------------------------------------------------------------
import json as _json
from pathlib import Path as _Path

def _load_sitrad_config():
    cfg_path = _Path(__file__).parent.parent / "config" / "client_config.json"
    if cfg_path.exists():
        try:
            cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))
            sitrad = cfg.get("sitrad", {})
            return (
                sitrad.get("url",  "https://localhost:8002"),
                sitrad.get("user", "admin"),
                sitrad.get("pass", "admin"),
            )
        except Exception:
            pass
    return "https://localhost:8002", "admin", "admin"

SITRAD_URL, SITRAD_USER, SITRAD_PASS = _load_sitrad_config()


def _make_opener() -> urllib.request.OpenerDirector:
    """Cria opener com SSL sem verificação (certificado auto-assinado Sitrad)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    handler = urllib.request.HTTPSHandler(context=ctx)
    return urllib.request.build_opener(handler)


def _auth_header() -> str:
    token = base64.b64encode(f"{SITRAD_USER}:{SITRAD_PASS}".encode()).decode()
    return f"Basic {token}"


def get(path: str) -> dict[str, Any]:
    """Faz GET na API e retorna o JSON parseado."""
    url = f"{SITRAD_URL}/api/v1{path}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Authorization": _auth_header(),
    })
    opener = _make_opener()
    with opener.open(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Funções de alto nível
# ---------------------------------------------------------------------------

def list_instruments() -> list[dict]:
    """Retorna lista de instrumentos configurados na API."""
    data = get("/instruments")
    return data.get("results", [])


def list_converters() -> list[dict]:
    """Retorna lista de conversores (CONV32 etc.)."""
    data = get("/converters")
    return data.get("results", [])


def get_values(instrument_id: int) -> dict[str, Any]:
    """
    Retorna dicionário {code: {value, unit, isInError, date}}
    para todos os valores do instrumento.
    """
    data = get(f"/instruments/{instrument_id}/values")
    out: dict[str, Any] = {}
    for item in data.get("results", []):
        vals = item.get("values", [])
        if vals:
            v = vals[0]
            out[item["code"]] = {
                "value":    v.get("value"),
                "unit":     v.get("measurementUnity", ""),
                "error":    v.get("isInError", False),
                "date":     v.get("date"),
            }
    return out


def get_snapshot(instrument_id: int) -> dict[str, Any]:
    """
    Extrai os campos mais relevantes para monitoramento de câmara fria.
    Retorna um snapshot limpo e normalizado.
    """
    vals = get_values(instrument_id)

    def v(code: str):
        entry = vals.get(code)
        return entry["value"] if entry and not entry["error"] else None

    return {
        # Sensores de temperatura
        "t1":            v("Sensor1"),
        "t2":            v("Sensor2"),
        "t3":            v("Sensor3"),

        # Setpoint e diferencial atual
        "setpoint":      v("CurrentSetpoint"),
        "differential":  v("CurrentDifferential"),

        # Status operacional
        "process_status":  v("ProcessStatus"),
        "process_text":    v("ProcessStatusText"),

        # Saídas
        "out_refrigeration": v("IsOutputRefr"),
        "out_fan":           v("IsOutputFan"),
        "out_defrost":       v("IsOutputDefr1"),
        "out_buzzer":        v("IsOutputBuzzer"),

        # Alarmes de temperatura
        "alm_high_t1":  v("IsAlrHighTempS1"),
        "alm_low_t1":   v("IsAlrLowTempS1"),
        "alm_door":     v("IsAlrmDoorOpn"),

        # Alarmes de pressão (se disponíveis)
        "alm_high_press": v("IsAlrHighPressure"),
        "alm_low_press":  v("IsAlrLowPressure"),

        # Erros de sonda
        "err_s1": v("IsErrorS1"),
        "err_s2": v("IsErrorS2"),
        "err_s3": v("IsErrorS3"),

        # Modo especial
        "fast_freezing":  v("IsFastFreezingActive"),
        "economic_mode":  v("IsEconomicModeActive"),

        # Relógio do instrumento
        "rtc": v("InternalRtc"),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Conversores ===")
    for c in list_converters():
        print(f"  [{c['id']}] {c['name']} — tipo={c['type']} status={c['status']}")

    print("\n=== Instrumentos ===")
    instruments = list_instruments()
    for inst in instruments:
        print(f"  [{inst['id']}] {inst['name']} addr={inst['address']} status={inst['status']}")

    print("\n=== Snapshot (instrumento 3) ===")
    snap = get_snapshot(3)
    for k, val in snap.items():
        print(f"  {k:25s} = {val}")
