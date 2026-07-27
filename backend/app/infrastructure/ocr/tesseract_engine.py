import io
import shutil

import pytesseract
from PIL import Image

from app.application.ports import OcrEngine
from app.core.exceptions import DomainError


class TesseractIndisponivel(DomainError):
    def __init__(self):
        super().__init__("Executável 'tesseract' não encontrado no PATH.")


class TesseractOcrEngine(OcrEngine):
    def __init__(self):
        if shutil.which("tesseract") is None:
            raise TesseractIndisponivel()

    def extrair_texto(self, imagem_bytes: bytes) -> str:
        imagem = Image.open(io.BytesIO(imagem_bytes))
        return pytesseract.image_to_string(imagem, lang="por").strip()
