import type { Empresa, EmpresaCreateInput } from "../types/empresa";
import type { Conta, ImportPreview, PlanoContas } from "../types/planoContas";

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
};
