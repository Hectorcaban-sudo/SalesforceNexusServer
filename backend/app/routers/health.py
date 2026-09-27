from fastapi import APIRouter, Response
from ..config import settings
from ..metrics import render_prometheus

router = APIRouter(tags=["health"])


@router.get("/healthz")
@router.get("/api/healthz")
def healthz():
    return {"status": "ok", "app": settings.app_name}


@router.get("/readyz")
@router.get("/api/readyz")
def readyz():
    checks = {"app": True}
    try:
        from ..database import users_table
        users_table.all()
        checks["store"] = True
    except Exception as exc:
        checks["store"] = False
        checks["store_error"] = str(exc)
    try:
        from ..broker import broker
        checks["broker"] = bool(getattr(broker, "backend_name", None))
    except Exception as exc:
        checks["broker"] = False
        checks["broker_error"] = str(exc)
    ready = checks.get("store") and checks.get("broker")
    return {"ready": bool(ready), "checks": checks}


@router.get("/metrics")
def metrics():
    return Response(content=render_prometheus(), media_type="text/plain; version=0.0.4")
