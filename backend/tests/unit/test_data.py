from datetime import date

from app.infrastructure.extracao.data import extrair_data


def test_extrai_data_com_barra():
    assert extrair_data("Data do pagamento: 15/03/2026") == date(2026, 3, 15)


def test_extrai_data_com_hifen():
    assert extrair_data("Pago em 31-12-2025") == date(2025, 12, 31)


def test_data_invalida_retorna_none():
    assert extrair_data("Data: 32/13/2026") is None


def test_texto_sem_data_retorna_none():
    assert extrair_data("Nenhuma data aqui.") is None
