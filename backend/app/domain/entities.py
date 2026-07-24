from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import NaturezaConta


@dataclass
class Empresa:
    id: int | None
    razao_social: str
    nome_fantasia: str | None
    cnpj: str
    ativo: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PlanoContas:
    id: int | None
    empresa_id: int
    nome: str
    versao: int = 1
    ativo: bool = True
    created_at: datetime | None = None


@dataclass
class Conta:
    id: int | None
    plano_conta_id: int
    codigo: str
    descricao: str
    natureza: NaturezaConta
    conta_analitica: bool
    conta_pai_id: int | None = None

    def validar_uso_em_lancamento(self) -> None:
        if not self.conta_analitica:
            raise ValueError(
                f"Conta {self.codigo} é uma conta sintética e não pode ser usada em lançamentos."
            )
