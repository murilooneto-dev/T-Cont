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


def test_extrai_texto_de_pdf_com_texto_pesquisavel():
    conteudo = _pdf_com_texto("COMPROVANTE DE PAGAMENTO - VALOR R$ 150,00")

    texto = extrair_texto_nativo(conteudo)

    assert texto is not None
    assert "COMPROVANTE" in texto


def test_retorna_none_para_pdf_sem_texto_pesquisavel():
    conteudo = _pdf_vazio()

    texto = extrair_texto_nativo(conteudo)

    assert texto is None
