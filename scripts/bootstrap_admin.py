from app.database.init_db import create_tables, seed_admin
from app.database.session import SessionLocal


def main() -> None:
    create_tables()
    with SessionLocal() as session:
        seed_admin(session)
    print("Admin user is ready.")


if __name__ == "__main__":
    main()
