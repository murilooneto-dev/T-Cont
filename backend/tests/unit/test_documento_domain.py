from app.domain.entities import Documento, LoteProcessamento, OcrResultado
from app.domain.enums import MetodoOcr, StatusDocumento, StatusLote


def test_documento_default_status_is_pendente():
    documento = Documento(
        id=None, empresa_id=1, nome_arquivo="20260727_ab12cd34.pdf",
        nome_exibicao="comprovante.pdf", caminho_arquivo="empresa_1/documentos/x.pdf",
        extensao=".pdf", tamanho_bytes=1024,
    )
    assert documento.status == StatusDocumento.PENDENTE
    assert documento.mensagem_erro is None


def test_ocr_resultado_holds_metodo_e_texto():
    resultado = OcrResultado(
        id=None, documento_id=1, texto_extraido="Texto do comprovante",
        metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=42,
    )
    assert resultado.metodo == MetodoOcr.PDF_NATIVO


def test_lote_processamento_default_status_e_zero_processados():
    lote = LoteProcessamento(id=None, empresa_id=1, total_documentos=5)
    assert lote.status == StatusLote.EM_ANDAMENTO
    assert lote.documentos_processados == 0
