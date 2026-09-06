import os
import shutil
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Support zero-config local SQLite, Vercel serverless /tmp SQLite, or production PostgreSQL via DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    if os.getenv("VERCEL"):
        # Vercel serverless function filesystem is read-only except /tmp
        tmp_db = "/tmp/agri_exchange.db"
        src_db = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agri_exchange.db")
        if not os.path.exists(tmp_db) and os.path.exists(src_db):
            try:
                shutil.copyfile(src_db, tmp_db)
            except Exception:
                pass
        DATABASE_URL = f"sqlite:///{tmp_db}"
    else:
        DATABASE_URL = "sqlite:///./agri_exchange.db"

# Standardize postgres:// to postgresql:// for SQLAlchemy 2.0+
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=not is_sqlite,
    **({} if is_sqlite else {"pool_size": 10, "max_overflow": 20})
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()