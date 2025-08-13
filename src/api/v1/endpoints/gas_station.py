# Эндпоинты для управления газовым депозитом
from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
try:
    from core.database.db_service import get_db  # type: ignore
    from core.database.models import Seller  # type: ignore
except ImportError:  # pragma: no cover
    from src.core.database.db_service import get_db  # type: ignore
    from src.core.database.models import Seller  # type: ignore

try:
    from core.services.gas_station import gas_station as _gas_station
except ImportError:  # pragma: no cover
    from src.core.services.gas_station import gas_station as _gas_station

router = APIRouter()

# --- GET /deposit/address ---
@router.get("/deposit/address")
def get_deposit_address(
    telegram_id: int = Query(..., description="Seller telegram id")
):
    """
    Возвращает адрес для пополнения газового депозита и memo (telegram_id).
    Для MVP адрес фиксированный.
    """
    DEPOSIT_ADDRESS = "T...PLATFORM-DEPOSIT-ADDRESS"  # TODO: заменить на реальный адрес
    return {"deposit_address": DEPOSIT_ADDRESS, "memo": str(telegram_id)}

# --- GET /deposit/balance ---
@router.get("/deposit/balance")
def get_deposit_balance(
    telegram_id: int = Query(..., description="Seller telegram id"),
    db: Session = Depends(get_db)
):
    """
    Возвращает текущий баланс газового депозита продавца.
    """
    seller = db.query(Seller).filter(Seller.telegram_id == telegram_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")
    return {"balance_trx": str(seller.gas_deposit_balance)}

# --- GET /gasstation/status ---
@router.get("/gasstation/status")
def gasstation_status():
    """Return basic gas station status including configuration warnings."""
    try:
        from core.config import config as _cfg  # type: ignore
    except ImportError:  # pragma: no cover
        from src.core.config import config as _cfg  # type: ignore
    base = _cfg.tron.get_tron_client_config().get("full_node")
    warns = []
    try:
        warns = _gas_station.get_configuration_warnings() or []
    except Exception:
        warns = []
    # Dynamic permission warning: control signer not present in any active permission
    try:
        summary = _gas_station.get_control_permissions_summary()
        control_addr = summary.get("control_address")
        perm = summary.get("permission") or {}
        ctrl_weight = perm.get("control_weight")
        perm_id = perm.get("id")
        found_by = summary.get("found_by")
        owner_addr = summary.get("owner_address")
        # If a control signer is configured but not found in any active permission keys, warn clearly
        if control_addr and (ctrl_weight is None or int(ctrl_weight or 0) <= 0 or found_by not in ("key_match", "key_match_override")):
            warns.append(
                f"Control signer {control_addr} is not present in any active permission on {owner_addr}. Activation/delegation with control will fail. Add the key to an active permission and set GAS_WALLET_CONTROL_PERMISSION_ID."
            )
    except Exception:
        # best-effort; ignore if node unavailable
        pass
    return {
        "node": base,
        "warnings": warns,
    }
