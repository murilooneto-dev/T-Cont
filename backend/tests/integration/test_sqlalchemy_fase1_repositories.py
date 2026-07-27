from app.domain.entities import Documento, LoteProcessamento, OcrResultado
from app.domain.enums import MetodoOcr, StatusDocumento, StatusLote
from app.infrastructure.repositories.sqlalchemy_documento_repository import (
    SqlAlchemyDocumentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_lote_processamento_repository import (
    SqlAlchemyLoteProcessamentoRepository,
)
from app.infrastructure.repositories.sqlalchemy_ocr_resultado_repository import (
    SqlAlchemyOcrResultadoRepository,
)
from app.infrastructure.repositories.sqlalchemy_empresa_repository import (
    SqlAlchemyEmpresaRepository,
)
from app.domain.entities import Empresa


def _criar_empresa(db_session):
    repo = SqlAlchemyEmpresaRepository(db_session)
    empresa = repo.criar(
        Empresa(id=None, razao_social="Tesserato", nome_fantasia=None, cnpj="12345678000199")
    )
    db_session.commit()
    return empresa


def test_criar_listar_e_atualizar_documento(db_session):
    empresa = _criar_empresa(db_session)
    repo = SqlAlchemyDocumentoRepository(db_session)

    documento = repo.criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="20260727_abcd1234.pdf",
            nome_exibicao="comprovante.pdf", caminho_arquivo=f"empresa_{empresa.id}/documentos/x.pdf",
            extensao=".pdf", tamanho_bytes=1024,
        )
    )
    db_session.commit()

    pendentes = repo.listar_pendentes_por_empresa(empresa.id)
    assert len(pendentes) == 1

    documento.status = StatusDocumento.CONCLUIDO
    repo.atualizar(documento)
    db_session.commit()

    assert repo.listar_pendentes_por_empresa(empresa.id) == []
    assert len(repo.listar_por_empresa(empresa.id)) == 1


def test_criar_e_obter_ocr_resultado(db_session):
    empresa = _criar_empresa(db_session)
    doc_repo = SqlAlchemyDocumentoRepository(db_session)
    documento = doc_repo.criar(
        Documento(
            id=None, empresa_id=empresa.id, nome_arquivo="a.pdf", nome_exibicao="a.pdf",
            caminho_arquivo="x/a.pdf", extensao=".pdf", tamanho_bytes=10,
        )
    )
    db_session.commit()

    resultado_repo = SqlAlchemyOcrResultadoRepository(db_session)
    resultado_repo.criar(
        OcrResultado(
            id=None, documento_id=documento.id, texto_extraido="texto",
            metodo=MetodoOcr.PDF_NATIVO, tempo_processamento_ms=10,
        )
    )
    db_session.commit()

    encontrado = resultado_repo.obter_por_documento_id(documento.id)
    assert encontrado.texto_extraido == "texto"


def test_criar_e_atualizar_lote(db_session):
    empresa = _criar_empresa(db_session)
    repo = SqlAlchemyLoteProcessamentoRepository(db_session)

    lote = repo.criar(LoteProcessamento(id=None, empresa_id=empresa.id, total_documentos=3))
    db_session.commit()
    assert lote.status == StatusLote.EM_ANDAMENTO

    lote.documentos_processados = 3
    lote.status = StatusLote.CONCLUIDO
    repo.atualizar(lote)
    db_session.commit()

    atualizado = repo.obter_por_id(lote.id)
    assert atualizado.documentos_processados == 3
    assert atualizado.status == StatusLote.CONCLUIDO
