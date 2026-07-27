import io
import shutil

import pytest
from PIL import Image, ImageDraw

from app.infrastructure.ocr.tesseract_engine import TesseractIndisponivel, TesseractOcrEngine

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None,
    reason="Tesseract binary not installed on this machine",
)


def _imagem_com_texto(texto: str) -> bytes:
    imagem = Image.new("RGB", (400, 100), color="white")
    desenho = ImageDraw.Draw(imagem)
    desenho.text((10, 40), texto, fill="black")
    buffer = io.BytesIO()
    imagem.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extrai_texto_de_imagem():
    engine = TesseractOcrEngine()
    imagem_bytes = _imagem_com_texto("TESTE OCR")

    texto = engine.extrair_texto(imagem_bytes)

    assert "TESTE" in texto.upper() or "OCR" in texto.upper()


def test_engine_indisponivel_levanta_excecao(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)

    with pytest.raises(TesseractIndisponivel):
        TesseractOcrEngine()
