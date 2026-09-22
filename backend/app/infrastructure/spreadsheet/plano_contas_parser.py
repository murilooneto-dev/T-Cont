import csv
import io
import re
from dataclasses import dataclass

from openpyxl import load_workbook

from app.core.exceptions import ImportacaoPlanoContasInvalida
from app.domain.enums import NaturezaConta
from app.infrastructure.spreadsheet.column_detector import (
    CAMPOS_OBRIGATORIOS,
    detectar_colunas,
)

_CODIGO_RE = re.compile(r"^(\d+(?:\.\d+)*)")

_REGRAS_NATUREZA: list[tuple[str, NaturezaConta]] = [
    ("2.3", NaturezaConta.PATRIMONIO_LIQUIDO),
    ("2.1", NaturezaConta.PASSIVO),
    ("2.2", NaturezaConta.PASSIVO),
    ("3.1", NaturezaConta.RECEITA),
    ("3.2", NaturezaConta.DESPESA),
    ("1", NaturezaConta.ATIVO),
    ("2", NaturezaConta.PASSIVO),
    ("3", NaturezaConta.RECEITA),
]


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


def _extrair_codigo(celula: str) -> str | None:
    match = _CODIGO_RE.match((celula or "").strip())
    return match.group(1) if match else None


def _inferir_natureza(codigo: str) -> NaturezaConta:
    for prefixo, natureza in _REGRAS_NATUREZA:
        if codigo == prefixo or codigo.startswith(prefixo + "."):
            return natureza
    # Alguns planos de contas têm uma raiz "4" (Resultado do Exercício,
    # Balanço de Abertura) fora da convenção 1/2/3 e sem equivalente exato
    # entre os 5 valores de NaturezaConta — são contas de apuração/fechamento,
    # tipicamente sintéticas e fora do uso operacional do classificador.
    # Decisão confirmada com o usuário: cair em ATIVO por padrão é aceitável.
    return NaturezaConta.ATIVO


def _parece_relatorio_hierarquico(linhas_brutas: list[list[str]]) -> bool:
    """Detecta relatórios contábeis hierárquicos exportados por ERPs.

    Nesses relatórios o código/classificação vem sempre na primeira coluna,
    mas o nome da conta muda de coluna conforme o nível hierárquico (a
    indentação é codificada em posição de coluna), e não há coluna de
    natureza/analítica — só dá pra inferir pelo próprio código. Exigir 2+
    códigos com ponto evita falso positivo num CSV simples cuja primeira
    coluna por acaso seja numérica.
    """
    contagem = 0
    for linha in linhas_brutas:
        codigo = _extrair_codigo(linha[0]) if linha else None
        if codigo and "." in codigo:
            contagem += 1
            if contagem >= 2:
                return True
    return False


def _parsear_relatorio_hierarquico(linhas_brutas: list[list[str]]) -> ParsePlanoContasResultado:
    linhas: list[LinhaPlanoContas] = []
    for linha in linhas_brutas:
        if not linha:
            continue
        codigo = _extrair_codigo(linha[0])
        if codigo is None:
            # Linha de cabeçalho/rodapé de página do relatório impresso
            # (ex.: "TESSERATO CONTABILIDADE LTDA", "Página : 2") — não tem
            # um código hierárquico válido na primeira coluna, então não é
            # uma linha de conta.
            continue

        descricao = ""
        for celula in linha[1:]:
            if celula and celula.strip():
                descricao = celula.strip()
                break

        partes = codigo.split(".")
        conta_pai = ".".join(partes[:-1]) if len(partes) > 1 else None

        linhas.append(
            LinhaPlanoContas(
                codigo=codigo,
                descricao=descricao,
                natureza=_inferir_natureza(codigo).value,
                conta_analitica=None,
                conta_pai=conta_pai,
            )
        )

    mapeamento = {
        "codigo": 0, "descricao": None, "natureza": None,
        "conta_analitica": None, "conta_pai": None,
    }
    return ParsePlanoContasResultado(mapeamento=mapeamento, linhas=linhas)


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
        if _parece_relatorio_hierarquico(linhas_brutas):
            return _parsear_relatorio_hierarquico(linhas_brutas)
        raise ImportacaoPlanoContasInvalida(
            "Não foi possível identificar as colunas obrigatórias "
            f"{faltantes} no cabeçalho {cabecalhos}. Ajuste os nomes das colunas e reenvie."
        )

    def valor(linha: list[str], campo: str) -> str | None:
        indice = mapeamento.get(campo)
        if indice is None or indice >= len(linha):
            return None
        return linha[indice] or None

    def valor_normalizado(linha: list[str], campo: str) -> str | None:
        """Como `valor`, mas com espaços nas pontas removidos.

        Usado para codigo/conta_pai: essas strings viram chave de
        comparação/link (duplicidade, hierarquia pai/filho) em todo o
        fluxo de importação, então precisam ser normalizadas uma única vez
        aqui na origem — não em cada consumidor — para que todos os pontos
        do fluxo (checagem de duplicidade, resolução de hierarquia,
        persistência) enxerguem exatamente o mesmo valor.
        """
        bruto = valor(linha, campo)
        return bruto.strip() if bruto is not None else None

    linhas = [
        LinhaPlanoContas(
            codigo=valor_normalizado(linha, "codigo") or "",
            descricao=valor(linha, "descricao") or "",
            natureza=valor(linha, "natureza"),
            conta_analitica=_parse_bool(valor(linha, "conta_analitica")),
            conta_pai=valor_normalizado(linha, "conta_pai"),
        )
        for linha in linhas_dados
    ]

    return ParsePlanoContasResultado(mapeamento=mapeamento, linhas=linhas)
