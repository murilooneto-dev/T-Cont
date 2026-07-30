from decimal import Decimal

from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento


def test_regra_permite_todos_os_campos_opcionais_ausentes():
    regra = Regra(
        id=None, empresa_id=1, conta_id=10, lado_alvo=None, documento_fiscal=None,
        tipo_documento=TipoDocumento.PIX, valor_min=None, valor_max=None,
        palavra_chave_nome=None,
    )
    assert regra.ativo is True
    assert regra.lado_alvo is None


def test_regra_com_todos_os_campos_preenchidos():
    regra = Regra(
        id=None, empresa_id=1, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=TipoDocumento.PIX,
        valor_min=Decimal("100.00"), valor_max=Decimal("500.00"),
        palavra_chave_nome="ENERGISA", ativo=False,
    )
    assert regra.lado_alvo == LadoRegra.RECEBEDOR
    assert regra.valor_min == Decimal("100.00")
    assert regra.ativo is False
