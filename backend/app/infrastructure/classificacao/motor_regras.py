from app.domain.entities import Extracao, Regra
from app.domain.enums import LadoRegra


def _nome_do_lado(extracao: Extracao, lado: LadoRegra | None) -> str | None:
    if lado == LadoRegra.PAGADOR:
        return extracao.pagador_nome
    if lado == LadoRegra.RECEBEDOR:
        return extracao.recebedor_nome
    return None


def _documento_do_lado(extracao: Extracao, lado: LadoRegra | None) -> str | None:
    if lado == LadoRegra.PAGADOR:
        return extracao.pagador_documento
    if lado == LadoRegra.RECEBEDOR:
        return extracao.recebedor_documento
    return None


def _regra_bate(regra: Regra, extracao: Extracao) -> bool:
    if regra.documento_fiscal is not None:
        if _documento_do_lado(extracao, regra.lado_alvo) != regra.documento_fiscal:
            return False
    if regra.tipo_documento is not None:
        if extracao.tipo_documento != regra.tipo_documento:
            return False
    if regra.valor_min is not None or regra.valor_max is not None:
        if extracao.valor is None:
            return False
        if regra.valor_min is not None and extracao.valor < regra.valor_min:
            return False
        if regra.valor_max is not None and extracao.valor > regra.valor_max:
            return False
    if regra.palavra_chave_nome is not None:
        nome = _nome_do_lado(extracao, regra.lado_alvo)
        if nome is None or regra.palavra_chave_nome.upper() not in nome.upper():
            return False
    return True


def _especificidade(regra: Regra) -> int:
    pontos = 0
    if regra.documento_fiscal is not None:
        pontos += 1
    if regra.tipo_documento is not None:
        pontos += 1
    if regra.valor_min is not None or regra.valor_max is not None:
        pontos += 1
    if regra.palavra_chave_nome is not None:
        pontos += 1
    return pontos


def encontrar_regra_mais_especifica(extracao: Extracao, regras: list[Regra]) -> Regra | None:
    candidatas = [r for r in regras if r.ativo and _regra_bate(r, extracao)]
    if not candidatas:
        return None
    # Mais específica vence; empate: id mais antigo (menor) vence.
    return max(candidatas, key=lambda r: (_especificidade(r), -(r.id or 0)))
