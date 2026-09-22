import { useState } from "react";
import { api } from "../api/client";

function baixarArquivo(blob: Blob, nomeArquivo: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nomeArquivo;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportarPlanilha({ empresaId }: { empresaId: number }) {
  const [exportando, setExportando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function handleExportar() {
    setExportando(true);
    setAviso(null);
    setErro(null);
    try {
      const pendentes = await api.documentos.filaRevisao(empresaId);
      const { blob, nomeArquivo } = await api.documentos.exportar(empresaId);
      baixarArquivo(blob, nomeArquivo);
      if (pendentes.length > 0) {
        setAviso(
          `${pendentes.length} documento(s) ainda na fila de revisão — as linhas sem conta ficaram em branco na planilha.`,
        );
      }
    } catch (err) {
      setErro((err as Error).message);
    } finally {
      setExportando(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handleExportar}
        disabled={exportando}
        className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {exportando ? "Exportando..." : "Exportar planilha"}
      </button>
      {aviso && <p className="text-xs text-amber-700">{aviso}</p>}
      {erro && <p className="text-xs text-red-600">{erro}</p>}
    </div>
  );
}
