import logging

import httpx

from app.core.config import settings
from app.domain.entities import Conta, Extracao

logger = logging.getLogger(__name__)


def _montar_prompt(extracao: Extracao, contas: list[Conta]) -> str:
    linhas_contas = "\n".join(f"{conta.codigo} — {conta.descricao}" for conta in contas)
    return (
        "Você é um assistente de classificação contábil. Dado um comprovante de "
        "pagamento e uma lista de contas, responda APENAS o código de uma das contas "
        "listadas que melhor representa a natureza deste pagamento, ou a palavra "
        "NENHUMA se nenhuma parecer adequada. Não escreva mais nada além do código "
        "ou da palavra NENHUMA.\n\n"
        f"Tipo de documento: {extracao.tipo_documento.value}\n"
        f"Pagador: {extracao.pagador_nome or 'não identificado'}\n"
        f"Recebedor: {extracao.recebedor_nome or 'não identificado'}\n"
        f"Valor: {extracao.valor if extracao.valor is not None else 'não identificado'}\n"
        f"Banco: {extracao.banco_nome or 'não identificado'}\n\n"
        "Contas disponíveis:\n"
        f"{linhas_contas}\n"
    )


def classificar_por_ia(extracao: Extracao, contas: list[Conta]) -> int | None:
    """Tenta classificar via IA local (Ollama). Nunca lança exceção — qualquer

    falha (servidor indisponível, timeout, resposta fora das opções oferecidas)
    vira `None`, para que a cadeia de classificação caia pro fuzzy sem quebrar
    o processamento do documento/lote.
    """
    if not contas:
        return None

    prompt = _montar_prompt(extracao, contas)
    try:
        resposta = httpx.post(
            f"{settings.ollama_host}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=settings.ollama_timeout_segundos,
        )
        resposta.raise_for_status()
        texto = resposta.json().get("response", "").strip()
    except Exception:
        logger.warning("Falha ao consultar a IA (Ollama) para classificação.", exc_info=True)
        return None

    for conta in contas:
        if texto.upper() == conta.codigo.upper():
            return conta.id
    return None
