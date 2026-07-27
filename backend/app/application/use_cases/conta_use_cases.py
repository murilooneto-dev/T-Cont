from app.application.dto import AtualizarContaDTO, CriarContaDTO
from app.application.repositories import ContaRepository, PlanoContasRepository
from app.core.exceptions import (
    ContaJaCadastrada,
    ContaNaoEncontrada,
    PlanoContasNaoEncontrado,
)
from app.domain.entities import Conta
from app.domain.enums import NaturezaConta


class CriarContaUseCase:
    def __init__(self, repo: ContaRepository, plano_repo: PlanoContasRepository):
        self._repo = repo
        self._plano_repo = plano_repo

    def executar(self, plano_conta_id: int, dto: CriarContaDTO) -> Conta:
        if self._plano_repo.obter_por_id(plano_conta_id) is None:
            raise PlanoContasNaoEncontrado(plano_conta_id)
        # O banco garante a unicidade de (plano_conta_id, codigo); checar antes
        # transforma o IntegrityError (que viraria um 500) em um erro de domínio.
        existentes = {c.codigo for c in self._repo.listar_por_plano(plano_conta_id)}
        if dto.codigo in existentes:
            raise ContaJaCadastrada(dto.codigo, plano_conta_id)
        if dto.conta_pai_id is not None:
            # Com PRAGMA foreign_keys=ON, um conta_pai_id inexistente (ou de
            # outro plano) viraria um IntegrityError (500) sem esta checagem.
            pai = self._repo.obter_por_id(dto.conta_pai_id)
            if pai is None or pai.plano_conta_id != plano_conta_id:
                raise ContaNaoEncontrada(dto.conta_pai_id)
        conta = Conta(
            id=None,
            plano_conta_id=plano_conta_id,
            codigo=dto.codigo,
            descricao=dto.descricao,
            natureza=NaturezaConta(dto.natureza),
            conta_analitica=dto.conta_analitica,
            conta_pai_id=dto.conta_pai_id,
        )
        return self._repo.criar(conta)


class ListarContasUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, plano_conta_id: int) -> list[Conta]:
        return self._repo.listar_por_plano(plano_conta_id)


class AtualizarContaUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, conta_id: int, dto: AtualizarContaDTO) -> Conta:
        conta = self._repo.obter_por_id(conta_id)
        if conta is None:
            raise ContaNaoEncontrada(conta_id)
        # Mesma lógica de CriarContaUseCase: checar antes transforma o
        # IntegrityError da UniqueConstraint (que viraria um 500) em um erro
        # de domínio. Exclui a própria conta para não autocolidir num rename
        # que mantém o código atual.
        outras = {
            c.codigo
            for c in self._repo.listar_por_plano(conta.plano_conta_id)
            if c.id != conta.id
        }
        if dto.codigo in outras:
            raise ContaJaCadastrada(dto.codigo, conta.plano_conta_id)
        conta.codigo = dto.codigo
        conta.descricao = dto.descricao
        conta.natureza = NaturezaConta(dto.natureza)
        conta.conta_analitica = dto.conta_analitica
        conta.conta_pai_id = dto.conta_pai_id
        return self._repo.atualizar(conta)


class DeletarContaUseCase:
    def __init__(self, repo: ContaRepository):
        self._repo = repo

    def executar(self, conta_id: int) -> None:
        self._repo.deletar(conta_id)
