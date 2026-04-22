"""
Human-readable explanations for activity codes and change types.

Single source of truth for what each technical code/change_type *means* to a
user without deep accessibility knowledge. Used by:

* ``activity.emit`` → enriches ``details.explanation`` so the SSE log and the
  activity panel can show plain-language tooltips.
* ``ReportBuilder.build_narrative`` → weaves codes/changes into a cronological
  story at the end of the job.
* The HTML report template → renders the "why" next to every row.

Lookups fall back gracefully: if a code or change_type is not in the maps, the
caller keeps its original short message with no explanation payload.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Explanation:
    title: str                       # plain-language short title ("Texto alternativo generado")
    what: str                        # what happened in one sentence
    why: str                         # why it matters for accessibility
    impact: str                      # who benefits ("Lectores de pantalla podrán…")
    wcag: Optional[str] = None       # e.g. "1.1.1 Contenido no textual (A)"
    pdfua: Optional[str] = None      # e.g. "PDF/UA §7.18.1"
    user_level: str = "info"         # "info" | "warn" | "error" — severity for humans
    tags: list[str] = field(default_factory=list)  # e.g. ["ocr", "auto-repair"]

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [])}


# ─────────────────────────────────────────────────────────────────────────────
# WCAG / PDF/UA glossary — used by the frontend to render a reference pane
# and by the narrative to expand "criterion 1.1.1" into words.
# ─────────────────────────────────────────────────────────────────────────────
WCAG_CRITERIA: dict[str, dict[str, str]] = {
    "1.1.1": {
        "name": "Contenido no textual",
        "level": "A",
        "plain": (
            "Toda imagen, gráfico o ícono que aporte información debe "
            "tener un texto alternativo que describa lo que muestra. "
            "Las imágenes decorativas deben marcarse como tales para que "
            "los lectores de pantalla las ignoren."
        ),
    },
    "1.3.1": {
        "name": "Información y relaciones",
        "level": "A",
        "plain": (
            "La estructura del documento (encabezados, listas, tablas, "
            "orden de lectura) tiene que ser reconocible por software, "
            "no sólo visualmente. Sin esto, un lector de pantalla ve una "
            "sopa de texto sin jerarquía."
        ),
    },
    "1.3.2": {
        "name": "Secuencia significativa",
        "level": "A",
        "plain": (
            "El orden en que se presenta el contenido debe tener sentido "
            "cuando se lee en secuencia, aunque no se vea la presentación "
            "visual (columnas, cajas laterales, notas al pie)."
        ),
    },
    "1.4.3": {
        "name": "Contraste (mínimo)",
        "level": "AA",
        "plain": (
            "El texto necesita al menos 4.5:1 de contraste con su fondo "
            "(3:1 para texto grande) para que personas con baja visión "
            "puedan leerlo cómodamente."
        ),
    },
    "2.4.1": {
        "name": "Evitar bloques",
        "level": "A",
        "plain": (
            "El usuario debe poder saltar a secciones del documento. "
            "En PDF se logra con marcadores (bookmarks) y con encabezados "
            "etiquetados semánticamente."
        ),
    },
    "2.4.2": {
        "name": "Titulado de páginas",
        "level": "A",
        "plain": (
            "El documento necesita un título visible en los metadatos. "
            "Es lo primero que anuncia un lector de pantalla al abrirlo."
        ),
    },
    "2.4.4": {
        "name": "Propósito de los enlaces (en contexto)",
        "level": "A",
        "plain": (
            "Cada enlace debe dejar claro a dónde lleva. No vale "
            "«haz clic aquí»: el texto del enlace debe ser descriptivo, "
            "y en PDF, además, debe estar etiquetado como /Link."
        ),
    },
    "3.1.1": {
        "name": "Idioma de la página",
        "level": "A",
        "plain": (
            "El idioma del documento debe estar declarado. Si no lo está, "
            "los lectores de pantalla lo pronuncian con la fonética "
            "equivocada (por ejemplo, leyendo español con acento inglés)."
        ),
    },
    "3.1.2": {
        "name": "Idioma de las partes",
        "level": "AA",
        "plain": (
            "Los fragmentos en otro idioma (una cita en inglés dentro "
            "de un documento en español) deben marcarse con su idioma "
            "específico para que se pronuncien correctamente."
        ),
    },
    "3.1.4": {
        "name": "Abreviaturas",
        "level": "AAA",
        "plain": (
            "Las siglas y abreviaturas deben poder expandirse. En PDF se "
            "consigue con /E (expansion text) en el tagueado, para que el "
            "lector diga «Organización de las Naciones Unidas» en vez de "
            "deletrear «O N U»."
        ),
    },
    "4.1.2": {
        "name": "Nombre, función, valor",
        "level": "A",
        "plain": (
            "Los campos interactivos (formularios, botones) tienen que "
            "tener nombre y rol legibles por tecnologías de asistencia. "
            "Sin esto, un lector de pantalla anuncia «casilla sin "
            "etiqueta» y el usuario no sabe qué rellenar."
        ),
    },
}


PDFUA_RULES: dict[str, str] = {
    "7.1-1": (
        "El documento debe estar marcado como 'tagged PDF' y declararse "
        "conforme a PDF/UA-1 en los metadatos XMP."
    ),
    "7.1-2": (
        "Todos los objetos gráficos del contenido deben estar o bien "
        "etiquetados semánticamente o bien marcados como artefactos "
        "(decorativos)."
    ),
    "7.5": (
        "Las tablas deben tener encabezados (/TH) con /Scope y, si tienen "
        "encabezados de fila y columna, enlazar cada celda a sus "
        "encabezados con /Headers."
    ),
    "7.6": (
        "Las listas deben usar los elementos estructurales /L, /LI, /Lbl "
        "y /LBody para que los lectores de pantalla anuncien «1 de 5», "
        "«2 de 5», etc."
    ),
    "7.9": (
        "Las abreviaturas y acrónimos deben expandirse con /E para que "
        "la tecnología de asistencia los lea como palabras, no deletreados."
    ),
    "7.18.1": (
        "Las figuras informativas deben llevar un texto alternativo "
        "(/Alt) que las describa; las decorativas deben marcarse como "
        "artefactos."
    ),
    "7.18.3": (
        "Cada página con campos de formulario debe tener /Tabs /S para "
        "que el orden de tabulación siga la estructura semántica, no la "
        "posición física."
    ),
    "7.18.4": (
        "Cada campo de formulario (widget) debe estar dentro de un "
        "/Form StructElem y tener un nombre accesible (/TU)."
    ),
    "7.18.5": (
        "Cada anotación /Link debe estar dentro de un /Link StructElem "
        "y tener /Contents que describan el destino."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Explanations for activity codes emitted by the pipeline.
# ─────────────────────────────────────────────────────────────────────────────
CODE_EXPLANATIONS: dict[str, Explanation] = {
    "upload_received": Explanation(
        title="Documento recibido",
        what="El backend recibió el PDF y lo puso en la cola de procesamiento.",
        why="Este es el punto de partida del pipeline; a partir de aquí todo lo que suceda quedará registrado.",
        impact="Todavía no hemos tocado tu documento.",
    ),
    "pdf_opened": Explanation(
        title="Análisis del PDF original",
        what="Abrimos el PDF con pikepdf + PyMuPDF y lo inventariamos.",
        why="Necesitamos saber cuántas páginas tiene, si ya venía etiquetado (tagged) y si el texto es extraíble o son imágenes escaneadas.",
        impact="Sin esta radiografía inicial, no podríamos decidir qué necesita arreglo.",
    ),
    "page_extracted": Explanation(
        title="Página extraída",
        what="Sacamos el texto, las tablas y las imágenes de una página.",
        why="Es el inventario de la página antes de cualquier arreglo: nos dice cuántos bloques de texto, tablas e imágenes hay.",
        impact="Si aquí no aparece nada, probablemente la página sea escaneada y tengamos que usar OCR a continuación.",
    ),
    "ocr_needed": Explanation(
        title="Documento escaneado detectado",
        what="Detectamos que la mayor parte del texto está como imagen, no como texto seleccionable.",
        why="Un PDF escaneado es totalmente invisible para lectores de pantalla: para ellos sólo hay imágenes sin alternativa textual.",
        impact="Si el OCR está activado, intentaremos reconocer el texto con Tesseract; si no, quedará como pendiente de revisión manual.",
        user_level="warn",
        tags=["ocr"],
    ),
    "ocr_started": Explanation(
        title="OCR iniciado",
        what="Lanzamos Tesseract sobre el PDF para reconocer el texto de las imágenes.",
        why="Queremos convertir las imágenes de texto en texto real seleccionable y leíble por software.",
        impact="Esto puede tardar varios segundos por página escaneada; el resultado se mezcla como capa invisible sobre la imagen original.",
        tags=["ocr"],
    ),
    "ocr_completed": Explanation(
        title="OCR completado",
        what="Tesseract terminó de reconocer el texto de las páginas escaneadas.",
        why="Ahora el PDF tiene una capa de texto real bajo las imágenes; todo lo demás del pipeline puede trabajar sobre él.",
        impact="Los lectores de pantalla ya podrán leer el contenido que antes era sólo visual.",
        wcag="1.1.1",
        tags=["ocr"],
    ),
    "ocr_failed": Explanation(
        title="Fallo en el OCR",
        what="Tesseract terminó con error o no se pudo lanzar.",
        why="Sin OCR, un documento escaneado sigue siendo una colección de imágenes sin texto alternativo.",
        impact="El documento quedará con un aviso en 'issues pendientes' pidiendo revisión manual.",
        user_level="warn",
        tags=["ocr"],
    ),
    "page_analysis_started": Explanation(
        title="Análisis semántico de página iniciado",
        what="Enviamos la página a Gemma (vision LLM) junto con el texto extraído.",
        why="El modelo tiene que decidir qué es cada bloque: título, párrafo, lista, tabla, figura decorativa…",
        impact="Esta clasificación es la base del árbol de etiquetas PDF/UA que construiremos después.",
        tags=["llm"],
    ),
    "block_classified": Explanation(
        title="Bloque clasificado",
        what="El modelo asignó un rol semántico (H1, P, Figure, Table…) a un bloque concreto.",
        why="Sin este rol el PDF no sabría diferenciar un título de un pie de foto. Los lectores de pantalla lo necesitan para anunciar «Encabezado nivel 2».",
        impact="Este rol termina como StructElem en el árbol de etiquetas del PDF accesible.",
        wcag="1.3.1",
        tags=["llm"],
    ),
    "low_confidence_fallback": Explanation(
        title="Clasificación de baja confianza",
        what="El modelo no estuvo seguro del rol de un bloque (confianza < 0.5).",
        why="En esos casos aplicamos heurísticas de respaldo (tamaño de fuente, negrita, posición) para no propagar un error del LLM.",
        impact="El bloque se etiqueta igualmente, pero queda marcado para revisión en el tab 'Por página'.",
        user_level="warn",
        tags=["llm", "fallback"],
    ),
    "alt_text_generated": Explanation(
        title="Texto alternativo generado",
        what="Generamos una descripción breve para una imagen informativa usando el modelo multimodal.",
        why="Una imagen sin /Alt es invisible para lectores de pantalla. Las decorativas se marcan como artefacto; las informativas necesitan texto.",
        impact="Al leer el PDF, un usuario ciego escuchará la descripción en lugar de silencio o 'imagen'.",
        wcag="1.1.1",
        pdfua="7.18.1",
        tags=["llm", "alt-text"],
    ),
    "alt_text_failed": Explanation(
        title="Fallo generando texto alternativo",
        what="La llamada al modelo falló; marcamos la figura como decorativa por defecto.",
        why="Sin alt-text y sin marcado de decorativa, la imagen bloquea el cumplimiento PDF/UA-1.",
        impact="Dejamos un issue pendiente para que revises manualmente la imagen.",
        user_level="warn",
        tags=["llm", "alt-text"],
    ),
    "hierarchy_normalized": Explanation(
        title="Estructura del documento consolidada",
        what="Unimos las clasificaciones de todas las páginas en una jerarquía global coherente (H1 > H2 > H3 sin saltos).",
        why="PDF/UA requiere que los encabezados estén anidados sin saltar niveles. Si el LLM generó H1 → H3, lo corregimos a H1 → H2.",
        impact="La tabla de contenidos y la navegación por encabezados funcionarán en el lector de pantalla.",
        wcag="1.3.1",
        pdfua="7.4",
    ),
    "title_detected": Explanation(
        title="Título del documento detectado",
        what="Identificamos el título del documento y lo escribimos en los metadatos XMP.",
        why="WCAG 2.4.2 exige que todo documento tenga título. El lector de pantalla lo anuncia al abrir el PDF.",
        impact="Aparecerá en la barra de título del visor y será lo primero que escuche un usuario de tecnología de asistencia.",
        wcag="2.4.2",
    ),
    "language_detected": Explanation(
        title="Idioma detectado",
        what="Detectamos el idioma principal del documento y lo fijamos en /Lang y en los metadatos.",
        why="Sin idioma, los lectores de pantalla pronuncian el texto con la fonética equivocada.",
        impact="El contenido se leerá con la pronunciación correcta del idioma detectado.",
        wcag="3.1.1",
    ),
    "mcid_assigned": Explanation(
        title="MCIDs asignados a la página",
        what="Reescribimos el content stream insertando marcadores BDC/EMC que conectan cada fragmento de texto con su etiqueta semántica.",
        why="Sin MCIDs, las etiquetas viven 'a un lado' y no saben a qué porción visible del PDF corresponden.",
        impact="Los lectores de pantalla pueden saltar entre el texto visible y su rol (párrafo, encabezado, celda…).",
        wcag="1.3.1",
        pdfua="7.1-2",
    ),
    "page_labels_set": Explanation(
        title="Numeración de páginas configurada",
        what="Añadimos un árbol /PageLabels decimal que empieza en 1.",
        why="Los lectores de pantalla y asistentes necesitan una numeración lógica coherente con la visible para anunciar «Página 3 de 10».",
        impact="Navegar por número de página coincide con lo que ve una persona vidente.",
    ),
    "annotations_tagged": Explanation(
        title="Enlaces etiquetados",
        what="Cada anotación /Link se envolvió en un StructElem /Link con /OBJR y se le añadió /Contents con el destino.",
        why="PDF/UA §7.18.5: un enlace sin etiqueta es un punto clicable invisible para lectores de pantalla.",
        impact="El usuario escuchará «Enlace a https://…» o «Enlace interno del documento» al llegar a la anotación.",
        wcag="2.4.4",
        pdfua="7.18.5",
    ),
    "form_fields_tagged": Explanation(
        title="Campos de formulario etiquetados",
        what="Cada widget (campo de texto, casilla, botón) se envolvió en un StructElem /Form con tooltip /TU y la página recibió /Tabs /S para orden de tabulación.",
        why="PDF/UA §7.18.4: un campo sin /Form y sin /TU se anuncia como «casilla sin etiqueta» en los lectores de pantalla.",
        impact="El usuario escuchará el nombre del campo («Nombre», «Email»…) y podrá tabular en orden lógico.",
        wcag="4.1.2",
        pdfua="7.18.4",
    ),
    "abbreviations_expanded": Explanation(
        title="Abreviaturas expandidas",
        what="Añadimos /E (expansion text) a los spans con acrónimos conocidos.",
        why="WCAG 3.1.4: una sigla sin expansión se deletrea letra a letra (O-N-U) en vez de pronunciarse como «Organización de las Naciones Unidas».",
        impact="El audio del lector de pantalla suena natural en vez de robótico.",
        wcag="3.1.4",
        pdfua="7.9",
    ),
    "pdf_written": Explanation(
        title="PDF accesible escrito en disco",
        what="Guardamos el PDF con todos los StructElems, MCIDs, /Tabs y metadatos añadidos.",
        why="Esta es la versión que descargará el usuario: el documento original más todas las capas de accesibilidad.",
        impact="El archivo resultante es un PDF/UA-1 candidato; la validación posterior confirmará si cumple.",
    ),
    "verapdf_started": Explanation(
        title="Validación PDF/UA-1 iniciada",
        what="Lanzamos veraPDF, el validador oficial de la fundación PDF Association.",
        why="Es la única forma independiente de saber si el documento cumple realmente el estándar ISO 14289 (PDF/UA-1).",
        impact="Los fallos de veraPDF son los que determinan si hace falta un intento de corrección extra.",
    ),
    "verapdf_completed": Explanation(
        title="Validación PDF/UA-1 completada",
        what="veraPDF terminó y nos dio un veredicto: cumple / no cumple, puntuación, reglas pasadas.",
        why="Este es el corazón del 'score después': mide de forma objetiva la accesibilidad del PDF remediado.",
        impact="Si el score es bajo, entramos en la fase de reintentos con el LLM.",
    ),
    "verapdf_rule_failed": Explanation(
        title="Regla PDF/UA fallida",
        what="veraPDF detectó un problema concreto en una regla del estándar.",
        why="Cada regla mapea a un requisito medible (p. ej. 7.18.4 = formularios sin /Form).",
        impact="Lo veremos en 'issues pendientes' o se intentará arreglar en los reintentos.",
        user_level="warn",
    ),
    "fix_attempt_started": Explanation(
        title="Intento de corrección automática",
        what="Tomamos los fallos de veraPDF y los mandamos de vuelta al LLM para que proponga arreglos a la estructura.",
        why="Algunos fallos (títulos mal jerarquizados, figuras sin alt) se pueden corregir aplicando los feedback del validador.",
        impact="Si el score mejora > 70, paramos; si no, hacemos un segundo intento.",
        tags=["retry", "llm"],
    ),
    "fix_attempt_completed": Explanation(
        title="Intento de corrección completado",
        what="Reescribimos el PDF con las correcciones y lo volvimos a validar.",
        why="Queremos saber si el reintento efectivamente mejoró el score.",
        impact="Si mejoró, ese es el PDF final; si no, pasamos al siguiente intento o nos quedamos con el mejor hasta ahora.",
        tags=["retry"],
    ),
    "fix_attempt_failed": Explanation(
        title="Intento de corrección fallido",
        what="El LLM o el writer tiraron excepción durante el reintento.",
        why="No rompe el job: seguimos con la versión anterior y dejamos los issues como pendientes.",
        impact="El PDF final será el del intento anterior, con sus issues marcados para revisión manual.",
        user_level="warn",
        tags=["retry"],
    ),
    "font_issues_detected": Explanation(
        title="Fuentes sin /ToUnicode",
        what="Detectamos fuentes embebidas que no tienen mapa /ToUnicode.",
        why="Sin ese mapa, cuando copias texto del PDF o lo lee un screen reader, salen caracteres incorrectos o símbolos raros.",
        impact="No lo podemos arreglar automáticamente (requiere re-embeder la fuente); queda como issue pendiente.",
        user_level="warn",
        wcag="1.1.1",
    ),
    "contrast_unverifiable": Explanation(
        title="Contraste no verificable",
        what="Una o más páginas tienen contraste que no pudimos medir con confianza (p. ej. texto sobre imagen de fondo).",
        why="WCAG 1.4.3 exige 4.5:1 (texto normal) o 3:1 (texto grande). Si no podemos medirlo, no podemos certificar.",
        impact="Queda como issue pendiente para revisión manual con un medidor de contraste.",
        user_level="warn",
        wcag="1.4.3",
    ),
    "report_generated": Explanation(
        title="Informe final generado",
        what="Consolidamos scores, cambios aplicados e issues pendientes en el informe JSON/HTML.",
        why="Es el entregable que verás en pantalla y descargarás.",
        impact="Contiene la trazabilidad completa: qué se arregló, cómo y qué falta.",
    ),
    "pipeline_failed": Explanation(
        title="Error en el pipeline",
        what="Una excepción no controlada detuvo el procesamiento.",
        why="Puede ser un PDF corrupto, una dependencia caída (Gemma, veraPDF) o un bug nuestro.",
        impact="El job se marca como fallido y no podrás descargar un PDF accesible hasta que se reintente.",
        user_level="error",
    ),
    "activity_rate_limited": Explanation(
        title="Eventos coalescidos por rate-limit",
        what="Durante un pico, generamos más eventos info por segundo de lo permitido y se descartaron algunos.",
        why="Proteger el canal SSE de saturar al frontend cuando el pipeline hace muchas cosas a la vez.",
        impact="No afecta al resultado; sólo verás una línea resumen en vez de decenas de eventos casi idénticos.",
    ),
    "page_analysis_completed": Explanation(
        title="Análisis de página completado",
        what="Terminamos de clasificar todos los bloques de una página.",
        why="Podemos pasar a la siguiente página o, si es la última, a la consolidación global.",
        impact="Acumulamos estos resultados para construir el árbol de etiquetas completo al final.",
        tags=["llm"],
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Explanations for change_types recorded as BlockChange.
#
# `template` placeholders are filled at render time with the actual
# before/after/after-string if present.
# ─────────────────────────────────────────────────────────────────────────────
CHANGE_EXPLANATIONS: dict[str, Explanation] = {
    "title_set": Explanation(
        title="Título del documento añadido",
        what="Fijamos el título del documento en los metadatos XMP (dc:title).",
        why="Un PDF sin título se anuncia como «Documento sin título» en los lectores de pantalla, y el visor muestra el nombre del archivo en vez del título real.",
        impact="Ahora el lector de pantalla anuncia el título del documento al abrirlo.",
        wcag="2.4.2",
    ),
    "language_set": Explanation(
        title="Idioma del documento declarado",
        what="Escribimos /Lang en el catálogo y dc:language en XMP.",
        why="Sin idioma declarado, los lectores de pantalla usan la voz por defecto y pronuncian mal el contenido.",
        impact="El texto se leerá con la fonética correcta del idioma detectado.",
        wcag="3.1.1",
    ),
    "xmp_extended": Explanation(
        title="Metadatos XMP extendidos",
        what="Añadimos descripción, autor, herramienta creadora y productor a los metadatos XMP.",
        why="PDF/UA y motores de búsqueda de documentos accesibles leen estos campos para catalogar el archivo.",
        impact="El PDF queda auto-descrito: cualquier sistema puede leer de dónde viene y qué contiene sin abrirlo.",
    ),
    "page_labels_set": Explanation(
        title="Etiquetas de página añadidas",
        what="Creamos /PageLabels con numeración decimal 1..N.",
        why="Los lectores de pantalla anuncian «Página X de N» usando estas etiquetas, no la cuenta física de páginas.",
        impact="La navegación por página del lector coincide con los números visibles en el documento.",
        wcag="1.3.1",
    ),
    "bookmark_added": Explanation(
        title="Marcador (bookmark) añadido",
        what="Añadimos una entrada en el outline del PDF apuntando a un encabezado.",
        why="WCAG 2.4.1 exige una forma de saltar a secciones del documento; los marcadores son el equivalente PDF del índice.",
        impact="El panel de marcadores del visor ahora muestra la estructura de encabezados navegable.",
        wcag="2.4.1",
    ),
    "heading_tagged": Explanation(
        title="Encabezado etiquetado",
        what="El texto se marcó como /H1, /H2, /H3… en el árbol de etiquetas.",
        why="Sin tags de encabezado, el lector de pantalla no puede ofrecer el atajo «siguiente encabezado», clave para navegar documentos largos.",
        impact="Los atajos H/1/2/3 del lector de pantalla (NVDA, JAWS, VoiceOver) funcionarán en este documento.",
        wcag="1.3.1",
        pdfua="7.4",
    ),
    "alt_text_added": Explanation(
        title="Texto alternativo añadido",
        what="Añadimos /Alt en el StructElem /Figure con una descripción generada por el modelo.",
        why="Una imagen informativa sin /Alt es invisible para lectores de pantalla; sin /Alt ni marcado de decorativa, PDF/UA falla.",
        impact="El usuario escuchará la descripción de la imagen en lugar de silencio o del texto «imagen».",
        wcag="1.1.1",
        pdfua="7.18.1",
    ),
    "table_header_tagged": Explanation(
        title="Tabla etiquetada con encabezados",
        what="La tabla quedó con /Table > /TR > /TH (encabezados con /Scope Column o Row) y /TD.",
        why="Sin /TH con /Scope, los lectores de pantalla no pueden anunciar «columna: Precio» al navegar a una celda.",
        impact="Al moverte celda a celda en NVDA/JAWS, escucharás el encabezado de fila y columna que aplica.",
        wcag="1.3.1",
        pdfua="7.5",
    ),
    "list_structured": Explanation(
        title="Lista estructurada",
        what="El bloque se etiquetó como /L > /LI > (/Lbl + /LBody).",
        why="Sin esta estructura, la lista es sólo líneas de texto sueltas; con ella, el lector anuncia «1 de 5», «2 de 5»…",
        impact="El usuario sabrá cuántos ítems tiene la lista y podrá saltar entre ellos.",
        wcag="1.3.1",
        pdfua="7.6",
    ),
    "reading_order_fixed": Explanation(
        title="Orden de lectura corregido",
        what="Reorganizamos el árbol de etiquetas para que el contenido se anuncie en orden lógico (no en orden de posición física).",
        why="En documentos multi-columna o con cajas laterales, el orden visual no coincide con el orden de lectura deseado.",
        impact="El lector de pantalla sigue la secuencia pensada por el autor en vez de saltar de columna en columna.",
        wcag="1.3.2",
    ),
    "link_tagged": Explanation(
        title="Enlace etiquetado como /Link",
        what="La anotación /Link se envolvió en un StructElem /Link con /OBJR y /Contents.",
        why="Sin esto, el enlace es un área clicable pero 'invisible' para el árbol de etiquetas; PDF/UA §7.18.5 lo marca como fallo.",
        impact="El lector de pantalla anuncia el destino del enlace y el usuario puede activarlo con el atajo correspondiente.",
        wcag="2.4.4",
        pdfua="7.18.5",
    ),
    "form_field_tagged": Explanation(
        title="Campo de formulario etiquetado",
        what="Envolvimos el widget en un /Form StructElem con /OBJR, añadimos /TU (tooltip accesible) y pusimos /Tabs /S en la página.",
        why="PDF/UA §7.18.4 + WCAG 4.1.2: un campo sin /Form y sin /TU se anuncia como «casilla sin etiqueta».",
        impact="Al tabular por el formulario, el lector anuncia el nombre del campo y el orden sigue la estructura del documento.",
        wcag="4.1.2",
        pdfua="7.18.4",
    ),
    "abbreviation_expanded": Explanation(
        title="Abreviatura expandida con /E",
        what="Añadimos /E a un /Span con la versión expandida del acrónimo.",
        why="Sin /E, los lectores de pantalla deletrean letra a letra las siglas.",
        impact="El audio suena natural: «Organización de las Naciones Unidas» en vez de «O N U».",
        wcag="3.1.4",
        pdfua="7.9",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Explanations for remaining issue criterion/description pairs.
# Keyed by criterion code. Used to expand "description" with a human-friendly
# "how to fix manually" hint in the final report.
# ─────────────────────────────────────────────────────────────────────────────
ISSUE_HINTS: dict[str, str] = {
    "1.1.1": (
        "Revisa visualmente las imágenes del documento y decide si son "
        "informativas (añade descripción en el software original) o "
        "decorativas (márcalas como artefacto)."
    ),
    "1.3.1": (
        "Falta estructura semántica en algún punto. Con frecuencia se "
        "soluciona re-etiquetando manualmente en Acrobat Pro → Herramientas "
        "de accesibilidad → Modificar orden de lectura."
    ),
    "1.4.3": (
        "Usa un medidor de contraste (p. ej. WebAIM Contrast Checker) sobre "
        "las páginas señaladas. Si el texto está sobre una imagen, puede "
        "necesitar un fondo sólido o un ajuste de color."
    ),
    "3.1.1": (
        "Abre el PDF en Acrobat Pro → Archivo → Propiedades → Avanzado → "
        "Idioma y establece el idioma correcto del documento."
    ),
    "2.4.4": (
        "Revisa los enlaces del documento y asegúrate de que su texto "
        "sea descriptivo del destino, no genérico como «haz clic aquí»."
    ),
    "4.1.2": (
        "Abre el PDF en Acrobat Pro → Preparar formulario, selecciona cada "
        "campo y rellena el tooltip con una descripción del propósito."
    ),
    "7.18.1": (
        "Revisa las figuras sin /Alt en Acrobat → Herramientas → "
        "Accesibilidad → Establecer texto alternativo."
    ),
    "unicode_mapping": (
        "Las fuentes sin /ToUnicode no se pueden arreglar sin re-exportar "
        "el documento desde su origen (Word, InDesign, LaTeX…) con fuentes "
        "que embeban el mapa Unicode correctamente."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────
def for_code(code: str) -> Optional[dict]:
    """Return an explanation dict for an activity code, or None if unknown."""
    exp = CODE_EXPLANATIONS.get(code)
    return exp.to_dict() if exp else None


def for_change_type(change_type: str) -> Optional[dict]:
    """Return an explanation dict for a BlockChange.change_type, or None."""
    exp = CHANGE_EXPLANATIONS.get(change_type)
    return exp.to_dict() if exp else None


def wcag_info(criterion: str) -> Optional[dict]:
    """Return {name, level, plain} for a WCAG criterion like '1.1.1'."""
    return WCAG_CRITERIA.get(criterion)


def pdfua_info(rule: str) -> Optional[str]:
    """Return a plain-language description of a PDF/UA rule number."""
    return PDFUA_RULES.get(rule)


def issue_hint(criterion: Optional[str]) -> Optional[str]:
    if not criterion:
        return None
    return ISSUE_HINTS.get(criterion)
