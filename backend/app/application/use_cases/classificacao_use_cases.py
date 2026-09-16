from app.application.repositories import (
    AprendizadoRepository,
    ClassificacaoRepository,
    ContaRepository,
    DocumentoRepository,
    ExtracaoRepository,
    PlanoContasRepository,
    RegraRepository,
)
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    DocumentoNaoEncontrado,
)
from app.domain.entities import Aprendizado, Classificacao, Regra
from app.domain.enums import LadoRegra, OrigemClassificacao


def _validar_conta(conta_repo, plano_repo, conta_id: int, empresa_id: int) -> None:
    conta = conta_repo.obter_por_id(conta_id)
    if conta is None:
        raise ContaNaoEncontrada(conta_id)
    plano = plano_repo.obter_por_id(conta.plano_conta_id)
    if plano is None or plano.empresa_id != empresa_id:
        raise ContaNaoPertenceAEmpresa(conta_id, empresa_id)
    try:
        conta.validar_uso_em_lancamento()
    except ValueError as exc:
        raise ContaNaoAnalitica(str(exc)) from exc


class CorrigirClassificacaoUseCase:
    def __init__(
        self,
        documento_repo: DocumentoRepository,
        extracao_repo: ExtracaoRepository,
        classificacao_repo: ClassificacaoRepository,
        regra_repo: RegraRepository,
        aprendizado_repo: AprendizadoRepository,
        conta_repo: ContaRepository,
        plano_repo: PlanoContasRepository,
    ):
        self._documento_repo = documento_repo
        self._extracao_repo = extracao_repo
        self._classificacao_repo = classificacao_repo
        self._regra_repo = regra_repo
        self._aprendizado_repo = aprendizado_repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, documento_id: int, conta_id: int) -> Classificacao:
        documento = self._documento_repo.obter_por_id(documento_id)
        if documento is None:
            raise DocumentoNaoEncontrado(documento_id)
        _validar_conta(self._conta_repo, self._plano_repo, conta_id, documento.empresa_id)

        classificacao_existente = self._classificacao_repo.obter_por_documento_id(documento_id)
        conta_anterior_id = classificacao_existente.conta_id if classificacao_existente else None
        origem_anterior = classificacao_existente.origem if classificacao_existente else None

        documento_fiscal, lado_alvo = self._documento_fiscal_do_recebedor_ou_pagador(
            documento_id
        )

        regra_id = None
        if documento_fiscal is not None:
            regra_id = self._criar_ou_atualizar_regra(
                documento.empresa_id, conta_id, documento_fiscal, lado_alvo
            )

        if classificacao_existente is not None:
            classificacao_existente.conta_id = conta_id
            classificacao_existente.origem = OrigemClassificacao.MANUAL
            classificacao_existente.regra_id = regra_id
            classificacao_existente.score_similaridade = None
            classificacao_final = self._classificacao_repo.atualizar(classificacao_existente)
        else:
            classificacao_final = self._classificacao_repo.criar(
                Classificacao(
                    id=None, empresa_id=documento.empresa_id, documento_id=documento_id,
                    conta_id=conta_id, origem=OrigemClassificacao.MANUAL, regra_id=regra_id,
                    score_similaridade=None,
                )
            )

        self._aprendizado_repo.criar(
            Aprendizado(
                id=None, empresa_id=documento.empresa_id, documento_id=documento_id,
                conta_anterior_id=conta_anterior_id, origem_anterior=origem_anterior,
                conta_corrigida_id=conta_id, regra_id=regra_id,
            )
        )
        return classificacao_final

    def _documento_fiscal_do_recebedor_ou_pagador(
        self, documento_id: int
    ) -> tuple[str | None, LadoRegra | None]:
        extracao = self._extracao_repo.obter_por_documento_id(documento_id)
        if extracao is None:
            return None, None
        if extracao.recebedor_documento is not None:
            return extracao.recebedor_documento, LadoRegra.RECEBEDOR
        if extracao.pagador_documento is not None:
            return extracao.pagador_documento, LadoRegra.PAGADOR
        return None, None

    def _criar_ou_atualizar_regra(
        self, empresa_id: int, conta_id: int, documento_fiscal: str, lado_alvo: LadoRegra
    ) -> int:
        regra_existente = next(
            (
                r for r in self._regra_repo.listar_por_empresa(empresa_id)
                if r.documento_fiscal == documento_fiscal and r.lado_alvo == lado_alvo
            ),
            None,
        )
        if regra_existente is not None:
            regra_existente.conta_id = conta_id
            regra_atualizada = self._regra_repo.atualizar(regra_existente)
            return regra_atualizada.id

        nova_regra = self._regra_repo.criar(
            Regra(
                id=None, empresa_id=empresa_id, conta_id=conta_id, lado_alvo=lado_alvo,
                documento_fiscal=documento_fiscal, tipo_documento=None, valor_min=None,
                valor_max=None, palavra_chave_nome=None, ativo=True,
            )
        )
        return nova_regra.id
