"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import approval_config, auth, health, letter_template, master, submission

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
api_router.include_router(submission.router)
