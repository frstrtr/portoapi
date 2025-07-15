# API package init


from fastapi import FastAPI
from .v1.endpoints import register, invoices, gas_station, sweep

app = FastAPI()

app.include_router(register.router, prefix="/api/v1")
app.include_router(invoices.router, prefix="/api/v1")
app.include_router(gas_station.router, prefix="/api/v1")
app.include_router(sweep.router, prefix="/api/v1")
