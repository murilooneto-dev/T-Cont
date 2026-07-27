export interface Empresa {
  id: number;
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmpresaCreateInput {
  razao_social: string;
  nome_fantasia: string | null;
  cnpj: string;
}
