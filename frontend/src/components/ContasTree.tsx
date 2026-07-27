import type { Conta } from "../types/planoContas";

function montarArvore(contas: Conta[], paiId: number | null): Conta[] {
  return contas
    .filter((c) => c.conta_pai_id === paiId)
    .sort((a, b) => a.codigo.localeCompare(b.codigo));
}

function No({ conta, contas, nivel }: { conta: Conta; contas: Conta[]; nivel: number }) {
  const filhas = montarArvore(contas, conta.id);
  return (
    <li style={{ marginLeft: nivel * 16 }}>
      <span className="text-sm text-slate-800">
        {conta.codigo} — {conta.descricao}
        {conta.conta_analitica ? "" : " (sintética)"}
      </span>
      {filhas.length > 0 && (
        <ul>
          {filhas.map((filha) => (
            <No key={filha.id} conta={filha} contas={contas} nivel={nivel + 1} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function ContasTree({ contas }: { contas: Conta[] }) {
  const raizes = montarArvore(contas, null);
  if (contas.length === 0) {
    return <p className="text-sm text-slate-500">Nenhuma conta importada ainda.</p>;
  }
  return (
    <ul>
      {raizes.map((raiz) => (
        <No key={raiz.id} conta={raiz} contas={contas} nivel={0} />
      ))}
    </ul>
  );
}
