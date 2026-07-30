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
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

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
def conta_id(client):
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    conta = client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()
    return empresa_id, conta["id"]


def test_criar_listar_atualizar_e_deletar_regra(client, conta_id):
    empresa_id, conta_id_ = conta_id

    resposta_criar = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id_, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    assert resposta_criar.status_code == 201
    regra_id = resposta_criar.json()["id"]
    assert resposta_criar.json()["ativo"] is True

    resposta_listar = client.get(f"/empresas/{empresa_id}/regras")
    assert resposta_listar.status_code == 200
    assert len(resposta_listar.json()) == 1

    resposta_atualizar = client.patch(
        f"/empresas/{empresa_id}/regras/{regra_id}",
        json={
            "conta_id": conta_id_, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
            "ativo": False,
        },
    )
    assert resposta_atualizar.status_code == 200
    assert resposta_atualizar.json()["ativo"] is False

    resposta_deletar = client.delete(f"/empresas/{empresa_id}/regras/{regra_id}")
    assert resposta_deletar.status_code == 204
    assert client.get(f"/empresas/{empresa_id}/regras").json() == []


def test_criar_regra_sem_condicoes_retorna_400(client, conta_id):
    empresa_id, conta_id_ = conta_id

    resposta = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id_, "lado_alvo": None, "documento_fiscal": None,
            "tipo_documento": None, "valor_min": None, "valor_max": None,
            "palavra_chave_nome": None,
        },
    )
    assert resposta.status_code == 400


def test_deletar_conta_referenciada_por_regra_retorna_409(client, conta_id):
    empresa_id, conta_id_ = conta_id
    client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": conta_id_, "lado_alvo": "RECEBEDOR",
            "documento_fiscal": "12345678000195", "tipo_documento": None,
            "valor_min": None, "valor_max": None, "palavra_chave_nome": None,
        },
    )
    resposta = client.delete(f"/contas/{conta_id_}")
    assert resposta.status_code == 409


def test_criar_regra_com_conta_inexistente_retorna_404(client):
    empresa_id = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    ).json()["id"]

    resposta = client.post(
        f"/empresas/{empresa_id}/regras",
        json={
            "conta_id": 999, "lado_alvo": "RECEBEDOR", "documento_fiscal": "12345678000195",
            "tipo_documento": None, "valor_min": None, "valor_max": None,
            "palavra_chave_nome": None,
        },
    )
    assert resposta.status_code == 404
