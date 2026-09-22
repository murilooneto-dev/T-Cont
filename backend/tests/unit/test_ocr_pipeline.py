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
    assert len(resultado.textos_por_pagina) == 1
    assert "COMPROVANTE" in resultado.textos_por_pagina[0]
    assert resultado.erro is None


def test_pdf_escaneado_usa_paddleocr_quando_disponivel():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto via paddle"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto via paddle"]
    assert resultado.erro is None


def test_pdf_escaneado_cai_para_tesseract_quando_paddle_falha():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine") as MockTesseract:
        MockTesseract.return_value.extrair_texto.return_value = "texto via tesseract"

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.TESSERACT
    assert resultado.textos_por_pagina == ["texto via tesseract"]
    assert resultado.erro is None


def test_imagem_direta_pula_extracao_nativa_e_vai_para_ocr():
    conteudo = b"fake-imagem-bytes"

    with patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.return_value = "texto de imagem"

        resultado = processar_documento(conteudo, ".png")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto de imagem"]


def test_pdf_com_multiplas_paginas_de_texto_nativo_preserva_cada_pagina():
    conteudo = fitz.open()
    for texto in ("PAGINA UM COMPROVANTE", "PAGINA DOIS COMPROVANTE"):
        pagina = conteudo.new_page()
        pagina.insert_text((72, 72), texto)
    conteudo_bytes = conteudo.tobytes()
    conteudo.close()

    resultado = processar_documento(conteudo_bytes, ".pdf")

    assert resultado.metodo == MetodoOcr.PDF_NATIVO
    assert len(resultado.textos_por_pagina) == 2
    assert "PAGINA UM" in resultado.textos_por_pagina[0]
    assert "PAGINA DOIS" in resultado.textos_por_pagina[1]


def test_pdf_escaneado_com_multiplas_paginas_preserva_cada_pagina():
    conteudo = _pdf_vazio()

    with patch(
        "app.infrastructure.ocr.pipeline.renderizar_paginas_pdf",
        return_value=[b"fake-imagem-1", b"fake-imagem-2"],
    ), patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine") as MockPaddle:
        MockPaddle.return_value.extrair_texto.side_effect = ["texto pagina 1", "texto pagina 2"]

        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.metodo == MetodoOcr.PADDLEOCR
    assert resultado.textos_por_pagina == ["texto pagina 1", "texto pagina 2"]


def test_ambos_engines_falham_retorna_resultado_com_erro():
    conteudo = _pdf_vazio()

    with patch("app.infrastructure.ocr.pipeline.renderizar_paginas_pdf", return_value=[b"fake-imagem"]), \
         patch("app.infrastructure.ocr.paddle_engine.PaddleOcrEngine", side_effect=RuntimeError("sem modelo")), \
         patch("app.infrastructure.ocr.tesseract_engine.TesseractOcrEngine", side_effect=RuntimeError("sem binario")):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []


def test_pdf_malformado_na_extracao_nativa_nao_propaga_excecao():
    conteudo = b"not a real pdf"

    resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []
    assert resultado.metodo == MetodoOcr.TESSERACT


def test_falha_ao_renderizar_paginas_pdf_nao_propaga_excecao():
    conteudo = _pdf_vazio()

    with patch(
        "app.infrastructure.ocr.pipeline.renderizar_paginas_pdf",
        side_effect=RuntimeError("falha ao renderizar pagina"),
    ):
        resultado = processar_documento(conteudo, ".pdf")

    assert resultado.erro is not None
    assert resultado.textos_por_pagina == []
    assert resultado.metodo == MetodoOcr.TESSERACT
