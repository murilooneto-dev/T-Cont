from app.domain.entities import Conta, Empresa, PlanoContas
from app.domain.enums import NaturezaConta
from app.infrastructure.repositories.sqlalchemy_conta_repository import (
    SqlAlchemyContaRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.infrastructure.repositories.sqlalchemy_plano_contas_repository import (
    SqlAlchemyPlanoContasRepository,
)


def test_criar_e_obter_empresa(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")

    criada = repo.criar(empresa)
    db_session.commit()

    encontrada = repo.obter_por_id(criada.id)
    assert encontrada.razao_social == "Tesserato"
    assert encontrada.cnpj == "12345678000199"


def test_obter_empresa_por_cnpj(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    repo.criar(Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199"))
    db_session.commit()

    encontrada = repo.obter_por_cnpj("12345678000199")
    assert encontrada is not None


def test_criar_plano_contas_e_contas_com_hierarquia(db_session):
    empresa_repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = empresa_repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()

    plano_repo = SqlAlchemyPlanoContasRepository(db_session)
    plano = plano_repo.criar(PlanoContas(id=None, empresa_id=empresa.id, nome="Plano Padrão"))
    db_session.commit()

    conta_repo = SqlAlchemyContaRepository(db_session)
    pai = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1", descricao="Disponibilidades",
            natureza=NaturezaConta.ATIVO, conta_analitica=False,
        )
    )
    db_session.commit()
    filha = conta_repo.criar(
        Conta(
            id=None, plano_conta_id=plano.id, codigo="1.1.01", descricao="Caixa",
            natureza=NaturezaConta.ATIVO, conta_analitica=True, conta_pai_id=pai.id,
        )
    )
    db_session.commit()

    contas = conta_repo.listar_por_plano(plano.id)
    assert len(contas) == 2
    assert filha.conta_pai_id == pai.id
