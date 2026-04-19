# AccessDoc — Modificaciones de accesibilidad y gaps pendientes

Este documento inventaría (1) **qué modificaciones de accesibilidad aplica hoy AccessDoc** al PDF original y (2) **qué falta** para que los lectores de pantalla (NVDA, JAWS, VoiceOver, Narrator) realmente expongan el contenido en orden y con semántica correcta, cumpliendo PDF/UA-1 (ISO 14289-1) y WCAG 2.1 AA.

El pipeline actual está en [backend/app/services/pipeline.py](backend/app/services/pipeline.py) y la escritura del PDF final en [backend/app/services/writing/pdf_writer.py](backend/app/services/writing/pdf_writer.py).

---

## 1. Modificaciones que ya realiza el programa

### 1.1 Extracción y análisis previo
Archivo: [backend/app/services/extraction/pdf_extractor.py](backend/app/services/extraction/pdf_extractor.py)

- Extracción de palabras con `pdfplumber` (texto + fuente + tamaño) y render de página a PNG 150 DPI con `pymupdf`.
- Detección heurística de candidatos a heading (`size ≥ 1.15 × body_size` o `bold + tamaño ≈ body`).
- Detección de tablas con `pdfplumber.find_tables()` y heurística de fila cabecera.
- Extracción de imágenes embebidas por xref con bbox.
- Detección de PDF cifrado y de PDFs escaneados (si `avg_chars/página < 50` → `needs_ocr=True`, pero **OCR no se ejecuta**, ver §2).
- Detección de si el PDF ya está tagueado (`MarkInfo` presente en el catálogo).

### 1.2 Clasificación semántica con Gemma (vía OpenRouter)
Archivo: [backend/app/services/analysis/gemma_client.py](backend/app/services/analysis/gemma_client.py)

- Se envía la imagen de página + resumen de texto al modelo multimodal, que devuelve, por bloque:
  - `role` ∈ {H1–H6, P, Figure, Table, L, LI, LBody, Caption, TOC, Artifact, Formula, Code, Footnote…}
  - `is_decorative`, `alt_text_needed`
  - `reading_order_position`
  - `language` de página
  - `confidence`
- Para cada `Figure` informativa: se recorta, se envía a Gemma y se **genera alt text** (WCAG 1.1.1).
- Si veraPDF falla, se reintenta hasta 2 veces pidiendo al modelo que **corrija** la estructura en base a los fallos.

### 1.3 Normalización de jerarquía
Archivo: [backend/app/services/analysis/hierarchy_fixer.py](backend/app/services/analysis/hierarchy_fixer.py)

- **Un solo H1**: H1 posteriores se degradan a H2.
- **Niveles de heading no saltados**: H1→H3 se reescribe a H1→H2 (WCAG 1.3.1 / 2.4.6).
- **Título del documento**: primer H1 o primer bloque no-artifact.
- **Idioma del documento**: voto mayoritario del idioma detectado por página.

### 1.4 Escritura del PDF/UA-1
Archivo: [backend/app/services/writing/pdf_writer.py](backend/app/services/writing/pdf_writer.py)

En el PDF de salida se añaden:

| Elemento | Objeto/entrada | WCAG/PDF-UA |
|---|---|---|
| Título | XMP `dc:title` | 2.4.2 |
| Idioma | XMP `dc:language` | 3.1.1 |
| Identificador PDF/UA | XMP `pdfuaid:part=1` | PDF-UA 5 |
| Marcado como tagueado | `MarkInfo.Marked=true`, `Suspects=false` | PDF-UA 7.1 |
| Mostrar título en ventana | `ViewerPreferences.DisplayDocTitle=true` | PDF-UA 7.1 |
| Árbol estructural | `/StructTreeRoot` + `/Document` raíz | 1.3.1 |
| RoleMap | H1–H6, P, L/LI/LBody/Lbl, Table/TR/TH/TD, Figure, Caption, TOC/TOCI, Note, Code, Formula | 1.3.1 |
| `/StructElem` por bloque | con `S=/Role`, `P=parent`, `K=[]` | 1.3.1 |
| Alt-text en figuras | `/Alt` en `/Figure` | 1.1.1 |
| Bookmarks | `/Outlines` a partir de headings | 2.4.1 / 2.4.5 |
| PDF linealizado | `linearize=True` | — |

### 1.5 Validación
Archivo: [backend/app/services/validation/verapdf_runner.py](backend/app/services/validation/verapdf_runner.py)

- Validación automática **PDF/UA-1** con veraPDF al final del pipeline.
- Cálculo de score "before/after" ([score_calculator.py](backend/app/services/validation/score_calculator.py)) y reintentos si < 70.

---

## 2. Gaps críticos para lectores de pantalla

Aunque el PDF sale con `StructTreeRoot` y etiquetas, **hay omisiones que impiden que un lector de pantalla use realmente esa estructura**. En orden de impacto:

### 2.1 🔴 CRÍTICO — Los `StructElem` no están vinculados al contenido real (MCID / ParentTree)

**Estado actual:** cada `StructElem` tiene `K=Array()` vacío (ver [pdf_writer.py:117](backend/app/services/writing/pdf_writer.py#L117)) y `ParentTree.Nums=Array()` también vacío ([pdf_writer.py:75](backend/app/services/writing/pdf_writer.py#L75)).

**Problema:** para que un lector de pantalla navegue por la estructura:
1. El **content stream** de cada página debe envolver cada fragmento con operadores `BDC /P <</MCID n>> … EMC` (marked content).
2. Cada `StructElem` debe tener en su `K` una referencia al MCID (`MCR` dict con `/Pg`, `/MCID`, o directamente el entero) o, en caso de XObjects, un `OBJR`.
3. Cada página debe tener `/StructParents n` apuntando a una entrada del `ParentTree.Nums` que mapea MCIDs → StructElems.

**Sin esto, el lector de pantalla ignora el tag tree** y lee el content stream crudo en orden de dibujo. Es la causa número uno de que PDFs "tagueados" fallen en NVDA/JAWS aunque veraPDF dé un score alto en otros criterios.

**Para implementar:** reescribir el content stream de cada página (con pikepdf o pypdf) insertando los operadores BDC/EMC, o usar una librería que lo haga (ej. `pdfix`, `autotag` de Adobe, o escribir un content stream nuevo desde cero con reportlab+rlextra).

### 2.2 🔴 Los `Artifact` no se marcan en el content stream

**Estado actual:** los bloques con `role=Artifact` se excluyen del tag tree ([pdf_writer.py:97](backend/app/services/writing/pdf_writer.py#L97)), pero **siguen presentes en el content stream sin envolver**.

**Problema:** PDF/UA exige que todo contenido no-estructural esté marcado como `/Artifact` en el content stream (`BMC /Artifact … EMC`). Si no, el lector lee "Page 1 of 42" y los encabezados/pies de página junto con el contenido real.

### 2.3 🟠 Tablas sin semántica completa

Hoy solo se genera `/Table`, `/TR`, `/TH`, `/TD`. Faltan:
- **`/Scope`** en `/TH` (`Row` | `Column` | `Both`) — sin esto, NVDA no anuncia "columna X" al navegar.
- **`/Headers` + `/ID`** para tablas complejas (WCAG 1.3.1, técnica PDF6).
- **`/Summary`** opcional para tablas complejas.
- Los elementos Table no anidan `/THead`/`/TBody`/`/TFoot`.

### 2.4 🟠 Listas incompletas

El `RoleMap` incluye `Lbl` y `LBody`, pero el pipeline solo clasifica `L` y `LI` — **no se emiten `Lbl` (bullet/número) ni `LBody` (texto)** como hijos de cada `LI`. Los lectores no podrán anunciar "bullet 1 of 5" correctamente.

### 2.5 🟠 Figuras sin `ActualText` ni `BBox`

- `/Alt` se añade, pero no `/ActualText` (necesario cuando la imagen contiene texto que debe leerse literalmente).
- Falta `/BBox` y `/Attributes <</O /Layout /Placement /Block>>` para que el lector sepa que la figura es un bloque y no inline.
- Las figuras no envuelven sus XObjects con `/Figure BDC` + `OBJR` en el árbol.

### 2.6 🟠 Idioma por bloque (WCAG 3.1.2)

Solo se fija el idioma a nivel de documento (`dc:language`). Si un bloque está en otro idioma (p. ej. una cita en inglés dentro de un doc en español), el `StructElem` debería tener `/Lang "en"`.

### 2.7 🟠 Enlaces y anotaciones

No se procesan:
- Anotaciones de enlace (`/Link`): deberían estar envueltas por un `/Link StructElem` con `/OBJR` apuntando a la anotación, y la anotación necesita `/Contents` (texto alternativo) y `/StructParent`.
- Anotaciones de texto/comentarios: `/Contents`.
- Anotaciones sin texto alternativo violan PDF/UA-1 §7.18 y WCAG 2.4.4.

### 2.8 🟠 Formularios

Campos de formulario (`/AcroForm`) necesitan:
- `/TU` (tooltip accesible) — es la "etiqueta" que lee el screen reader.
- `/V` (valor), orden de tabulación (`/Tabs /S`).
- `/Role /Form` en el StructElem.

Si el PDF trae formularios, hoy se ignoran.

### 2.9 🟡 Page Labels (WCAG 2.4.1)

PDFs con numeración lógica ("i, ii, iii, 1, 2…") necesitan `/PageLabels` en el catálogo. Hoy no se escribe.

### 2.10 🟡 OCR para PDFs escaneados

[pdf_extractor.py:103](backend/app/services/extraction/pdf_extractor.py#L103) detecta `needs_ocr=True` pero **el pipeline no lanza OCR**. Tesseract ya está instalado en el contenedor ([backend/Dockerfile:5-7](backend/Dockerfile#L5-L7)) pero no se invoca. Un PDF escaneado entra como una imagen: imposible de exponer textualmente sin OCR previo.

### 2.11 🟡 Fuentes embebidas + `ToUnicode` CMap

PDF/UA exige que **todas** las fuentes estén embebidas con `/ToUnicode` válido. Si una fuente no embebida o sin mapa Unicode se usa para texto, el lector anuncia glyphs incorrectos o nada. Hoy no se verifica ni se corrige (habría que reembeber o sustituir la fuente).

### 2.12 🟡 Orden de lectura real

El campo `reading_order_position` del modelo se usa para ordenar hijos del `/Document` StructElem ([pdf_writer.py:90-93](backend/app/services/writing/pdf_writer.py#L90-L93)), pero **el lector de pantalla usa el orden MCID dentro del content stream**, no el orden de hijos del tag tree, cuando los tags no están ligados (ver §2.1). Solucionar §2.1 también resuelve esto.

### 2.13 🟡 Contraste de color (WCAG 1.4.3)

No se analiza. No se puede "arreglar" en un PDF rasterizado, pero sí **reportarlo** al usuario en `remaining_issues`.

### 2.14 🟡 Extensiones XMP adicionales

Hoy solo se fijan `dc:title`, `dc:language`, `pdfuaid:part`. Convendría también:
- `dc:description` (si hay abstract/resumen)
- `dc:creator` (autor)
- `xmp:CreatorTool`
- `pdf:Producer` — coherente para validadores.

### 2.15 🟢 Expansión de abreviaturas (opcional)

`/E "Web Content Accessibility Guidelines"` en un StructElem con texto "WCAG" mejora la experiencia con screen readers, pero es opcional.

---

## 3. Roadmap sugerido (por impacto)

Orden recomendado para cerrar gaps sin romper lo que ya funciona:

1. **MCID linkage + ParentTree + Artifact en content stream** (§2.1, §2.2, §2.12) — desbloquea que los lectores de pantalla usen la estructura. Es el 80 % del valor.
2. **OCR para PDFs escaneados** (§2.10) — sin esto, un PDF de imagen es irrecuperable.
3. **Semántica de tablas**: `/Scope` en TH como mínimo (§2.3).
4. **Listas con `/Lbl` + `/LBody`** (§2.4).
5. **Enlaces** con `/Link` + `/OBJR` (§2.7).
6. **Figura: `/ActualText` + `/BBox`** (§2.5).
7. **Idioma por bloque** (§2.6).
8. **Page labels + XMP completo** (§2.9, §2.14).
9. **Formularios** (§2.8) — solo si el alcance cubre PDFs con `/AcroForm`.
10. **Fuentes embebidas / ToUnicode** (§2.11) — solo como validación/reporte si detectarlo es barato; corregirlo implica reembeber.

### Librerías candidatas

- **pikepdf** (ya en uso) — cubre todo lo estructural salvo reescribir content streams con comodidad.
- **pypdf** — similar nivel, API más ergonómica para content streams.
- **pdfix SDK** (comercial) — hace tag+MCID end-to-end, lo más rápido a producción si se acepta dependencia comercial.
- **Apache PDFBox + jpod (vía Java)** — hay bindings, dado que ya tenemos JRE en el contenedor.
- **Tesseract + ocrmypdf** — para §2.10, `ocrmypdf` ya resuelve OCR+sidecar y es apt-installable.

---

## 4. Validadores recomendados además de veraPDF

- **PAC 2024** (PDF Accessibility Checker, gratuito Windows) — complementa veraPDF, muestra el árbol visualmente.
- **axesPDF QuickFix** — da feedback equivalente al manual que hace un experto.
- **NVDA + Acrobat Reader** (pruebas reales) — nada sustituye escuchar el PDF con un lector de pantalla real.
- **Tests automatizados**: conviene añadir tests que abran el PDF con pikepdf y comprueben que `ParentTree.Nums` no esté vacío, que cada página tenga `/StructParents`, y que el content stream contenga `/MCID` — estos son invariantes fáciles de chequear.
