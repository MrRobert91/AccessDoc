import { act, renderHook, waitFor } from "@testing-library/react"
import { useFileUpload } from "@/hooks/useFileUpload"

describe("useFileUpload", () => {
  const originalFetch = global.fetch
  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  it("starts idle", () => {
    const { result } = renderHook(() => useFileUpload())
    expect(result.current.state).toBe("idle")
    expect(result.current.jobId).toBeNull()
    expect(result.current.error).toBeNull()
  })

  it("transitions to success and exposes job_id on 202", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({
        job_id: "job-1",
        sse_url: "/api/v1/jobs/job-1/progress",
        status: "pending",
      }),
    } as Response) as unknown as typeof fetch

    const { result } = renderHook(() => useFileUpload())
    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "a.pdf", {
      type: "application/pdf",
    })

    await act(async () => {
      await result.current.upload(file)
    })

    await waitFor(() => {
      expect(result.current.state).toBe("success")
    })
    expect(result.current.jobId).toBe("job-1")
    expect(result.current.error).toBeNull()
  })

  it("exposes the error message on failure", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: {
          error_code: "FILE_TOO_LARGE",
          message: "Archivo demasiado grande",
        },
      }),
    } as Response) as unknown as typeof fetch

    const { result } = renderHook(() => useFileUpload())
    const file = new File(["x"], "x.pdf", { type: "application/pdf" })
    await act(async () => {
      await result.current.upload(file).catch(() => {})
    })

    await waitFor(() => expect(result.current.state).toBe("error"))
    expect(result.current.error).toMatch(/FILE_TOO_LARGE|demasiado grande/)
  })
})
