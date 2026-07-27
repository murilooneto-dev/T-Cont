from app.application.repositories import ContaRepository, PlanoContasRepository
from app.core.exceptions import (
    ImportacaoPlanoContasInvalida,
    PlanoContasNaoEncontrado,
)
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta
from app.infrastructure.spreadsheet.column_detector import _normalizar
from app.infrastructure.spreadsheet.plano_contas_parser import (
    LinhaPlanoContas,
    ParsePlanoContasResultado,
    parsear_planilha,
)

# Mapa de valor normalizado -> membro do enum. Reutiliza o mesmo
# `_normalizar` da detecção de colunas (minúsculas, sem acento, "_" -> " ")
# para aceitar planilhas reais que escrevem "Ativo", "Patrimônio Líquido",
# " RECEITA " etc. sem precisar da grafia exata do enum.
_NATUREZAS_POR_VALOR_NORMALIZADO: dict[str, NaturezaConta] = {
    _normalizar(natureza.value): natureza for natureza in NaturezaConta
}

_NATUREZAS_ACEITAS = ", ".join(natureza.value for natureza in NaturezaConta)


class PreviewImportacaoUseCase:
    def executar(
        self, conteudo: bytes, nome_arquivo: str | None
    ) -> ParsePlanoContasResultado:
        return parsear_planilha(conteudo, nome_arquivo)


def _resolver_natureza(linha: LinhaPlanoContas) -> NaturezaConta:
    """Converte o valor bruto de natureza em um NaturezaConta.

    Nunca adivinha: se a coluna não veio ou o valor não é reconhecido,
    falha com erro claro em vez de assumir um padrão silencioso, que as
    fases seguintes (regras/IA) tratariam como verdade.
    """
    bruto = (linha.natureza or "").strip()
    if not bruto:
        raise ImportacaoPlanoContasInvalida(
            f"A conta '{linha.codigo}' não informa a natureza. "
            f"Preencha a coluna de natureza com um dos valores aceitos: {_NATUREZAS_ACEITAS}."
        )

    natureza = _NATUREZAS_POR_VALOR_NORMALIZADO.get(_normalizar(bruto))
    if natureza is None:
        raise ImportacaoPlanoContasInvalida(
            f"Natureza '{bruto}' da conta '{linha.codigo}' não é reconhecida. "
            f"Valores aceitos: {_NATUREZAS_ACEITAS}."
        )
    return natureza


def _validar_campos_obrigatorios(linhas: list[LinhaPlanoContas]) -> None:
    for indice, linha in enumerate(linhas, start=1):
        if not (linha.codigo or "").strip():
            raise ImportacaoPlanoContasInvalida(
                f"A linha {indice} da planilha está sem código "
                f"(descrição: '{linha.descricao}'). Preencha o código e reenvie."
            )
        if not (linha.descricao or "").strip():
            raise ImportacaoPlanoContasInvalida(
                f"A conta '{linha.codigo}' (linha {indice}) está sem descrição. "
                "Preencha a descrição e reenvie."
            )


def _validar_duplicidades(
    linhas: list[LinhaPlanoContas], codigos_existentes: set[str]
) -> None:
    vistos: set[str] = set()
    duplicados_no_arquivo: list[str] = []
    for linha in linhas:
        codigo = linha.codigo.strip()
        if codigo in vistos:
            duplicados_no_arquivo.append(codigo)
        vistos.add(codigo)

    if duplicados_no_arquivo:
        raise ImportacaoPlanoContasInvalida(
            "A planilha contém códigos de conta repetidos: "
            f"{sorted(set(duplicados_no_arquivo))}. Cada código deve aparecer uma única vez."
        )

    ja_existentes = sorted(vistos & codigos_existentes)
    if ja_existentes:
        raise ImportacaoPlanoContasInvalida(
            f"As contas {ja_existentes} já existem neste plano de contas. "
            "A reimportação de um plano já importado ainda não é suportada; "
            "use um novo plano de contas ou remova as contas existentes antes de reimportar."
        )


def _derivar_conta_analitica(linhas: list[LinhaPlanoContas]) -> dict[str, bool]:
    """Deriva analítica/sintética a partir do grafo pai/filho do lote.

    Uma conta é sintética (não analítica) se e somente se alguma outra linha
    do lote a declara como `conta_pai`. Vale apenas como fallback: um valor
    explícito da planilha sempre tem precedência.
    """
    pais = {
        (linha.conta_pai or "").strip()
        for linha in linhas
        if (linha.conta_pai or "").strip()
    }
    return {linha.codigo.strip(): linha.codigo.strip() not in pais for linha in linhas}


class ConfirmarImportacaoUseCase:
    def __init__(self, repo: ContaRepository, plano_repo: PlanoContasRepository):
        self._repo = repo
        self._plano_repo = plano_repo

    def executar(self, plano_conta_id: int, linhas: list[LinhaPlanoContas]) -> list[Conta]:
        if self._plano_repo.obter_por_id(plano_conta_id) is None:
            raise PlanoContasNaoEncontrado(plano_conta_id)

        _validar_campos_obrigatorios(linhas)

        codigos_existentes = {
            conta.codigo for conta in self._repo.listar_por_plano(plano_conta_id)
        }
        _validar_duplicidades(linhas, codigos_existentes)

        # Valida todas as naturezas antes de criar qualquer conta, para não
        # deixar uma importação parcial gravada quando uma linha falha.
        naturezas = {linha.codigo.strip(): _resolver_natureza(linha) for linha in linhas}
        analiticas_derivadas = _derivar_conta_analitica(linhas)

        codigo_para_id: dict[str, int] = {}
        contas_criadas: list[Conta] = []

        pendentes = list(linhas)

        def _criar(linha: LinhaPlanoContas, conta_pai_id: int | None) -> None:
            codigo = linha.codigo.strip()
            conta = Conta(
                id=None,
                plano_conta_id=plano_conta_id,
                codigo=linha.codigo,
                descricao=linha.descricao,
                natureza=naturezas[codigo],
                conta_analitica=(
                    linha.conta_analitica
                    if linha.conta_analitica is not None
                    else analiticas_derivadas[codigo]
                ),
                conta_pai_id=conta_pai_id,
            )
            criada = self._repo.criar(conta)
            codigo_para_id[linha.codigo] = criada.id
            contas_criadas.append(criada)

        # Resolve rows in multiple passes: a row can be created once its
        # conta_pai (if any) has already been created (or is empty/None).
        # This correctly handles arbitrary hierarchy depth and out-of-order
        # input, unlike a length-based sort which only works when code
        # length strictly correlates with hierarchy depth.
        while pendentes:
            proxima_rodada = []
            progresso = False

            for linha in pendentes:
                if not linha.conta_pai or linha.conta_pai in codigo_para_id:
                    conta_pai_id = codigo_para_id.get(linha.conta_pai) if linha.conta_pai else None
                    _criar(linha, conta_pai_id)
                    progresso = True
                else:
                    proxima_rodada.append(linha)

            if not progresso:
                # Remaining rows reference a conta_pai code that never
                # appears in this batch. Parent-matching is scoped to
                # within the same batch, so treat these as root accounts
                # as a last resort rather than raising.
                for linha in proxima_rodada:
                    _criar(linha, None)
                break

            pendentes = proxima_rodada

        return contas_criadas
