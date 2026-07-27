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


def test_confirmar_importacao_em_plano_inexistente_retorna_404(client, plano_id):
    response = client.post(
        "/planos-contas/999/import/confirm",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert response.status_code == 404


def test_confirmar_importacao_aceita_natureza_em_caixa_titulo(client, plano_id):
    conteudo = (
        "Codigo,Descricao,Natureza,Conta Pai\n"
        "1.1,Disponibilidades,Ativo,\n"
        "1.1.01,Caixa,ativo,1.1\n"
    ).encode("utf-8")

    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", conteudo, "text/csv")},
    )

    assert response.status_code == 201
    contas = response.json()
    assert {c["natureza"] for c in contas} == {"ATIVO"}
    # Sem coluna de conta analítica, a hierarquia é derivada do lote.
    por_codigo = {c["codigo"]: c for c in contas}
    assert por_codigo["1.1"]["conta_analitica"] is False
    assert por_codigo["1.1.01"]["conta_analitica"] is True


def test_confirmar_importacao_com_natureza_desconhecida_retorna_422(client, plano_id):
    conteudo = b"Codigo,Descricao,Natureza\n1.1,Disponibilidades,Resultado\n"

    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", conteudo, "text/csv")},
    )

    assert response.status_code == 422
    assert client.get(f"/planos-contas/{plano_id}/contas").json() == []


def test_confirmar_importacao_sem_natureza_retorna_422(client, plano_id):
    conteudo = b"Codigo,Descricao\n1.1,Disponibilidades\n"

    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", conteudo, "text/csv")},
    )

    assert response.status_code == 422
    assert client.get(f"/planos-contas/{plano_id}/contas").json() == []


def test_confirmar_importacao_com_codigo_em_branco_retorna_422(client, plano_id):
    conteudo = b"Codigo,Descricao,Natureza\n,SemCodigo,ATIVO\n"

    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", conteudo, "text/csv")},
    )

    assert response.status_code == 422
    assert client.get(f"/planos-contas/{plano_id}/contas").json() == []


def test_reimportar_mesmo_arquivo_retorna_422_e_nao_duplica(client, plano_id):
    primeira = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert primeira.status_code == 201

    segunda = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", CSV_CONTEUDO, "text/csv")},
    )
    assert segunda.status_code == 422

    assert len(client.get(f"/planos-contas/{plano_id}/contas").json()) == 2


def test_importar_csv_latin1_nao_retorna_500(client, plano_id):
    conteudo = (
        "Código,Descrição,Natureza\n"
        "3.1.02,Manutenção Predial,DESPESA\n"
    ).encode("latin-1")

    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", conteudo, "text/csv")},
    )

    assert response.status_code in (201, 422)


def test_importar_conteudo_binario_retorna_422(client, plano_id):
    response = client.post(
        f"/planos-contas/{plano_id}/import/confirm",
        files={"arquivo": ("plano.csv", bytes(range(256)) * 4, "text/csv")},
    )

    assert response.status_code == 422
