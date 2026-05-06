"""
Account domain — instance / clinic / PMS / campaign config endpoints.

Each module exports a `router` (FastAPI APIRouter). The package-level `routers`
list is what `api/__init__.py` registers with the app.
"""
from api.account.instances import router as instances_router
from api.account.clinics import router as clinics_router
from api.account.pms_config import router as pms_config_router
from api.account.campaigns import router as campaigns_router

routers = [instances_router, clinics_router, pms_config_router, campaigns_router]
