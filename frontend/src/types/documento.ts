export type StatusDocumento = "PENDENTE" | "PROCESSANDO" | "CONCLUIDO" | "ERRO";
export type MetodoOcr = "PDF_NATIVO" | "PADDLEOCR" | "TESSERACT";
export type StatusLote = "EM_ANDAMENTO" | "CONCLUIDO" | "CANCELADO" | "FALHOU";
export type TipoDocumento = "PIX" | "TED" | "DOC" | "BOLETO" | "OUTRO";

export interface Documento {
  id: number;
  empresa_id: number;
  nome_arquivo: string;
  nome_exibicao: string;
  extensao: string;
  tamanho_bytes: number;
  status: StatusDocumento;
  mensagem_erro: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadItemResultado {
  nome_original: string;
  documento: Documento | null;
  erro: string | null;
}

export interface OcrResultadoDetalhe {
  texto_extraido: string;
  metodo: MetodoOcr;
  tempo_processamento_ms: number;
}

export interface Extracao {
  pagador_nome: string;
  pagador_documento: string;
  recebedor_nome: string;
  recebedor_documento: string;
  valor: string;
  data_pagamento: string;
  tipo_documento: TipoDocumento;
  banco_nome: string;
}

export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
  extracao: Extracao | null;
}

export interface Lote {
  id: number;
  empresa_id: number;
  total_documentos: number;
  documentos_processados: number;
  status: StatusLote;
  created_at: string;
  concluido_em: string | null;
}
