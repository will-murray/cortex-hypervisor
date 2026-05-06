"""
Voice agent domain — assistant lifecycle, capability toggles, ticket ingest,
and the Blueprint OMS proxy.

Each router module exports a `router` (FastAPI APIRouter). Service modules
(capabilities, factory, locale, twilio, vapi) are imported by the routers as
needed.
"""
from api.voice_agent.voice_agent import router as voice_agent_router
from api.voice_agent.blueprint import router as blueprint_router

routers = [voice_agent_router, blueprint_router]
