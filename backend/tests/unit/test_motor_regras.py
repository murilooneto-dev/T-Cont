from decimal import Decimal

from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra, TipoDocumento
from app.infrastructure.classificacao.motor_regras import encontrar_regra_mais_especifica


def _extracao(**overrides):
    base = dict(
        id=1, documento_id=1, pagador_nome="JOAO", pagador_documento="12345678900",
        recebedor_nome="ENERGISA", recebedor_documento="12345678000195",
        valor=Decimal("150.00"), data_pagamento=None, tipo_documento=TipoDocumento.PIX,
        banco_nome=None,
    )
    base.update(overrides)
    return Extracao(**base)


def _regra(id=1, **overrides):
    base = dict(
        id=id, empresa_id=1, conta_id=10, lado_alvo=None, documento_fiscal=None,
        tipo_documento=None, valor_min=None, valor_max=None, palavra_chave_nome=None,
        ativo=True,
    )
    base.update(overrides)
    return Regra(**base)


def test_regra_por_cnpj_recebedor_bate():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is regra


def test_regra_por_cnpj_nao_bate_com_documento_diferente():
    regra = _regra(lado_alvo=LadoRegra.PAGADOR, documento_fiscal="99999999999")
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is None


def test_regra_mais_especifica_vence_sobre_regra_generica():
    regra_generica = _regra(id=1, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    regra_especifica = _regra(
        id=2, conta_id=20, lado_alvo=LadoRegra.RECEBEDOR,
        documento_fiscal="12345678000195", tipo_documento=TipoDocumento.PIX,
    )
    encontrada = encontrar_regra_mais_especifica(_extracao(), [regra_generica, regra_especifica])
    assert encontrada is regra_especifica


def test_empate_de_especificidade_regra_mais_antiga_vence():
    regra_a = _regra(id=5, conta_id=10, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    regra_b = _regra(id=2, conta_id=20, lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195")
    encontrada = encontrar_regra_mais_especifica(_extracao(), [regra_a, regra_b])
    assert encontrada is regra_b


def test_regra_por_faixa_de_valor():
    regra = _regra(valor_min=Decimal("100.00"), valor_max=Decimal("200.00"))
    assert encontrar_regra_mais_especifica(_extracao(valor=Decimal("150.00")), [regra]) is regra
    assert encontrar_regra_mais_especifica(_extracao(valor=Decimal("50.00")), [regra]) is None
    assert encontrar_regra_mais_especifica(_extracao(valor=None), [regra]) is None


def test_regra_por_palavra_chave_no_nome():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, palavra_chave_nome="ENERGISA")
    assert encontrar_regra_mais_especifica(_extracao(recebedor_nome="ENERGISA CE"), [regra]) is regra
    assert encontrar_regra_mais_especifica(_extracao(recebedor_nome="CLARO"), [regra]) is None


def test_regra_inativa_e_ignorada():
    regra = _regra(lado_alvo=LadoRegra.RECEBEDOR, documento_fiscal="12345678000195", ativo=False)
    assert encontrar_regra_mais_especifica(_extracao(), [regra]) is None


def test_sem_regras_retorna_none():
    assert encontrar_regra_mais_especifica(_extracao(), []) is None
