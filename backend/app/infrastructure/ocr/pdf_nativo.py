import io

from pypdf import PdfReader

TAMANHO_MINIMO_TEXTO = 20


def extrair_texto_nativo(conteudo_pdf: bytes) -> str | None:
    leitor = PdfReader(io.BytesIO(conteudo_pdf))
    texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages).strip()
    if len(texto) < TAMANHO_MINIMO_TEXTO:
        return None
    return texto
