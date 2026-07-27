import io

import numpy as np
from PIL import Image

from app.application.ports import OcrEngine


class PaddleOcrEngine(OcrEngine):
    def __init__(self):
        from paddleocr import PaddleOCR

        self._ocr = PaddleOCR(use_angle_cls=True, lang="pt", show_log=False)

    def extrair_texto(self, imagem_bytes: bytes) -> str:
        imagem = Image.open(io.BytesIO(imagem_bytes)).convert("RGB")
        resultado = self._ocr.ocr(np.array(imagem), cls=True)

        linhas = []
        for bloco in resultado or []:
            for _caixa, (texto, _confianca) in bloco:
                linhas.append(texto)
        return "\n".join(linhas).strip()
