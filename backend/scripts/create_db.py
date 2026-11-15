"""Create the database named in DATABASE_URL if it does not exist yet."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings


def main() -> None:
    url = make_url(settings.database_url)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if exists:
            print(f"database {url.database} already exists")
        else:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
            print(f"created database {url.database}")
    admin.dispose()


if __name__ == "__main__":
    main()
