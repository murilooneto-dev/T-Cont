import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.main import app


@pytest.fixture
def client():
    # Reusa get_engine() (em vez de duplicar create_engine aqui) para que
    # este fixture rode com o mesmo PRAGMA foreign_keys=ON da aplicação.
    engine = get_engine("sqlite:///:memory:", poolclass=StaticPool)
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


def test_criar_conta_com_codigo_duplicado_retorna_409(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"}
    ).json()["id"]
    payload = {
        "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
        "conta_analitica": True, "conta_pai_id": None,
    }

    assert client.post(f"/planos-contas/{plano_id}/contas", json=payload).status_code == 201

    # A UniqueConstraint do banco viraria um IntegrityError (500) sem a
    # checagem no use case; aqui precisa ser um 409 limpo.
    assert client.post(f"/planos-contas/{plano_id}/contas", json=payload).status_code == 409
    assert len(client.get(f"/planos-contas/{plano_id}/contas").json()) == 1


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


def test_criar_conta_com_conta_pai_inexistente_retorna_404(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"}
    ).json()["id"]

    # Com PRAGMA foreign_keys=ON, um conta_pai_id inexistente viraria um
    # IntegrityError (500) sem a checagem no use case; aqui precisa ser um
    # 404 limpo.
    response = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": 999,
        },
    )

    assert response.status_code == 404
    assert client.get(f"/planos-contas/{plano_id}/contas").json() == []


def test_atualizar_conta_com_codigo_duplicado_retorna_409(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"}
    ).json()["id"]
    client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1", "descricao": "Disponibilidades", "natureza": "ATIVO",
            "conta_analitica": False, "conta_pai_id": None,
        },
    )
    conta2_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.2", "descricao": "Bancos", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]

    # A UniqueConstraint do banco viraria um IntegrityError (500) sem a
    # checagem no use case; aqui precisa ser um 409 limpo.
    response = client.put(
        f"/contas/{conta2_id}",
        json={
            "codigo": "1.1", "descricao": "Bancos", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )
    assert response.status_code == 409

    contas = client.get(f"/planos-contas/{plano_id}/contas").json()
    assert {c["codigo"] for c in contas} == {"1.1", "1.2"}


def test_atualizar_conta_mantendo_o_proprio_codigo_retorna_200(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano Padrão"}
    ).json()["id"]
    conta_id = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1.1.01", "descricao": "Caixa", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]

    response = client.put(
        f"/contas/{conta_id}",
        json={
            "codigo": "1.1.01", "descricao": "Caixa Renomeado", "natureza": "ATIVO",
            "conta_analitica": True, "conta_pai_id": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["codigo"] == "1.1.01"
    assert response.json()["descricao"] == "Caixa Renomeado"
