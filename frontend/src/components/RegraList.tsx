import { useState } from "react";
import { api } from "../api/client";
import type { Conta } from "../types/planoContas";
import type { Regra } from "../types/regra";

function descricaoConta(contas: Conta[], contaId: number): string {
  const conta = contas.find((c) => c.id === contaId);
  return conta ? `${conta.codigo} — ${conta.descricao}` : `Conta ${contaId}`;
}

function resumoCondicoes(regra: Regra): string {
  const partes: string[] = [];
  if (regra.documento_fiscal) partes.push(`CNPJ/CPF ${regra.lado_alvo ?? "—"}: ${regra.documento_fiscal}`);
  if (regra.tipo_documento) partes.push(`Tipo: ${regra.tipo_documento}`);
  if (regra.valor_min || regra.valor_max) {
    partes.push(`Valor: ${regra.valor_min ?? "0"} a ${regra.valor_max ?? "∞"}`);
  }
  if (regra.palavra_chave_nome) {
    partes.push(`Palavra-chave (${regra.lado_alvo ?? "—"}): "${regra.palavra_chave_nome}"`);
  }
  return partes.join(" · ");
}

export function RegraList({
  empresaId,
  regras,
  contas,
  onChanged,
}: {
  empresaId: number;
  regras: Regra[];
  contas: Conta[];
  onChanged: (regras: Regra[]) => void;
}) {
  async function alternarAtivo(regra: Regra) {
    const atualizada = await api.regras.update(empresaId, regra.id, {
      conta_id: regra.conta_id,
      lado_alvo: regra.lado_alvo,
      documento_fiscal: regra.documento_fiscal,
      tipo_documento: regra.tipo_documento,
      valor_min: regra.valor_min,
      valor_max: regra.valor_max,
      palavra_chave_nome: regra.palavra_chave_nome,
      ativo: !regra.ativo,
    });
    onChanged(regras.map((r) => (r.id === atualizada.id ? atualizada : r)));
  }

  const [erro, setErro] = useState<string | null>(null);

  async function apagar(regraId: number) {
    setErro(null);
    try {
      await api.regras.remove(empresaId, regraId);
      onChanged(regras.filter((r) => r.id !== regraId));
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  if (regras.length === 0) {
    return <p className="text-sm text-slate-500">Nenhuma regra cadastrada ainda.</p>;
  }

  return (
    <div className="flex flex-col gap-1">
    {erro && <p className="text-xs text-red-600">{erro}</p>}
    <ul className="flex flex-col gap-1">
      {regras.map((regra) => (
        <li
          key={regra.id}
          className="flex items-center justify-between gap-2 rounded border border-slate-200 px-3 py-1.5 text-sm"
        >
          <div>
            <p className="font-medium text-slate-800">{descricaoConta(contas, regra.conta_id)}</p>
            <p className="text-xs text-slate-500">{resumoCondicoes(regra)}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => alternarAtivo(regra)}
              className={`rounded px-2 py-0.5 text-xs ${
                regra.ativo ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"
              }`}
            >
              {regra.ativo ? "Ativa" : "Inativa"}
            </button>
            <button
              onClick={() => apagar(regra.id)}
              className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700"
            >
              Apagar
            </button>
          </div>
        </li>
      ))}
    </ul>
    </div>
  );
}
