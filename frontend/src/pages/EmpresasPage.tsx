import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { ContasTree } from "../components/ContasTree";
import { DocumentoDropzone } from "../components/DocumentoDropzone";
import { DocumentoList } from "../components/DocumentoList";
import { EmpresaForm } from "../components/EmpresaForm";
import { EmpresaList } from "../components/EmpresaList";
import { PlanoContasImport } from "../components/PlanoContasImport";
import { ProgressoLote } from "../components/ProgressoLote";
import type { Documento, Lote } from "../types/documento";
import type { Empresa } from "../types/empresa";
import type { Conta, PlanoContas } from "../types/planoContas";

export function EmpresasPage() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionadaId, setEmpresaSelecionadaId] = useState<number | null>(null);
  const [planos, setPlanos] = useState<PlanoContas[]>([]);
  const [planoSelecionadoId, setPlanoSelecionadoId] = useState<number | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [nomePlano, setNomePlano] = useState("");
  const [documentos, setDocumentos] = useState<Documento[]>([]);
  const [lote, setLote] = useState<Lote | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.empresas.list().then(setEmpresas);
  }, []);

  useEffect(() => {
    if (empresaSelecionadaId === null) {
      setDocumentos([]);
      setLote(null);
      return;
    }
    api.documentos.list(empresaSelecionadaId).then(setDocumentos);
  }, [empresaSelecionadaId]);

  useEffect(() => {
    if (lote === null || lote.status !== "EM_ANDAMENTO") {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }
    pollingRef.current = setInterval(async () => {
      const atualizado = await api.lotes.status(lote.id);
      setLote(atualizado);
      if (atualizado.status !== "EM_ANDAMENTO" && empresaSelecionadaId !== null) {
        const documentosAtualizados = await api.documentos.list(empresaSelecionadaId);
        setDocumentos(documentosAtualizados);
      }
    }, 2000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [lote, empresaSelecionadaId]);

  useEffect(() => {
    setPlanoSelecionadoId(null);
    if (empresaSelecionadaId === null) {
      setPlanos([]);
      return;
    }
    api.planosContas.list(empresaSelecionadaId).then(setPlanos);
  }, [empresaSelecionadaId]);

  const carregarContas = useCallback(() => {
    if (planoSelecionadoId === null) {
      setContas([]);
      return;
    }
    api.contas.listByPlano(planoSelecionadoId).then(setContas);
  }, [planoSelecionadoId]);

  useEffect(() => {
    carregarContas();
  }, [carregarContas]);

  async function handleCriarPlano() {
    if (empresaSelecionadaId === null || !nomePlano) return;
    const plano = await api.planosContas.create(empresaSelecionadaId, nomePlano);
    setPlanos((atual) => [...atual, plano]);
    setNomePlano("");
  }

  async function handleProcessar() {
    if (empresaSelecionadaId === null) return;
    const novoLote = await api.lotes.processar(empresaSelecionadaId);
    setLote(novoLote);
  }

  async function handleCancelarLote() {
    if (lote === null) return;
    const cancelado = await api.lotes.cancelar(lote.id);
    setLote(cancelado);
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-8">
      <h1 className="text-2xl font-bold text-slate-800">
        Classificador de Comprovantes — Fase 0
      </h1>

      <section className="grid grid-cols-2 gap-4">
        <EmpresaForm onCreated={(empresa) => setEmpresas((atual) => [...atual, empresa])} />
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Empresas</h2>
          <EmpresaList
            empresas={empresas}
            selectedId={empresaSelecionadaId}
            onSelect={setEmpresaSelecionadaId}
          />
        </div>
      </section>

      {empresaSelecionadaId !== null && (
        <section className="flex flex-col gap-3 border-t border-slate-200 pt-4">
          <h2 className="text-sm font-semibold text-slate-700">Planos de Contas</h2>
          <div className="flex gap-2">
            <input
              className="flex-1 rounded border border-slate-300 px-2 py-1"
              placeholder="Nome do novo plano de contas"
              value={nomePlano}
              onChange={(e) => setNomePlano(e.target.value)}
            />
            <button
              onClick={handleCriarPlano}
              className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white"
            >
              Criar
            </button>
          </div>
          <ul className="flex flex-col gap-1">
            {planos.map((plano) => (
              <li key={plano.id}>
                <button
                  onClick={() => setPlanoSelecionadoId(plano.id)}
                  className={`w-full rounded px-3 py-1.5 text-left text-sm ${
                    planoSelecionadoId === plano.id
                      ? "bg-slate-800 text-white"
                      : "bg-slate-100 text-slate-800"
                  }`}
                >
                  {plano.nome}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {empresaSelecionadaId !== null && (
        <section className="flex flex-col gap-3 border-t border-slate-200 pt-4">
          <h2 className="text-sm font-semibold text-slate-700">Comprovantes</h2>
          <DocumentoDropzone
            empresaId={empresaSelecionadaId}
            onUploaded={(novos) => setDocumentos((atual) => [...atual, ...novos])}
          />
          <button
            onClick={handleProcessar}
            disabled={documentos.every((d) => d.status !== "PENDENTE")}
            className="self-start rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Processar
          </button>
          {lote && <ProgressoLote lote={lote} onCancelar={handleCancelarLote} />}
          <DocumentoList documentos={documentos} />
        </section>
      )}

      {planoSelecionadoId !== null && (
        <section className="grid grid-cols-2 gap-4 border-t border-slate-200 pt-4">
          <PlanoContasImport
            planoId={planoSelecionadoId}
            onImported={carregarContas}
          />
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Contas</h2>
            <ContasTree contas={contas} />
          </div>
        </section>
      )}
    </div>
  );
}
