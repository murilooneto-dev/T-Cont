from dataclasses import dataclass

from app.domain.entities import Documento


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


@dataclass
class ArquivoUploadDTO:
    nome_original: str
    conteudo: bytes
    # Preenchido quando a camada de transporte já rejeitou o arquivo (ex.: tamanho
    # acima do limite detectado antes de bufferizar todo o conteúdo). O use case
    # apenas repassa o erro, sem tentar salvar.
    erro_previo: str | None = None


@dataclass
class ResultadoUploadDTO:
    documento: Documento | None
    nome_original: str
    erro: str | None
