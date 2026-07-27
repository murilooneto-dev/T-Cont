from unittest.mock import patch

import fitz

from app.domain.enums import MetodoOcr
from app.infrastructure.ocr.pipeline import processar_documento


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


def test_pdf_com_texto_usa_extracao_nativa():
    conteudo = _pdf_com_texto("COMPROVANTE TESTE 123456789012345")

    resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PDF_NATIVO
    assert "COMPROVANTE" in resultado.texto
    assert resultado.erro is None


def test_pdf_escaneado_usa_paddleocr_quando_disponivel():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto via paddle"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.texto == "texto via paddle"
    assert resultado.erro is None


def test_pdf_escaneado_cai_para_tesseract_quando_paddle_falha():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine") as MockTesseract:
        MockTesseract.return_value.extrair_texto.return_value = "texto via tesseract"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.TESSERACT
    assert resultado.texto == "texto via tesseract"
    assert resultado.erro is None


def test_imagem_direta_pula_extracao_nativa_e_vai_para_ocr():
    conteudo = b"fake-imagem-bytes"

    with patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto de imagem"

        resultado = processar_documento(conteudo, ".png")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.texto == "texto de imagem"


def test_ambos_engines_falham_retorna_resultado_com_erro():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine", side_effect=RuntimeError("sem binario")):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.texto == ""
