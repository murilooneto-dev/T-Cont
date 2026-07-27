import fitz


def renderizar_paginas_pdf(conteudo_pdf: bytes, dpi: int = 200) -> list[bytes]:
    documento = fitz.open(stream=conteudo_pdf, filetype="pdf")
    zoom = dpi / 72
    matriz = fitz.Matrix(zoom, zoom)
    imagens = [pagina.get_pixmap(matrix=matriz).tobytes("png") for pagina in documento]
    documento.close()
    return imagens
