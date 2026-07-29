from app.application.ports import ArmazenamentoArquivos
from app.application.repositories import (
    ContaRepository,
    DocumentoRepository,
    EmpresaRepository,
    ExtracaoRepository,
    LoteProcessamentoRepository,
    OcrResultadoRepository,
    PlanoContasRepository,
)
from app.domain.entities import (
    Conta, Documento, Empresa, Extracao, LoteProcessamento, OcrResultado, PlanoContas,
)
from app.domain.enums import StatusDocumento
from app.infrastructure.storage.file_storage import validar_extensao_e_tamanho


class FakeEmpresaRepository(EmpresaRepository):
    def __init__(self):
        self._items: dict[int, Empresa] = {}
        self._next_id = 1

    def criar(self, empresa: Empresa) -> Empresa:
        empresa.id = self._next_id
        self._items[self._next_id] = empresa
        self._next_id += 1
        return empresa

    def obter_por_id(self, empresa_id: int) -> Empresa | None:
        return self._items.get(empresa_id)

    def obter_por_cnpj(self, cnpj: str) -> Empresa | None:
        return next((e for e in self._items.values() if e.cnpj == cnpj), None)

    def listar(self) -> list[Empresa]:
        return list(self._items.values())

    def atualizar(self, empresa: Empresa) -> Empresa:
        self._items[empresa.id] = empresa
        return empresa


class FakePlanoContasRepository(PlanoContasRepository):
    def __init__(self):
        self._items: dict[int, PlanoContas] = {}
        self._next_id = 1

    def criar(self, plano: PlanoContas) -> PlanoContas:
        plano.id = self._next_id
        self._items[self._next_id] = plano
        self._next_id += 1
        return plano

    def obter_por_id(self, plano_id: int) -> PlanoContas | None:
        return self._items.get(plano_id)

    def listar_por_empresa(self, empresa_id: int) -> list[PlanoContas]:
        return [p for p in self._items.values() if p.empresa_id == empresa_id]


class FakeContaRepository(ContaRepository):
    def __init__(self):
        self._items: dict[int, Conta] = {}
        self._next_id = 1

    def criar(self, conta: Conta) -> Conta:
        conta.id = self._next_id
        self._items[self._next_id] = conta
        self._next_id += 1
        return conta

    def criar_em_lote(self, contas: list[Conta]) -> list[Conta]:
        return [self.criar(c) for c in contas]

    def obter_por_id(self, conta_id: int) -> Conta | None:
        return self._items.get(conta_id)

    def listar_por_plano(self, plano_conta_id: int) -> list[Conta]:
        return [c for c in self._items.values() if c.plano_conta_id == plano_conta_id]

    def atualizar(self, conta: Conta) -> Conta:
        self._items[conta.id] = conta
        return conta

    def deletar(self, conta_id: int) -> None:
        self._items.pop(conta_id, None)


class FakeDocumentoRepository(DocumentoRepository):
    def __init__(self):
        self._items: dict[int, Documento] = {}
        self._next_id = 1

    def criar(self, documento: Documento) -> Documento:
        documento.id = self._next_id
        self._items[self._next_id] = documento
        self._next_id += 1
        return documento

    def obter_por_id(self, documento_id: int) -> Documento | None:
        return self._items.get(documento_id)

    def listar_por_empresa(self, empresa_id: int) -> list[Documento]:
        return [d for d in self._items.values() if d.empresa_id == empresa_id]

    def listar_pendentes_por_empresa(self, empresa_id: int) -> list[Documento]:
        return [
            d for d in self._items.values()
            if d.empresa_id == empresa_id and d.status == StatusDocumento.PENDENTE
        ]

    def atualizar(self, documento: Documento) -> Documento:
        self._items[documento.id] = documento
        return documento


class FakeOcrResultadoRepository(OcrResultadoRepository):
    def __init__(self):
        self._items: dict[int, OcrResultado] = {}
        self._next_id = 1

    def criar(self, resultado: OcrResultado) -> OcrResultado:
        resultado.id = self._next_id
        self._items[self._next_id] = resultado
        self._next_id += 1
        return resultado

    def obter_por_documento_id(self, documento_id: int) -> OcrResultado | None:
        return next((r for r in self._items.values() if r.documento_id == documento_id), None)


class FakeLoteProcessamentoRepository(LoteProcessamentoRepository):
    def __init__(self):
        self._items: dict[int, LoteProcessamento] = {}
        self._next_id = 1

    def criar(self, lote: LoteProcessamento) -> LoteProcessamento:
        lote.id = self._next_id
        self._items[self._next_id] = lote
        self._next_id += 1
        return lote

    def obter_por_id(self, lote_id: int) -> LoteProcessamento | None:
        return self._items.get(lote_id)

    def atualizar(self, lote: LoteProcessamento) -> LoteProcessamento:
        self._items[lote.id] = lote
        return lote


class FakeArmazenamentoArquivos(ArmazenamentoArquivos):
    def __init__(self):
        self._arquivos: dict[str, bytes] = {}
        self._contador = 0

    def salvar(self, empresa_id: int, nome_original: str, conteudo: bytes) -> tuple[str, str, str]:
        extensao = validar_extensao_e_tamanho(nome_original, len(conteudo))
        self._contador += 1
        nome_fisico = f"fake_{self._contador}{extensao}"
        caminho_relativo = f"empresa_{empresa_id}/documentos/{nome_fisico}"
        self._arquivos[caminho_relativo] = conteudo
        return nome_fisico, caminho_relativo, extensao

    def ler(self, caminho_relativo: str) -> bytes:
        return self._arquivos[caminho_relativo]


class FakeExtracaoRepository(ExtracaoRepository):
    def __init__(self):
        self._items: dict[int, Extracao] = {}
        self._next_id = 1

    def criar(self, extracao: Extracao) -> Extracao:
        extracao.id = self._next_id
        self._items[self._next_id] = extracao
        self._next_id += 1
        return extracao

    def obter_por_documento_id(self, documento_id: int) -> Extracao | None:
        return next((e for e in self._items.values() if e.documento_id == documento_id), None)
