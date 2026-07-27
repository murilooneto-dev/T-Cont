import time
from dataclasses import dataclass

from app.domain.enums import MetodoOcr
from app.infrastructure.ocr.pdf_nativo import extrair_texto_nativo
from app.infrastructure.ocr.renderizador_pdf import renderizar_paginas_pdf


@dataclass
class ResultadoPipelineOcr:
    texto: str
    metodo: MetodoOcr
    tempo_processamento_ms: int
    erro: str | None = None


def _executar_engine_em_imagens(engine, imagens: list[bytes]) -> str:
    return "\n".join(engine.extrair_texto(imagem) for imagem in imagens).strip()


def processar_documento(conteudo: bytes, extensao: str) -> ResultadoPipelineOcr:
    inicio = time.monotonic()

    if extensao == ".pdf":
        texto_nativo = extrair_texto_nativo(conteudo)
        if texto_nativo is not None:
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                texto=texto_nativo, metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=tempo_ms
            )
        imagens = renderizar_paginas_pdf(conteudo)
    else:
        imagens = [conteudo]

    erro_paddle: str | None = None
    try:
        from app.infrastructure.ocr.paddle_engine import PaddleOcrEngine

        texto = _executar_engine_em_imagens(PaddleOcrEngine(), imagens)
        if texto:
            tempo_ms = int((time.monotonic() - inicio) * 1000)
            return ResultadoPipelineOcr(
                texto=texto, metodo=MetodoOcr.PADDLEOCR, tempo_processamento_ms=tempo_ms
            )
        erro_paddle = "PaddleOCR não reconheceu texto."
    except Exception as exc:
        erro_paddle = str(exc)

    try:
        from app.infrastructure.ocr.tesseract_engine import TesseractOcrEngine

        texto = _executar_engine_em_imagens(TesseractOcrEngine(), imagens)
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        if texto:
            return ResultadoPipelineOcr(
                texto=texto, metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms
            )
        return ResultadoPipelineOcr(
            texto="", metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"Nenhum engine de OCR reconheceu texto (PaddleOCR: {erro_paddle}).",
        )
    except Exception as exc:
        tempo_ms = int((time.monotonic() - inicio) * 1000)
        return ResultadoPipelineOcr(
            texto="", metodo=MetodoOcr.TESSERACT, tempo_processamento_ms=tempo_ms,
            erro=f"PaddleOCR: {erro_paddle}; Tesseract: {exc}",
        )
