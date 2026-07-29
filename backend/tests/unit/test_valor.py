from decimal import Decimal

from app.infrastructure.extracao.valor import extrair_valor


def test_extrai_valor_com_milhar():
    assert extrair_valor("Valor: R$ 1.234,56") == Decimal("1234.56")


def test_extrai_valor_sem_espaco():
    assert extrair_valor("Total R$150,00 pago") == Decimal("150.00")


def test_texto_sem_valor_retorna_none():
    assert extrair_valor("Nenhum valor monetário aqui.") is None
