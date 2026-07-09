from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from pathlib import Path


# Store database locally inside project
DATABASE_PATH = Path("ai_hedge_fund.db")

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


# Create database engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)


# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# Base class for database models
class Base(DeclarativeBase):
    pass


def get_db():
    """
    Database session generator.
    Used by agents/services that need database access.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database():
    """
    Create all database tables.
    """
    Base.metadata.create_all(bind=engine)
