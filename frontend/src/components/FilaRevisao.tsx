import { useEffect, useState, type KeyboardEvent } from "react";
import { api } from "../api/client";
import { CorrecaoClassificacao } from "./CorrecaoClassificacao";
import type { Classificacao, ItemFilaRevisao } from "../types/documento";
import type { Conta } from "../types/planoContas";

function paraClassificacaoView(item: ItemFilaRevisao): Classificacao | null {
  if (item.classificacao_sugerida === null) return null;
  const sugestao = item.classificacao_sugerida;
  return {
    conta_id: sugestao.conta_id,
    conta_codigo: sugestao.conta_codigo,
    conta_descricao: sugestao.conta_descricao,
    origem: sugestao.origem ?? "FUZZY",
    regra_id: null,
    score_similaridade: sugestao.score_similaridade,
    direcao: sugestao.direcao,
    debito_codigo: sugestao.debito_codigo,
    debito_descricao: sugestao.debito_descricao,
    credito_codigo: sugestao.credito_codigo,
    credito_descricao: sugestao.credito_descricao,
  };
}

/** O botão/fluxo de "Confirmar sugestão fuzzy" só faz sentido quando a
 * origem da classificação é realmente FUZZY (ou quando não há classificação
 * nenhuma ainda). Para REGRA/IA/MANUAL, a contrapartida já está correta — o
 * que falta é só completar o lançamento (banco/direção), que é resolvido
 * pelo select de conta bancária em CorrecaoClassificacao, não por este botão.
 */
function ehSugestaoFuzzy(item: ItemFilaRevisao): boolean {
  return (
    item.classificacao_sugerida !== null &&
    (item.classificacao_sugerida.origem === null ||
      item.classificacao_sugerida.origem === "FUZZY")
  );
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

  function carregarFila(
    manterSelecionados?: Set<number>,
    manterErros?: Record<number, string>,
  ) {
    api.documentos
      .filaRevisao(empresaId)
      .then((novosItens) => {
        setItens(novosItens);
        setSelecionados(manterSelecionados ?? new Set());
        setErrosLote(manterErros ?? {});
        setFocoIndex(0);
      })
      .catch((err) => {
        console.error("Erro ao carregar fila de revisão:", err);
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
    try {
      await api.documentos.corrigirClassificacao(documentoId, contaId);
      const errosRestantes = { ...errosLote };
      delete errosRestantes[documentoId];
      carregarFila(undefined, errosRestantes);
    } catch (err) {
      setErrosLote((atual) => ({
        ...atual,
        [documentoId]: (err as Error).message,
      }));
    }
  }

  async function confirmarContaBancaria(documentoId: number, contaBancariaId: number) {
    try {
      await api.documentos.corrigirContaBancaria(documentoId, contaBancariaId);
      const errosRestantes = { ...errosLote };
      delete errosRestantes[documentoId];
      carregarFila(undefined, errosRestantes);
    } catch (err) {
      setErrosLote((atual) => ({
        ...atual,
        [documentoId]: (err as Error).message,
      }));
    }
  }

  async function aplicarLote() {
    if (contaLoteId === "" || selecionados.size === 0) return;
    try {
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
      const restantes = new Set(selecionados);
      idsComSucesso.forEach((id) => restantes.delete(id));
      setContaLoteId("");
      carregarFila(restantes, novosErros);
    } catch (err) {
      console.error("Erro ao aplicar classificação em lote:", err);
    }
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.target !== e.currentTarget) return;
    if (itens.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocoIndex((atual) => Math.min(atual + 1, itens.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocoIndex((atual) => Math.max(atual - 1, 0));
    } else if (e.key === "Enter" || e.key === "c" || e.key === "C") {
      const item = itens[focoIndex];
      if (item && item.classificacao_sugerida && ehSugestaoFuzzy(item)) {
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
                  onCorrigirContaBancaria={(contaBancariaId) =>
                    confirmarContaBancaria(item.documento.id, contaBancariaId)
                  }
                  mostrarSelecaoContrapartida={ehSugestaoFuzzy(item)}
                />
              </div>
              {item.classificacao_sugerida && ehSugestaoFuzzy(item) && (
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
