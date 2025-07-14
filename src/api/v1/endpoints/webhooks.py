# Эндпоинты для настройки вебхуков

from fastapi import APIRouter

router = APIRouter()

@router.post("/webhooks")
def setup_webhook():
    return {"status": "webhook set"}
