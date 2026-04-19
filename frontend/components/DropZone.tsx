"use client"

import { useCallback, useId, useRef, useState } from "react"

type Props = {
  onFileSelected: (file: File) => void
  maxSizeMB?: number
  disabled?: boolean
}

export function DropZone({ onFileSelected, maxSizeMB = 20, disabled = false }: Props) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const validate = useCallback(
    (file: File): string | null => {
      const isPdfName = file.name.toLowerCase().endsWith(".pdf")
      const isPdfType = file.type === "application/pdf" || file.type === ""
      if (!isPdfName || !isPdfType) {
        return "Solo se aceptan archivos PDF."
      }
      const maxBytes = maxSizeMB * 1024 * 1024
      if (file.size > maxBytes) {
        return `El archivo supera el tamaño máximo de ${maxSizeMB}MB.`
      }
      return null
    },
    [maxSizeMB]
  )

  const handleFile = useCallback(
    (file: File | undefined | null) => {
      if (!file) return
      const err = validate(file)
      if (err) {
        setError(err)
        return
      }
      setError(null)
      onFileSelected(file)
    },
    [onFileSelected, validate]
  )

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        if (disabled) return
        handleFile(e.dataTransfer.files?.[0])
      }}
      className={[
        "rounded-2xl border-2 border-dashed p-8 text-center transition-colors",
        dragging ? "border-blue-500 bg-blue-50" : "border-slate-300 bg-white",
        disabled ? "opacity-60 pointer-events-none" : "",
      ].join(" ")}
    >
      <p className="text-lg font-medium text-slate-900">
        Arrastra tu PDF aquí o selecciónalo desde tu equipo
      </p>
      <p className="mt-1 text-sm text-slate-500">
        Tamaño máximo {maxSizeMB}MB. Nada se almacena de forma permanente.
      </p>

      <label
        htmlFor={inputId}
        className="mt-4 inline-flex cursor-pointer items-center rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2"
      >
        Seleccionar archivo PDF
      </label>
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        aria-label="Archivo PDF a remediar"
        className="sr-only"
        onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
        disabled={disabled}
      />

      {error && (
        <p role="alert" className="mt-4 text-sm font-medium text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
