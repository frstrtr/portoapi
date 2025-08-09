# Withdrawals endpoints for Mini App signer flow
from fastapi import APIRouter, HTTPException, Depends, Query, Header
from pydantic import BaseModel
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from src.core.database.db_service import get_db, get_transactions_by_invoice
from src.core.database.models import Seller, Invoice
from src.core.config import config
from src.core.security.telegram_webapp import verify_webapp_init_data
import requests
from tronpy import Tron
from tronpy.providers import HTTPProvider
import time

try:
    import jwt  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    jwt = None  # type: ignore[assignment]

try:
    from jwt.exceptions import InvalidTokenError, DecodeError, ExpiredSignatureError  # type: ignore[import-not-found]
    JWT_INVALID_ERRORS = (InvalidTokenError, DecodeError, ExpiredSignatureError)
except ImportError:  # pragma: no cover - optional dependency
    JWT_INVALID_ERRORS = tuple()

router = APIRouter()

# ----- Schemas -----
class PendingIntent(BaseModel):
    intent_id: str
    invoice_id: int
    from_address: str
    amount_usdt: float
    token_contract: str
    expires_at: Optional[int] = None
    diagnostics: Optional[dict] = None

class PendingListResponse(BaseModel):
    items: List[PendingIntent]

class PrepareRequest(BaseModel):
    invoice_id: int
    to_address: str

class PrepareResponse(BaseModel):
    raw_tx: dict
    owner: str
    token_contract: str

class SubmitRequest(BaseModel):
    invoice_id: int
    signed_tx_hex: str

class SubmitResponse(BaseModel):
    result: bool
    txid: Optional[str] = None
    error: Optional[str] = None

class AuthRequest(BaseModel):
    initData: str

class AuthResponse(BaseModel):
    token: str
    expires_at: int


# ----- Helpers -----
JWT_ALG = "HS256"
JWT_TTL = 5 * 60  # 5 minutes


def _tron_client() -> Tron:
    conf = config.tron
    full = conf.get_tron_client_config().get("full_node") or conf.get_fallback_client_config().get("full_node")
    provider = HTTPProvider(endpoint_uri=full, api_key=(conf.api_key or None))
    return Tron(provider=provider)


def _broadcast_signed_hex(hexstr: str) -> dict:
    try:
        base = config.tron.get_tron_client_config().get("full_node") or config.tron.get_fallback_client_config().get("full_node")
        headers = {"Content-Type": "application/json"}
        payload = {"transaction": hexstr}
        resp = requests.post(f"{base}/wallet/broadcasthex", json=payload, headers=headers, timeout=20)
        return resp.json() if resp.ok else {"result": False, "error": resp.text}
    except requests.RequestException as e:
        return {"result": False, "error": str(e)}


def _calc_invoice_available_usdt(db: Session, inv: Invoice) -> float:
    # Sum received from transactions table if available
    try:
        txs = get_transactions_by_invoice(db, inv.id)
        total_received = sum(float(getattr(t, "amount_received", 0) or 0) for t in txs)
    except (SQLAlchemyError, AttributeError, TypeError):
        total_received = 0.0
    try:
        amount_required = float(getattr(inv, "amount", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        amount_required = 0.0
    if amount_required > 0:
        return max(0.0, min(total_received, amount_required))
    return max(0.0, total_received)


def _issue_jwt(seller_telegram_id: int, tg_user_id: int) -> Tuple[str, int]:
    if jwt is None:
        raise RuntimeError("PyJWT is not installed")
    now = int(time.time())
    exp = now + JWT_TTL
    payload = {"sid": seller_telegram_id, "tg": tg_user_id, "iat": now, "exp": exp}
    secret = config.bot.secret_token or config.bot.token
    token = jwt.encode(payload, secret, algorithm=JWT_ALG)
    return token, exp


def _auth_from_bearer(authorization: Optional[str]) -> Optional[int]:
    if not authorization:
        return None
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            return None
        if jwt is None:
            return None
        secret = config.bot.secret_token or config.bot.token
        data = jwt.decode(token, secret, algorithms=[JWT_ALG], options={"verify_aud": False})
        return int(data.get("sid"))
    except (ValueError, KeyError):
        return None
    except JWT_INVALID_ERRORS:
        return None


# ----- Routes -----
@router.post("/withdrawals/auth", response_model=AuthResponse)
def exchange_initdata_for_token(req: AuthRequest):
    ver = verify_webapp_init_data(req.initData, config.bot.token, max_age=600)
    if not ver or not ver.get("ok"):
        raise HTTPException(status_code=401, detail="Invalid initData")
    user = ver.get("user") or {}
    tg_user_id = int(user.get("id") or 0)
    if not tg_user_id:
        raise HTTPException(status_code=401, detail="No Telegram user")
    # In this app, seller.telegram_id equals Telegram user id
    try:
        token, exp = _issue_jwt(seller_telegram_id=tg_user_id, tg_user_id=tg_user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return AuthResponse(token=token, expires_at=exp)


@router.get("/withdrawals/pending", response_model=PendingListResponse)
def list_pending_withdrawals(
    seller_id: Optional[int] = Query(None, description="Temporary fallback: seller telegram id (dev only)"),
    initData: Optional[str] = Query(None, description="Telegram initData (dev only)"),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    sid = _auth_from_bearer(authorization)
    if not sid:
        # Fallbacks for dev/testing
        if initData:
            ver = verify_webapp_init_data(initData, config.bot.token, max_age=600)
            if ver and ver.get("ok") and ver.get("user") and ver["user"].get("id"):
                sid = int(ver["user"]["id"])  # map 1:1
        if not sid and seller_id:
            sid = int(seller_id)
    if not sid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    seller = db.query(Seller).filter(Seller.telegram_id == sid).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found")

    # Seller primary key is telegram_id, not id
    invoices = db.query(Invoice).filter(Invoice.seller_id == seller.telegram_id).all()
    items: List[PendingIntent] = []
    for inv in invoices:
        amt = _calc_invoice_available_usdt(db, inv)
        if amt <= 0:
            continue
        items.append(
            PendingIntent(
                intent_id=str(inv.id),
                invoice_id=inv.id,
                from_address=inv.address,
                amount_usdt=round(amt, 6),
                token_contract=config.tron.usdt_contract,
                diagnostics=None,
            )
        )

    return PendingListResponse(items=items)


@router.post("/withdrawals/prepare", response_model=PrepareResponse)
def prepare_withdrawal(
    req: PrepareRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    sid = _auth_from_bearer(authorization)
    if not sid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    inv = db.query(Invoice).filter(Invoice.id == req.invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        tron = _tron_client()
        contract = tron.get_contract(config.tron.usdt_contract)
        amount_usdt = _calc_invoice_available_usdt(db, inv)
        if amount_usdt <= 0:
            raise HTTPException(status_code=400, detail="No funds available for this invoice")
        amount_6 = int(round(amount_usdt * 1_000_000))
        txn = (
            contract.functions.transfer(req.to_address, amount_6)
            .with_owner(inv.address)
            .fee_limit(10_000_000)
            .build()
        )
        try:
            raw_tx = txn.to_json()
        except AttributeError:
            raw_tx = getattr(txn, "raw_data", {})
        return PrepareResponse(raw_tx=raw_tx, owner=inv.address, token_contract=config.tron.usdt_contract)
    except HTTPException:
        raise
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=500, detail=f"Failed to build transaction: {e}") from e


@router.post("/withdrawals/submit", response_model=SubmitResponse)
def submit_withdrawal(
    req: SubmitRequest,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    sid = _auth_from_bearer(authorization)
    if not sid:
        raise HTTPException(status_code=401, detail="Unauthorized")
    resp = _broadcast_signed_hex(req.signed_tx_hex)
    ok = bool(resp.get("result"))
    txid = resp.get("txid") or (resp.get("transaction", {}) or {}).get("txID")
    if ok and txid:
        try:
            inv = db.query(Invoice).filter(Invoice.id == req.invoice_id).first()
            if inv:
                inv.status = "withdrawn"
                db.add(inv)
                db.commit()
        except SQLAlchemyError:
            pass
        return SubmitResponse(result=True, txid=txid)
    else:
        return SubmitResponse(result=False, error=resp.get("message") or resp.get("error") or str(resp))
