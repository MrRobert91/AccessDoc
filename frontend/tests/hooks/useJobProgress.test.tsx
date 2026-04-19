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

describe("useJobProgress", () => {
  const originalES = (global as unknown as { EventSource: unknown }).EventSource
  beforeEach(() => {
    MockEventSource.instances = []
    ;(global as unknown as { EventSource: typeof MockEventSource }).EventSource =
      MockEventSource
  })
  afterEach(() => {
    ;(global as unknown as { EventSource: unknown }).EventSource = originalES
  })

  it("starts connecting and subscribes to the SSE url", () => {
    renderHook(() => useJobProgress("job-x"))
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain("job-x")
    expect(MockEventSource.instances[0].url).toContain("/progress")
  })

  it("updates progress on progress events", async () => {
    const { result } = renderHook(() => useJobProgress("job-y"))
    const es = MockEventSource.instances[0]

    act(() => {
      es.dispatch("progress", {
        job_id: "job-y",
        status: "analyzing",
        progress_pct: 40,
        current_step: "Analizando páginas...",
      })
    })

    await waitFor(() => expect(result.current.progressPct).toBe(40))
    expect(result.current.status).toBe("analyzing")
    expect(result.current.currentStep).toContain("Analizando")
    expect(result.current.terminal).toBe(false)
  })

  it("marks terminal+completed when completed event arrives", async () => {
    const { result } = renderHook(() => useJobProgress("job-z"))
    const es = MockEventSource.instances[0]

    act(() => {
      es.dispatch("completed", {
        job_id: "job-z",
        result_url: "/api/v1/jobs/job-z/result",
      })
    })

    await waitFor(() => expect(result.current.terminal).toBe(true))
    expect(result.current.status).toBe("completed")
    expect(result.current.progressPct).toBe(100)
    expect(es.closed).toBe(true)
  })

  it("captures failure and closes the stream", async () => {
    const { result } = renderHook(() => useJobProgress("job-f"))
    const es = MockEventSource.instances[0]

    act(() => {
      es.dispatch("failed", {
        job_id: "job-f",
        error_code: "INTERNAL_ERROR",
        message: "Algo falló",
      })
    })

    await waitFor(() => expect(result.current.status).toBe("failed"))
    expect(result.current.error).toMatch(/Algo falló|INTERNAL_ERROR/)
    expect(es.closed).toBe(true)
    expect(result.current.terminal).toBe(true)
  })
})
