import csv
import io
from dataclasses import dataclass

from openpyxl import load_workbook

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.infrastructure.spreadsheet.column_detector import (
    CAMPOS_OBRIGATORIOS,
    detectar_colunas,
)


@dataclass
class LinhaPlanoContas:
    codigo: str
    descricao: str
    natureza: str | None
    conta_analitica: bool | None
    conta_pai: str | None


@dataclass
class ParsePlanoContasResultado:
    mapeamento: dict[str, int | None]
    linhas: list[LinhaPlanoContas]


def _ler_linhas_csv(conteudo: bytes) -> list[list[str]]:
    texto = conteudo.decode("utf-8-sig")
    leitor = csv.reader(io.StringIO(texto))
    return [linha for linha in leitor if any(celula.strip() for celula in linha)]


def _ler_linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    aba = planilha.active
    linhas = []
    for linha in aba.iter_rows(values_only=True):
        if any(celula is not None and str(celula).strip() for celula in linha):
            linhas.append(["" if celula is None else str(celula) for celula in linha])
    return linhas


def _parse_bool(valor: str | None) -> bool | None:
    if valor is None or valor == "":
        return None
    return valor.strip().lower() in {"true", "verdadeiro", "sim", "1"}


def parsear_planilha(conteudo: bytes, nome_arquivo: str) -> ParsePlanoContasResultado:
    if nome_arquivo.lower().endswith(".xlsx"):
        linhas_brutas = _ler_linhas_xlsx(conteudo)
    else:
        linhas_brutas = _ler_linhas_csv(conteudo)

    if not linhas_brutas:
        raise ImportacaoPlanoContasInvalida("A planilha está vazia.")

    cabecalhos, *linhas_dados = linhas_brutas
    mapeamento = detectar_colunas(cabecalhos)

    faltantes = [campo for campo in CAMPOS_OBRIGATORIOS if mapeamento.get(campo) is None]
    if faltantes:
        raise ImportacaoPlanoContasInvalida(
            "Não foi possível identificar as colunas obrigatórias "
            f"{faltantes} no cabeçalho {cabecalhos}. Ajuste os nomes das colunas e reenvie."
        )

    def valor(linha: list[str], campo: str) -> str | None:
        indice = mapeamento.get(campo)
        if indice is None or indice >= len(linha):
            return None
        return linha[indice] or None

    linhas = [
        LinhaPlanoContas(
            codigo=valor(linha, "codigo") or "",
            descricao=valor(linha, "descricao") or "",
            natureza=valor(linha, "natureza"),
            conta_analitica=_parse_bool(valor(linha, "conta_analitica")),
            conta_pai=valor(linha, "conta_pai"),
        )
        for linha in linhas_dados
    ]

    return ParsePlanoContasResultado(mapeamento=mapeamento, linhas=linhas)
