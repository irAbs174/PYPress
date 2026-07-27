import sys
import time

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.database_url.startswith("postgresql"):
        return

    engine = create_engine(settings.database_url)
    for attempt in range(30):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception:
            if attempt == 29:
                raise
            time.sleep(1)

    sys.exit(1)


if __name__ == "__main__":
    main()
