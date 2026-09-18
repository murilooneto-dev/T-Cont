from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, get_storage
from app.infrastructure.db.base import Base
from app.infrastructure.db import models  # noqa: F401
from app.infrastructure.db.session import get_engine
from app.infrastructure.storage.file_storage import LocalFileStorageService
from app.main import app


@pytest.fixture
def client(tmp_path):
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

    def override_get_storage():
        return LocalFileStorageService(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = override_get_storage
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empresa_id(client):
    response = client.post(
        "/empresas", json={"razao_social": "Tesserato", "nome_fantasia": None, "cnpj": "12345678000199"}
    )
    return response.json()["id"]


@pytest.fixture
def conta_id(client, empresa_id):
    plano_id = client.post(
        f"/empresas/{empresa_id}/planos-contas", json={"nome": "Plano"}
    ).json()["id"]
    return client.post(
        f"/planos-contas/{plano_id}/contas",
        json={
            "codigo": "1", "descricao": "Energia", "natureza": "DESPESA",
            "conta_analitica": True, "conta_pai_id": None,
        },
    ).json()["id"]


def test_lote_corrige_multiplos_documentos_com_sucesso(client, empresa_id, conta_id):
    ids = [
        client.post(
            f"/empresas/{empresa_id}/documentos",
            files={"arquivos": (f"{i}.pdf", b"conteudo", "application/pdf")},
        ).json()[0]["documento"]["id"]
        for i in range(2)
    ]

    resposta = client.patch(
        "/documentos/classificacao/lote", json={"documento_ids": ids, "conta_id": conta_id}
    )

    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert len(resultados) == 2
    assert all(r["sucesso"] for r in resultados)
    assert all(r["classificacao"]["conta_id"] == conta_id for r in resultados)


def test_lote_com_documento_inexistente_reporta_erro_por_item_sem_falhar_o_resto(
    client, empresa_id, conta_id
):
    documento_id = client.post(
        f"/empresas/{empresa_id}/documentos",
        files={"arquivos": ("a.pdf", b"conteudo", "application/pdf")},
    ).json()[0]["documento"]["id"]

    resposta = client.patch(
        "/documentos/classificacao/lote",
        json={"documento_ids": [documento_id, 9999], "conta_id": conta_id},
    )

    assert resposta.status_code == 200
    resultados = resposta.json()["resultados"]
    assert resultados[0]["sucesso"] is True
    assert resultados[1]["sucesso"] is False
    assert resultados[1]["erro"] is not None
    assert resultados[1]["classificacao"] is None
