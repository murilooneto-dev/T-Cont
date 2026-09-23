import re
import unicodedata

from app.domain.entities import Conta, Extracao
from app.domain.enums import DirecaoLancamento


def _somente_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


def resolver_direcao(empresa_cnpj: str, extracao: Extracao) -> DirecaoLancamento | None:
    """Compara o CNPJ da empresa contra pagador/recebedor extraídos (só dígitos).

    None quando nenhum dos dois bate, ou quando os dois batem ao mesmo tempo
    (extração ambígua/degenerada) — os dois casos caem pra revisão manual.
    """
    cnpj_empresa = _somente_digitos(empresa_cnpj)
    pagador = _somente_digitos(extracao.pagador_documento) if extracao.pagador_documento else None
    recebedor = _somente_digitos(extracao.recebedor_documento) if extracao.recebedor_documento else None

    empresa_e_pagador = pagador == cnpj_empresa
    empresa_e_recebedor = recebedor == cnpj_empresa

    if empresa_e_pagador and empresa_e_recebedor:
        return None
    if empresa_e_pagador:
        return DirecaoLancamento.PAGAMENTO
    if empresa_e_recebedor:
        return DirecaoLancamento.RECEBIMENTO
    return None


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.upper()


def resolver_conta_bancaria(banco_nome: str | None, contas_bancarias: list[Conta]) -> int | None:
    """Casa `banco_nome` (extraído do comprovante) contra a descrição das contas
    bancárias do plano (substring, sem acento, case-insensitive).

    None quando o banco não foi identificado na extração, quando nenhuma conta
    bate, ou quando mais de uma bate (ambiguidade entre agências/filiais do
    mesmo banco) — todos os casos caem pra revisão manual.
    """
    if banco_nome is None:
        return None
    alvo = _normalizar(banco_nome)
    correspondencias = [
        conta for conta in contas_bancarias if alvo in _normalizar(conta.descricao)
    ]
    if len(correspondencias) != 1:
        return None
    return correspondencias[0].id


def resolver_lados_lancamento(
    direcao: DirecaoLancamento | None,
    conta_contrapartida: Conta,
    conta_bancaria: Conta | None,
) -> tuple[Conta | None, Conta | None]:
    """Devolve (conta_debito, conta_credito) a partir da direção já resolvida.

    Se a direção não foi resolvida, não dá pra saber de que lado a
    contrapartida entra — os dois lados vêm None. Se a direção é conhecida mas
    a conta bancária não foi resolvida, a contrapartida ainda aparece no lado
    certo; só o lado do banco fica None.
    """
    if direcao is None:
        return None, None
    if direcao == DirecaoLancamento.PAGAMENTO:
        return conta_contrapartida, conta_bancaria
    return conta_bancaria, conta_contrapartida
