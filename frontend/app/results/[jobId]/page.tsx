"use client"

import { useParams } from "next/navigation"
import { useEffect, useState } from "react"
import { downloadUrl, fetchResult, type RemediationResult } from "@/lib/api"

export default function ResultsPage() {
  const params = useParams<{ jobId: string }>()
  const jobId = params?.jobId ?? ""
  const [result, setResult] = useState<RemediationResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    fetchResult(jobId)
      .then((r) => {
        if (!cancelled) setResult(r)
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err))
        }
      })
    return () => {
      cancelled = true
    }
  }, [jobId])

  if (error) {
    return (
      <main id="main-content" className="min-h-screen bg-slate-50 px-4 py-16">
        <div
          role="alert"
          className="mx-auto max-w-xl rounded-xl bg-red-50 p-4 text-sm text-red-700"
        >
          No pudimos cargar los resultados: {error}
        </div>
      </main>
    )
  }

  if (!result) {
    return (
      <main id="main-content" className="min-h-screen bg-slate-50 px-4 py-16">
        <p className="mx-auto max-w-xl text-center text-slate-600">
          Cargando resultados...
        </p>
      </main>
    )
  }

  const before = result.before_score?.overall ?? 0
  const after = result.after_score?.overall ?? 0
  const delta = after - before

  return (
    <main id="main-content" className="min-h-screen bg-slate-50 px-4 py-16">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-3xl font-bold text-slate-900">
          Documento remediado
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Se procesaron {result.page_count} páginas.{" "}
          {result.model_used && <>Modelo: {result.model_used}.</>}
        </p>

        <section className="mt-8 grid gap-4 sm:grid-cols-3">
          <ScoreCard label="Antes" score={before} tone="slate" />
          <ScoreCard label="Después" score={after} tone="emerald" highlight />
          <ScoreCard label="Mejora" score={delta} tone="blue" isDelta />
        </section>

        <div className="mt-8 flex flex-wrap gap-3">
          <a
            href={downloadUrl(jobId)}
            className="inline-flex items-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            download
          >
            Descargar PDF accesible
          </a>
          <a
            href="/"
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
          >
            Procesar otro documento
          </a>
        </div>

        {result.changes_summary && (
          <section className="mt-10">
            <h2 className="text-lg font-semibold text-slate-900">
              Cambios aplicados
            </h2>
            <ul className="mt-3 grid gap-2 text-sm text-slate-700">
              {Object.entries(result.changes_summary).map(([type, count]) => (
                <li key={type} className="flex justify-between rounded-lg bg-white px-3 py-2 ring-1 ring-slate-200">
                  <span>{formatChangeType(type)}</span>
                  <span className="font-semibold">{count}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {result.remaining_issues && result.remaining_issues.length > 0 && (
          <section className="mt-10">
            <h2 className="text-lg font-semibold text-slate-900">
              Puntos a revisar manualmente
            </h2>
            <ul className="mt-3 space-y-2">
              {result.remaining_issues.map((issue, idx) => (
                <li
                  key={idx}
                  className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200"
                >
                  <strong className="block font-semibold">
                    {issue.rule} ({issue.severity})
                  </strong>
                  <p>{issue.description}</p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </main>
  )
}

function ScoreCard({
  label,
  score,
  tone,
  highlight = false,
  isDelta = false,
}: {
  label: string
  score: number
  tone: "slate" | "emerald" | "blue"
  highlight?: boolean
  isDelta?: boolean
}) {
  const toneClass = {
    slate: "bg-slate-100 text-slate-900",
    emerald: "bg-emerald-100 text-emerald-900",
    blue: "bg-blue-100 text-blue-900",
  }[tone]

  return (
    <div
      className={`rounded-2xl p-5 ring-1 ring-slate-200 ${
        highlight ? "ring-emerald-400" : ""
      } ${toneClass}`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide">{label}</p>
      <p className="mt-2 text-4xl font-bold">
        {isDelta && score > 0 ? "+" : ""}
        {score}
      </p>
      <p className="text-xs opacity-70">de 100</p>
    </div>
  )
}

function formatChangeType(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}
