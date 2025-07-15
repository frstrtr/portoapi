
# Эндпоинты для управления газовым депозитом
from fastapi import APIRouter, HTTPException, status, Depends, Body
from sqlalchemy.orm import Session
from core.database.db_service import get_db

from core.database.models import Seller, Invoice

# --- GET /deposit/address ---
@router.get("/deposit/address")
def get_deposit_address(
    telegram_id: int = Body(..., embed=True)
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
    telegram_id: int = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Возвращает текущий баланс газового депозита продавца.
    """
    seller = db.query(Seller).filter(Seller.telegram_id == telegram_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")
    return {"balance_trx": str(seller.gas_deposit_balance)}
