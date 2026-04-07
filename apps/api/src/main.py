from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routes.audit_logs import router as audit_logs_router
from src.api.routes.auth import router as auth_router
from src.api.routes.assets import router as assets_router
from src.api.routes.health import router as health_router
from src.api.routes.jobs import router as jobs_router
from src.api.routes.memories import router as memories_router
from src.api.routes.metrics import router as metrics_router
from src.api.routes.monitoring import router as monitoring_router
from src.api.routes.previews import router as previews_router
from src.api.routes.projects import router as projects_router
from src.api.routes.prompt_evolution import router as prompt_evolution_router
from src.api.routes.reviews import router as reviews_router
from src.api.routes.settings import router as settings_router
from src.api.routes.storage import router as storage_router
from src.api.routes.workflows import router as workflows_router
from src.core.config import get_settings
from src.core.security import derive_audit_action, required_role_for_request, role_satisfies, sanitize_detail
from src.infrastructure.db.base import get_session_factory, init_database
from src.infrastructure.db.repositories.audit_repository import AuditRepository
from src.infrastructure.db.repositories.provider_repository import ProviderRepository
from src.infrastructure.db.repositories.security_repository import SecurityRepository


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    session = get_session_factory()()
    try:
        ProviderRepository(session).seed_defaults()
        SecurityRepository(session).seed_bootstrap_users()
        session.commit()
    finally:
        session.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Industrial AI manga drama factory API.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        path = request.url.path
        method = request.method.upper()
        settings = get_settings()
        actor = None
        unauthorized_detail: str | None = None
        should_protect = path.startswith("/api/v1")
        should_audit = should_protect and method not in {"GET", "HEAD", "OPTIONS"}
        required_role = required_role_for_request(path, method) if should_protect else None

        if should_protect and settings.auth_enabled:
            session = get_session_factory()()
            try:
                authorization = request.headers.get("Authorization", "")
                if not authorization.startswith("Bearer "):
                    unauthorized_detail = "Missing Bearer token."
                else:
                    raw_token = authorization.split(" ", 1)[1].strip()
                    actor = SecurityRepository(session).authenticate_token(raw_token)
                    session.commit()
                    if actor is None:
                        unauthorized_detail = "Invalid or expired access token."
                if unauthorized_detail is None and actor is not None and required_role is not None and not role_satisfies(actor.role, required_role):
                    unauthorized_detail = "Insufficient permissions for this resource."
                if actor is not None:
                    request.state.actor = actor
            finally:
                session.close()

        if unauthorized_detail is not None:
            response_status = 403 if actor is not None else 401
            response = JSONResponse(
                status_code=response_status,
                content={"detail": unauthorized_detail},
            )
            if should_audit:
                _write_audit_log(
                    actor=actor,
                    request=request,
                    response_status=response.status_code,
                    outcome="forbidden" if response_status == 403 else "unauthorized",
                )
            return response

        response = await call_next(request)
        if should_audit:
            outcome = "success" if response.status_code < 400 else "failed"
            _write_audit_log(
                actor=actor,
                request=request,
                response_status=response.status_code,
                outcome=outcome,
            )
        return response

    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(audit_logs_router, prefix="/api/v1")
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(assets_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(monitoring_router, prefix="/api/v1")
    app.include_router(previews_router, prefix="/api/v1")
    app.include_router(storage_router, prefix="/api/v1")
    app.include_router(prompt_evolution_router, prefix="/api/v1")
    app.include_router(memories_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    return app


def _write_audit_log(*, actor, request: Request, response_status: int, outcome: str) -> None:
    action, resource_type, resource_id = derive_audit_action(request.url.path, request.method)
    detail = sanitize_detail(
        {
            "query": dict(request.query_params),
            "client": request.client.host if request.client else None,
        }
    )
    session = get_session_factory()()
    try:
        AuditRepository(session).create_audit_log(
            actor_user_id=None if actor is None else actor.user_id,
            actor_email=None if actor is None else actor.email,
            actor_role=None if actor is None else actor.role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_method=request.method.upper(),
            request_path=request.url.path,
            response_status=response_status,
            outcome=outcome,
            detail=detail,
        )
        session.commit()
    finally:
        session.close()


app = create_app()
