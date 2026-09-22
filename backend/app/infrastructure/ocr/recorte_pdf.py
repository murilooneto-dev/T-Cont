import fitz


def recortar_paginas_pdf(conteudo_pdf: bytes, indices_paginas: list[int]) -> bytes:
    origem = fitz.open(stream=conteudo_pdf, filetype="pdf")
    try:
        novo = fitz.open()
        try:
            for indice in indices_paginas:
                novo.insert_pdf(origem, from_page=indice, to_page=indice)
            return novo.tobytes()
        finally:
            novo.close()
    finally:
        origem.close()
