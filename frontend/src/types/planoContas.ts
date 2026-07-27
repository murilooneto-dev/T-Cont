export interface PlanoContas {
  id: number;
  empresa_id: number;
  nome: string;
  versao: number;
  ativo: boolean;
}

export interface Conta {
  id: number;
  plano_conta_id: number;
  codigo: string;
  descricao: string;
  natureza: string;
  conta_analitica: boolean;
  conta_pai_id: number | null;
}

export interface ImportPreviewLinha {
  codigo: string;
  descricao: string;
  natureza: string | null;
  conta_analitica: boolean | null;
  conta_pai: string | null;
}

export interface ImportPreview {
  mapeamento: Record<string, number | null>;
  linhas: ImportPreviewLinha[];
}
