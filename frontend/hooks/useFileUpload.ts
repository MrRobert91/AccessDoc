"use client"

import { useCallback, useState } from "react"
import { uploadPdf, type UploadResponse } from "@/lib/api"

export type UploadState = "idle" | "uploading" | "success" | "error"

export function useFileUpload() {
  const [state, setState] = useState<UploadState>("idle")
  const [jobId, setJobId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<UploadResponse | null>(null)

  const upload = useCallback(
    async (file: File, options: Record<string, unknown> = {}) => {
      setState("uploading")
      setError(null)
      try {
        const data = await uploadPdf(file, options)
        setResponse(data)
        setJobId(data.job_id)
        setState("success")
        return data
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        setError(message)
        setState("error")
        throw err
      }
    },
    []
  )

  const reset = useCallback(() => {
    setState("idle")
    setJobId(null)
    setError(null)
    setResponse(null)
  }, [])

  return { state, jobId, error, response, upload, reset }
}
