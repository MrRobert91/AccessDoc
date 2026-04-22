export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export type UploadResponse = {
  job_id: string
  status: string
  estimated_seconds: number
  sse_url: string
  activity_url?: string
  report_url?: string
  expires_at: string
}

export type Explanation = {
  title?: string
  what?: string
  why?: string
  impact?: string
  wcag?: string
  pdfua?: string
  user_level?: string
  tags?: string[]
}

export type ActivityEvent = {
  seq: number
  job_id: string
  phase: string
  code: string
  message: string
  level: "info" | "warn" | "error"
  page: number | null
  duration_ms: number | null
  details: (Record<string, unknown> & { explanation?: Explanation }) | null
  ts: string
}

export type RemediationResult = {
  job_id: string
  status: string
  original_filename?: string
  page_count: number
  before_score: { overall: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean }
  after_score: { overall: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean }
  changes_applied?: Array<{ block_id: string; page_num?: number; page?: number; change_type: string; criterion?: string; wcag_reference?: string; before?: string; after?: string; confidence?: number; role?: string; mcid?: number; pdfua_rule?: string }>
  changes_summary?: Record<string, number>
  remaining_issues?: Array<{ rule?: string; criterion?: string; severity: string; description: string; count?: number }>
  download_url: string
  report_url: string
  processed_at?: string
  processing_time_seconds?: number
  model_used?: string
}

export type BlockChangeEntry = {
  block_id: string
  page_num?: number
  change_type: string
  criterion?: string
  before?: string
  after?: string
  confidence?: number
  role?: string
  mcid?: number
  pdfua_rule?: string
  wcag_level?: string
  explanation?: Explanation
}

export type ChangeSummaryRow = {
  change_type: string
  count: number
  title: string
  what?: string
  why?: string
  impact?: string
  wcag?: string
  pdfua?: string
  examples?: Array<{ page?: number | null; before?: string; after?: string }>
}

export type EnrichedIssue = {
  criterion?: string
  criterion_name?: string
  criterion_level?: string
  criterion_plain?: string
  pdfua_plain?: string
  severity: string
  description: string
  count?: number
  hint?: string
}

export type NarrativeStep = {
  number: number
  title: string
  what?: string
  why?: string
  impact?: string
  wcag?: string
  pdfua?: string
  count?: number
  examples?: string[]
}

export type NarrativeSection = {
  heading: string
  paragraphs?: string[]
  items?: Array<string | Record<string, unknown>>
  steps?: NarrativeStep[]
}

export type GlossaryEntry = {
  code?: string
  rule?: string
  name?: string
  level?: string
  plain: string
}

export type Glossary = {
  wcag: GlossaryEntry[]
  pdfua: GlossaryEntry[]
}

export type RemediationReport = {
  job_id: string
  filename?: string
  status: string
  processed_at?: string
  processing_time_seconds?: number
  page_count: number
  model_used?: string
  scores: {
    before?: { overall?: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean; criteria_scores?: Record<string, number> }
    after?: { overall?: number; pdfua1_compliant?: boolean; wcag21_aa_compliant?: boolean; criteria_scores?: Record<string, number> }
  }
  changes_by_page: Record<string, BlockChangeEntry[]>
  changes_by_criterion: Record<string, BlockChangeEntry[]>
  changes_applied?: BlockChangeEntry[]
  changes_summary: Record<string, number>
  changes_summary_detailed: ChangeSummaryRow[]
  remaining_issues: EnrichedIssue[]
  activity_log: ActivityEvent[]
  narrative?: NarrativeSection[]
  glossary?: Glossary
  download_url: string
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

export async function fetchReport(jobId: string): Promise<RemediationReport> {
  const response = await fetch(`${API_BASE}/jobs/${jobId}/report`)
  if (!response.ok) {
    const message = await readError(response)
    throw new Error(message)
  }
  return (await response.json()) as RemediationReport
}

export function downloadUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/download`
}

export function reportJsonUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report.json`
}

export function reportHtmlUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report.html`
}

export function sseUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/progress`
}
