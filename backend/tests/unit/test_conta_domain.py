import pytest

from app.domain.entities import Conta
from app.domain.enums import NaturezaConta


def test_conta_analitica_pode_ser_usada_em_lancamento():
    conta = Conta(
        id=1,
        plano_conta_id=1,
        codigo="1.1.01",
        descricao="Caixa",
        natureza=NaturezaConta.ATIVO,
        conta_analitica=True,
        conta_pai_id=None,
    )
    conta.validar_uso_em_lancamento()  # não deve levantar exceção


def test_conta_sintetica_nao_pode_ser_usada_em_lancamento():
    conta = Conta(
        id=1,
        plano_conta_id=1,
        codigo="1.1",
        descricao="Disponibilidades",
        natureza=NaturezaConta.ATIVO,
        conta_analitica=False,
        conta_pai_id=None,
    )
    with pytest.raises(ValueError, match="conta sintética"):
        conta.validar_uso_em_lancamento()
