"""
modbus_client.py — Leitura do TC-900E Log via Modbus RTU (Waveshare COM3)
Fonte de dados real para o SitradColetor.

Registros lidos (FC03 - Holding Registers):
  0x1F (31)  — Setpoint normal (F31)
  0x65 (101) — Temperatura S1 (camara)
  0x66 (102) — Temperatura S2 (evaporador)
  0x67 (103) — Temperatura S3
  0x68 (104) — Status Word 1: saidas e processo
  0x69 (105) — Status Word 2: erros de sensor
  0x6A (106) — Status Word 3: alarmes
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger("modbus_client")

# ---------------------------------------------------------------------------
# Configuracao
# ---------------------------------------------------------------------------
MODBUS_PORT    = "COM3"
MODBUS_ADDRESS = 5
MODBUS_BAUD    = 9600
MODBUS_TIMEOUT = 1.0

# ID sintetico unico para o TC-900E no banco (nao colide com IDs do Sitrad)
TC900_SITRAD_ID = 9001

# Registros
REG_SETPOINT    = 0x1F
REG_S1          = 0x65
REG_S2          = 0x66
REG_S3          = 0x67
REG_SW1         = 0x68
REG_SW2         = 0x69
REG_SW3         = 0x6A

# ---------------------------------------------------------------------------
# SW1 — processo
_SW1_COMP  = 1 << 0
_SW1_FAN   = 1 << 1
_SW1_DEFR  = 1 << 2
_SW1_BUZZ  = 1 << 3
_SW1_REFRI = 1 << 10
_SW1_DEGL  = 1 << 12
_SW1_FAST  = 1 << 8
_SW1_ECO   = 1 << 9

# SW2 — erros de sensor
_SW2_ERR_S1 = 1 << 0
_SW2_ERR_S2 = 1 << 1
_SW2_ERR_S3 = 1 << 2

# SW3 — alarmes
_SW3_ALM_HIGH_T1 = 1 << 0
_SW3_ALM_LOW_T1  = 1 << 1
_SW3_ALM_DOOR    = 1 << 4

# ---------------------------------------------------------------------------
# Cliente singleton com lock para thread-safety
# ---------------------------------------------------------------------------
_lock   = threading.Lock()
_client = None


def _get_client():
    """Retorna cliente conectado. Reconecta apenas se _client for None."""
    global _client
    try:
        from pymodbus.client import ModbusSerialClient
    except ImportError:
        raise RuntimeError("pymodbus nao instalado no venv do SitradColetor")

    if _client is not None:
        return _client

    _client = ModbusSerialClient(
        port=MODBUS_PORT, baudrate=MODBUS_BAUD,
        parity="N", stopbits=1, bytesize=8,
        timeout=MODBUS_TIMEOUT,
    )
    if not _client.connect():
        _client = None
        raise ConnectionError(f"Nao foi possivel abrir {MODBUS_PORT}")
    logger.info("Modbus conectado: %s addr=%d", MODBUS_PORT, MODBUS_ADDRESS)
    return _client


def _raw_to_temp(raw: int) -> float:
    if raw > 32767:
        raw -= 65536
    return round(raw / 10.0, 1)


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------

def get_instrument_info() -> dict:
    return {
        "id":             TC900_SITRAD_ID,
        "name":           "TC-900E Log (Modbus)",
        "address":        MODBUS_ADDRESS,
        "converter_name": f"Waveshare RS-485 {MODBUS_PORT}",
        "modelId":        None,
        "model_name":     "TC-900E Log",
        "source":         "modbus",
        "status":         "Online",
    }


def get_snapshot() -> dict:
    """
    Le todos os registros relevantes e retorna snapshot compativel
    com o formato esperado pelo collector._save_reading().
    Levanta excecao em caso de falha de comunicacao.
    """
    import time
    global _client

    with _lock:
        try:
            c = _get_client()
            # Bloco principal: S1..SW3 (6 registros a partir de 0x65)
            r_block = c.read_holding_registers(REG_S1, count=6, slave=MODBUS_ADDRESS)
            time.sleep(0.12)
            # Setpoint separado (0x1F)
            r_sp = c.read_holding_registers(REG_SETPOINT, count=1, slave=MODBUS_ADDRESS)
        except Exception as exc:
            # Fecha a porta e reseta para reconexao no proximo tick
            try:
                if _client:
                    _client.close()
            except Exception:
                pass
            _client = None
            raise IOError(f"Erro de comunicacao Modbus: {exc}") from exc

    if r_block is None or r_block.isError():
        raise IOError("Falha ao ler registros do TC-900E")

    regs = r_block.registers
    s1   = _raw_to_temp(regs[0])
    s2   = _raw_to_temp(regs[1])
    s3   = _raw_to_temp(regs[2])
    sw1  = regs[3]
    sw2  = regs[4]
    sw3  = regs[5]
    sp   = _raw_to_temp(r_sp.registers[0]) if r_sp and not r_sp.isError() else None

    # S3 desconectado: valor absurdo (< -50)
    s3_valid = s3 if s3 > -50 else None

    # Processo: texto baseado nos bits de SW1
    if sw1 & _SW1_DEGL:
        process_text = "Degelo"
    elif sw1 & _SW1_REFRI:
        process_text = "Refrigeracao"
    elif sw1 & _SW1_FAST:
        process_text = "Fast Freezing"
    elif sw1 & _SW1_ECO:
        process_text = "Modo Economico"
    else:
        process_text = "Standby"

    # Alarmes ativos
    active_alarms = []
    if sw2 & _SW2_ERR_S1:
        active_alarms.append({"code": "ERR_S1", "description": "Erro sonda S1", "severity": "alarm"})
    if sw2 & _SW2_ERR_S2:
        active_alarms.append({"code": "ERR_S2", "description": "Erro sonda S2", "severity": "alarm"})
    if sw2 & _SW2_ERR_S3:
        active_alarms.append({"code": "ERR_S3", "description": "Erro sonda S3", "severity": "warning"})
    if sw3 & _SW3_ALM_HIGH_T1:
        active_alarms.append({"code": "ALH_T1", "description": "Alta temperatura S1", "severity": "alarm"})
    if sw3 & _SW3_ALM_LOW_T1:
        active_alarms.append({"code": "ALL_T1", "description": "Baixa temperatura S1", "severity": "alarm"})
    if sw3 & _SW3_ALM_DOOR:
        active_alarms.append({"code": "ALM_DOOR", "description": "Porta aberta", "severity": "warning"})

    return {
        # Temperaturas
        "t1": s1,
        "t2": s2,
        "t3": s3_valid,
        "t4": None,
        # Pressoes: TC-900E nao tem transdutor de pressao
        "p1": None, "p2": None,
        "t_sat_p1": None, "t_sat_p2": None,
        "superheat": None, "subcooling": None,
        # Analogicas
        "an1_pct": None, "an2_pct": None,
        # Controle
        "setpoint":       sp,
        "differential":   None,
        "process_status": sw1,
        "process_text":   process_text,
        # Saidas digitais
        "out_refrigeration": bool(sw1 & _SW1_COMP),
        "out_fan":           bool(sw1 & _SW1_FAN),
        "out_defrost":       bool(sw1 & _SW1_DEFR),
        "out_buzzer":        bool(sw1 & _SW1_BUZZ),
        # Alarmes via bitmask
        "alm_high_t1":   bool(sw3 & _SW3_ALM_HIGH_T1),
        "alm_low_t1":    bool(sw3 & _SW3_ALM_LOW_T1),
        "alm_door":      bool(sw3 & _SW3_ALM_DOOR),
        "alm_high_press": False,
        "alm_low_press":  False,
        # Erros de sonda
        "err_s1": bool(sw2 & _SW2_ERR_S1),
        "err_s2": bool(sw2 & _SW2_ERR_S2),
        "err_s3": bool(sw2 & _SW2_ERR_S3),
        # Modos
        "fast_freezing":  bool(sw1 & _SW1_FAST),
        "economic_mode":  bool(sw1 & _SW1_ECO),
        # Lista de alarmes ativos (formato _active_alarms do coletor)
        "_active_alarms": active_alarms,
    }
