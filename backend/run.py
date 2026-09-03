import uvicorn

from app.config import settings

if __name__ == "__main__":
    if settings.uvicorn_workers > 1:
        print(
            f"WARNING: UVICORN_WORKERS={settings.uvicorn_workers} - this is not supported. "
            "Every background task (CometD listeners, broker consumers) runs per-process, so "
            "more than one worker means every Salesforce event gets processed and published "
            "multiple times. Forcing workers=1. Scale with multiple independent instances "
            "behind a real broker (RabbitMQ) instead - see Admin Configuration -> Message broker."
        )

    uvicorn.run(
        "app.main:app",
        host=settings.uvicorn_host,
        port=settings.uvicorn_port,
        reload=settings.uvicorn_reload,
        log_level=settings.uvicorn_log_level,
        # workers is intentionally not passed through - see the warning above
        # and the comment on Settings.uvicorn_workers in app/config.py
    )
