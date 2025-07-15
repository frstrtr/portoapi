from fastapi import APIRouter, HTTPException, status, Depends, Body
from sqlalchemy.orm import Session
from core.database.db_service import get_db
from core.database.models import Seller, Invoice
from core.services.gas_station import prepare_for_sweep

router = APIRouter()

# --- POST /sweep/prepare ---
@router.post("/sweep/prepare", status_code=status.HTTP_202_ACCEPTED)
def sweep_prepare(
    telegram_id: int = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """
    Запускает сервис Gas Station для всех оплаченных инвойсов продавца.
    """
    seller = db.query(Seller).filter(Seller.telegram_id == telegram_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")
    paid_invoices = db.query(Invoice).filter_by(seller_id=seller.id, status='paid').all()
    if not paid_invoices:
        raise HTTPException(status_code=404, detail="No paid invoices to sweep.")
    # Примерная стоимость (можно заменить на реальный расчет)
    estimated_cost_trx = 2.0 * len(paid_invoices)
    if seller.gas_deposit_balance < estimated_cost_trx:
        raise HTTPException(status_code=402, detail="Insufficient gas deposit to prepare sweep.")
    # Списать стоимость услуги
    seller.gas_deposit_balance -= estimated_cost_trx
    db.commit()
    # Вызов сервиса Gas Station для подготовки адресов к свипу
    for inv in paid_invoices:
        try:
            prepare_for_sweep(inv.address)
        except Exception as e:
            # Логируем ошибку, но продолжаем обработку остальных адресов
            print(f"Error preparing sweep for {inv.address}: {e}")
    return {
        "status": "processing",
        "message": f"Preparing {len(paid_invoices)} invoices for sweep. You will be notified.",
        "estimated_cost_trx": str(estimated_cost_trx)
    }