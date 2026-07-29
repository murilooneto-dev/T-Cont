from decimal import Decimal

from app.infrastructure.extracao.valor import extrair_valor


def test_extrai_valor_com_milhar():
    assert extrair_valor("Valor: R$ 1.234,56") == Decimal("1234.56")


def test_extrai_valor_sem_espaco():
    assert extrair_valor("Total R$150,00 pago") == Decimal("150.00")


def test_texto_sem_valor_retorna_none():
    assert extrair_valor("Nenhum valor monetário aqui.") is None


def test_prioriza_valor_total_quando_ha_multiplos_valores():
    texto = "Tarifa: R$ 5,00\nValor Total: R$ 1.239,56"
    assert extrair_valor(texto) == Decimal("1239.56")


def test_usa_primeiro_valor_quando_nenhum_e_total():
    texto = "Valor Tarifa: R$ 5,00\nValor Adicional: R$ 3,00"
    assert extrair_valor(texto) == Decimal("5.00")


def test_nao_confunde_subtotal_com_total():
    texto = "Subtotal: R$ 50,00\nDesconto: R$ 5,00\nTotal: R$ 45,00"
    assert extrair_valor(texto) == Decimal("45.00")
