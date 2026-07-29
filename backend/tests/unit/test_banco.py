from app.infrastructure.extracao.banco import extrair_banco


def test_extrai_itau():
    assert extrair_banco("Banco Itaú Unibanco S.A.") == "Itaú"


def test_extrai_bradesco_case_insensitive():
    assert extrair_banco("BRADESCO S.A. - Comprovante") == "Bradesco"


def test_extrai_nubank():
    assert extrair_banco("Comprovante Nubank") == "Nubank"


def test_sem_banco_conhecido_retorna_none():
    assert extrair_banco("Comprovante de um banco não listado") is None
