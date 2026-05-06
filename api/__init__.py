import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.account import routers as account_routers
from api.voice_agent import routers as voice_agent_routers

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


for r in account_routers + voice_agent_routers:
    app.include_router(r)
