import { useState } from "react";
import { api } from "../api/client";
import type { Conta, ImportPreview } from "../types/planoContas";

export function PlanoContasImport({
  planoId,
  onImported,
}: {
  planoId: number;
  onImported: (contas: Conta[]) => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function handlePreview() {
    if (!arquivo) return;
    setErro(null);
    try {
      const resultado = await api.contas.importPreview(planoId, arquivo);
      setPreview(resultado);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  async function handleConfirmar() {
    if (!arquivo) return;
    setErro(null);
    try {
      const contas = await api.contas.importConfirm(planoId, arquivo);
      setPreview(null);
      setArquivo(null);
      onImported(contas);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded border border-slate-200 p-4">
      <input
        type="file"
        accept=".csv,.xlsx"
        onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
      />
      <button
        onClick={handlePreview}
        disabled={!arquivo}
        className="rounded bg-slate-200 px-3 py-1.5 text-sm text-slate-800 disabled:opacity-50"
      >
        Pré-visualizar
      </button>

      {erro && <p className="text-sm text-red-600">{erro}</p>}

      {preview && (
        <div>
          <p className="text-sm text-slate-600">
            Colunas detectadas: {JSON.stringify(preview.mapeamento)}
          </p>
          <p className="text-sm text-slate-600">{preview.linhas.length} linha(s) encontradas.</p>
          <button
            onClick={handleConfirmar}
            className="mt-2 rounded bg-slate-800 px-3 py-1.5 text-sm text-white"
          >
            Confirmar Importação
          </button>
        </div>
      )}
    </div>
  );
}
