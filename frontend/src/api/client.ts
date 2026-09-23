import type { Empresa, EmpresaCreateInput } from "../types/empresa";
import type { Conta, ImportPreview, PlanoContas } from "../types/planoContas";
import type {
  Classificacao, CorrecaoLoteResultado, Documento, DocumentoResultado, ItemFilaRevisao, Lote,
  UploadItemResultado,
} from "../types/documento";
import type { Regra, RegraCreateInput, RegraUpdateInput } from "../types/regra";

const BASE_URL = "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? "Erro na requisição");
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  empresas: {
    list: () => request<Empresa[]>("/empresas"),
    create: (input: EmpresaCreateInput) =>
      request<Empresa>("/empresas", { method: "POST", body: JSON.stringify(input) }),
    deactivate: (id: number) => request<void>(`/empresas/${id}`, { method: "DELETE" }),
  },
  planosContas: {
    list: (empresaId: number) =>
      request<PlanoContas[]>(`/empresas/${empresaId}/planos-contas`),
    create: (empresaId: number, nome: string) =>
      request<PlanoContas>(`/empresas/${empresaId}/planos-contas`, {
        method: "POST",
        body: JSON.stringify({ nome }),
      }),
  },
  contas: {
    listByPlano: (planoId: number) => request<Conta[]>(`/planos-contas/${planoId}/contas`),
    importPreview: (planoId: number, file: File) => {
      const formData = new FormData();
      formData.append("arquivo", file);
      return request<ImportPreview>(`/planos-contas/${planoId}/import/preview`, {
        method: "POST",
        body: formData,
      });
    },
    importConfirm: (planoId: number, file: File) => {
      const formData = new FormData();
      formData.append("arquivo", file);
      return request<Conta[]>(`/planos-contas/${planoId}/import/confirm`, {
        method: "POST",
        body: formData,
      });
    },
  },
  documentos: {
    upload: (empresaId: number, arquivos: File[]) => {
      const formData = new FormData();
      arquivos.forEach((arquivo) => formData.append("arquivos", arquivo));
      return request<UploadItemResultado[]>(`/empresas/${empresaId}/documentos`, {
        method: "POST",
        body: formData,
      });
    },
    list: (empresaId: number) => request<Documento[]>(`/empresas/${empresaId}/documentos`),
    resultado: (documentoId: number) =>
      request<DocumentoResultado>(`/documentos/${documentoId}/resultado`),
    corrigirClassificacao: (documentoId: number, contaId: number) =>
      request<Classificacao>(`/documentos/${documentoId}/classificacao`, {
        method: "PATCH",
        body: JSON.stringify({ conta_id: contaId }),
      }),
    corrigirContaBancaria: (documentoId: number, contaBancariaId: number) =>
      request<Classificacao>(`/documentos/${documentoId}/classificacao/conta-bancaria`, {
        method: "PATCH",
        body: JSON.stringify({ conta_bancaria_id: contaBancariaId }),
      }),
    filaRevisao: (empresaId: number) =>
      request<ItemFilaRevisao[]>(`/empresas/${empresaId}/documentos/fila-revisao`),
    limparFilaRevisao: (empresaId: number) =>
      request<{ documentos_apagados: number }>(
        `/empresas/${empresaId}/documentos/fila-revisao`,
        { method: "DELETE" },
      ),
    limparProcessados: (empresaId: number) =>
      request<{ documentos_apagados: number }>(
        `/empresas/${empresaId}/documentos/processados`,
        { method: "DELETE" },
      ),
    corrigirClassificacaoLote: (documentoIds: number[], contaId: number) =>
      request<CorrecaoLoteResultado>("/documentos/classificacao/lote", {
        method: "PATCH",
        body: JSON.stringify({ documento_ids: documentoIds, conta_id: contaId }),
      }),
    exportar: async (empresaId: number): Promise<{ blob: Blob; nomeArquivo: string }> => {
      const response = await fetch(`${BASE_URL}/empresas/${empresaId}/documentos/exportar`);
      if (!response.ok) {
        const body = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(body.detail ?? "Erro na requisição");
      }
      const disposicao = response.headers.get("Content-Disposition") ?? "";
      const correspondencia = /filename="([^"]+)"/.exec(disposicao);
      return {
        blob: await response.blob(),
        nomeArquivo: correspondencia ? correspondencia[1] : "comprovantes.xlsx",
      };
    },
  },
  lotes: {
    processar: (empresaId: number) =>
      request<Lote>(`/empresas/${empresaId}/documentos/processar`, { method: "POST" }),
    status: (loteId: number) => request<Lote>(`/lotes/${loteId}`),
    cancelar: (loteId: number) =>
      request<Lote>(`/lotes/${loteId}/cancelar`, { method: "POST" }),
  },
  regras: {
    list: (empresaId: number) => request<Regra[]>(`/empresas/${empresaId}/regras`),
    create: (empresaId: number, input: RegraCreateInput) =>
      request<Regra>(`/empresas/${empresaId}/regras`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    update: (empresaId: number, regraId: number, input: RegraUpdateInput) =>
      request<Regra>(`/empresas/${empresaId}/regras/${regraId}`, {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    remove: (empresaId: number, regraId: number) =>
      request<void>(`/empresas/${empresaId}/regras/${regraId}`, { method: "DELETE" }),
  },
};
