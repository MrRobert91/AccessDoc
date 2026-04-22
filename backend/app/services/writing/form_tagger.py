from dataclasses import dataclass, field

import pikepdf
import structlog
from pikepdf import Array, Dictionary, Name, String

from app.models.accessibility import BlockChange

log = structlog.get_logger()


@dataclass
class FormTagResult:
    fields_tagged: int = 0
    annotations_scanned: int = 0
    tab_orders_set: int = 0
    changes: list[BlockChange] = field(default_factory=list)


class FormFieldsTagger:
    """
    FR-A12: tag /Widget (form field) annotations so PDF/UA-1 announces them.

    For each AcroForm widget on a page:
      * ensure the field has `/TU` (tool tip / accessible name) — falling back
        to `/T` (partial field name) when absent
      * wrap it in a /Form StructElem whose /K contains an /OBJR
        referencing the annotation and the page
      * set /StructParent on the annotation
      * set the page's `/Tabs` entry to `/S` (structure order) — required
        by PDF/UA §7.18.3 so AT follow the tab order

    Assumes AccessiblePDFWriter has already built a StructTreeRoot with a
    /Document child and ParentTree.Nums populated for pages.
    """

    def __init__(self, document_language: str = "es"):
        self.document_language = document_language

    def tag(self, pdf: pikepdf.Pdf) -> FormTagResult:
        result = FormTagResult()

        struct_root = pdf.Root.get("/StructTreeRoot")
        if struct_root is None:
            return result

        parent_tree = struct_root.get("/ParentTree")
        if parent_tree is None:
            return result
        nums = parent_tree.get("/Nums")
        if nums is None:
            parent_tree.Nums = Array()
            nums = parent_tree.Nums

        doc_elem = self._find_doc_elem(struct_root)
        if doc_elem is None:
            return result

        next_key = int(struct_root.get("/ParentTreeNextKey", len(pdf.pages)))

        # AcroForm presence is a strong signal the doc has any fields.
        if "/AcroForm" not in pdf.Root:
            # Still iterate pages so pages without widgets get /Tabs set
            # defensively when there's nothing to tag.
            pass
        else:
            acroform = pdf.Root.AcroForm
            if "/NeedAppearances" not in acroform:
                acroform.NeedAppearances = False

        for page_idx, page in enumerate(pdf.pages):
            annots = page.get("/Annots")
            if annots is None:
                continue
            try:
                annot_list = list(annots)
            except Exception:
                continue

            page_had_widget = False
            for annot in annot_list:
                if not isinstance(annot, pikepdf.Dictionary):
                    continue
                result.annotations_scanned += 1
                subtype = annot.get("/Subtype")
                if subtype is None or str(subtype) != "/Widget":
                    continue
                page_had_widget = True

                name = self._accessible_name(annot)
                if not annot.get("/TU"):
                    annot.TU = String(name)

                form_elem = pdf.make_indirect(Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/Form"),
                    P=doc_elem,
                    Alt=String(name),
                    K=Array([
                        Dictionary(
                            Type=Name("/OBJR"),
                            Obj=annot,
                            Pg=page.obj,
                        ),
                    ]),
                ))
                if self.document_language:
                    form_elem.Lang = String(self.document_language)
                doc_elem.K.append(form_elem)

                annot.StructParent = next_key
                nums.append(next_key)
                nums.append(form_elem)
                next_key += 1
                result.fields_tagged += 1

                result.changes.append(BlockChange(
                    block_id=f"form_p{page_idx}_k{next_key - 1}",
                    page_num=page_idx + 1,
                    change_type="form_field_tagged",
                    criterion="4.1.2",
                    before="(untagged widget)",
                    after=name[:60],
                    confidence=0.9,
                    role="Form",
                    wcag_level="A",
                    pdfua_rule="7.18.4",
                ))

            if page_had_widget:
                # PDF/UA §7.18.3: every page must declare tab order as structure.
                page.Tabs = Name("/S")
                result.tab_orders_set += 1

        struct_root.ParentTreeNextKey = next_key
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
    def _accessible_name(annot: pikepdf.Dictionary) -> str:
        for key in ("/TU", "/T", "/TM"):
            val = annot.get(key)
            if val is not None:
                s = str(val).strip()
                if s:
                    return s
        ft = annot.get("/FT")
        if ft is not None:
            mapping = {"/Tx": "Texto", "/Btn": "Botón", "/Ch": "Selección", "/Sig": "Firma"}
            return mapping.get(str(ft), "Campo de formulario")
        return "Campo de formulario"
