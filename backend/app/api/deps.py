from collections.abc import Generator
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.storage.file_storage import LocalFileStorageService


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_storage() -> LocalFileStorageService:
    return LocalFileStorageService(Path(settings.storage_root))
