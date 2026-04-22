"""
Deterministic narrative generator for the remediation report.

Given the raw artifacts of a job (changes, remaining issues, activity log,
scores), it assembles a chronological story in plain Spanish that a
non-expert can read to understand what happened. No LLM is involved: the
narrative is built from templates filled with real data so the output is
predictable and fast.

The narrative is returned as a list of sections:

    [
        {"heading": "El documento original",     "paragraphs": [...]},
        {"heading": "Qué detectamos",             "paragraphs": [...]},
        {"heading": "Qué hicimos",                "paragraphs": [...], "steps": [...]},
        {"heading": "Qué queda pendiente",        "paragraphs": [...], "items": [...]},
        {"heading": "Resultado",                  "paragraphs": [...]},
    ]

The frontend renders the list top-to-bottom.
"""

from typing import Any, Optional

from app.services.observability.explanations import (
    for_change_type,
    issue_hint,
    wcag_info,
)


# Order in which change_types are narrated. Everything not in this list
# falls through to the end grouped by count.
_NARRATIVE_ORDER: list[str] = [
    "title_set",
    "language_set",
    "xmp_extended",
    "page_labels_set",
    "heading_tagged",
    "reading_order_fixed",
    "alt_text_added",
    "table_header_tagged",
    "list_structured",
    "link_tagged",
    "form_field_tagged",
    "abbreviation_expanded",
    "bookmark_added",
]


def build_narrative(
    filename: Optional[str],
    page_count: int,
    before_score: Optional[dict],
    after_score: Optional[dict],
    changes: list[dict],
    remaining: list[dict],
    activity: list[dict],
    processing_time: Optional[float],
) -> list[dict]:
    sections: list[dict] = []

    # 1. El documento original
    sections.append(_section_original(filename, page_count, activity))

    # 2. Qué detectamos
    sections.append(_section_detected(activity, changes, before_score))

    # 3. Qué hicimos, paso a paso
    sections.append(_section_actions(changes, activity))

    # 4. Qué queda pendiente
    sections.append(_section_pending(remaining))

    # 5. Resultado
    sections.append(_section_result(before_score, after_score, processing_time))

    return sections


# ─────────────────────────────────────────────────────────────────────────────

def _section_original(
    filename: Optional[str],
    page_count: int,
    activity: list[dict],
) -> dict:
    ext = _find_event(activity, "upload_received") or {}
    size_mb = ((ext.get("details") or {}).get("size_mb"))
    opened = _find_event(activity, "pdf_opened") or {}
    opened_details = opened.get("details") or {}

    name = filename or "tu documento"
    paragraphs = [
        f"Subiste «{name}»"
        + (f" ({size_mb:.2f} MB)" if size_mb else "")
        + f": un PDF de {page_count} página"
        + ("s" if page_count != 1 else "")
        + "."
    ]

    if opened_details.get("has_existing_tags") is True:
        paragraphs.append(
            "El documento ya venía parcialmente etiquetado (tenía un árbol "
            "de tags), pero con frecuencia estas etiquetas tienen errores "
            "u omisiones, así que lo reconstruimos desde cero."
        )
    elif opened_details.get("has_existing_tags") is False:
        paragraphs.append(
            "El documento no tenía ningún árbol de tags: para un lector "
            "de pantalla era una hoja en blanco con formas. Toda la "
            "estructura semántica que verás en el resultado la hemos "
            "añadido nosotros."
        )

    if opened_details.get("needs_ocr") is True:
        paragraphs.append(
            "Detectamos que las páginas son mayoritariamente imágenes "
            "(texto escaneado, no seleccionable). Ejecutamos OCR antes de "
            "cualquier otra cosa para que el resto del pipeline pudiera "
            "trabajar sobre texto real."
        )

    return {"heading": "El documento original", "paragraphs": paragraphs}


def _section_detected(
    activity: list[dict],
    changes: list[dict],
    before_score: Optional[dict],
) -> dict:
    paragraphs: list[str] = []
    bullets: list[str] = []

    title_change = _first_change(changes, "title_set")
    if title_change:
        before = title_change.get("before") or "(sin título)"
        if "no title" in str(before).lower() or "sin título" in str(before).lower():
            bullets.append(
                "No tenía título declarado en los metadatos. "
                "Los lectores de pantalla lo habrían anunciado como "
                "«documento sin título»."
            )

    lang_change = _first_change(changes, "language_set")
    if lang_change and "no language" in str(lang_change.get("before", "")).lower():
        bullets.append(
            "No tenía el idioma declarado, así que los lectores de "
            "pantalla habrían usado la voz por defecto del sistema "
            "con la pronunciación equivocada."
        )

    pages_ocr = 0
    for e in activity:
        if e.get("code") == "ocr_completed":
            pages_ocr = (e.get("details") or {}).get("pages", 0) or 0

    if pages_ocr:
        bullets.append(
            f"Tenía texto como imagen en {pages_ocr} página(s): invisible "
            "para tecnologías de asistencia sin OCR."
        )

    figure_changes = [c for c in changes if c.get("change_type") == "alt_text_added"]
    if figure_changes:
        bullets.append(
            f"Tenía {len(figure_changes)} figura(s) informativas sin texto "
            "alternativo: sin describir, serían inaudibles en un lector "
            "de pantalla."
        )

    table_changes = [c for c in changes if c.get("change_type") == "table_header_tagged"]
    if table_changes:
        bullets.append(
            f"Tenía {len(table_changes)} tabla(s) sin encabezados marcados: "
            "al navegar celda a celda, el lector no habría podido decir "
            "«columna: Precio»."
        )

    link_changes = [c for c in changes if c.get("change_type") == "link_tagged"]
    if link_changes:
        bullets.append(
            f"Tenía {len(link_changes)} enlace(s) que no estaban anunciados "
            "al árbol de etiquetas: áreas clicables invisibles para "
            "tecnologías de asistencia."
        )

    form_changes = [c for c in changes if c.get("change_type") == "form_field_tagged"]
    if form_changes:
        bullets.append(
            f"Tenía {len(form_changes)} campo(s) de formulario sin /TU "
            "(tooltip accesible): al tabular se habrían anunciado como "
            "«casilla sin etiqueta»."
        )

    low_conf = sum(
        1 for e in activity if e.get("code") == "low_confidence_fallback"
    )
    if low_conf:
        bullets.append(
            f"En {low_conf} bloque(s), el modelo no estaba seguro del rol; "
            "aplicamos heurísticas de respaldo (fuente, negrita, posición)."
        )

    if not bullets:
        bullets.append(
            "No detectamos problemas estructurales graves — el documento "
            "ya tenía la mayor parte de la base necesaria."
        )

    score_pct = (before_score or {}).get("overall")
    if score_pct is not None:
        paragraphs.append(
            f"La puntuación inicial de accesibilidad del documento fue "
            f"{score_pct}/100. Esto es lo que encontramos al analizarlo:"
        )
    else:
        paragraphs.append("Esto es lo que encontramos al analizarlo:")

    return {
        "heading": "Qué detectamos",
        "paragraphs": paragraphs,
        "items": bullets,
    }


def _section_actions(changes: list[dict], activity: list[dict]) -> dict:
    """Chronological list of actions taken, grouped by change_type."""
    steps: list[dict] = []

    # Mention OCR explicitly when it ran.
    for e in activity:
        if e.get("code") == "ocr_completed":
            details = e.get("details") or {}
            steps.append({
                "number": len(steps) + 1,
                "title": "Ejecutamos OCR",
                "what": (
                    "Reconocimos el texto de las páginas escaneadas con "
                    f"Tesseract (idioma: {details.get('language', 'auto')})."
                ),
                "why": (
                    "Sin OCR, el contenido de un documento escaneado es "
                    "totalmente invisible para lectores de pantalla. A "
                    "partir de este paso, el resto del pipeline trabaja "
                    "sobre texto real en lugar de sobre imágenes."
                ),
                "examples": [],
                "wcag": "1.1.1",
            })
            break

    # Group changes by type in the narrative order.
    by_type: dict[str, list[dict]] = {}
    for c in changes:
        by_type.setdefault(c.get("change_type", "other"), []).append(c)

    ordered_types = [t for t in _NARRATIVE_ORDER if t in by_type]
    for t in by_type:
        if t not in ordered_types:
            ordered_types.append(t)

    for change_type in ordered_types:
        group = by_type.get(change_type, [])
        if not group:
            continue
        exp = for_change_type(change_type) or {}
        examples = []
        for c in group[:3]:
            page = c.get("page_num") or c.get("page")
            after = (c.get("after") or "").strip()
            if change_type == "alt_text_added" and after:
                examples.append(f"pág. {page}: «{after[:80]}»")
            elif change_type == "title_set" and after:
                examples.append(f"título añadido: «{after[:80]}»")
            elif change_type == "language_set" and after:
                examples.append(f"idioma declarado: {after}")
            elif change_type == "heading_tagged":
                role = c.get("role", "H?")
                examples.append(
                    f"pág. {page}: {role} «{(after or '').replace('(untagged: ', '').replace(')', '')[:60]}»"
                )
            elif change_type == "link_tagged" and after:
                examples.append(f"pág. {page}: {after[:80]}")
            elif change_type == "form_field_tagged" and after:
                examples.append(f"pág. {page}: campo «{after[:60]}»")
            elif change_type == "abbreviation_expanded":
                before = c.get("before", "")
                examples.append(f"{before} → «{after[:60]}»")
            elif change_type == "table_header_tagged":
                examples.append(f"pág. {page}: tabla etiquetada con /TH + /Scope")
            elif change_type == "bookmark_added" and after:
                examples.append(f"pág. {page}: «{after[:60]}»")

        steps.append({
            "number": len(steps) + 1,
            "title": (
                f"{exp.get('title', change_type.replace('_', ' ').capitalize())}"
                + (f" ({len(group)})" if len(group) > 1 else "")
            ),
            "what": exp.get("what") or "",
            "why": exp.get("why") or "",
            "impact": exp.get("impact") or "",
            "wcag": exp.get("wcag"),
            "pdfua": exp.get("pdfua"),
            "count": len(group),
            "examples": examples,
        })

    # Retries
    retries = [e for e in activity if e.get("code") == "fix_attempt_completed"]
    if retries:
        last = retries[-1]
        details = last.get("details") or {}
        steps.append({
            "number": len(steps) + 1,
            "title": "Reintento de corrección automática",
            "what": (
                f"Hicimos {len(retries)} ronda(s) extra con el LLM para "
                "corregir los fallos que veraPDF detectó tras la "
                "primera escritura."
            ),
            "why": (
                "Algunos problemas (jerarquía de encabezados, figuras sin "
                "alt) se pueden arreglar dando al modelo el feedback del "
                "validador y pidiendo una nueva estructura."
            ),
            "impact": (
                f"Puntuación tras los reintentos: {details.get('new_score', '?')}."
            ),
            "examples": [],
        })

    paragraphs = (
        ["Esto es todo lo que tocamos, en el orden en que sucedió:"]
        if steps
        else ["El documento no necesitaba cambios estructurales."]
    )

    return {
        "heading": "Qué hicimos, paso a paso",
        "paragraphs": paragraphs,
        "steps": steps,
    }


def _section_pending(remaining: list[dict]) -> dict:
    items: list[dict] = []
    for i in remaining:
        criterion = i.get("criterion")
        info = wcag_info(criterion) if criterion else None
        items.append({
            "description": i.get("description") or "",
            "criterion": criterion,
            "criterion_name": info.get("name") if info else None,
            "criterion_level": info.get("level") if info else None,
            "severity": i.get("severity"),
            "count": i.get("count"),
            "hint": issue_hint(criterion),
        })

    if not items:
        return {
            "heading": "Qué queda pendiente",
            "paragraphs": [
                "No quedan problemas sin resolver: el documento cumple "
                "todos los criterios automatizables."
            ],
            "items": [],
        }

    return {
        "heading": "Qué queda pendiente",
        "paragraphs": [
            "Los siguientes puntos requieren tu intervención manual. "
            "No los hemos arreglado porque dependen de decisiones "
            "editoriales (¿es decorativa esta imagen?) o de re-exportar "
            "el documento desde su origen."
        ],
        "items": items,
    }


def _section_result(
    before: Optional[dict],
    after: Optional[dict],
    processing_time: Optional[float],
) -> dict:
    before_pct = (before or {}).get("overall") or 0
    after_pct = (after or {}).get("overall") or 0
    delta = after_pct - before_pct

    paragraphs = [
        f"Tu documento pasó de una puntuación de accesibilidad de "
        f"{before_pct}/100 a {after_pct}/100 "
        f"({'+' if delta >= 0 else ''}{delta} puntos)."
    ]

    if (after or {}).get("pdfua1_compliant"):
        paragraphs.append(
            "El PDF resultante es conforme con PDF/UA-1 (ISO 14289-1) "
            "según la validación de veraPDF."
        )
    else:
        paragraphs.append(
            "El PDF resultante todavía no cumple PDF/UA-1 en todos sus "
            "requisitos. Revisa «Qué queda pendiente» para ver qué falta."
        )

    if (after or {}).get("wcag21_aa_compliant"):
        paragraphs.append(
            "Cumple también los criterios aplicables a PDF de WCAG 2.1 "
            "nivel AA."
        )

    if processing_time:
        paragraphs.append(
            f"Tiempo total de procesamiento: {processing_time:.1f} segundos."
        )

    return {"heading": "Resultado", "paragraphs": paragraphs}


# ─────────────────────────────────────────────────────────────────────────────

def _find_event(activity: list[dict], code: str) -> Optional[dict]:
    for e in activity:
        if e.get("code") == code:
            return e
    return None


def _first_change(changes: list[dict], change_type: str) -> Optional[dict]:
    for c in changes:
        if c.get("change_type") == change_type:
            return c
    return None
