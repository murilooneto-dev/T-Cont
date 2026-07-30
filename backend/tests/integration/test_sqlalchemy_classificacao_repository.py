from app.domain.entities import (
    Conta, Documento, Empresa, PlanoContas,
)
from app.domain.enums import NaturezaConta, OrigemClassificacao
from app.domain.entities import Classificacao
from app.infrastructure.repositories.sqlalchemy_classificacao_repository import (
    SqlAlchemyClassificacaoRepository,
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


def test_criar_classificacao_por_regra(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyClassificacaoRepository(db_session)

    criada = repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.REGRA, regra_id=None, score_similaridade=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_documento_id(documento.id)
    assert encontrada.id == criada.id
    assert encontrada.origem == OrigemClassificacao.REGRA
    assert encontrada.score_similaridade is None


def test_criar_classificacao_por_fuzzy_com_score(db_session):
    empresa, conta, documento = _empresa_conta_documento(db_session)
    repo = SqlAlchemyClassificacaoRepository(db_session)

    repo.criar(
        Classificacao(
            id=None, empresa_id=empresa.id, documento_id=documento.id, conta_id=conta.id,
            origem=OrigemClassificacao.FUZZY, regra_id=None, score_similaridade=0.87,
        )
    )
    db_session.commit()

    encontradas = repo.listar_por_empresa(empresa.id)
    assert len(encontradas) == 1
    assert encontradas[0].score_similaridade == 0.87


def test_obter_por_documento_id_inexistente_retorna_none(db_session):
    repo = SqlAlchemyClassificacaoRepository(db_session)
    assert repo.obter_por_documento_id(999) is None
