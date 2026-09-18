import { useState } from "react";
import type { Classificacao, OrigemClassificacao } from "../types/documento";
import type { Conta } from "../types/planoContas";

export function rotuloOrigem(origem: OrigemClassificacao): string {
  switch (origem) {
    case "REGRA":
      return "por regra";
    case "IA":
      return "sugestão por IA";
    case "MANUAL":
      return "corrigida manualmente";
    default:
      return "sugestão por similaridade";
  }
}

export function CorrecaoClassificacao({
  classificacao,
  contas,
  onCorrigir,
}: {
  classificacao: Classificacao | null;
  contas: Conta[];
  onCorrigir: (contaId: number) => Promise<void>;
}) {
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleCorrigir() {
    if (contaCorrecaoId === "") return;
    setErro(null);
    try {
      await onCorrigir(contaCorrecaoId);
      setContaCorrecaoId("");
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      <span className="font-semibold">Classificação: </span>
      {classificacao ? (
        <span>
          {classificacao.conta_codigo} — {classificacao.conta_descricao} (
          {rotuloOrigem(classificacao.origem)}
          {classificacao.score_similaridade !== null &&
            ` — ${Math.round(classificacao.score_similaridade * 100)}%`}
          )
        </span>
      ) : (
        <span>SEM CLASSIFICAÇÃO</span>
      )}
      <div className="mt-2 flex items-center gap-2">
        <select
          className="rounded border border-slate-300 px-2 py-1 text-xs"
          value={contaCorrecaoId}
          onChange={(e) => setContaCorrecaoId(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Corrigir para...</option>
          {contas
            .filter((conta) => conta.conta_analitica)
            .map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
        </select>
        <button
          onClick={handleCorrigir}
          disabled={contaCorrecaoId === ""}
          className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
        >
          Corrigir
        </button>
      </div>
      {erro && <p className="mt-1 text-red-600">{erro}</p>}
    </div>
  );
}
