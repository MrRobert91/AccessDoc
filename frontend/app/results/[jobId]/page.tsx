"use client"

import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { LiveActivityPanel } from "@/components/LiveActivityPanel"
import {
  downloadUrl,
  fetchReport,
  type BlockChangeEntry,
  type RemediationReport,
} from "@/lib/api"

type Tab = "summary" | "by-page" | "by-criterion" | "activity"

const TAB_LABEL: Record<Tab, string> = {
  summary: "Resumen",
  "by-page": "Por página",
  "by-criterion": "Por criterio",
  activity: "Log de actividad",
}

export default function ResultsPage() {
  const params = useParams<{ jobId: string }>()
  const jobId = params?.jobId ?? ""
  const [report, setReport] = useState<RemediationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("summary")

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    fetchReport(jobId)
      .then((r) => {
        if (!cancelled) setReport(r)
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
          No pudimos cargar el reporte: {error}
        </div>
      </main>
    )
  }

  if (!report) {
    return (
      <main id="main-content" className="min-h-screen bg-slate-50 px-4 py-16">
        <p className="mx-auto max-w-xl text-center text-slate-600">
          Cargando reporte...
        </p>
      </main>
    )
  }

  const before = report.scores.before?.overall ?? 0
  const after = report.scores.after?.overall ?? 0
  const delta = after - before

  return (
    <main id="main-content" className="min-h-screen bg-slate-50 px-4 py-16">
      <div className="mx-auto max-w-5xl">
        <h1 className="text-3xl font-bold text-slate-900">
          Documento remediado
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Se procesaron {report.page_count} páginas.{" "}
          {report.model_used && <>Modelo: {report.model_used}.</>}{" "}
          {report.processing_time_seconds != null && (
            <>Tiempo: {report.processing_time_seconds.toFixed(1)} s.</>
          )}
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
            href={`/api/v1/jobs/${jobId}/report`}
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
            download={`reporte-${jobId}.json`}
          >
            Descargar reporte (JSON)
          </a>
          <a
            href="/"
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
          >
            Procesar otro documento
          </a>
        </div>

        <div className="mt-10 border-b border-slate-200" role="tablist">
          {(["summary", "by-page", "by-criterion", "activity"] as Tab[]).map(
            (t) => (
              <button
                key={t}
                type="button"
                role="tab"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={`mr-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                  tab === t
                    ? "border-blue-600 text-blue-700"
                    : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
              >
                {TAB_LABEL[t]}
              </button>
            )
          )}
        </div>

        <div className="mt-6">
          {tab === "summary" && <SummaryTab report={report} />}
          {tab === "by-page" && <ByPageTab report={report} />}
          {tab === "by-criterion" && <ByCriterionTab report={report} />}
          {tab === "activity" && (
            <LiveActivityPanel events={report.activity_log} />
          )}
        </div>
      </div>
    </main>
  )
}

function SummaryTab({ report }: { report: RemediationReport }) {
  const summary = report.changes_summary ?? {}
  return (
    <>
      {Object.keys(summary).length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-900">
            Cambios aplicados
          </h2>
          <ul className="mt-3 grid gap-2 text-sm text-slate-700 sm:grid-cols-2">
            {Object.entries(summary).map(([type, count]) => (
              <li
                key={type}
                className="flex justify-between rounded-lg bg-white px-3 py-2 ring-1 ring-slate-200"
              >
                <span>{formatChangeType(type)}</span>
                <span className="font-semibold">{count}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.remaining_issues.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">
            Puntos a revisar manualmente
          </h2>
          <ul className="mt-3 space-y-2">
            {report.remaining_issues.map((issue, idx) => (
              <li
                key={idx}
                className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200"
              >
                <strong className="block font-semibold">
                  {(issue.criterion || "—")} ({issue.severity})
                </strong>
                <p>{issue.description}</p>
                {issue.count != null && (
                  <p className="text-xs text-amber-800">
                    {issue.count} ocurrencia(s)
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

function ByPageTab({ report }: { report: RemediationReport }) {
  const [confFilter, setConfFilter] = useState<"all" | "low">("all")
  const [pageFilter, setPageFilter] = useState<string>("all")
  const [typeFilter, setTypeFilter] = useState<string>("all")

  const pages = useMemo(() => {
    return Object.entries(report.changes_by_page)
      .map(([k, v]) => ({ page: Number(k), changes: v }))
      .sort((a, b) => a.page - b.page)
  }, [report])

  const allTypes = useMemo(() => {
    const set = new Set<string>()
    pages.forEach(({ changes }) => changes.forEach((c) => set.add(c.change_type)))
    return Array.from(set).sort()
  }, [pages])

  if (pages.length === 0) {
    return (
      <p className="text-sm text-slate-500">Sin cambios por página.</p>
    )
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs">
        <label className="flex items-center gap-1">
          <span className="text-slate-600">Confianza:</span>
          <select
            value={confFilter}
            onChange={(e) => setConfFilter(e.target.value as "all" | "low")}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            <option value="all">Todas</option>
            <option value="low">Sólo &lt; 0.7</option>
          </select>
        </label>
        <label className="flex items-center gap-1">
          <span className="text-slate-600">Página:</span>
          <select
            value={pageFilter}
            onChange={(e) => setPageFilter(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            <option value="all">Todas</option>
            {pages.map(({ page }) => (
              <option key={page} value={String(page)}>
                {page}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1">
          <span className="text-slate-600">Tipo:</span>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            <option value="all">Todos</option>
            {allTypes.map((t) => (
              <option key={t} value={t}>
                {formatChangeType(t)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="space-y-3">
        {pages.map(({ page, changes }) => {
          if (pageFilter !== "all" && String(page) !== pageFilter) return null
          const visible = changes.filter((c) => {
            if (confFilter === "low" && (c.confidence ?? 1) >= 0.7) return false
            if (typeFilter !== "all" && c.change_type !== typeFilter) return false
            return true
          })
          if (visible.length === 0) return null
          return (
            <details
              key={page}
              open
              className="rounded-xl bg-white ring-1 ring-slate-200"
            >
              <summary className="cursor-pointer px-4 py-2 text-sm font-semibold text-slate-900">
                Página {page} ({visible.length} cambios)
              </summary>
              <ul className="divide-y divide-slate-100 text-xs">
                {visible.map((c, idx) => (
                  <ChangeRow key={`${c.block_id}-${idx}`} change={c} />
                ))}
              </ul>
            </details>
          )
        })}
      </div>
    </div>
  )
}

function ByCriterionTab({ report }: { report: RemediationReport }) {
  const [levelFilter, setLevelFilter] = useState<"all" | "A" | "AA">("all")
  const criteria = useMemo(() => {
    return Object.entries(report.changes_by_criterion).sort(
      ([a], [b]) => a.localeCompare(b)
    )
  }, [report])

  if (criteria.length === 0) {
    return (
      <p className="text-sm text-slate-500">Sin agrupación por criterio.</p>
    )
  }

  const filtered = criteria.filter(([, list]) => {
    if (levelFilter === "all") return true
    return list.some((c) => c.wcag_level === levelFilter)
  })

  return (
    <div>
      <div className="mb-3 flex items-center gap-2 text-xs">
        <label className="flex items-center gap-1">
          <span className="text-slate-600">Nivel WCAG:</span>
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value as typeof levelFilter)}
            className="rounded-md border border-slate-300 bg-white px-2 py-1"
          >
            <option value="all">Todos</option>
            <option value="A">A</option>
            <option value="AA">AA</option>
          </select>
        </label>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase text-slate-500">
            <th className="py-2">Criterio</th>
            <th className="py-2">Cambios</th>
            <th className="py-2">Regla PDF/UA</th>
            <th className="py-2">Tipos</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {filtered.map(([crit, list]) => (
            <tr key={crit} className="bg-white">
              <td className="px-2 py-2 font-medium text-slate-800">{crit}</td>
              <td className="px-2 py-2">{list.length}</td>
              <td className="px-2 py-2 text-slate-500">
                {uniq(list.map((c) => c.pdfua_rule).filter(Boolean)).join(", ") ||
                  "—"}
              </td>
              <td className="px-2 py-2 text-slate-500">
                {uniq(list.map((c) => c.change_type))
                  .map((t) => formatChangeType(t))
                  .join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChangeRow({ change }: { change: BlockChangeEntry }) {
  const confidence = change.confidence ?? 1
  const lowConfidence = confidence < 0.7
  return (
    <li
      className={`grid grid-cols-[6rem_1fr_1fr] gap-3 px-4 py-2 ${
        lowConfidence ? "bg-amber-50" : ""
      }`}
    >
      <div className="text-slate-600">
        <div className="font-semibold">{change.change_type}</div>
        <div className="text-[10px] text-slate-400">
          {change.criterion ?? "—"} · conf {confidence.toFixed(2)}
        </div>
      </div>
      <div className="text-slate-500 line-through">{change.before ?? "—"}</div>
      <div className="text-slate-800">{change.after ?? "—"}</div>
    </li>
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

function uniq<T>(xs: (T | undefined | null)[]): T[] {
  const seen = new Set<T>()
  const out: T[] = []
  for (const x of xs) {
    if (x == null) continue
    if (seen.has(x)) continue
    seen.add(x)
    out.push(x)
  }
  return out
}
