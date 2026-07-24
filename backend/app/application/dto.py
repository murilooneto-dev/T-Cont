from dataclasses import dataclass


@dataclass
class CriarEmpresaDTO:
    razao_social: str
    nome_fantasia: str | None
    cnpj: str


@dataclass
class AtualizarEmpresaDTO:
    razao_social: str
    nome_fantasia: str | None
    ativo: bool


@dataclass
class CriarPlanoContasDTO:
    nome: str


@dataclass
class CriarContaDTO:
    codigo: str
    descricao: str
    natureza: str
    conta_analitica: bool
    conta_pai_id: int | None = None


@dataclass
class AtualizarContaDTO:
    codigo: str
    descricao: str
    natureza: str
    conta_analitica: bool
    conta_pai_id: int | None = None
