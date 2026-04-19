import { API_BASE, uploadPdf, fetchResult } from "@/lib/api"

describe("api client", () => {
  const originalFetch = global.fetch

  afterEach(() => {
    global.fetch = originalFetch
    jest.restoreAllMocks()
  })

  it("exposes an API_BASE env-driven constant", () => {
    expect(typeof API_BASE).toBe("string")
    expect(API_BASE.length).toBeGreaterThan(0)
  })

  it("POSTs the file as multipart form-data to /api/v1/jobs", async () => {
    const mock = jest.fn().mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({
        job_id: "abc",
        sse_url: "/api/v1/jobs/abc/progress",
        status: "pending",
        estimated_seconds: 42,
        expires_at: "2030-01-01T00:00:00Z",
      }),
    } as Response)
    global.fetch = mock as unknown as typeof fetch

    const file = new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], "x.pdf", {
      type: "application/pdf",
    })
    const response = await uploadPdf(file)

    expect(mock).toHaveBeenCalledTimes(1)
    const [url, init] = mock.mock.calls[0]
    expect(String(url)).toContain("/api/v1/jobs")
    expect((init as RequestInit).method).toBe("POST")
    expect((init as RequestInit).body).toBeInstanceOf(FormData)
    expect(response.job_id).toBe("abc")
  })

  it("throws a readable error when upload fails", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        detail: {
          error_code: "INVALID_FILE_TYPE",
          message: "Solo PDF",
        },
      }),
    } as Response) as unknown as typeof fetch

    const file = new File(["x"], "x.txt", { type: "text/plain" })
    await expect(uploadPdf(file)).rejects.toThrow(/INVALID_FILE_TYPE|Solo PDF/)
  })

  it("fetchResult hits /api/v1/jobs/{id}/result and returns JSON", async () => {
    const payload = {
      job_id: "abc",
      status: "completed",
      after_score: { overall: 88 },
      download_url: "/api/v1/jobs/abc/download",
    }
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => payload,
    } as Response) as unknown as typeof fetch

    const res = await fetchResult("abc")
    expect(res.job_id).toBe("abc")
    expect(res.after_score.overall).toBe(88)
  })
})
