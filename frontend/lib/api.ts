export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export type UploadResponse = {
  job_id: string
  status: string
  estimated_seconds: number
  sse_url: string
  expires_at: string
}

export type RemediationResult = {
  job_id: string
  status: string
  original_filename?: string
  page_count: number
  before_score: { overall: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean }
  after_score: { overall: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean }
  changes_applied?: Array<{ block_id: string; page: number; change_type: string; wcag_reference?: string }>
  changes_summary?: Record<string, number>
  remaining_issues?: Array<{ rule: string; severity: string; description: string }>
  download_url: string
  report_url: string
  processed_at?: string
  processing_time_seconds?: number
  model_used?: string
}

type ApiErrorDetail = {
  detail?: {
    error_code?: string
    message?: string
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as ApiErrorDetail
    const detail = body?.detail
    if (detail?.message) return detail.message
    if (detail?.error_code) return detail.error_code
  } catch {
    // fall through
  }
  return `Request failed with status ${response.status}`
}

export async function uploadPdf(
  file: File,
  options: Record<string, unknown> = {}
): Promise<UploadResponse> {
  const form = new FormData()
  form.append("file", file, file.name)
  form.append("options", JSON.stringify(options))

  const response = await fetch(`${API_BASE}/jobs`, {
    method: "POST",
    body: form,
  })

  if (!response.ok) {
    const message = await readError(response)
    throw new Error(message)
  }

  return (await response.json()) as UploadResponse
}

export async function fetchResult(jobId: string): Promise<RemediationResult> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/result`)
  if (!response.ok) {
    const message = await readError(response)
    throw new Error(message)
  }
  return (await response.json()) as RemediationResult
}

export function downloadUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/download`
}

export function sseUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/progress`
}
