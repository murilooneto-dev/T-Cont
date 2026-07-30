from decimal import Decimal

from app.domain.entities import Conta, Empresa, PlanoContas, Regra
from app.domain.enums import LadoRegra, NaturezaConta, TipoDocumento
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)
from app.infrastructure.repositories.sqlalchemy_regra_repository import (
    SqlAlchemyRegraRepository,
)


def _empresa_e_conta(db_session):
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
    return empresa, conta


def test_criar_regra_com_campos_minimos(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)

    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    encontrada = repo.obter_por_id(criada.id)
    assert encontrada.tipo_documento == TipoDocumento.PIX
    assert encontrada.lado_alvo is None
    assert encontrada.ativo is True


def test_criar_regra_com_todos_os_campos(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)

    repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id,
            lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195",
            tipo_documento=TipoDocumento.PIX, valor_min=Decimal("100.00"),
            valor_max=Decimal("500.00"), palavra_chave_nome="ENERGISA", ativo=False,
        )
    )
    db_session.commit()

    encontradas = repo.listar_por_empresa(empresa.id)
    assert len(encontradas) == 1
    assert encontradas[0].lado_alvo == LadoRegra.RECEBEDOR
    assert encontradas[0].valor_min == Decimal("100.00")
    assert encontradas[0].ativo is False


def test_atualizar_regra(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)
    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    criada.ativo = False
    criada.tipo_documento = TipoDocumento.BOLETO
    repo.atualizar(criada)
    db_session.commit()

    atualizada = repo.obter_por_id(criada.id)
    assert atualizada.ativo is False
    assert atualizada.tipo_documento == TipoDocumento.BOLETO


def test_deletar_regra(db_session):
    empresa, conta = _empresa_e_conta(db_session)
    repo = SqlAlchemyRegraRepository(db_session)
    criada = repo.criar(
        Regra(
            id=None, empresa_id=empresa.id, conta_id=conta.id, lado_alvo=None,
            documento_fiscal=None, tipo_documento=TipoDocumento.PIX,
            valor_min=None, valor_max=None, palavra_chave_nome=None,
        )
    )
    db_session.commit()

    repo.deletar(criada.id)
    db_session.commit()

    assert repo.obter_por_id(criada.id) is None
