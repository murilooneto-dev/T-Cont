export type StatusDocumento = "PENDENTE" | "PROCESSANDO" | "CONCLUIDO" | "ERRO" | "DIVIDIDO";
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
  documento_origem_id: number | null;
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

export type OrigemClassificacao = "REGRA" | "FUZZY" | "IA" | "MANUAL";

export type DirecaoLancamento = "PAGAMENTO" | "RECEBIMENTO";

export interface Classificacao {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  origem: OrigemClassificacao;
  regra_id: number | null;
  score_similaridade: number | null;
  direcao: DirecaoLancamento | null;
  debito_codigo: string | null;
  debito_descricao: string | null;
  credito_codigo: string | null;
  credito_descricao: string | null;
}

export interface DocumentoResultado {
  documento: Documento;
  resultado: OcrResultadoDetalhe | null;
  extracao: Extracao | null;
  classificacao: Classificacao | null;
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

export interface ClassificacaoSugerida {
  conta_id: number;
  conta_codigo: string;
  conta_descricao: string;
  score_similaridade: number | null;
}

export interface ItemFilaRevisao {
  documento: Documento;
  extracao: Extracao | null;
  classificacao_sugerida: ClassificacaoSugerida | null;
}

export interface ResultadoCorrecaoLoteItem {
  documento_id: number;
  sucesso: boolean;
  classificacao: Classificacao | null;
  erro: string | null;
}

export interface CorrecaoLoteResultado {
  resultados: ResultadoCorrecaoLoteItem[];
}
