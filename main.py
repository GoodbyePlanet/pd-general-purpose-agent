import logging
from app.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)


def main():
    import uvicorn

    uvicorn.run(
        "app.api:api",
        host=settings.host,
        port=settings.port,
        workers=1,  # must be 1 — multiple workers cause duplicate Slack events
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
