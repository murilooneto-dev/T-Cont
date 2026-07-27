import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
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


def test_criar_e_listar_empresa(client):
    response = client.post(
        "/empresas",
        json={"razao_social": "Tesserato", "nome_fantasia": "Tesserato", "cnpj": "12345678000199"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["razao_social"] == "Tesserato"
    empresa_id = body["id"]

    response = client.get("/empresas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"/empresas/{empresa_id}")
    assert response.status_code == 200
    assert response.json()["cnpj"] == "12345678000199"


def test_criar_empresa_cnpj_duplicado_retorna_409(client):
    payload = {"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    client.post("/empresas", json=payload)

    response = client.post("/empresas", json=payload)
    assert response.status_code == 409


def test_obter_empresa_inexistente_retorna_404(client):
    response = client.get("/empresas/999")
    assert response.status_code == 404


def test_atualizar_e_desativar_empresa(client):
    response = client.post(
        "/empresas", json={"razao_social": "A", "nome_fantasia": None, "cnpj": "11111111000191"}
    )
    empresa_id = response.json()["id"]

    response = client.put(
        f"/empresas/{empresa_id}",
        json={"razao_social": "A Ltda", "nome_fantasia": "A", "ativo": True},
    )
    assert response.status_code == 200
    assert response.json()["razao_social"] == "A Ltda"

    response = client.delete(f"/empresas/{empresa_id}")
    assert response.status_code == 204

    response = client.get(f"/empresas/{empresa_id}")
    assert response.json()["ativo"] is False
