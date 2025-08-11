# Основной файл API (FastAPI)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import os
from .endpoints import invoices, webhooks, register, gas_station, sweep, withdrawals

app = FastAPI()

# Unified prefix: tests expect '/v1/*'
PREFIX = "/v1"

app.include_router(register.router, prefix=PREFIX)
app.include_router(invoices.router, prefix=PREFIX)
app.include_router(webhooks.router, prefix=PREFIX)
app.include_router(gas_station.router, prefix=PREFIX)
app.include_router(sweep.router, prefix=PREFIX)
app.include_router(withdrawals.router, prefix=PREFIX)

# Serve Mini App static files (frontend)
_miniapp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static_web", "miniapp")
if os.path.isdir(_miniapp_dir):
	app.mount("/miniapp", StaticFiles(directory=_miniapp_dir, html=True), name="miniapp")
