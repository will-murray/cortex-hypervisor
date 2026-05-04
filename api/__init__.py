import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import (
    instance, clinics, voice_agent, pms_config, campaigns, blueprint,
)

app = FastAPI()

_raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000")
_allowed_origins = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def hello():
    return {"message": "This is the Cortex Hypervisor"}


app.include_router(instance.router)
app.include_router(clinics.router)
app.include_router(voice_agent.router)
app.include_router(pms_config.router)
app.include_router(campaigns.router)
app.include_router(blueprint.router)
