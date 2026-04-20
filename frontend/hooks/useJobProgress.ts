"use client"

import { useEffect, useRef, useState } from "react"
import { sseUrl, type ActivityEvent } from "@/lib/api"

export type ProgressState = {
  status: string
  progressPct: number
  currentStep: string
  pagesProcessed: number | null
  pagesTotal: number | null
  terminal: boolean
  error: string | null
  resultUrl: string | null
  reportUrl: string | null
  activity: ActivityEvent[]
  lastSeq: number
}

const INITIAL: ProgressState = {
  status: "connecting",
  progressPct: 0,
  currentStep: "Conectando al servidor...",
  pagesProcessed: null,
  pagesTotal: null,
  terminal: false,
  error: null,
  resultUrl: null,
  reportUrl: null,
  activity: [],
  lastSeq: -1,
}

const MAX_BUFFER = 2000

type ProgressEventData = {
  status?: string
  progress_pct?: number
  current_step?: string
  pages_processed?: number | null
  pages_total?: number | null
}

type CompletedEvent = { result_url?: string; report_url?: string }
type FailedEvent = { error_code?: string; message?: string }

export function useJobProgress(jobId: string | null) {
  const [state, setState] = useState<ProgressState>(INITIAL)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return
    const source = new EventSource(sseUrl(jobId))
    sourceRef.current = source

    source.addEventListener("progress", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as ProgressEventData
      setState((prev) => ({
        ...prev,
        status: data.status ?? prev.status,
        progressPct:
          typeof data.progress_pct === "number"
            ? data.progress_pct
            : prev.progressPct,
        currentStep: data.current_step ?? prev.currentStep,
        pagesProcessed:
          data.pages_processed ?? prev.pagesProcessed ?? null,
        pagesTotal: data.pages_total ?? prev.pagesTotal ?? null,
      }))
    })

    source.addEventListener("activity", (event) => {
      const msg = event as MessageEvent
      try {
        const data = JSON.parse(msg.data) as ActivityEvent
        setState((prev) => {
          if (data.seq <= prev.lastSeq) return prev
          const nextBuf = prev.activity.length >= MAX_BUFFER
            ? [...prev.activity.slice(prev.activity.length - MAX_BUFFER + 1), data]
            : [...prev.activity, data]
          return { ...prev, activity: nextBuf, lastSeq: data.seq }
        })
      } catch {
        // ignore malformed event
      }
    })

    source.addEventListener("completed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as CompletedEvent
      setState((prev) => ({
        ...prev,
        status: "completed",
        progressPct: 100,
        currentStep: "Completado",
        terminal: true,
        resultUrl: data.result_url ?? null,
        reportUrl: data.report_url ?? null,
      }))
      source.close()
    })

    source.addEventListener("failed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as FailedEvent
      setState((prev) => ({
        ...prev,
        status: "failed",
        currentStep: data.message ?? "El proceso ha fallado",
        terminal: true,
        error: data.message ?? data.error_code ?? "Error desconocido",
      }))
      source.close()
    })

    source.onerror = () => {
      setState((prev) =>
        prev.terminal
          ? prev
          : { ...prev, error: "Conexión perdida con el servidor" }
      )
    }

    return () => {
      source.close()
      sourceRef.current = null
    }
  }, [jobId])

  return state
}
