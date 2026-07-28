import io

import fitz
import pytest
from PIL import Image

from app.infrastructure.ocr.pipeline import processar_documento
from app.infrastructure.ocr.renderizador_pdf import (
    MAX_PAGINAS,
    PdfComPaginasDemais,
    renderizar_paginas_pdf,
)


def _pdf_com_n_paginas(n: int) -> bytes:
    documento = fitz.open()
    for _ in range(n):
        documento.new_page()
    conteudo = documento.tobytes()
    documento.close()
    return conteudo


def test_renderiza_uma_imagem_por_pagina():
    conteudo = _pdf_com_n_paginas(2)

    imagens = renderizar_paginas_pdf(conteudo)

    assert len(imagens) == 2
    for imagem_bytes in imagens:
        imagem = Image.open(io.BytesIO(imagem_bytes))
        assert imagem.format == "PNG"
        assert imagem.width > 0 and imagem.height > 0


def test_recusa_pdf_acima_do_limite_de_paginas():
    conteudo = _pdf_com_n_paginas(MAX_PAGINAS + 5)

    with pytest.raises(PdfComPaginasDemais):
        renderizar_paginas_pdf(conteudo)


def test_renderiza_pdf_exatamente_no_limite_de_paginas():
    imagens = renderizar_paginas_pdf(_pdf_com_n_paginas(MAX_PAGINAS), dpi=36)

    assert len(imagens) == MAX_PAGINAS


def test_pipeline_converte_pdf_gigante_em_erro_do_documento():
    """Páginas em branco não têm texto nativo, então o pipeline cai no
    renderizador — que recusa o PDF e vira um erro no documento (status ERRO),
    em vez de derrubar o worker ou gravar um OCR parcial."""
    resultado = processar_documento(_pdf_com_n_paginas(MAX_PAGINAS + 5), ".pdf")

    assert resultado.erro is not None
    assert "página" in resultado.erro
