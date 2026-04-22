"""
FR-A15: /E (expansion text) on /Span StructElems for detected abbreviations.

Opt-in via ENABLE_ABBREVIATION_EXPANSION. The expander walks the
Document elem and, for each /Span (or /P) whose /ActualText matches a
known acronym regex, appends /E with a spoken expansion so NVDA reads
"Organización de las Naciones Unidas" instead of "O N U".

The expansion map is seeded from the document's detected language and
can be overridden by passing a custom dict.
"""
from dataclasses import dataclass, field

import pikepdf
import structlog
from pikepdf import Dictionary, Name, String

from app.models.accessibility import BlockChange

log = structlog.get_logger()


@dataclass
class ExpansionResult:
    expansions_applied: int = 0
    changes: list[BlockChange] = field(default_factory=list)


DEFAULT_EXPANSIONS_ES = {
    "ONU": "Organización de las Naciones Unidas",
    "UE": "Unión Europea",
    "PDF": "Portable Document Format",
    "WCAG": "Web Content Accessibility Guidelines",
    "PDF/UA": "PDF Universal Accessibility",
    "OCR": "Reconocimiento Óptico de Caracteres",
    "EE.UU.": "Estados Unidos",
    "IA": "Inteligencia Artificial",
    "API": "Application Programming Interface",
    "ISO": "International Organization for Standardization",
}


class AbbreviationExpander:
    def __init__(self, expansions: dict[str, str] | None = None):
        self.expansions = expansions or DEFAULT_EXPANSIONS_ES

    def expand(self, pdf: pikepdf.Pdf) -> ExpansionResult:
        result = ExpansionResult()
        struct_root = pdf.Root.get("/StructTreeRoot")
        if struct_root is None:
            return result
        doc_elem = self._find_doc_elem(struct_root)
        if doc_elem is None:
            return result

        for elem in self._walk(doc_elem):
            text = self._text_of(elem)
            if not text:
                continue
            for token in text.split():
                clean = token.strip(".,;:()[]").upper()
                if clean in self.expansions:
                    elem.E = String(self.expansions[clean])
                    result.expansions_applied += 1
                    result.changes.append(BlockChange(
                        block_id=f"abbrev_{clean}",
                        page_num=0,
                        change_type="abbreviation_expanded",
                        criterion="3.1.4",
                        before=clean,
                        after=self.expansions[clean],
                        confidence=0.9,
                        role="Span",
                        wcag_level="AAA",
                        pdfua_rule="7.9",
                    ))
                    break
        return result

    @staticmethod
    def _find_doc_elem(struct_root):
        k = struct_root.get("/K")
        if k is None:
            return None
        try:
            kids = list(k) if not isinstance(k, pikepdf.Dictionary) else [k]
        except Exception:
            return None
        for kid in kids:
            if isinstance(kid, pikepdf.Dictionary) and str(kid.get("/S", "")) == "/Document":
                return kid
        return kids[0] if kids else None

    @staticmethod
    def _walk(elem):
        stack = [elem]
        while stack:
            cur = stack.pop()
            if not isinstance(cur, pikepdf.Dictionary):
                continue
            s = cur.get("/S")
            if s is not None and str(s) in ("/P", "/Span", "/H1", "/H2", "/H3", "/H4"):
                yield cur
            k = cur.get("/K")
            if k is None:
                continue
            try:
                children = list(k)
            except TypeError:
                children = [k]
            for child in children:
                if isinstance(child, pikepdf.Dictionary):
                    stack.append(child)

    @staticmethod
    def _text_of(elem: pikepdf.Dictionary) -> str:
        actual = elem.get("/ActualText") or elem.get("/Alt") or elem.get("/T")
        if actual is not None:
            return str(actual)
        return ""
