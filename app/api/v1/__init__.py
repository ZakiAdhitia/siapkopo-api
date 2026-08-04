"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import (
    approval_config, auth, dashboard, domain_master, health, letter_template, master,
    portal, public_portal, public_submission, submission, users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(domain_master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
# public_submission's literal /submissions/guest/... paths MUST be registered
# before submission's parameterized /submissions/{submission_id}/... routes,
# same reason as the /templates/{id}/fields/reorder ordering in
# letter_template.py -- FastAPI matches routes in registration order, and a
# plain {submission_id} path segment (str) would otherwise swallow "guest"
# before Pydantic ever gets a chance to reject it as an invalid UUID.
api_router.include_router(public_submission.router)
api_router.include_router(submission.router)
api_router.include_router(users.router)
api_router.include_router(dashboard.router)
api_router.include_router(portal.router)
api_router.include_router(public_portal.router)
