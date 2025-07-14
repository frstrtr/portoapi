# Основной файл API (FastAPI)
from fastapi import FastAPI
from .endpoints import invoices, webhooks

app = FastAPI()

app.include_router(invoices.router, prefix="/v1")
app.include_router(webhooks.router, prefix="/v1")
