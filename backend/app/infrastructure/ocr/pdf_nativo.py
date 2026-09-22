import io

from pypdf import PdfReader

TAMANHO_MINIMO_TEXTO = 20


def extrair_texto_nativo(conteudo_pdf: bytes) -> list[str] | None:
    leitor = PdfReader(io.BytesIO(conteudo_pdf))
    textos_por_pagina = [pagina.extract_text() or "" for pagina in leitor.pages]
    total = sum(len(texto) for texto in textos_por_pagina)
    if total < TAMANHO_MINIMO_TEXTO:
        return None
    return textos_por_pagina
