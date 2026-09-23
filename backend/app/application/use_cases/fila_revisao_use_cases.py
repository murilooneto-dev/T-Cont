from dataclasses import dataclass

from app.application.repositories import (
    ClassificacaoRepository, ContaRepository, DocumentoRepository, ExtracaoRepository,
)
from app.domain.entities import Documento, Extracao
from app.domain.enums import DirecaoLancamento, OrigemClassificacao, StatusDocumento
from app.infrastructure.classificacao.lancamento_contabil import resolver_lados_lancamento


@dataclass
class SugestaoFilaRevisao:
    conta_id: int
    conta_codigo: str
    conta_descricao: str
    score_similaridade: float | None
    origem: OrigemClassificacao | None = None
    direcao: DirecaoLancamento | None = None
    debito_codigo: str | None = None
    debito_descricao: str | None = None
    credito_codigo: str | None = None
    credito_descricao: str | None = None


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
            lancamento_incompleto = classificacao is not None and (
                classificacao.direcao is None or classificacao.conta_bancaria_id is None
            )
            ja_e_fuzzy = classificacao is not None and classificacao.origem == OrigemClassificacao.FUZZY
            if classificacao is not None and not ja_e_fuzzy and not lancamento_incompleto:
                continue

            sugestao = None
            if classificacao is not None:
                conta = self._conta_repo.obter_por_id(classificacao.conta_id)
                if conta is not None:
                    conta_bancaria = (
                        self._conta_repo.obter_por_id(classificacao.conta_bancaria_id)
                        if classificacao.conta_bancaria_id is not None
                        else None
                    )
                    conta_debito, conta_credito = resolver_lados_lancamento(
                        classificacao.direcao, conta, conta_bancaria
                    )
                    sugestao = SugestaoFilaRevisao(
                        conta_id=conta.id,
                        conta_codigo=conta.codigo,
                        conta_descricao=conta.descricao,
                        score_similaridade=classificacao.score_similaridade,
                        origem=classificacao.origem,
                        direcao=classificacao.direcao,
                        debito_codigo=conta_debito.codigo if conta_debito else None,
                        debito_descricao=conta_debito.descricao if conta_debito else None,
                        credito_codigo=conta_credito.codigo if conta_credito else None,
                        credito_descricao=conta_credito.descricao if conta_credito else None,
                    )

            extracao = self._extracao_repo.obter_por_documento_id(documento.id)
            itens.append(ItemFilaRevisao(documento=documento, extracao=extracao, sugestao=sugestao))
        return itens
