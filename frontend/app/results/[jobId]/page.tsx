"use client"

import { useParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { LiveActivityPanel } from "@/components/LiveActivityPanel"
import {
  downloadUrl,
  fetchReport,
  reportHtmlUrl,
  reportJsonUrl,
  type BlockChangeEntry,
  type ChangeSummaryRow,
  type EnrichedIssue,
  type NarrativeSection,
  type NarrativeStep,
  type RemediationReport,
} from "@/lib/api"

type Tab = "narrative" | "summary" | "by-page" | "by-criterion" | "glossary" | "activity"

const TAB_LABEL: Record<Tab, string> = {
  narrative: "Qué hicimos y por qué",
  summary: "Resumen de cambios",
  "by-page": "Por página",
  "by-criterion": "Por criterio",
  glossary: "Glosario",
  activity: "Log de actividad",
}

export default function ResultsPage() {
  const params = useParams<{ jobId: string }>()
  const jobId = params?.jobId ?? ""
  const [report, setReport] = useState<RemediationReport | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("narrative")

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
            href={reportJsonUrl(jobId)}
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
            download
          >
            Descargar reporte (JSON)
          </a>
          <a
            href={reportHtmlUrl(jobId)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
          >
            Ver reporte (HTML)
          </a>
          <a
            href="/"
            className="inline-flex items-center rounded-lg bg-white px-4 py-2 text-sm font-semibold text-slate-700 ring-1 ring-slate-300 hover:bg-slate-100"
          >
            Procesar otro documento
          </a>
        </div>

        <div className="mt-10 flex flex-wrap border-b border-slate-200" role="tablist">
          {(["narrative", "summary", "by-page", "by-criterion", "glossary", "activity"] as Tab[]).map(
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
          {tab === "narrative" && <NarrativeTab report={report} />}
          {tab === "summary" && <SummaryTab report={report} />}
          {tab === "by-page" && <ByPageTab report={report} />}
          {tab === "by-criterion" && <ByCriterionTab report={report} />}
          {tab === "glossary" && <GlossaryTab report={report} />}
          {tab === "activity" && (
            <LiveActivityPanel events={report.activity_log} />
          )}
        </div>
      </div>
    </main>
  )
}

function NarrativeTab({ report }: { report: RemediationReport }) {
  const sections = report.narrative ?? []
  if (sections.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No hay narrativa disponible para este documento.
      </p>
    )
  }
  return (
    <div className="space-y-8">
      {sections.map((s, i) => (
        <NarrativeBlock key={i} section={s} />
      ))}
    </div>
  )
}

function NarrativeBlock({ section }: { section: NarrativeSection }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-slate-900">{section.heading}</h2>
      <div className="mt-2 space-y-2 text-sm text-slate-700">
        {section.paragraphs?.map((p, i) => (
          <p key={i}>{p}</p>
        ))}
      </div>

      {section.items && section.items.length > 0 && (
        <ul className="mt-3 space-y-2 text-sm">
          {section.items.map((item, i) => (
            <NarrativeItem key={i} item={item} />
          ))}
        </ul>
      )}

      {section.steps && section.steps.length > 0 && (
        <ol className="mt-4 space-y-3">
          {section.steps.map((step) => (
            <StepCard key={step.number} step={step} />
          ))}
        </ol>
      )}
    </section>
  )
}

function NarrativeItem({ item }: { item: string | Record<string, unknown> }) {
  if (typeof item === "string") {
    return <li className="text-slate-700">{item}</li>
  }
  const obj = item as Partial<EnrichedIssue>
  return (
    <li className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="text-amber-900">
          {obj.criterion_name
            ? `${obj.criterion} · ${obj.criterion_name}`
            : obj.criterion ?? "—"}
        </strong>
        {obj.criterion_level && (
          <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
            WCAG {obj.criterion_level}
          </span>
        )}
        {obj.severity && (
          <span className="text-xs text-amber-800">{obj.severity}</span>
        )}
        {obj.count != null && (
          <span className="text-xs text-amber-800">· {obj.count} ocurrencia(s)</span>
        )}
      </div>
      <p className="mt-1 text-sm text-amber-900">{obj.description}</p>
      {obj.hint && (
        <div className="mt-2 rounded bg-white/60 p-2 text-xs text-amber-900">
          <strong>Cómo revisar: </strong>{obj.hint}
        </div>
      )}
    </li>
  )
}

function StepCard({ step }: { step: NarrativeStep }) {
  return (
    <li className="rounded-xl border-l-4 border-blue-500 bg-white p-4 ring-1 ring-slate-200">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-900">
          {step.number}. {step.title}
        </span>
        {step.wcag && (
          <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800">
            WCAG {step.wcag}
          </span>
        )}
        {step.pdfua && (
          <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-semibold text-purple-800">
            PDF/UA §{step.pdfua}
          </span>
        )}
      </div>
      {step.what && (
        <p className="mt-2 text-sm text-slate-700">
          <strong className="text-slate-500">Qué hicimos: </strong>{step.what}
        </p>
      )}
      {step.why && (
        <p className="mt-1 text-sm text-slate-700">
          <strong className="text-slate-500">Por qué: </strong>{step.why}
        </p>
      )}
      {step.impact && (
        <p className="mt-1 text-sm text-slate-700">
          <strong className="text-slate-500">Impacto: </strong>{step.impact}
        </p>
      )}
      {step.examples && step.examples.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-slate-600">
          {step.examples.map((ex, i) => (
            <li key={i}>{ex}</li>
          ))}
        </ul>
      )}
    </li>
  )
}

function SummaryTab({ report }: { report: RemediationReport }) {
  const rows: ChangeSummaryRow[] = useMemo(() => {
    return report.changes_summary_detailed ?? []
  }, [report])

  return (
    <div className="space-y-4">
      {rows.length === 0 ? (
        <p className="text-sm text-slate-500">Sin cambios registrados.</p>
      ) : (
        rows.map((row) => <SummaryRow key={row.change_type} row={row} />)
      )}

      {report.remaining_issues.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold text-slate-900">
            Puntos a revisar manualmente
          </h2>
          <ul className="mt-3 space-y-2">
            {report.remaining_issues.map((issue, idx) => (
              <IssueCard key={idx} issue={issue} />
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function SummaryRow({ row }: { row: ChangeSummaryRow }) {
  return (
    <details className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
      <summary className="cursor-pointer text-sm">
        <span className="font-semibold text-slate-900">{row.title}</span>
        <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
          ×{row.count}
        </span>
        {row.wcag && (
          <span className="ml-2 rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800">
            WCAG {row.wcag}
          </span>
        )}
        {row.pdfua && (
          <span className="ml-1 rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-semibold text-purple-800">
            PDF/UA §{row.pdfua}
          </span>
        )}
      </summary>
      <div className="mt-3 space-y-1 text-sm text-slate-700">
        {row.what && (
          <p><strong className="text-slate-500">Qué: </strong>{row.what}</p>
        )}
        {row.why && (
          <p><strong className="text-slate-500">Por qué: </strong>{row.why}</p>
        )}
        {row.impact && (
          <p><strong className="text-slate-500">Impacto: </strong>{row.impact}</p>
        )}
      </div>
      {row.examples && row.examples.length > 0 && (
        <div className="mt-3">
          <strong className="text-xs uppercase tracking-wide text-slate-500">
            Ejemplos
          </strong>
          <ul className="mt-1 space-y-1 text-xs text-slate-600">
            {row.examples.map((ex, i) => (
              <li key={i}>
                {ex.page != null && <>pág. {ex.page} — </>}
                <span className="text-slate-400 line-through">{ex.before ?? "—"}</span>
                {" → "}
                <span className="text-slate-800">{ex.after ?? "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </details>
  )
}

function IssueCard({ issue }: { issue: EnrichedIssue }) {
  return (
    <li className="rounded-lg bg-amber-50 p-3 ring-1 ring-amber-200">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="text-amber-900">
          {issue.criterion_name
            ? `${issue.criterion} · ${issue.criterion_name}`
            : issue.criterion ?? "—"}
        </strong>
        {issue.criterion_level && (
          <span className="rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
            WCAG {issue.criterion_level}
          </span>
        )}
        <span className="text-xs text-amber-800">({issue.severity})</span>
      </div>
      <p className="mt-1 text-sm text-amber-900">{issue.description}</p>
      {issue.count != null && (
        <p className="text-xs text-amber-800">{issue.count} ocurrencia(s)</p>
      )}
      {issue.criterion_plain && (
        <p className="mt-2 text-xs text-amber-900">
          <strong>Qué significa: </strong>{issue.criterion_plain}
        </p>
      )}
      {issue.pdfua_plain && (
        <p className="mt-1 text-xs text-amber-900">
          <strong>Regla PDF/UA: </strong>{issue.pdfua_plain}
        </p>
      )}
      {issue.hint && (
        <div className="mt-2 rounded bg-white/60 p-2 text-xs text-amber-900">
          <strong>Cómo revisarlo: </strong>{issue.hint}
        </div>
      )}
    </li>
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
              <ul className="divide-y divide-slate-100">
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

function GlossaryTab({ report }: { report: RemediationReport }) {
  const g = report.glossary
  if (!g || (g.wcag.length === 0 && g.pdfua.length === 0)) {
    return (
      <p className="text-sm text-slate-500">
        No se usaron criterios o reglas en este documento.
      </p>
    )
  }
  return (
    <div className="space-y-8">
      {g.wcag.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-900">
            Criterios WCAG mencionados
          </h2>
          <ul className="mt-3 space-y-3">
            {g.wcag.map((c) => (
              <li key={c.code} className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="text-slate-900">{c.code} · {c.name}</strong>
                  {c.level && (
                    <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800">
                      Nivel {c.level}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-slate-700">{c.plain}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
      {g.pdfua.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-slate-900">
            Reglas PDF/UA-1 mencionadas
          </h2>
          <ul className="mt-3 space-y-3">
            {g.pdfua.map((r) => (
              <li key={r.rule} className="rounded-xl bg-white p-4 ring-1 ring-slate-200">
                <strong className="text-slate-900">§{r.rule}</strong>
                <p className="mt-2 text-sm text-slate-700">{r.plain}</p>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function ChangeRow({ change }: { change: BlockChangeEntry }) {
  const confidence = change.confidence ?? 1
  const lowConfidence = confidence < 0.7
  const exp = change.explanation
  return (
    <li
      className={`px-4 py-3 ${lowConfidence ? "bg-amber-50" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-slate-800">
          {exp?.title ?? formatChangeType(change.change_type)}
        </span>
        {change.criterion && (
          <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-800">
            WCAG {change.criterion}
          </span>
        )}
        {change.pdfua_rule && (
          <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-semibold text-purple-800">
            PDF/UA §{change.pdfua_rule}
          </span>
        )}
        <span className="text-[10px] text-slate-400">
          conf {confidence.toFixed(2)}
        </span>
      </div>
      <div className="mt-1 text-xs">
        <span className="text-slate-400 line-through">{change.before ?? "—"}</span>
        {" → "}
        <span className="text-slate-800">{change.after ?? "—"}</span>
      </div>
      {exp?.why && (
        <p className="mt-1 text-xs text-slate-600">
          <strong className="text-slate-500">Por qué: </strong>{exp.why}
        </p>
      )}
      {exp?.impact && (
        <p className="mt-0.5 text-xs text-slate-600">
          <strong className="text-slate-500">Impacto: </strong>{exp.impact}
        </p>
      )}
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
