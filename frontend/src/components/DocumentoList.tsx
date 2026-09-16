import { useState } from "react";
import { api } from "../api/client";
import type { Documento, DocumentoResultado, OrigemClassificacao } from "../types/documento";
import type { Conta } from "../types/planoContas";

function corStatus(status: Documento["status"]): string {
  switch (status) {
    case "CONCLUIDO":
      return "text-green-700";
    case "ERRO":
      return "text-red-700";
    case "PROCESSANDO":
      return "text-amber-700";
    default:
      return "text-slate-500";
  }
}

function rotuloOrigem(origem: OrigemClassificacao): string {
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

export function DocumentoList({
  documentos,
  contas,
}: {
  documentos: Documento[];
  contas: Conta[];
}) {
  const [resultadoAberto, setResultadoAberto] = useState<DocumentoResultado | null>(null);
  const [contaCorrecaoId, setContaCorrecaoId] = useState<number | "">("");

  async function verResultado(documentoId: number) {
    const resultado = await api.documentos.resultado(documentoId);
    setResultadoAberto(resultado);
  }

  async function corrigirClassificacao() {
    if (resultadoAberto === null || contaCorrecaoId === "") return;
    const classificacao = await api.documentos.corrigirClassificacao(
      resultadoAberto.documento.id,
      contaCorrecaoId,
    );
    setResultadoAberto({ ...resultadoAberto, classificacao });
    setContaCorrecaoId("");
  }

  if (documentos.length === 0) {
    return <p className="text-sm text-slate-500">Nenhum documento enviado ainda.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1">
        {documentos.map((documento) => (
          <li
            key={documento.id}
            className="flex items-center justify-between rounded border border-slate-200 px-3 py-1.5 text-sm"
          >
            <span>{documento.nome_exibicao}</span>
            <div className="flex items-center gap-2">
              <span className={corStatus(documento.status)}>{documento.status}</span>
              {documento.status === "CONCLUIDO" && (
                <button
                  onClick={() => verResultado(documento.id)}
                  className="rounded bg-slate-200 px-2 py-0.5 text-xs"
                >
                  Ver texto
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
      {resultadoAberto && (
        <div className="rounded border border-slate-300 bg-slate-50 p-3 text-xs">
          {resultadoAberto.extracao && (
            <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1">
              <span className="font-semibold">Tipo:</span>
              <span>{resultadoAberto.extracao.tipo_documento}</span>
              <span className="font-semibold">Pagador:</span>
              <span>{resultadoAberto.extracao.pagador_nome}</span>
              <span className="font-semibold">CPF/CNPJ Pagador:</span>
              <span>{resultadoAberto.extracao.pagador_documento}</span>
              <span className="font-semibold">Recebedor:</span>
              <span>{resultadoAberto.extracao.recebedor_nome}</span>
              <span className="font-semibold">CPF/CNPJ Recebedor:</span>
              <span>{resultadoAberto.extracao.recebedor_documento}</span>
              <span className="font-semibold">Valor:</span>
              <span>{resultadoAberto.extracao.valor}</span>
              <span className="font-semibold">Data:</span>
              <span>{resultadoAberto.extracao.data_pagamento}</span>
              <span className="font-semibold">Banco:</span>
              <span>{resultadoAberto.extracao.banco_nome}</span>
            </div>
          )}
          <div className="mb-3 rounded border border-slate-200 bg-white p-2">
            <span className="font-semibold">Classificação: </span>
            {resultadoAberto.classificacao ? (
              <span>
                {resultadoAberto.classificacao.conta_codigo} —{" "}
                {resultadoAberto.classificacao.conta_descricao} (
                {rotuloOrigem(resultadoAberto.classificacao.origem)}
                {resultadoAberto.classificacao.score_similaridade !== null &&
                  ` — ${Math.round(resultadoAberto.classificacao.score_similaridade * 100)}%`}
                )
              </span>
            ) : (
              <span>SEM CLASSIFICAÇÃO</span>
            )}
            <div className="mt-2 flex items-center gap-2">
              <select
                className="rounded border border-slate-300 px-2 py-1 text-xs"
                value={contaCorrecaoId}
                onChange={(e) =>
                  setContaCorrecaoId(e.target.value ? Number(e.target.value) : "")
                }
              >
                <option value="">Corrigir para...</option>
                {contas.map((conta) => (
                  <option key={conta.id} value={conta.id}>
                    {conta.codigo} — {conta.descricao}
                  </option>
                ))}
              </select>
              <button
                onClick={corrigirClassificacao}
                disabled={contaCorrecaoId === ""}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-white disabled:opacity-50"
              >
                Corrigir
              </button>
            </div>
          </div>
          <p className="mb-1 font-semibold">
            Método: {resultadoAberto.resultado?.metodo} (
            {resultadoAberto.resultado?.tempo_processamento_ms}ms)
          </p>
          <pre className="whitespace-pre-wrap">{resultadoAberto.resultado?.texto_extraido}</pre>
        </div>
      )}
    </div>
  );
}
