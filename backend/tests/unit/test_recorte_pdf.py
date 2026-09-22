import fitz

from app.infrastructure.ocr.recorte_pdf import recortar_paginas_pdf


def _pdf_com_paginas(*textos: str) -> bytes:
    documento = fitz.open()
    for texto in textos:
        pagina = documento.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_recorta_um_subconjunto_de_paginas_contiguo():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS", "PAGINA TRES")

    recorte = recortar_paginas_pdf(original, [1, 2])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 2
        assert "PAGINA DOIS" in resultado[0].get_text()
        assert "PAGINA TRES" in resultado[1].get_text()
    finally:
        resultado.close()


def test_recorta_uma_unica_pagina():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS")

    recorte = recortar_paginas_pdf(original, [0])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 1
        assert "PAGINA UM" in resultado[0].get_text()
    finally:
        resultado.close()


def test_recorte_preserva_ordem_dos_indices():
    original = _pdf_com_paginas("PAGINA UM", "PAGINA DOIS", "PAGINA TRES")

    recorte = recortar_paginas_pdf(original, [2, 0])

    resultado = fitz.open(stream=recorte, filetype="pdf")
    try:
        assert resultado.page_count == 2
        assert "PAGINA TRES" in resultado[0].get_text()
        assert "PAGINA UM" in resultado[1].get_text()
    finally:
        resultado.close()
