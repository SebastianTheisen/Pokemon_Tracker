"""API Version 1: bündelt alle Router unter ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1 import admin, auth, catalog, health, me, pricing

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(catalog.router)
api_router.include_router(pricing.router)
