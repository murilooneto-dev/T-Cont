import io

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("paddleocr")

from app.infrastructure.ocr.paddle_engine import PaddleOcrEngine  # noqa: E402


def _imagem_com_texto(texto: str) -> bytes:
    imagem = Image.new("RGB", (400, 100), color="white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text((10, 40), texto, fill="black")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extrai_texto_de_imagem():
    engine = PaddleOcrEngine()
    imagem_bytes = _imagem_com_texto("TESTE OCR")

    texto = engine.extrair_texto(imagem_bytes)

    assert isinstance(texto, str)
