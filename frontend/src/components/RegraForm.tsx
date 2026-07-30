import { useState } from "react";
import { api } from "../api/client";
import type { TipoDocumento } from "../types/documento";
import type { Conta } from "../types/planoContas";
import type { LadoRegra, Regra } from "../types/regra";

const TIPOS_DOCUMENTO: TipoDocumento[] = ["PIX", "TED", "DOC", "BOLETO", "OUTRO"];

export function RegraForm({
  empresaId,
  contas,
  onCreated,
}: {
  empresaId: number;
  contas: Conta[];
  onCreated: (regra: Regra) => void;
}) {
  const [contaId, setContaId] = useState<number | "">("");
  const [ladoAlvo, setLadoAlvo] = useState<LadoRegra | "">("");
  const [documentoFiscal, setDocumentoFiscal] = useState("");
  const [tipoDocumento, setTipoDocumento] = useState<TipoDocumento | "">("");
  const [valorMin, setValorMin] = useState("");
  const [valorMax, setValorMax] = useState("");
  const [palavraChave, setPalavraChave] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    if (contaId === "") return;
    try {
      const regra = await api.regras.create(empresaId, {
        conta_id: contaId,
        lado_alvo: ladoAlvo || null,
        documento_fiscal: documentoFiscal || null,
        tipo_documento: tipoDocumento || null,
        valor_min: valorMin || null,
        valor_max: valorMax || null,
        palavra_chave_nome: palavraChave || null,
      });
      setContaId("");
      setLadoAlvo("");
      setDocumentoFiscal("");
      setTipoDocumento("");
      setValorMin("");
      setValorMax("");
      setPalavraChave("");
      onCreated(regra);
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 rounded border border-slate-200 p-4">
      <label className="text-sm font-medium text-slate-700">
        Conta
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={contaId}
          onChange={(e) => setContaId(e.target.value ? Number(e.target.value) : "")}
          required
        >
          <option value="">Selecione...</option>
          {contas.map((conta) => (
            <option key={conta.id} value={conta.id}>
              {conta.codigo} — {conta.descricao}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm font-medium text-slate-700">
        Lado alvo (CNPJ/palavra-chave)
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={ladoAlvo}
          onChange={(e) => setLadoAlvo(e.target.value as LadoRegra | "")}
        >
          <option value="">Nenhum</option>
          <option value="PAGADOR">Pagador</option>
          <option value="RECEBEDOR">Recebedor</option>
        </select>
      </label>
      <label className="text-sm font-medium text-slate-700">
        CNPJ/CPF
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={documentoFiscal}
          onChange={(e) => setDocumentoFiscal(e.target.value)}
          placeholder="Somente dígitos"
        />
      </label>
      <label className="text-sm font-medium text-slate-700">
        Tipo de documento
        <select
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={tipoDocumento}
          onChange={(e) => setTipoDocumento(e.target.value as TipoDocumento | "")}
        >
          <option value="">Qualquer</option>
          {TIPOS_DOCUMENTO.map((tipo) => (
            <option key={tipo} value={tipo}>
              {tipo}
            </option>
          ))}
        </select>
      </label>
      <div className="flex gap-2">
        <label className="flex-1 text-sm font-medium text-slate-700">
          Valor mínimo
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={valorMin}
            onChange={(e) => setValorMin(e.target.value)}
            placeholder="0.00"
          />
        </label>
        <label className="flex-1 text-sm font-medium text-slate-700">
          Valor máximo
          <input
            className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
            value={valorMax}
            onChange={(e) => setValorMax(e.target.value)}
            placeholder="0.00"
          />
        </label>
      </div>
      <label className="text-sm font-medium text-slate-700">
        Palavra-chave no nome
        <input
          className="mt-1 w-full rounded border border-slate-300 px-2 py-1"
          value={palavraChave}
          onChange={(e) => setPalavraChave(e.target.value)}
        />
      </label>
      {erro && <p className="text-sm text-red-600">{erro}</p>}
      <button type="submit" className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white">
        Cadastrar Regra
      </button>
    </form>
  );
}
