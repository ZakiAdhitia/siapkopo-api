"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import auth, health, master

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
