from unittest.mock import patch

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


@pytest.fixture(autouse=True)
def _ia_desativada_por_padrao():
    """Desativa a chamada real ao Ollama por padrão em toda a suíte de testes.

    Sem isto, qualquer teste que alcance a etapa de IA na cadeia de
    classificação (nenhuma regra bateu) faria uma chamada de rede real a um
    servidor Ollama, tornando a suíte não-determinística e dependente de uma
    máquina específica. Testes que precisam simular uma resposta específica
    da IA continuam podendo usar seu próprio `patch(...)` local, que tem
    precedência sobre este fixture enquanto está ativo.
    """
    with patch("app.infrastructure.classificacao.pipeline.classificar_por_ia", return_value=None):
        yield
