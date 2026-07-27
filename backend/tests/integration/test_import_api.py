import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def plano_id(client):
    empresa = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()
    plano = client.post(f"/empresas/{empresa['id']}/planos-contas", json={"nome": "Plano Padrão"}).json()
    return plano["id"]


CSV_CONTEUDO = b"Codigo,Descricao,Natureza,Conta Analitica,Conta Pai\n1.1,Disponibilidades,ATIVO,False,\n1.1.01,Caixa,ATIVO,True,1.1\n"


def test_preview_importacao(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/preview",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mapeamento"]["codigo"] == 0
    assert len(body["linhas"]) == 2


def test_preview_importacao_invalida_retorna_422(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/preview",
        files={"arquivo": ("plano.csv", b"A,B\nx,y\n", "text/csv")},
    )
    assert response.status_code == 422


def test_confirmar_importacao(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert response.status_code == 201
    contas = response.json()
    assert len(contas) == 2

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert len(response.json()) == 2
