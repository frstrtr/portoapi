# Эндпоинты для управления инвойсами

# Example FastAPI endpoint stub
from fastapi import APIRouter

router = APIRouter()

@router.get("/invoices")
def list_invoices():
    return {"invoices": []}
