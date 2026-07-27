import pytest
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine


@pytest.fixture
def db_session():
    # Reusa get_engine() (em vez de duplicar create_engine aqui) para que
    # este fixture rode com o mesmo PRAGMA foreign_keys=ON da aplicação.
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
