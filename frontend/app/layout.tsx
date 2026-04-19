import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "AccessDoc — PDF Accessibility Remediation",
  description: "Convierte cualquier PDF en un documento accesible para lectores de pantalla. Conforme a PDF/UA-1 y WCAG 2.1 AA.",
  keywords: ["accesibilidad", "PDF", "WCAG", "lectores de pantalla", "discapacidad visual"],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es">
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 bg-blue-600 text-white px-4 py-2 rounded z-50"
        >
          Saltar al contenido principal
        </a>
        {children}
      </body>
    </html>
  )
}
