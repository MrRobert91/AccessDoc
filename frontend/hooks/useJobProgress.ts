"use client"

import { useEffect, useRef, useState } from "react"
import { sseUrl } from "@/lib/api"

export type ProgressState = {
  status: string
  progressPct: number
  currentStep: string
  pagesProcessed: number | null
  pagesTotal: number | null
  terminal: boolean
  error: string | null
  resultUrl: string | null
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
}

type ProgressEvent = {
  status?: string
  progress_pct?: number
  current_step?: string
  pages_processed?: number | null
  pages_total?: number | null
}

type CompletedEvent = { result_url?: string }
type FailedEvent = { error_code?: string; message?: string }

export function useJobProgress(jobId: string | null) {
  const [state, setState] = useState<ProgressState>(INITIAL)
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!jobId) return
    const source = new EventSource(sseUrl(jobId))
    sourceRef.current = source

    source.addEventListener("progress", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as ProgressEvent
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

    source.addEventListener("completed", (event) => {
      const data = JSON.parse((event as MessageEvent).data) as CompletedEvent
      setState((prev) => ({
        ...prev,
        status: "completed",
        progressPct: 100,
        currentStep: "Completado",
        terminal: true,
        resultUrl: data.result_url ?? null,
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
