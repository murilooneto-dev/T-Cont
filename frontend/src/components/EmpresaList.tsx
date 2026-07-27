import type { Empresa } from "../types/empresa";

export function EmpresaList({
  empresas,
  selectedId,
  onSelect,
}: {
  empresas: Empresa[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <ul className="flex flex-col gap-1">
      {empresas.map((empresa) => (
        <li key={empresa.id}>
          <button
            onClick={() => onSelect(empresa.id)}
            className={`w-full rounded px-3 py-1.5 text-left text-sm ${
              selectedId === empresa.id ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-800"
            }`}
          >
            {empresa.razao_social} — {empresa.cnpj}
          </button>
        </li>
      ))}
    </ul>
  );
}
