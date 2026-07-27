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

        linhas_ordenadas = sorted(linhas, key=lambda l: len(l.codigo))

        for linha in linhas_ordenadas:
            conta_pai_id = codigo_para_id.get(linha.conta_pai) if linha.conta_pai else None
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

        return contas_criadas
