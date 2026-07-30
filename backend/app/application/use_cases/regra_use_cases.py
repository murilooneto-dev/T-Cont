from app.application.dto import AtualizarRegraDTO, CriarRegraDTO
from app.application.repositories import ContaRepository, PlanoContasRepository, RegraRepository
from app.core.exceptions import (
    ContaNaoAnalitica,
    ContaNaoEncontrada,
    ContaNaoPertenceAEmpresa,
    RegraNaoEncontrada,
    RegraSemCondicoes,
    RegraSemLadoAlvo,
)
from app.domain.entities import Regra
from app.domain.enums import LadoRegra, TipoDocumento


def _validar_conta(
    conta_repo: ContaRepository, plano_repo: PlanoContasRepository, conta_id: int, empresa_id: int
):
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


def _validar_condicoes(
    documento_fiscal: str | None,
    tipo_documento: str | None,
    valor_min,
    valor_max,
    palavra_chave_nome: str | None,
    lado_alvo: str | None,
) -> None:
    condicoes = [documento_fiscal, tipo_documento, valor_min, valor_max, palavra_chave_nome]
    if all(c is None for c in condicoes):
        raise RegraSemCondicoes()
    if (documento_fiscal is not None or palavra_chave_nome is not None) and lado_alvo is None:
        raise RegraSemLadoAlvo()


class CriarRegraUseCase:
    def __init__(
        self, repo: RegraRepository, conta_repo: ContaRepository, plano_repo: PlanoContasRepository
    ):
        self._repo = repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, empresa_id: int, dto: CriarRegraDTO) -> Regra:
        _validar_conta(self._conta_repo, self._plano_repo, dto.conta_id, empresa_id)
        _validar_condicoes(
            dto.documento_fiscal, dto.tipo_documento, dto.valor_min, dto.valor_max,
            dto.palavra_chave_nome, dto.lado_alvo,
        )
        regra = Regra(
            id=None,
            empresa_id=empresa_id,
            conta_id=dto.conta_id,
            lado_alvo=LadoRegra(dto.lado_alvo) if dto.lado_alvo else None,
            documento_fiscal=dto.documento_fiscal,
            tipo_documento=TipoDocumento(dto.tipo_documento) if dto.tipo_documento else None,
            valor_min=dto.valor_min,
            valor_max=dto.valor_max,
            palavra_chave_nome=dto.palavra_chave_nome,
            ativo=True,
        )
        return self._repo.criar(regra)


class ListarRegrasUseCase:
    def __init__(self, repo: RegraRepository):
        self._repo = repo

    def executar(self, empresa_id: int) -> list[Regra]:
        return self._repo.listar_por_empresa(empresa_id)


class AtualizarRegraUseCase:
    def __init__(
        self, repo: RegraRepository, conta_repo: ContaRepository, plano_repo: PlanoContasRepository
    ):
        self._repo = repo
        self._conta_repo = conta_repo
        self._plano_repo = plano_repo

    def executar(self, empresa_id: int, regra_id: int, dto: AtualizarRegraDTO) -> Regra:
        regra = self._repo.obter_por_id(regra_id)
        if regra is None or regra.empresa_id != empresa_id:
            raise RegraNaoEncontrada(regra_id)
        _validar_conta(self._conta_repo, self._plano_repo, dto.conta_id, empresa_id)
        _validar_condicoes(
            dto.documento_fiscal, dto.tipo_documento, dto.valor_min, dto.valor_max,
            dto.palavra_chave_nome, dto.lado_alvo,
        )
        regra.conta_id = dto.conta_id
        regra.lado_alvo = LadoRegra(dto.lado_alvo) if dto.lado_alvo else None
        regra.documento_fiscal = dto.documento_fiscal
        regra.tipo_documento = TipoDocumento(dto.tipo_documento) if dto.tipo_documento else None
        regra.valor_min = dto.valor_min
        regra.valor_max = dto.valor_max
        regra.palavra_chave_nome = dto.palavra_chave_nome
        regra.ativo = dto.ativo
        return self._repo.atualizar(regra)


class DeletarRegraUseCase:
    def __init__(self, repo: RegraRepository):
        self._repo = repo

    def executar(self, empresa_id: int, regra_id: int) -> None:
        regra = self._repo.obter_por_id(regra_id)
        if regra is None or regra.empresa_id != empresa_id:
            raise RegraNaoEncontrada(regra_id)
        self._repo.deletar(regra_id)
