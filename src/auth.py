"""
auth.py — Autenticação por cookie assinado (itsdangerous).

Perfis:
  admin  — acesso completo (demo, IA, configurações)
  viewer — somente dashboard (leitura)

Credenciais ficam em config/client_config.json → chave "usuarios".
Chave secreta para assinar cookies: config/.secret_key (arquivo separado).
"""

import json
import logging
import secrets
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

logger = logging.getLogger("auth")

_CONFIG_PATH  = Path(__file__).parent.parent / "config" / "client_config.json"
_SECRET_PATH  = Path(__file__).parent.parent / "config" / ".secret_key"
COOKIE_NAME   = "icenexus_session"
SESSION_MAX_AGE = 60 * 60 * 12   # 12 horas

router = APIRouter(tags=["Auth"])

# ---------------------------------------------------------------------------
# Config helpers — NUNCA grava em client_config.json
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Erro ao ler client_config.json: %s", exc)
    return {}


def _get_secret_key() -> str:
    """Lê/gera a chave em config/.secret_key — nunca toca em client_config.json."""
    if _SECRET_PATH.exists():
        key = _SECRET_PATH.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(32)
    _SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_PATH.write_text(key, encoding="utf-8")
    logger.info("Nova secret_key gerada em config/.secret_key")
    return key


def _get_usuarios() -> dict:
    """Retorna dict {username: {senha, role}} do config. Sempre garante admin padrão."""
    cfg = _load_config()
    usuarios = cfg.get("usuarios", {})
    if not usuarios:
        usuarios = {
            "admin":  {"senha": "cetra2025",  "role": "admin"},
            "viewer": {"senha": "cliente123", "role": "viewer"},
        }
    return usuarios


# ---------------------------------------------------------------------------
# Serializer — inicializado lazy para pegar secret_key do arquivo
# ---------------------------------------------------------------------------

_serializer: Optional[URLSafeTimedSerializer] = None


def _get_serializer() -> URLSafeTimedSerializer:
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(_get_secret_key(), salt="session")
    return _serializer


# ---------------------------------------------------------------------------
# Funções de sessão
# ---------------------------------------------------------------------------

def create_session_cookie(username: str, role: str) -> str:
    return _get_serializer().dumps({"u": username, "r": role})


def read_session_cookie(token: str) -> Optional[dict]:
    try:
        data = _get_serializer().loads(token, max_age=SESSION_MAX_AGE)
        return {"username": data["u"], "role": data["r"]}
    except (SignatureExpired, BadSignature, KeyError):
        return None


def get_current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return read_session_cookie(token)


# ---------------------------------------------------------------------------
# Dependências FastAPI
# ---------------------------------------------------------------------------

def require_auth(request: Request) -> dict:
    """Exige qualquer usuário autenticado. Redireciona para /login se não."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user


def require_admin(request: Request) -> dict:
    """Exige perfil admin. Retorna 403 se autenticado mas sem permissão."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito ao administrador")
    return user


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/login")
async def login(request: Request, response: Response):
    body = await request.json()
    username = (body.get("username") or "").strip().lower()
    senha    = (body.get("password") or "").strip()

    if not username or not senha:
        raise HTTPException(status_code=422, detail="Usuário e senha obrigatórios")

    usuarios = _get_usuarios()
    user_cfg = usuarios.get(username)

    if not user_cfg or user_cfg.get("senha") != senha:
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")

    role  = user_cfg.get("role", "viewer")
    token = create_session_cookie(username, role)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {"username": username, "role": role}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"status": "ok"}


@router.get("/api/v1/me")
async def me(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")
    return user
