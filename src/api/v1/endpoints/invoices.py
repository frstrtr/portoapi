# Эндпоинты для управления инвойсами

from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from src.core.database.db_service import get_db
from src.core.database.models import Seller, Invoice
from src.core.crypto.hd_wallet_service import generate_address_from_xpub

router = APIRouter()

# --- Schemas ---
class InvoiceCreateRequest(BaseModel):
    telegram_id: int
    amount: str
    description: str

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
    last_invoice = (
        db.query(Invoice)
        .filter(Invoice.seller_id == seller.id)
        .order_by(desc(Invoice.derivation_index))
        .first()
    )
    next_index = (last_invoice.derivation_index + 1) if last_invoice else 0
    # Generate address
    try:
        address = generate_address_from_xpub(seller.xpub, next_index)
    except Exception:
        raise HTTPException(status_code=500, detail="Address generation failed.")
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
    telegram_id: int = Query(..., description="Seller telegram id"),
    db: Session = Depends(get_db)
):
    seller = db.query(Seller).filter(Seller.telegram_id == telegram_id).first()
    if not seller:
        raise HTTPException(status_code=404, detail="Seller not found.")
    invoices = (
        db.query(Invoice)
        .filter(Invoice.seller_id == seller.id)
        .order_by(desc(Invoice.created_at))
        .all()
    )
    return {
        "invoices": [
            {"id": inv.id, "address": inv.address, "amount": inv.amount, "status": inv.status}
            for inv in invoices
        ]
    }
