from app.domain.entities import Aprendizado, Conta, Documento, Empresa, PlanoContas
from app.domain.enums import NaturezaConta, OrigemClassificacao
from app.infrastructure.repositories.sqlalchemy_aprendizado_repository import (
    SqlAlchemyAprendizadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)


def _empresa_conta_documento(db_session):
    empresa = SqlAlchemyEmpresaRepository(db_session).criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    plano = SqlAlchemyPlanoContasRepository(db_session).criar(
        PlanoContas(id=None, empresa_id=empresa.id, nome="Plano")
    )
    db_session.commit()
    conta = SqlAlchemyContaRepository(db_session).criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1", descricao="Energia",
            natureza=NaturezaConta.DESPESA, conta_analitica=True,
        )
    )
    db_session.commit()
    documento = SqlAlchemyDocumentoRepository(db_session).criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()
    return empresa, conta, documento


def test_criar_aprendizado_sem_classificacao_anterior(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyAprendizadoRepository(db_session)

    criado = repo.criar(
        Aprendizado(
            id=None, empresa_id=empresa.id, documento_id=documento.id,
            conta_anterior_id=None, origem_anterior=None, conta_corrigida_id=conta.id,
        )
    )
    db_session.commit()

    encontrados = repo.listar_por_empresa(empresa.id)
    assert len(encontrados) == 1
    assert encontrados[0].id == criado.id
    assert encontrados[0].conta_anterior_id is None
    assert encontrados[0].origem_anterior is None


def test_criar_aprendizado_com_classificacao_anterior_e_regra(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyAprendizadoRepository(db_session)

    repo.criar(
        Aprendizado(
            id=None, empresa_id=empresa.id, documento_id=documento.id,
            conta_anterior_id=conta.id, origem_anterior=OrigemClassificacao.FUZZY,
            conta_corrigida_id=conta.id, regra_id=None,
        )
    )
    db_session.commit()

    encontrados = repo.listar_por_empresa(empresa.id)
    assert encontrados[0].origem_anterior == OrigemClassificacao.FUZZY
