from fastapi import APIRouter, Depends

from api.deps import verify_token

router = APIRouter()

# TODO: Website management routes
# - POST   /websites/{instance_id}          attach a website to an instance
# - GET    /websites/{instance_id}          list attached websites
# - DELETE /websites/{website_id}           remove a website
