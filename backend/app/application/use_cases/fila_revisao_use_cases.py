from dataclasses import dataclass

from app.application.repositories import (
    ClassificacaoRepository, ContaRepository, DocumentoRepository, ExtracaoRepository,
)
from app.domain.entities import Documento, Extracao
from app.domain.enums import OrigemClassificacao, StatusDocumento


@dataclass
class SugestaoFilaRevisao:
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    score_similaridade: float | None


@dataclass
class ItemFilaRevisao:
    documento: Documento
    extracao: Extracao | None
    sugestao: SugestaoFilaRevisao | None


class ListarFilaRevisaoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        conta_repo: ContaRepository,
    ):
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._conta_repo = conta_repo

    def executar(self, empresa_id: int) -> list[ItemFilaRevisao]:
        itens: list[ItemFilaRevisao] = []
        for documento in self._documento_repo.listar_por_empresa(empresa_id):
            if documento.status != StatusDocumento.CONCLUIDO:
                continue
            classificacao = self._classificacao_repo.obter_por_documento_id(documento.id)
            if classificacao is not None and classificacao.origem != OrigemClassificacao.FUZZY:
                continue

            sugestao = None
            if classificacao is not None:
                conta = self._conta_repo.obter_por_id(classificacao.conta_id)
                if conta is not None:
                    sugestao = SugestaoFilaRevisao(
                        conta_id=conta.id,
                        conta_codigo=conta.codigo,
                        conta_descricao=conta.descricao,
                        score_similaridade=classificacao.score_similaridade,
                    )

            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            itens.append(ItemFilaRevisao(documento=documento, extracao=extracao, sugestao=sugestao))
        return itens
