import fitz

# Comprovantes de pagamento praticamente nunca passam de duas páginas. O limite
# existe para que um PDF gigante (acidental ou malicioso) não renderize
# centenas de bitmaps e estoure a memória do worker.
MAX_PAGINAS = 20


class PdfComPaginasDemais(Exception):
    def __init__(self, total_paginas: int):
        super().__init__(
            f"PDF com {total_paginas} páginas excede o limite de {MAX_PAGINAS} páginas."
        )


def renderizar_paginas_pdf(conteudo_pdf: bytes, dpi: int = 200) -> list[bytes]:
    documento = fitz.open(stream=conteudo_pdf, filetype="pdf")
    try:
        total_paginas = documento.page_count
        if total_paginas > MAX_PAGINAS:
            # Falhar explicitamente é mais honesto que truncar em silêncio: o
            # `processar_documento` converte esta exceção em um erro no
            # documento (status ERRO com mensagem), em vez de gravar um OCR
            # parcial como se fosse o documento inteiro.
            raise PdfComPaginasDemais(total_paginas)
        zoom = dpi / 72
        matriz = fitz.Matrix(zoom, zoom)
        return [pagina.get_pixmap(matrix=matriz).tobytes("png") for pagina in documento]
    finally:
        documento.close()
