import { useEffect, useState, type KeyboardEvent } from "react";
import { api } from "../api/client";
import { CorrecaoClassificacao } from "./CorrecaoClassificacao";
import type { Classificacao, ItemFilaRevisao } from "../types/documento";
import type { Conta } from "../types/planoContas";

function paraClassificacaoView(item: ItemFilaRevisao): Classificacao | null {
  if (item.classificacao_sugerida === null) return null;
  return {
    conta_id: item.classificacao_sugerida.conta_id,
    conta_codigo: item.classificacao_sugerida.conta_codigo,
    conta_descricao: item.classificacao_sugerida.conta_descricao,
    origem: "FUZZY",
    regra_id: null,
    score_similaridade: item.classificacao_sugerida.score_similaridade,
  };
}

export function FilaRevisao({
  empresaId,
  contas,
}: {
  empresaId: number;
  contas: Conta[];
}) {
  const [itens, setItens] = useState<ItemFilaRevisao[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [contaLoteId, setContaLoteId] = useState<number | "">("");
  const [errosLote, setErrosLote] = useState<Record<number, string>>({});
  const [focoIndex, setFocoIndex] = useState(0);

  function carregarFila() {
    api.documentos.filaRevisao(empresaId).then((novosItens) => {
      setItens(novosItens);
      setSelecionados(new Set());
      setFocoIndex(0);
    });
  }

  useEffect(() => {
    carregarFila();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaId]);

  function alternarSelecao(documentoId: number) {
    setSelecionados((atual) => {
      const novo = new Set(atual);
      if (novo.has(documentoId)) novo.delete(documentoId);
      else novo.add(documentoId);
      return novo;
    });
  }

  async function confirmar(documentoId: number, contaId: number) {
    await api.documentos.corrigirClassificacao(documentoId, contaId);
    carregarFila();
  }

  async function aplicarLote() {
    if (contaLoteId === "" || selecionados.size === 0) return;
    const resultado = await api.documentos.corrigirClassificacaoLote(
      Array.from(selecionados),
      contaLoteId,
    );
    const novosErros: Record<number, string> = {};
    const idsComSucesso = new Set<number>();
    for (const item of resultado.resultados) {
      if (item.sucesso) idsComSucesso.add(item.documento_id);
      else novosErros[item.documento_id] = item.erro ?? "Erro desconhecido.";
    }
    setErrosLote(novosErros);
    setSelecionados((atual) => {
      const restantes = new Set(atual);
      idsComSucesso.forEach((id) => restantes.delete(id));
      return restantes;
    });
    setContaLoteId("");
    carregarFila();
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (itens.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocoIndex((atual) => Math.min(atual + 1, itens.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocoIndex((atual) => Math.max(atual - 1, 0));
    } else if (e.key === "Enter" || e.key === "c" || e.key === "C") {
      const item = itens[focoIndex];
      if (item && item.classificacao_sugerida) {
        confirmar(item.documento.id, item.classificacao_sugerida.conta_id);
      }
    }
  }

  if (itens.length === 0) {
    return <p className="text-sm text-slate-500">Nenhum documento pendente de revisão.</p>;
  }

  const contasAnaliticas = contas.filter((conta) => conta.conta_analitica);

  return (
    <div className="flex flex-col gap-2" onKeyDown={handleKeyDown} tabIndex={0}>
      {selecionados.size > 0 && (
        <div className="flex items-center gap-2 rounded border border-slate-300 bg-slate-100 p-2 text-xs">
          <span>{selecionados.size} selecionado(s)</span>
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={contaLoteId}
            onChange={(e) => setContaLoteId(e.target.value ? Number(e.target.value) : "")}
          >
            <option value="">Aplicar conta...</option>
            {contasAnaliticas.map((conta) => (
              <option key={conta.id} value={conta.id}>
                {conta.codigo} — {conta.descricao}
              </option>
            ))}
          </select>
          <button
            onClick={aplicarLote}
            disabled={contaLoteId === ""}
            className="rounded bg-slate-800 px-2 py-1 text-white disabled:opacity-50"
          >
            Aplicar aos selecionados
          </button>
        </div>
      )}
      <ul className="flex flex-col gap-2">
        {itens.map((item, index) => (
          <li
            key={item.documento.id}
            className={`rounded border p-2 text-xs ${
              index === focoIndex ? "border-slate-500 bg-slate-50" : "border-slate-200"
            }`}
          >
            <div className="mb-1 flex items-center gap-2">
              <input
                type="checkbox"
                checked={selecionados.has(item.documento.id)}
                onChange={() => alternarSelecao(item.documento.id)}
              />
              <span className="font-semibold">{item.documento.nome_exibicao}</span>
            </div>
            {item.extracao && (
              <p className="mb-1 text-slate-600">
                {item.extracao.recebedor_nome} — {item.extracao.valor}
              </p>
            )}
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <CorrecaoClassificacao
                  classificacao={paraClassificacaoView(item)}
                  contas={contas}
                  onCorrigir={(contaId) => confirmar(item.documento.id, contaId)}
                />
              </div>
              {item.classificacao_sugerida && (
                <button
                  onClick={() => confirmar(item.documento.id, item.classificacao_sugerida!.conta_id)}
                  className="rounded bg-green-700 px-2 py-1 text-white"
                >
                  Confirmar
                </button>
              )}
            </div>
            {errosLote[item.documento.id] && (
              <p className="mt-1 text-red-600">{errosLote[item.documento.id]}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
