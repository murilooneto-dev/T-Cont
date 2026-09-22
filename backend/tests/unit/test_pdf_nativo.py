import fitz  # PyMuPDF, used here only to build test fixtures

from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo


def _pdf_com_texto(texto: str) -> bytes:
    documento = fitz.open()
    pagina = documento.new_page()
    pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def _pdf_vazio() -> bytes:
    documento = fitz.open()
    documento.new_page()
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def _pdf_com_paginas(*textos: str) -> bytes:
    documento = fitz.open()
    for texto in textos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_extrai_texto_de_pdf_com_texto_pesquisavel():
    conteudo = _pdf_com_texto("COMPROVANTE DE PAGAMENTO - VALOR R$ 150,00")

    texto = extrair_texto_nativo(conteudo)

    assert texto is not None
    assert "COMPROVANTE" in texto[0]


def test_retorna_none_para_pdf_sem_texto_pesquisavel():
    conteudo = _pdf_vazio()

    texto = extrair_texto_nativo(conteudo)

    assert texto is None


def test_devolve_uma_entrada_por_pagina():
    conteudo = _pdf_com_paginas("PRIMEIRA PAGINA TEXTO SUFICIENTE", "SEGUNDA PAGINA TEXTO SUFICIENTE")

    resultado = extrair_texto_nativo(conteudo)

    assert resultado is not None
    assert len(resultado) == 2
    assert "PRIMEIRA PAGINA" in resultado[0]
    assert "SEGUNDA PAGINA" in resultado[1]


def test_pdf_sem_texto_suficiente_devolve_none():
    documento = fitz.open()
    documento.new_page()
    conteudo = documento.tobytes()
    documento.close()

    assert extrair_texto_nativo(conteudo) is None


def test_limiar_minimo_e_avaliado_sobre_o_total_nao_por_pagina():
    # Uma página curta (poucas letras) não deve, sozinha, derrubar o
    # documento inteiro para OCR se o total combinado já é suficiente.
    conteudo = _pdf_com_paginas("AB", "TEXTO SUFICIENTEMENTE LONGO NA SEGUNDA PAGINA PARA PASSAR DO LIMIAR")

    resultado = extrair_texto_nativo(conteudo)

    assert resultado is not None
    assert len(resultado) == 2
    assert resultado[0] == "AB"
