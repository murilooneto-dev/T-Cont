import type { Lote } from "../types/documento";

export function ProgressoLote({
  lote,
  onCancelar,
}: {
  lote: Lote;
  onCancelar: () => void;
}) {
  const percentual =
    lote.total_documentos === 0
      ? 100
      : Math.round((lote.documentos_processados / lote.total_documentos) * 100);

  return (
    <div className="flex flex-col gap-2 rounded border border-slate-200 p-3">
      <div className="flex items-center justify-between text-sm">
        <span>
          {lote.documentos_processados} de {lote.total_documentos} processados —{" "}
          {lote.status}
        </span>
        {lote.status === "EM_ANDAMENTO" && (
          <button onClick={onCancelar} className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
            Cancelar
          </button>
        )}
      </div>
      <div className="h-2 w-full rounded bg-slate-200">
        <div
          className="h-2 rounded bg-slate-700 transition-all"
          style={{ width: `${percentual}%` }}
        />
      </div>
    </div>
  );
}
