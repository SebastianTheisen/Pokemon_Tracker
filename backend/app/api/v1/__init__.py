"""API Version 1: bündelt alle Router unter ``/api/v1``."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    alerts,
    auth,
    catalog,
    collection,
    contributions,
    friends,
    health,
    me,
    pricing,
    reports,
    scan,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(admin.router)
api_router.include_router(catalog.router)
api_router.include_router(pricing.router)
api_router.include_router(collection.router)
api_router.include_router(contributions.router)
api_router.include_router(scan.router)
api_router.include_router(alerts.router)
api_router.include_router(friends.router)
api_router.include_router(reports.router)
