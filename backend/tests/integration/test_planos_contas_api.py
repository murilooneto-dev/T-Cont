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
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


def test_criar_plano_contas_e_contas(client, empresa_id):
    response = client.post(f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"})
    assert response.status_code == 201
    plano_id = response.json()["id"]

    response = client.get(f"/empresas/{empresa_id}/planos-contas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )
    assert response.status_code == 201
    conta_id = response.json()["id"]

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.put(
        f"/contas/{conta_id}",
        json={
            "codigo": "1.1.01", "descricao": "Caixa e Equivalentes", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["descricao"] == "Caixa e Equivalentes"

    response = client.delete(f"/contas/{conta_id}")
    assert response.status_code == 204

    response = client.get(f"/planos-contas/{plano_id}/contas")
    assert len(response.json()) == 0


def test_criar_plano_para_empresa_inexistente_retorna_404(client):
    response = client.post("/empresas/999/planos-contas", json={"nome": "Plano Órfão"})

    assert response.status_code == 404
    assert client.get("/empresas/999/planos-contas").json() == []


def test_criar_conta_em_plano_inexistente_retorna_404(client, empresa_id):
    response = client.post(
        "/planos-contas/999/contas",
        json={
            "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )

    assert response.status_code == 404
    assert client.get("/planos-contas/999/contas").json() == []
