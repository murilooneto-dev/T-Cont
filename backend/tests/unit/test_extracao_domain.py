from decimal import Decimal
from datetime import date

from app.domain.entities import Extracao
from app.domain.enums import TipoDocumento


def test_extracao_permite_todos_os_campos_ausentes_exceto_tipo():
    extracao = Extracao(
        id=None, documento_id=1, pagador_nome=None, pagador_documento=None,
        recebedor_nome=None, recebedor_documento=None, valor=None,
        data_pagamento=None, tipo_documento=TipoDocumento.OUTRO, banco_nome=None,
    )
    assert extracao.pagador_nome is None
    assert extracao.tipo_documento == TipoDocumento.OUTRO


def test_extracao_com_todos_os_campos_preenchidos():
    extracao = Extracao(
        id=None, documento_id=1, pagador_nome="JOAO DA SILVA",
        pagador_documento="12345678900", recebedor_nome="ENERGISA",
        recebedor_documento="12345678000199", valor=Decimal("150.00"),
        data_pagamento=date(2026, 3, 15), tipo_documento=TipoDocumento.PIX,
        banco_nome="Itaú",
    )
    assert extracao.valor == Decimal("150.00")
    assert extracao.data_pagamento == date(2026, 3, 15)
