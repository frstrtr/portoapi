# endpoints/register.py

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
try:
    from core.database.db_service import get_db  # type: ignore
    from core.database.models import Seller  # type: ignore
except ImportError:  # pragma: no cover
    from src.core.database.db_service import get_db  # type: ignore
    from src.core.database.models import Seller  # type: ignore

router = APIRouter()

class RegisterCompleteRequest(BaseModel):
    token: str
    xpub: str

@router.post("/register/complete")
def register_complete(
    req: RegisterCompleteRequest,
    db: Session = Depends(get_db)
):
    """
    Завершает регистрацию продавца, сохраняя его xPub.
    """
    seller = db.query(Seller).filter(Seller.token == req.token).first()
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired token."
        )
    seller.xpub = req.xpub
    seller.status = 'active'
    db.commit()
    return {"status": "success", "message": "Registration complete."}