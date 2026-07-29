from decimal import Decimal
from datetime import date

from app.domain.entities import Documento, Empresa, Extracao
from app.domain.enums import TipoDocumento
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_extracao_repository import (
    SqlAlchemyExtracaoRepository,
)


def _criar_documento(db_session):
    empresa = SqlAlchemyEmpresaRepository(db_session).criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    documento = SqlAlchemyDocumentoRepository(db_session).criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()
    return documento


def test_criar_extracao_com_campos_nulos(db_session):
    documento = _criar_documento(db_session)
    repo = SqlAlchemyExtracaoRepository(db_session)

    criada = repo.criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome=None, pagador_documento=None,
            recebedor_nome=None, recebedor_documento=None, valor=None,
            data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.id == criada.id
    assert encontrada.pagador_nome is None
    assert encontrada.tipo_documento == TipoDocumento.OUTRO


def test_criar_extracao_com_todos_os_campos(db_session):
    documento = _criar_documento(db_session)
    repo = SqlAlchemyExtracaoRepository(db_session)

    repo.criar(
        Extracao(
            id=None, documento_id=documento.id, pagador_nome="JOAO DA SILVA",
            pagador_documento="12345678900", recebedor_nome="ENERGISA",
            recebedor_documento="12345678000199", valor=Decimal("150.00"),
            data_pagamento=date(2026, 3, 15), tipo_documento=TipoDocumento.PIX,
            banco_nome="Itaú",
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.valor == Decimal("150.00")
    assert encontrada.data_pagamento == date(2026, 3, 15)
    assert encontrada.tipo_documento == TipoDocumento.PIX


def test_obter_por_documento_id_inexistente_retorna_none(db_session):
    repo = SqlAlchemyExtracaoRepository(db_session)
    assert repo.obter_por_documento_id(999) is None
