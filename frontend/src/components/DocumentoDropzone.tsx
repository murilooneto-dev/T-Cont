import { useRef, useState } from "react";
import { api } from "../api/client";
import type { Documento } from "../types/documento";

export function DocumentoDropzone({
  empresaId,
  onUploaded,
}: {
  empresaId: number;
  onUploaded: (documentos: Documento[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviarArquivos(arquivos: FileList | File[]) {
    setErro(null);
    try {
      const resultados = await api.documentos.upload(empresaId, Array.from(arquivos));
      const documentosCriados = resultados
        .filter((r) => r.documento !== null)
        .map((r) => r.documento as Documento);
      const erros = resultados.filter((r) => r.erro !== null);
      if (erros.length > 0) {
        setErro(erros.map((e) => `${e.nome_original}: ${e.erro}`).join("; "));
      }
      if (documentosCriados.length > 0) {
        onUploaded(documentosCriados);
      }
    } catch (err) {
      setErro((err as Error).message);
    }
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setArrastando(true);
      }}
      onDragLeave={() => setArrastando(false)}
      onDrop={(e) => {
        e.preventDefault();
        setArrastando(false);
        if (e.dataTransfer.files.length > 0) enviarArquivos(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded border-2 border-dashed p-8 text-center text-sm ${
        arrastando ? "border-slate-500 bg-slate-100" : "border-slate-300 text-slate-500"
      }`}
    >
      Arraste comprovantes aqui (PDF/PNG/JPG) ou clique para selecionar
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.png,.jpg,.jpeg"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) enviarArquivos(e.target.files);
          e.target.value = "";
        }}
      />
      {erro && <p className="mt-2 text-red-600">{erro}</p>}
    </div>
  );
}
