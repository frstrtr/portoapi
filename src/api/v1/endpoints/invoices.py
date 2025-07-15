# Эндпоинты для управления инвойсами

# Example FastAPI endpoint stub

from fastapi import APIRouter, HTTPException, status, Depends, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.database.db_service import get_db
from core.database.models import Seller, Invoice
from core.crypto.hd_wallet_service import generate_address_from_xpub
from sqlalchemy import desc

router = APIRouter()

# --- Schemas ---
class InvoiceCreateRequest(BaseModel):
    telegram_id: int
    amount: str
    description: str

class InvoiceListRequest(BaseModel):
    telegram_id: int

# --- POST /invoices ---
@router.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(
    req: InvoiceCreateRequest,
    db: Session = Depends(get_db)
):
    seller = db.query(Seller).filter(Seller.telegram_id == req.telegram_id).first()
    if not seller or not seller.xpub:
        raise HTTPException(status_code=404, detail="Seller not found or not registered.")
    # Find next derivation index
    last_invoice = db.query(Invoice).filter(Invoice.seller_id == seller.id).order_by(desc(Invoice.derivation_index)).first()
    next_index = (last_invoice.derivation_index + 1) if last_invoice else 0
    # Generate address
    try:
        address = generate_address_from_xpub(seller.xpub, next_index)
    except Exception:
        raise HTTPException(status_code=500, detail="Address generation failed.")
    # TODO: check gas deposit balance, raise 402 if insufficient
    invoice = Invoice(
        seller_id=seller.id,
        address=address,
        amount=req.amount,
        status='pending',
        derivation_index=next_index,
        description=req.description
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return {
        "invoice_id": invoice.id,
        "address": invoice.address,
        "amount": invoice.amount,
        "status": invoice.status
    }

# --- GET /invoices ---
@router.get("/invoices")
def list_invoices(
    telegram_id: int = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    seller = db.query(Seller).filter(Seller.telegram_id == telegram_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")
    invoices = db.query(Invoice).filter(Invoice.seller_id == seller.id).order_by(desc(Invoice.created_at)).all()
    return {
        "invoices": [
            {"id": inv.id, "address": inv.address, "amount": inv.amount, "status": inv.status}
            for inv in invoices
        ]
    }

@router.get("/invoices")
def list_invoices():
    return {"invoices": []}
