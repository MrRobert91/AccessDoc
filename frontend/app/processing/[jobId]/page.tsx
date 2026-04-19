"use client"

import { useParams, useRouter } from "next/navigation"
import { useEffect } from "react"
import { useJobProgress } from "@/hooks/useJobProgress"

export default function ProcessingPage() {
  const router = useRouter()
  const params = useParams<{ jobId: string }>()
  const jobId = params?.jobId ?? null
  const progress = useJobProgress(jobId)

  useEffect(() => {
    if (progress.status === "completed" && jobId) {
      router.push(`/results/${jobId}`)
    }
  }, [progress.status, jobId, router])

  return (
    <main
      id="main-content"
      className="min-h-screen bg-slate-50 px-4 py-16"
    >
      <div className="mx-auto max-w-xl">
        <h1 className="text-2xl font-bold text-slate-900">
          Procesando tu documento
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Este proceso puede tardar entre 30 segundos y unos minutos según el
          tamaño del archivo.
        </p>

        <div className="mt-8 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div
            className="h-3 w-full overflow-hidden rounded-full bg-slate-200"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progress.progressPct}
            aria-label="Progreso de la remediación"
          >
            <div
              className="h-full bg-blue-600 transition-all duration-500"
              style={{ width: `${progress.progressPct}%` }}
            />
          </div>

          <p
            className="mt-3 text-sm font-medium text-slate-700"
            aria-live="polite"
          >
            {progress.progressPct}% — {progress.currentStep}
          </p>

          {progress.pagesTotal != null && progress.pagesProcessed != null && (
            <p className="mt-1 text-xs text-slate-500">
              Páginas procesadas: {progress.pagesProcessed} / {progress.pagesTotal}
            </p>
          )}
        </div>

        {progress.status === "failed" && (
          <div
            role="alert"
            className="mt-6 rounded-xl bg-red-50 p-4 text-sm text-red-700"
          >
            <strong className="block font-semibold">
              No se pudo procesar el PDF
            </strong>
            <p className="mt-1">{progress.error ?? "Error desconocido"}</p>
            <button
              type="button"
              onClick={() => router.push("/")}
              className="mt-3 inline-flex items-center rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
            >
              Volver a empezar
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
