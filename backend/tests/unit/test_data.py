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


def test_prioriza_data_de_pagamento_quando_ha_multiplas_datas():
    assert extrair_data("Data de emissão: 01/03/2026\nData de pagamento: 15/03/2026") == date(2026, 3, 15)


def test_usa_primeira_data_quando_nenhuma_e_pagamento():
    assert extrair_data("Data de emissão: 01/03/2026\nData de vencimento: 10/03/2026") == date(2026, 3, 1)


def test_reconhece_forma_pago():
    assert extrair_data("Pago em 20/04/2026, referente à fatura de 01/04/2026") == date(2026, 4, 20)


def test_ignora_digitos_de_um_numero_de_protocolo_maior():
    assert extrair_data("Protocolo 999912/03/2026999") is None


def test_fallback_pula_data_invalida_e_usa_a_proxima_valida():
    assert extrair_data("Emissao: 32/13/2026 e Vencimento: 15/03/2026") == date(2026, 3, 15)
