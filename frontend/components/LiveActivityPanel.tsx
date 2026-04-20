"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import type { ActivityEvent } from "@/lib/api"

type Props = {
  events: ActivityEvent[]
  maxVisible?: number
  className?: string
}

type LevelFilter = "all" | "info" | "warn" | "error"
type PhaseFilter = "all" | string

const LEVEL_STYLES: Record<string, string> = {
  info: "text-slate-700",
  warn: "text-amber-700",
  error: "text-red-700",
}

const PHASE_LABELS: Record<string, string> = {
  extract: "Extracción",
  ocr: "OCR",
  analyze: "Análisis",
  tag: "Etiquetado",
  write: "Escritura",
  validate: "Validación",
  retry: "Reintento",
  report: "Reporte",
}

export function LiveActivityPanel({ events, maxVisible = 400, className = "" }: Props) {
  const [levelFilter, setLevelFilter] = useState<LevelFilter>("all")
  const [phaseFilter, setPhaseFilter] = useState<PhaseFilter>("all")
  const [autoscroll, setAutoscroll] = useState(true)
  const listRef = useRef<HTMLUListElement>(null)

  const phases = useMemo(() => {
    const set = new Set<string>()
    events.forEach((e) => set.add(e.phase))
    return Array.from(set).sort()
  }, [events])

  const filtered = useMemo(() => {
    const start = Math.max(0, events.length - maxVisible)
    return events
      .slice(start)
      .filter((e) =>
        (levelFilter === "all" || e.level === levelFilter) &&
        (phaseFilter === "all" || e.phase === phaseFilter)
      )
  }, [events, maxVisible, levelFilter, phaseFilter])

  useEffect(() => {
    if (!autoscroll) return
    const el = listRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [filtered.length, autoscroll])

  return (
    <section
      aria-label="Registro de actividad en vivo"
      className={`rounded-2xl bg-white ring-1 ring-slate-200 ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Actividad en vivo
          </h2>
          <p className="text-xs text-slate-500">
            {events.length} eventos · mostrando {filtered.length}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1">
            <span className="text-slate-600">Nivel:</span>
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value as LevelFilter)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1"
            >
              <option value="all">Todos</option>
              <option value="info">Info</option>
              <option value="warn">Warn</option>
              <option value="error">Error</option>
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-slate-600">Fase:</span>
            <select
              value={phaseFilter}
              onChange={(e) => setPhaseFilter(e.target.value as PhaseFilter)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1"
            >
              <option value="all">Todas</option>
              {phases.map((p) => (
                <option key={p} value={p}>
                  {PHASE_LABELS[p] ?? p}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={autoscroll}
              onChange={(e) => setAutoscroll(e.target.checked)}
              className="h-3 w-3"
            />
            <span className="text-slate-600">Autoscroll</span>
          </label>
        </div>
      </header>
      <ul
        ref={listRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        className="h-72 overflow-y-auto px-4 py-2 font-mono text-xs"
      >
        {filtered.length === 0 ? (
          <li className="py-2 text-center text-slate-400">
            Esperando eventos...
          </li>
        ) : (
          filtered.map((e) => (
            <li
              key={e.seq}
              className={`grid grid-cols-[3.5rem_4.5rem_1fr] gap-2 border-b border-slate-50 py-1 ${LEVEL_STYLES[e.level] ?? ""}`}
            >
              <time className="text-slate-400" dateTime={e.ts}>
                {formatTime(e.ts)}
              </time>
              <span className="font-semibold uppercase">
                {PHASE_LABELS[e.phase] ?? e.phase}
              </span>
              <span>
                {e.page != null && (
                  <span className="mr-1 rounded bg-slate-100 px-1 text-[10px] text-slate-600">
                    p{e.page}
                  </span>
                )}
                {e.message}
                {e.duration_ms != null && (
                  <span className="ml-1 text-slate-400">
                    · {e.duration_ms}ms
                  </span>
                )}
              </span>
            </li>
          ))
        )}
      </ul>
    </section>
  )
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
  } catch {
    return "--:--"
  }
}
