import type { TipoDocumento } from "./documento";

export type LadoRegra = "PAGADOR" | "RECEBEDOR";

export interface Regra {
  id: number;
  empresa_id: number;
  conta_id: number;
  lado_alvo: LadoRegra | null;
  documento_fiscal: string | null;
  tipo_documento: TipoDocumento | null;
  valor_min: string | null;
  valor_max: string | null;
  palavra_chave_nome: string | null;
  ativo: boolean;
}

export interface RegraCreateInput {
  conta_id: number;
  lado_alvo: LadoRegra | null;
  documento_fiscal: string | null;
  tipo_documento: TipoDocumento | null;
  valor_min: string | null;
  valor_max: string | null;
  palavra_chave_nome: string | null;
}

export interface RegraUpdateInput extends RegraCreateInput {
  ativo: boolean;
}
