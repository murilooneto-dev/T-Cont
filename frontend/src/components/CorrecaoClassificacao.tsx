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
  onCorrigirContaBancaria,
  mostrarSelecaoContrapartida = true,
}: {
  classificacao: Classificacao | null;
  contas: Conta[];
  onCorrigir: (contaId: number) => Promise<void>;
  onCorrigirContaBancaria: (contaBancariaId: number) => Promise<void>;
  /** Quando false, oculta o select/botão de "Corrigir para..." (troca da
   * contrapartida). Usado pela Fila de Revisão quando a origem já é
   * confiável (REGRA/IA/MANUAL) e só falta completar o lançamento — nesse
   * caso trocar a contrapartida via este fluxo teria efeitos colaterais
   * indesejados (vira MANUAL, cria/atualiza Regra, registra Aprendizado)
   * sem resolver o problema real, que é o banco/direção. Default true para
   * preservar o comportamento em outros usos deste componente (ex.: painel
   * "Ver texto" de DocumentoList). */
  mostrarSelecaoContrapartida?: boolean;
}) {
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");
  const [contaBancariaId, setContaBancariaId] = useState<number | "">("");
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

  async function handleCorrigirContaBancaria() {
    if (contaBancariaId === "") return;
    setErro(null);
    try {
      await onCorrigirContaBancaria(contaBancariaId);
      setContaBancariaId("");
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  const contasBancarias = contas.filter(
    (conta) => conta.conta_analitica && conta.natureza === "ATIVO",
  );
  const precisaDeContaBancaria = classificacao !== null && classificacao.direcao !== null
    && (classificacao.debito_codigo === null || classificacao.credito_codigo === null);

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      {classificacao ? (
        <div>
          <p>
            <span className="font-semibold">Débito: </span>
            {classificacao.debito_codigo
              ? `${classificacao.debito_codigo} — ${classificacao.debito_descricao}`
              : "—"}
          </p>
          <p>
            <span className="font-semibold">Crédito: </span>
            {classificacao.credito_codigo
              ? `${classificacao.credito_codigo} — ${classificacao.credito_descricao}`
              : "—"}
          </p>
          <p className="text-slate-500">
            {rotuloOrigem(classificacao.origem)}
            {classificacao.score_similaridade !== null &&
              ` — ${Math.round(classificacao.score_similaridade * 100)}%`}
          </p>
        </div>
      ) : (
        <span className="font-semibold">SEM CLASSIFICAÇÃO</span>
      )}
      {mostrarSelecaoContrapartida && (
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
      )}
      {precisaDeContaBancaria && (
        <div className="mt-2 flex items-center gap-2">
          <select
            className="rounded border border-slate-300 px-2 py-1 text-xs"
            value={contaBancariaId}
            onChange={(e) => setContaBancariaId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Conta bancária...</option>
            {contasBancarias.map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
          </select>
          <button
            onClick={handleCorrigirContaBancaria}
            disabled={contaBancariaId === ""}
            className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
          >
            Corrigir conta bancária
          </button>
        </div>
      )}
      {erro && <p className="mt-1 text-red-600">{erro}</p>}
    </div>
  );
}
