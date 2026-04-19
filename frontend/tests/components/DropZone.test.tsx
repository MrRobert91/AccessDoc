import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { DropZone } from "@/components/DropZone"

function makePdf(name = "sample.pdf", size = 1024) {
  const bytes = new Uint8Array(size)
  bytes.set([0x25, 0x50, 0x44, 0x46])
  return new File([bytes], name, { type: "application/pdf" })
}

describe("<DropZone />", () => {
  it("renders accessible instructions", () => {
    render(<DropZone onFileSelected={() => {}} />)
    expect(screen.getAllByText(/PDF/i).length).toBeGreaterThan(0)
  })

  it("has an accessible label on the file input", () => {
    render(<DropZone onFileSelected={() => {}} />)
    const input = screen.getByLabelText(/PDF|archivo/i)
    expect(input).toBeInstanceOf(HTMLInputElement)
    expect((input as HTMLInputElement).type).toBe("file")
    expect((input as HTMLInputElement).accept).toMatch(/pdf/)
  })

  it("invokes onFileSelected with the chosen PDF", async () => {
    const onFileSelected = jest.fn()
    render(<DropZone onFileSelected={onFileSelected} />)
    const input = screen.getByLabelText(/PDF|archivo/i) as HTMLInputElement
    await userEvent.upload(input, makePdf())
    expect(onFileSelected).toHaveBeenCalledTimes(1)
    expect(onFileSelected.mock.calls[0][0]).toBeInstanceOf(File)
  })

  it("rejects non-PDF files with an accessible error message", async () => {
    const onFileSelected = jest.fn()
    render(<DropZone onFileSelected={onFileSelected} />)
    const input = screen.getByLabelText(/PDF|archivo/i) as HTMLInputElement
    const bad = new File(["hi"], "hi.txt", { type: "text/plain" })
    await userEvent.upload(input, bad, { applyAccept: false })
    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByRole("alert").textContent).toMatch(/PDF/i)
  })

  it("rejects files larger than the max size", async () => {
    const onFileSelected = jest.fn()
    render(<DropZone onFileSelected={onFileSelected} maxSizeMB={0.0005} />)
    const input = screen.getByLabelText(/PDF|archivo/i) as HTMLInputElement
    await userEvent.upload(input, makePdf("big.pdf", 2048))
    expect(onFileSelected).not.toHaveBeenCalled()
    expect(screen.getByRole("alert").textContent).toMatch(/tamaño|size|MB/i)
  })
})
