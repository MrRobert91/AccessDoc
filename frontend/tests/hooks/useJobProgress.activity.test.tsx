import { act, renderHook, waitFor } from "@testing-library/react"
import { useJobProgress } from "@/hooks/useJobProgress"

type Listener = (ev: MessageEvent) => void

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, Listener[]> = {}
  closed = false
  onerror: ((ev: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(name: string, fn: Listener) {
    this.listeners[name] = this.listeners[name] || []
    this.listeners[name].push(fn)
  }

  dispatch(name: string, data: unknown) {
    const ev = { data: JSON.stringify(data) } as MessageEvent
    ;(this.listeners[name] || []).forEach((fn) => fn(ev))
  }

  close() {
    this.closed = true
  }
}

describe("useJobProgress activity stream", () => {
  const originalES = (global as unknown as { EventSource: unknown }).EventSource
  beforeEach(() => {
    MockEventSource.instances = []
    ;(global as unknown as { EventSource: typeof MockEventSource }).EventSource =
      MockEventSource
  })
  afterEach(() => {
    ;(global as unknown as { EventSource: unknown }).EventSource = originalES
  })

  it("appends activity events in order", async () => {
    const { result } = renderHook(() => useJobProgress("job-a"))
    const es = MockEventSource.instances[0]

    act(() => {
      es.dispatch("activity", {
        seq: 0,
        job_id: "job-a",
        phase: "extract",
        code: "upload_received",
        message: "PDF received",
        level: "info",
        page: null,
        duration_ms: null,
        details: null,
        ts: new Date().toISOString(),
      })
      es.dispatch("activity", {
        seq: 1,
        job_id: "job-a",
        phase: "analyze",
        code: "block_classified",
        message: "Block H1",
        level: "info",
        page: 1,
        duration_ms: 120,
        details: null,
        ts: new Date().toISOString(),
      })
    })

    await waitFor(() => expect(result.current.activity.length).toBe(2))
    expect(result.current.activity[0].code).toBe("upload_received")
    expect(result.current.activity[1].code).toBe("block_classified")
    expect(result.current.lastSeq).toBe(1)
  })

  it("deduplicates events by seq number", async () => {
    const { result } = renderHook(() => useJobProgress("job-b"))
    const es = MockEventSource.instances[0]

    const payload = {
      seq: 5,
      job_id: "job-b",
      phase: "write",
      code: "mcid_assigned",
      message: "14 MCIDs",
      level: "info" as const,
      page: 1,
      duration_ms: null,
      details: null,
      ts: new Date().toISOString(),
    }

    act(() => {
      es.dispatch("activity", payload)
      es.dispatch("activity", payload)
    })

    await waitFor(() => expect(result.current.lastSeq).toBe(5))
    expect(result.current.activity.length).toBe(1)
  })

  it("keeps reportUrl on completed", async () => {
    const { result } = renderHook(() => useJobProgress("job-c"))
    const es = MockEventSource.instances[0]

    act(() => {
      es.dispatch("completed", {
        job_id: "job-c",
        result_url: "/api/v1/jobs/job-c/result",
        report_url: "/api/v1/jobs/job-c/report",
      })
    })

    await waitFor(() => expect(result.current.terminal).toBe(true))
    expect(result.current.reportUrl).toBe("/api/v1/jobs/job-c/report")
  })
})
