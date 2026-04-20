# Spec-Driven Design: Accesibilidad real + Live Activity + Reporte detallado

Versión: 1.0 · Estado: Propuesto · Fuente: [ACCESSIBILITY.md](ACCESSIBILITY.md)

Este documento es el **diseño dirigido por especificación** para cerrar los gaps de accesibilidad identificados en [ACCESSIBILITY.md](ACCESSIBILITY.md) **e incorporar dos capacidades transversales nuevas**:

1. **Live Activity Stream** — la aplicación narra en pantalla, con granularidad fina, cada cosa que está haciendo mientras la hace.
2. **Reporte final pormenorizado** — al completarse, el usuario puede inspeccionar un resumen exhaustivo (por página, por criterio, con antes/después).

---

## 0. TL;DR

Implementar, en 4 fases, los 10 puntos del roadmap de [ACCESSIBILITY.md §3](ACCESSIBILITY.md) priorizando lo que desbloquea lectores de pantalla reales (MCID + Artifacts), y al mismo tiempo reescribir la capa de observabilidad para que **cada acción** del pipeline (extracción por página, clasificación de bloque, generación de alt-text, reintento, validación de regla) se emita como evento estructurado consumido por el frontend en tiempo real y persistido para el reporte final.

---

## 1. Objetivos y no-objetivos

### 1.1 Objetivos
| # | Objetivo | Métrica de éxito |
|---|---|---|
| O1 | Que el PDF de salida sea **realmente navegable** por NVDA y JAWS (no solo que valide) | PAC 2024 no reporta "tags sin contenido"; prueba manual NVDA lee en orden lógico |
| O2 | Que el pipeline **narre** cada acción relevante con latencia ≤ 500 ms desde que ocurre hasta que se ve en UI | Demo: el usuario ve "Clasificando página 3: 14 bloques" mientras ocurre |
| O3 | Que al finalizar se genere un **reporte detallado** inspeccionable: todos los cambios, agrupados por página / criterio / tipo, con diff antes→después y confianza | Reporte accesible desde `/results/{id}` con filtros y export JSON/HTML |
| O4 | Que OCR se ejecute automáticamente cuando el PDF está escaneado | PDFs 100 % imagen producen texto navegable en el output |
| O5 | Mantener backwards compatibility con el contrato actual de [SSE `progress`](backend/app/routers/jobs.py#L98-L108) | Ningún cambio rompe el frontend existente en http://localhost:3001 |

### 1.2 No-objetivos
- No reemplazar veraPDF por otro validador.
- No soportar PDF/UA-2 (ISO 14289-2) — solo PDF/UA-1.
- No reescribir el motor de clasificación (sigue siendo Gemma vía OpenRouter).
- No garantizar corrección 100 % de tablas complejas ni formularios en la v1 de este spec (están en fases tardías).

---

## 2. Historias de usuario

| ID | Como… | Quiero… | Para… |
|----|-------|---------|-------|
| US1 | Usuario que sube un PDF | ver **en vivo** qué está haciendo la app (página, acción, subtarea) | saber que el proceso avanza y qué se está corrigiendo |
| US2 | Usuario al finalizar | un **resumen por página** con cada cambio y su criterio WCAG/PDF-UA | revisar rápidamente el valor añadido |
| US3 | Usuario con PDF escaneado | que el sistema detecte y ejecute **OCR** sin que yo lo pida | obtener un PDF accesible sin conocer la diferencia |
| US4 | Usuario con lectores de pantalla | que el PDF generado **funcione realmente con NVDA** | consumir el documento con autonomía |
| US5 | Desarrollador | logs estructurados con `job_id`, `page`, `action`, `duration_ms` | diagnosticar incidencias sin adivinar |
| US6 | Auditor de accesibilidad | ver **cada regla PDF/UA fallida** con la página, la causa y la corrección aplicada | validar el trabajo |

---

## 3. Requisitos funcionales

### 3.1 Accesibilidad (cierre de gaps de ACCESSIBILITY.md)

| ID | Requisito | Referencia ACCESSIBILITY.md | Fase |
|----|-----------|----------------------------|------|
| FR-A1 | Cada `StructElem` del tag tree debe referenciar su contenido vía `MCID` (marked content) y cada página debe tener `/StructParents` vinculando al `ParentTree.Nums` | §2.1 | 1 |
| FR-A2 | Los `Artifact` deben envolverse en el content stream con `BMC /Artifact … EMC` | §2.2 | 1 |
| FR-A3 | `reading_order_position` debe traducirse a orden **real** de MCIDs, no solo orden de hijos del árbol | §2.12 | 1 |
| FR-A4 | Cuando `needs_ocr=True`, el pipeline debe ejecutar `ocrmypdf` antes de la extracción | §2.10 | 2 |
| FR-A5 | Tablas: cada `/TH` debe llevar `/Scope` (`Row`/`Column`). Tablas con múltiples cabeceras deben emitir `/ID` + `/Headers` | §2.3 | 2 |
| FR-A6 | Listas: cada `/LI` debe contener `/Lbl` (marcador) + `/LBody` (contenido) | §2.4 | 2 |
| FR-A7 | Anotaciones `/Link`: envolver en `/Link` StructElem + `/OBJR`; escribir `/Contents` y `/StructParent` | §2.7 | 3 |
| FR-A8 | `/Figure`: añadir `/ActualText` cuando la imagen contiene texto, `/BBox` y `/Attributes /O /Layout /Placement /Block` | §2.5 | 3 |
| FR-A9 | `/Lang` por StructElem cuando el idioma del bloque difiere del de documento | §2.6 | 3 |
| FR-A10 | `/PageLabels` en el catálogo si se detecta numeración lógica | §2.9 | 3 |
| FR-A11 | XMP extendido: `dc:description`, `dc:creator`, `xmp:CreatorTool`, `pdf:Producer` | §2.14 | 3 |
| FR-A12 | Campos de formulario: `/TU` + `/Role /Form` + orden de tabulación | §2.8 | 4 |
| FR-A13 | Detectar fuentes sin `/ToUnicode` y reportarlas en `remaining_issues` | §2.11 | 4 |
| FR-A14 | Detectar contraste insuficiente (raster) y reportarlo en `remaining_issues` | §2.13 | 4 |
| FR-A15 | `/E` expansion para abreviaturas detectadas por Gemma (opcional) | §2.15 | 4 |

### 3.2 Live Activity Stream

| ID | Requisito |
|----|-----------|
| FR-L1 | Cada acción atómica del pipeline emite un **evento `activity`** por SSE con estructura definida en §5.2 |
| FR-L2 | Los eventos se emiten con latencia ≤ 500 ms desde el momento de la acción |
| FR-L3 | Los eventos **no se agregan** (cada acción su evento) — agregación es responsabilidad del consumidor |
| FR-L4 | Los eventos se **persisten** en el `Job` (buffer circular de 2 000 eventos máximo para no hinchar memoria); se recuperan al volver a cargar `/jobs/{id}/activity` |
| FR-L5 | El frontend muestra un **panel de actividad** scrollable con autoscroll al último evento, filtrable por nivel (info/warn/error) y fase |
| FR-L6 | Al completar, el panel queda **como parte del reporte** (no se descarta) |
| FR-L7 | Todo evento lleva `job_id`, `phase`, `ts`, `level`, `code`, `message`, `details?`, `duration_ms?`, `page?` |
| FR-L8 | Backend y frontend deben tolerar desconexión de SSE: el cliente reconecta con `Last-Event-ID` y el servidor reenvía lo perdido desde el buffer |

### 3.3 Reporte final pormenorizado

| ID | Requisito |
|----|-----------|
| FR-R1 | Endpoint nuevo `GET /api/v1/jobs/{id}/report` que devuelve un JSON completo con: metadatos, scores antes/después, todos los `BlockChange`, activity log, `remaining_issues`, estadísticas agregadas |
| FR-R2 | Export HTML del reporte (plantilla con Jinja2 o render en frontend) |
| FR-R3 | Página `/results/{id}` con 4 pestañas: **Resumen**, **Por página**, **Por criterio**, **Log de actividad** |
| FR-R4 | Cada cambio mostrable con: página, bbox (si aplica), tipo, criterio WCAG/PDF-UA, valor antes, valor después, confianza del modelo, timestamp |
| FR-R5 | Filtros en UI: por página, por criterio, por tipo de cambio, por confianza (`< 0.7` destacados en ámbar) |
| FR-R6 | Descarga del reporte en JSON y HTML |

---

## 4. Arquitectura propuesta

### 4.1 Diagrama lógico

```
  Upload ──► /jobs (POST) ──► JobStore ──┐
                                         │
                                         ▼
                               AccessibilityPipeline
                                         │
              ┌──────────────┬───────────┼─────────────┬──────────────┐
              ▼              ▼           ▼             ▼              ▼
         Extractor      OCR (nuevo)    Gemma      PDFWriter        veraPDF
              │              │           │             │              │
              └──────────────┴───────────┴─────────────┴──────────────┘
                                         │
                                         ▼
                                 ActivityLogger  ◄─── NUEVO
                                         │
                              ┌──────────┴──────────┐
                              ▼                     ▼
                     Job.activity_buffer       SSE stream
                                                     │
                                                     ▼
                                            Frontend LivePanel
                                                     │
                                                     ▼
                                          /results/{id} Report
```

### 4.2 Módulos nuevos

- **`app/services/observability/activity_logger.py`** — publisher central. API:
  ```python
  activity.emit(
      job_id, phase, code, message,
      level="info", page=None, duration_ms=None, details=None
  )
  ```
  Internamente: (a) añade al buffer del `Job`, (b) empuja a un `asyncio.Queue` por job que consume el SSE handler.
- **`app/services/writing/content_stream_tagger.py`** — nuevo módulo responsable de FR-A1/A2/A3: lee el content stream original, inserta `BDC /Role <</MCID n>> … EMC`, asigna `/StructParents`, construye el `ParentTree.Nums` con `[mcid0, elem0, mcid1, elem1, …]` por página.
- **`app/services/extraction/ocr_runner.py`** — ejecuta `ocrmypdf` (subprocess) cuando `needs_ocr`; sustituye `original.pdf` por su versión OCR.
- **`app/services/writing/annotations_tagger.py`** — FR-A7 (enlaces y `/OBJR`).
- **`app/services/reporting/report_builder.py`** — FR-R1/R2/R4; genera JSON y HTML con Jinja2.

### 4.3 Módulos modificados

- **`app/services/pipeline.py`** — sustituir `job_store.update_progress(...)` por calls a `activity.emit(...)` con granularidad fina. `update_progress` se mantiene para el % agregado pero pasa a ser un **derivado** calculado a partir de la fase.
- **`app/routers/jobs.py`** — añadir `activity` event type al stream y endpoint `GET /jobs/{id}/activity?since=N` para recuperación post-desconexión. Añadir `GET /jobs/{id}/report`.
- **`app/services/writing/pdf_writer.py`** — orquesta el nuevo `content_stream_tagger`; cada `StructElem` se crea tras conocer sus MCIDs.
- **`app/models/job.py`** — añadir `activity: list[ActivityEvent]` (con cap) y `activity_cursor: int`.

---

## 5. Contratos de datos

### 5.1 `ActivityEvent` (modelo nuevo en `app/models/activity.py`)

```python
@dataclass
class ActivityEvent:
    seq: int                 # monotónico por job; permite Last-Event-ID
    job_id: str
    ts: str                  # ISO-8601 UTC
    phase: str               # "extract" | "ocr" | "analyze" | "tag" |
                             # "write" | "validate" | "retry" | "report"
    code: str                # "page_extracted", "block_classified",
                             # "alt_text_generated", "mcid_assigned",
                             # "artifact_wrapped", "verapdf_rule_passed",
                             # "verapdf_rule_failed", "ocr_started", etc.
    level: str               # "info" | "warn" | "error"
    message: str             # texto legible en UI, ya localizado (es)
    page: int | None = None
    duration_ms: int | None = None
    details: dict | None = None   # datos crudos para debugging/reporte
```

### 5.2 SSE — eventos enviados por `/jobs/{id}/progress`

**Mantener** `progress`, `completed`, `failed` tal como están hoy en [jobs.py:98-123](backend/app/routers/jobs.py#L98-L123). **Añadir**:

```
event: activity
id: 1247
data: {"seq":1247,"phase":"analyze","code":"block_classified","level":"info",
       "message":"Página 3 · bloque b7 → H2 \"Métodos\" (0.94)",
       "page":3,"duration_ms":180,
       "details":{"role":"H2","confidence":0.94,"text":"Métodos"}}
```

El `id` del SSE frame es `seq` para permitir `Last-Event-ID` reconexión.

### 5.3 `GET /api/v1/jobs/{id}/activity?since={seq}`

```json
{
  "job_id": "…",
  "from_seq": 120,
  "to_seq": 247,
  "events": [ActivityEvent, …],
  "truncated": false
}
```

### 5.4 `GET /api/v1/jobs/{id}/report`

```json
{
  "job_id": "…",
  "filename": "mydoc.pdf",
  "processed_at": "…",
  "processing_time_seconds": 42.1,
  "page_count": 18,
  "model_used": "google/gemma-4-31b-it:free",
  "scores": {
    "before": {…AccessibilityScore},
    "after":  {…AccessibilityScore}
  },
  "changes_by_page":    { "1": [BlockChange, …], "2": [...] },
  "changes_by_criterion": { "1.1.1": [...], "1.3.1": [...] },
  "changes_summary": { "alt_text_added": 12, "heading_tagged": 34, … },
  "remaining_issues": [RemainingIssue, …],
  "activity_log": [ActivityEvent, …],
  "download_url": "/api/v1/jobs/{id}/download",
  "report_html_url": "/api/v1/jobs/{id}/report.html"
}
```

### 5.5 Extensión de `BlockChange`

Añadir campos para el reporte detallado:

```python
@dataclass
class BlockChange:
    block_id: str
    page_num: int
    change_type: str
    criterion: str
    before: str | None = None
    after: str | None = None
    confidence: float = 1.0
    # NUEVOS:
    bbox: tuple[float, float, float, float] | None = None
    role: str | None = None
    mcid: int | None = None
    wcag_level: str | None = None      # "A" | "AA"
    pdfua_rule: str | None = None      # "7.1-1" etc.
    timestamp: str | None = None
```

---

## 6. Fases de entrega (con criterios de aceptación)

### Fase 1 — Accesibilidad real + activity v1  *(sprint 1-2)*
Desbloquea lectores de pantalla. Es la fase que **más valor** aporta.

Entregables:
- FR-A1, FR-A2, FR-A3 (MCID + Artifact + reading order)
- FR-L1 a FR-L7 (activity log mínimo viable con panel en frontend)
- FR-R1 (endpoint `/report` con JSON estructurado)
- FR-R3 parcial: pestaña **Log de actividad** en `/results/{id}`

Criterios de aceptación:
- AC1.1: Un PDF procesado abierto en NVDA lee los párrafos en el orden de `reading_order_position`, no en el de draw order.
- AC1.2: Para un PDF con pie de página "Página N", NVDA **no** lo lee.
- AC1.3: `GET /jobs/{id}/report` responde con `changes_by_page` y `activity_log` no vacíos.
- AC1.4: En la UI se ven mínimo 1 evento por página procesada y 1 por bloque clasificado, con latencia visible ≤ 1 s.
- AC1.5: Test de invariantes: `ParentTree.Nums` tiene `2 × (num_elems_vinculados)` entradas; cada página tiene `/StructParents`; al menos un `BDC /MCID` por página en content stream.

### Fase 2 — OCR + tablas + listas  *(sprint 3)*
- FR-A4, FR-A5, FR-A6
- FR-R3 completo (4 pestañas)
- FR-R5 (filtros UI)

Criterios:
- AC2.1: Un PDF escaneado (ejemplo: factura fotografiada) produce texto navegable.
- AC2.2: `/TH scope="col"` presente en al menos una tabla de prueba; NVDA anuncia el nombre de columna al tabular.
- AC2.3: Una lista con viñetas genera LI > (Lbl + LBody) verificable con pikepdf.

### Fase 3 — Enlaces + figuras avanzadas + idioma + page labels  *(sprint 4)*
- FR-A7, FR-A8, FR-A9, FR-A10, FR-A11
- FR-R2 (export HTML)
- FR-R6 (descarga)

Criterios:
- AC3.1: Un PDF con hipervínculos genera `/Link` StructElems; NVDA los lista en el diálogo "Links list".
- AC3.2: Un bloque marcado como inglés dentro de un doc en español conmuta la voz de NVDA.
- AC3.3: Reporte HTML renderizado correctamente en Chrome y Firefox.

### Fase 4 — Formularios + fuentes + contraste + expansiones  *(sprint 5)*
- FR-A12, FR-A13, FR-A14, FR-A15
- Endurecimiento: rate-limiting de eventos activity, compresión SSE, tests e2e.

---

## 7. Granularidad del live log (qué se emite)

Lista **exhaustiva** de códigos a implementar en Fase 1. Cada emisión es un `ActivityEvent`.

| Fase | Código | Cuándo | Detalles útiles |
|------|--------|--------|-----------------|
| extract | `upload_received` | POST /jobs recibido | `size_mb`, `pages_declared` |
| extract | `pdf_opened` | Tras abrir con pymupdf | `encrypted`, `has_existing_tags` |
| extract | `page_extracted` | Fin extracción de página | `page`, `text_blocks`, `tables`, `images`, `duration_ms` |
| extract | `ocr_needed` | Cuando `avg_chars<50` | `avg_chars` |
| ocr | `ocr_started` / `ocr_completed` / `ocr_failed` | Fase 2 | `engine`, `language`, `duration_ms` |
| analyze | `page_analysis_started` | Antes de llamar Gemma | `page`, `text_summary_chars` |
| analyze | `block_classified` | Por bloque devuelto | `block_id`, `role`, `confidence` |
| analyze | `alt_text_generated` | Por figura | `block_id`, `length`, `language`, `duration_ms` |
| analyze | `alt_text_failed` | Error Gemma en figura | `block_id`, `error` |
| tag | `hierarchy_normalized` | Tras `HierarchyFixer` | `h1_downgrades`, `level_jumps_fixed` |
| tag | `title_detected` / `language_detected` | | `value` |
| write | `mcid_assigned` | Por fragmento marcado (⚠ volumen alto — agrupar por página) | `page`, `mcid_count` |
| write | `artifact_wrapped` | Por artifact en content stream | `page`, `count` |
| write | `struct_elem_created` | Por StructElem emitido | `role`, `page`, `mcid` |
| write | `bookmark_added` | Por bookmark en outlines | `title`, `page` |
| validate | `verapdf_started` / `verapdf_completed` | | `compliant`, `score`, `duration_ms` |
| validate | `verapdf_rule_failed` | Por fallo reportado | `rule_id`, `clause`, `count` |
| retry | `fix_attempt_started` / `fix_attempt_completed` | Reintentos | `attempt`, `new_score` |
| report | `report_generated` | Al final | `json_bytes`, `html_bytes` |

Nota sobre volumen: `block_classified` puede emitirse decenas de veces por página. Se aplicará **coalescing** en el frontend (batch visual cada 200 ms) pero el backend los emite todos para el reporte.

---

## 8. Frontend — cambios

Archivos actuales relevantes: `frontend/app/processing/[jobId]/` y `frontend/lib/api.ts` (API helper), `useSSE` hook.

### 8.1 Componentes nuevos
- **`LiveActivityPanel`**: lista virtualizada (react-window) con autoscroll, filtros por `level` y `phase`, búsqueda por `code`/`message`.
- **`ReportViewer`** en `/results/[jobId]`: 4 pestañas (Resumen · Por página · Por criterio · Log).
  - **Por página**: acordeón, cada página muestra sus `BlockChange` con miniatura del bbox (futuro) y diff before/after.
  - **Por criterio**: tabla WCAG/PDF-UA → nº de cambios + remaining issues.

### 8.2 Hooks
- `useActivityStream(jobId)` — extensión de `useSSE` que distingue `activity` vs `progress` y gestiona reconexión con `Last-Event-ID`.

### 8.3 UX
- Mientras procesa: **dos columnas** — progreso/score arriba, live panel abajo (scroll propio).
- Al completar: redirect automático a `/results/{id}`, con el live panel preservado como pestaña.

---

## 9. Estrategia de tests

| Tipo | Qué cubre |
|------|-----------|
| Unit (backend) | `content_stream_tagger` — un PDF simple 1 página genera `ParentTree.Nums` correcto; `activity_logger` emite sin bloquear; `report_builder` agrupa correctamente |
| Property | MCID asignados siempre son únicos por página y consecutivos desde 0 |
| Integration | PDF sample → pipeline completo → abrir output con pikepdf y comprobar invariantes de AC1.5 |
| Golden | 5 PDFs representativos (texto simple, multi-columna, tabla, lista, mixto) con outputs esperados comparables semánticamente |
| Manual SR | Validación con NVDA + Acrobat Reader para AC1.1, AC1.2, AC3.1, AC3.2 — checklist documentado |
| E2E | Playwright: subir PDF, ver ≥ 50 eventos de activity llegar, completar, ver reporte con ≥ 4 pestañas |
| Performance | Procesar PDF 20 páginas: ≤ 60 s; eventos emitidos ≤ 2 000 sin OOM; SSE latencia p95 ≤ 500 ms |

---

## 10. Observabilidad, performance y límites

- **Buffer activity**: 2 000 eventos máx por job; al llegar al cap se descartan los más antiguos y se emite un evento `activity_truncated`.
- **Backpressure SSE**: `asyncio.Queue(maxsize=500)` por suscriptor; si se llena, se descartan eventos `info` pero **nunca** `warn`/`error`.
- **Rate de envío**: máximo 50 eventos/s al cliente; coalescing adicional en servidor si se supera.
- **Logging estructurado**: `structlog` continúa escribiendo a stdout con el mismo `job_id`/`phase`/`code` que los ActivityEvents, así los logs de contenedor y la UI están alineados (FR-US5).
- **Memoria**: el `activity_buffer` y el `result` se liberan al expirar el job (`JOB_TTL_HOURS`).

---

## 11. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|:---:|:---:|-----------|
| Reescribir content stream corrompe PDFs complejos | Alta | Alto | Validación con pikepdf + veraPDF tras cada write; feature flag `ENABLE_MCID_TAGGING` para fallback al writer actual |
| Volumen de eventos satura SSE | Media | Medio | Coalescing, niveles, rate-limit §10 |
| ocrmypdf lento (PDFs grandes) | Media | Medio | Ejecutar async en worker separado; progreso específico `ocr.page_done` |
| Gemma clasifica mal → se etiquetan erróneamente | Media | Medio | Umbral `confidence < 0.5` → marcar como `P` por defecto + evento `low_confidence_fallback` |
| Desconexión SSE pierde eventos | Media | Bajo | `Last-Event-ID` + endpoint `/activity?since=` |

---

## 12. Rollout y feature flags

Variables nuevas en `.env`:

```
ENABLE_MCID_TAGGING=true       # Fase 1 kill switch
ENABLE_OCR=true                # Fase 2
ENABLE_ANNOTATIONS_TAGGING=true # Fase 3
ENABLE_FORM_TAGGING=false      # Fase 4 (off por defecto v1)
ACTIVITY_BUFFER_MAX=2000
ACTIVITY_RATE_LIMIT_PER_SEC=50
```

Cada fase se merge detrás de su flag y se habilita progresivamente. Al promocionar una fase, el flag pasa a default `true` y se mantiene 1 release para rollback.

---

## 13. Métricas de éxito post-lanzamiento

- Porcentaje de PDFs procesados que pasan validación NVDA manual: meta **≥ 85 %** tras Fase 1.
- Tiempo medio de procesamiento de un PDF de 10 páginas: meta **≤ 25 s**.
- Tasa de errores por job: meta **≤ 2 %**.
- Abandono de usuarios durante el procesamiento (medido por desconexión SSE antes de completed): meta **≤ 10 %** (baseline por determinar).

---

## 14. Anexo — Mapeo directo con ACCESSIBILITY.md

| Gap de ACCESSIBILITY.md | Requisito en este spec | Fase |
|---|---|:---:|
| §2.1 MCID + ParentTree | FR-A1 | 1 |
| §2.2 Artifact en content stream | FR-A2 | 1 |
| §2.3 Tablas (Scope, Headers) | FR-A5 | 2 |
| §2.4 Listas (Lbl/LBody) | FR-A6 | 2 |
| §2.5 Figuras (ActualText, BBox) | FR-A8 | 3 |
| §2.6 Idioma por bloque | FR-A9 | 3 |
| §2.7 Enlaces y anotaciones | FR-A7 | 3 |
| §2.8 Formularios | FR-A12 | 4 |
| §2.9 Page Labels | FR-A10 | 3 |
| §2.10 OCR | FR-A4 | 2 |
| §2.11 Fuentes/ToUnicode | FR-A13 (solo reporte) | 4 |
| §2.12 Reading order | FR-A3 (derivado de FR-A1) | 1 |
| §2.13 Contraste | FR-A14 (solo reporte) | 4 |
| §2.14 XMP extendido | FR-A11 | 3 |
| §2.15 Expansión abreviaturas | FR-A15 | 4 |
