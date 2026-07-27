import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ContasTree } from "../components/ContasTree";
import { EmpresaForm } from "../components/EmpresaForm";
import { EmpresaList } from "../components/EmpresaList";
import { PlanoContasImport } from "../components/PlanoContasImport";
import type { Empresa } from "../types/empresa";
import type { Conta, PlanoContas } from "../types/planoContas";

export function EmpresasPage() {
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [empresaSelecionadaId, setEmpresaSelecionadaId] = useState<number | null>(null);
  const [planos, setPlanos] = useState<PlanoContas[]>([]);
  const [planoSelecionadoId, setPlanoSelecionadoId] = useState<number | null>(null);
  const [contas, setContas] = useState<Conta[]>([]);
  const [nomePlano, setNomePlano] = useState("");

  useEffect(() => {
    api.empresas.list().then(setEmpresas);
  }, []);

  useEffect(() => {
    setPlanoSelecionadoId(null);
    if (empresaSelecionadaId === null) {
      setPlanos([]);
      return;
    }
    api.planosContas.list(empresaSelecionadaId).then(setPlanos);
  }, [empresaSelecionadaId]);

  useEffect(() => {
    if (planoSelecionadoId === null) {
      setContas([]);
      return;
    }
    api.contas.listByPlano(planoSelecionadoId).then(setContas);
  }, [planoSelecionadoId]);

  async function handleCriarPlano() {
    if (empresaSelecionadaId === null || !nomePlano) return;
    const plano = await api.planosContas.create(empresaSelecionadaId, nomePlano);
    setPlanos((atual) => [...atual, plano]);
    setNomePlano("");
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

      {planoSelecionadoId !== null && (
        <section className="grid grid-cols-2 gap-4 border-t border-slate-200 pt-4">
          <PlanoContasImport
            planoId={planoSelecionadoId}
            onImported={(novasContas) => setContas((atual) => [...atual, ...novasContas])}
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
