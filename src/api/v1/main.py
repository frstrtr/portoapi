# Основной файл API (FastAPI)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .endpoints import invoices, webhooks, register, gas_station, sweep, withdrawals

app = FastAPI()

# Unified prefix
PREFIX = "/api/v1"

app.include_router(register.router, prefix=PREFIX)
app.include_router(invoices.router, prefix=PREFIX)
app.include_router(webhooks.router, prefix=PREFIX)
app.include_router(gas_station.router, prefix=PREFIX)
app.include_router(sweep.router, prefix=PREFIX)
app.include_router(withdrawals.router, prefix=PREFIX)

# Serve Mini App static files (frontend)
app.mount("/miniapp", StaticFiles(directory="src/static_web/miniapp", html=True), name="miniapp")
