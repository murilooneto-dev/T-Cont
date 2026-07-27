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


def _decodificar(conteudo: bytes) -> str:
    """Decodifica o CSV tolerando encodings legados de ERPs brasileiros.

    latin-1/cp1252 aceitam qualquer sequência de bytes, então o fallback
    nunca lança: no pior caso o texto sai truncado/ilegível e a detecção de
    colunas rejeita o arquivo com ImportacaoPlanoContasInvalida (422), em
    vez de estourar um UnicodeDecodeError não tratado (500).
    """
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return conteudo.decode(encoding)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="replace")


def _ler_linhas_csv(conteudo: bytes) -> list[list[str]]:
    texto = _decodificar(conteudo)
    leitor = csv.reader(io.StringIO(texto))
    try:
        return [linha for linha in leitor if any(celula.strip() for celula in linha)]
    except csv.Error as exc:
        raise ImportacaoPlanoContasInvalida(
            f"Não foi possível ler o arquivo como CSV: {exc}. "
            "Envie um arquivo .csv ou .xlsx válido."
        ) from exc


def _ler_linhas_xlsx(conteudo: bytes) -> list[list[str]]:
    try:
        planilha = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl lança tipos variados para arquivos inválidos
        raise ImportacaoPlanoContasInvalida(
            f"Não foi possível ler o arquivo como planilha Excel: {exc}. "
            "Envie um arquivo .xlsx válido."
        ) from exc
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


def parsear_planilha(
    conteudo: bytes, nome_arquivo: str | None
) -> ParsePlanoContasResultado:
    if (nome_arquivo or "").lower().endswith(".xlsx"):
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
