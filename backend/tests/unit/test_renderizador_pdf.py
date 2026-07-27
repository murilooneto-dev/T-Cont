import io

import fitz
from PIL import Image

from app.infrastructure.ocr.renderizador_pdf import renderizar_paginas_pdf


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
