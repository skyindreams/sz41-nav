from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "nav.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_legacy_schema():
    """Migrate from old schema (text group column) to new (groups table + FK)."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    links_cols = [c["name"] for c in inspector.get_columns("links")] if "links" in tables else []

    # If groups table exists, ensure it has data
    if "groups" in tables:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM groups"))
            if result.scalar() == 0:
                conn.execute(text("INSERT INTO groups (name, sort_order, is_default) VALUES ('外网', 0, 1)"))
                conn.execute(text("INSERT INTO groups (name, sort_order, is_default) VALUES ('内网', 1, 0)"))
                conn.commit()
        # Fix null group_ids
        if "group_id" in links_cols:
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE links SET group_id = (SELECT id FROM groups WHERE is_default=1 LIMIT 1)
                    WHERE group_id IS NULL
                """))
                conn.commit()
        return

    # Fresh: create groups + add group_id
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                sort_order INTEGER DEFAULT 0,
                is_default BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("INSERT OR IGNORE INTO groups (name, sort_order, is_default) VALUES ('外网', 0, 1)"))
        conn.execute(text("INSERT OR IGNORE INTO groups (name, sort_order, is_default) VALUES ('内网', 1, 0)"))
        conn.commit()

    if "group_id" not in links_cols:
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE links ADD COLUMN group_id INTEGER REFERENCES groups(id)"))
            conn.execute(text("UPDATE links SET group_id = (SELECT id FROM groups WHERE name='外网') WHERE `group`='public'"))
            conn.execute(text("UPDATE links SET group_id = (SELECT id FROM groups WHERE name='内网') WHERE `group`='internal'"))
            conn.execute(text("UPDATE links SET group_id = (SELECT id FROM groups WHERE is_default=1 LIMIT 1) WHERE group_id IS NULL"))
            conn.commit()


def init_db():
    Base.metadata.create_all(bind=engine)
    migrate_legacy_schema()
