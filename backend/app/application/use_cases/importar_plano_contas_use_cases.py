from app.application.repositories import ContaRepository
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta
from app.infrastructure.spreadsheet.plano_contas_parser import (
    LinhaPlanoContas,
    ParsePlanoContasResultado,
    parsear_planilha,
)


class PreviewImportacaoUseCase:
    def executar(self, conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado:
        return parsear_planilha(conteudo, nome_arquivo)


class ConfirmarImportacaoUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, plano_conta_id: int, linhas: list[LinhaPlanoContas]) -> list[Conta]:
        codigo_para_id: dict[str, int] = {}
        contas_criadas: list[Conta] = []

        pendentes = list(linhas)

        def _criar(linha: LinhaPlanoContas, conta_pai_id: int | None) -> None:
            conta = Conta(
                id=None,
                plano_conta_id=plano_conta_id,
                codigo=linha.codigo,
                descricao=linha.descricao,
                natureza=NaturezaConta(linha.natureza) if linha.natureza else NaturezaConta.DESPESA,
                conta_analitica=linha.conta_analitica if linha.conta_analitica is not None else True,
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
