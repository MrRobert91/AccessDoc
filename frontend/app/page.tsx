"use client"

import { useRouter } from "next/navigation"
import { useCallback } from "react"
import { DropZone } from "@/components/DropZone"
import { useFileUpload } from "@/hooks/useFileUpload"

export default function HomePage() {
  const router = useRouter()
  const { state, error, upload } = useFileUpload()

  const handleFile = useCallback(
    async (file: File) => {
      try {
        const response = await upload(file)
        router.push(`/processing/${response.job_id}`)
      } catch {
        // error state is surfaced below
      }
    },
    [router, upload]
  )

  return (
    <main
      id="main-content"
      className="min-h-screen bg-slate-50 px-4 py-16"
    >
      <div className="mx-auto max-w-2xl">
        <header className="mb-10 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900">
            AccessDoc
          </h1>
          <p className="mt-3 text-lg text-slate-600">
            Convierte cualquier PDF en un documento accesible conforme a{" "}
            <span className="font-semibold">PDF/UA-1</span> y{" "}
            <span className="font-semibold">WCAG 2.1 AA</span>.
          </p>
        </header>

        <DropZone
          onFileSelected={handleFile}
          disabled={state === "uploading"}
        />

        {state === "uploading" && (
          <p
            role="status"
            aria-live="polite"
            className="mt-4 text-center text-sm text-slate-600"
          >
            Subiendo tu archivo...
          </p>
        )}

        {state === "error" && error && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-red-50 p-3 text-center text-sm font-medium text-red-700"
          >
            {error}
          </p>
        )}

        <section className="mt-12 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Qué hacemos
          </h2>
          <ul className="mt-3 grid gap-2 text-sm text-slate-700">
            <li>• Etiquetado automático de estructura (encabezados, listas, tablas).</li>
            <li>• Generación de texto alternativo para imágenes significativas.</li>
            <li>• Orden de lectura lógico y metadatos accesibles.</li>
            <li>• Validación con veraPDF y puntuación antes/después.</li>
          </ul>
        </section>
      </div>
    </main>
  )
}
