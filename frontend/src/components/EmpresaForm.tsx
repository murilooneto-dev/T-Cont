import { useState } from "react";
import { api } from "../api/client";
import type { Empresa } from "../types/empresa";

export function EmpresaForm({ onCreated }: { onCreated: (empresa: Empresa) => void }) {
  const [razaoSocial, setRazaoSocial] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    try {
      const empresa = await api.empresas.create({
        razao_social: razaoSocial,
        nome_fantasia: null,
        cnpj,
      });
      setRazaoSocial("");
      setCnpj("");
      onCreated(empresa);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 rounded border border-slate-200 p-4">
      <label className="text-sm font-medium text-slate-700">
        Razão Social
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={razaoSocial}
          onChange={(e) => setRazaoSocial(e.target.value)}
          required
        />
      </label>
      <label className="text-sm font-medium text-slate-700">
        CNPJ
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={cnpj}
          onChange={(e) => setCnpj(e.target.value)}
          required
        />
      </label>
      {erro && <p className="text-sm text-red-600">{erro}</p>}
      <button type="submit" className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white">
        Cadastrar Empresa
      </button>
    </form>
  );
}
