from app.domain.enums import TipoDocumento
from app.infrastructure.extracao.tipo_documento import extrair_tipo_documento


def test_detecta_pix():
    assert extrair_tipo_documento("Comprovante de Transferência PIX") == TipoDocumento.PIX


def test_detecta_ted():
    assert extrair_tipo_documento("TED - Transferência Eletrônica Disponível") == TipoDocumento.TED


def test_detecta_doc():
    assert extrair_tipo_documento("Comprovante de DOC realizado com sucesso") == TipoDocumento.DOC


def test_detecta_boleto():
    assert extrair_tipo_documento("Pagamento de BOLETO bancário") == TipoDocumento.BOLETO


def test_nenhuma_palavra_chave_retorna_outro():
    assert extrair_tipo_documento("Recibo de pagamento diverso") == TipoDocumento.OUTRO


def test_detecta_pix_plural():
    assert extrair_tipo_documento("Confirmar pagamentos de PIXS realizados") == TipoDocumento.PIX


def test_detecta_ted_plural():
    assert extrair_tipo_documento("Comprovantes de TEDs enviados") == TipoDocumento.TED


def test_detecta_doc_plural():
    assert extrair_tipo_documento("Lista de DOCs pendentes") == TipoDocumento.DOC


def test_detecta_boleto_plural():
    assert extrair_tipo_documento("Pagamento de Boletos em atraso") == TipoDocumento.BOLETO


def test_doc_nao_confunde_com_palavra_documento():
    # "DOCUMENTO" contém "DOC" como substring, mas não é o tipo de transferência DOC.
    assert extrair_tipo_documento("Este é um DOCUMENTO de cobrança sem tipo especificado") == TipoDocumento.OUTRO
