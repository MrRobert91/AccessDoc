from dataclasses import dataclass, field

import pikepdf
import structlog
from pikepdf import Array, Dictionary, Name, String

from app.models.accessibility import BlockChange

log = structlog.get_logger()


@dataclass
class LinkTagResult:
    links_tagged: int = 0
    annotations_scanned: int = 0
    changes: list[BlockChange] = field(default_factory=list)


class LinkAnnotationsTagger:
    """
    FR-A7: tag /Link annotations so PDF/UA-1 considers them addressable.

    For each /Link annotation on a page:
      * wrap it in a /Link StructElem whose /K contains an /OBJR dict
        referencing the annotation object and the owning page
      * set /StructParent on the annotation to point back into ParentTree
      * ensure the annotation has /Contents so screen readers announce
        a destination (fallback to "Enlace a <URI>" or "Enlace interno")

    The tagger assumes the pdf already has a StructTreeRoot with a /Document
    child (produced by AccessiblePDFWriter._build_tag_tree) and a populated
    ParentTree.Nums array with keys 0..N-1 for the pages. It reserves new
    keys starting from ParentTreeNextKey and bumps it accordingly.
    """

    def __init__(self, document_language: str = "es"):
        self.document_language = document_language

    def tag(self, pdf: pikepdf.Pdf) -> LinkTagResult:
        result = LinkTagResult()

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

        for page_idx, page in enumerate(pdf.pages):
            annots = page.get("/Annots")
            if annots is None:
                continue
            try:
                annot_list = list(annots)
            except Exception:
                continue
            for annot in annot_list:
                if not isinstance(annot, pikepdf.Dictionary):
                    continue
                result.annotations_scanned += 1
                subtype = annot.get("/Subtype")
                if subtype is None or str(subtype) != "/Link":
                    continue

                contents = self._contents_for(annot)
                annot.Contents = String(contents)

                link_elem = pdf.make_indirect(Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/Link"),
                    P=doc_elem,
                    Alt=String(contents),
                    K=Array([
                        Dictionary(
                            Type=Name("/OBJR"),
                            Obj=annot,
                            Pg=page.obj,
                        ),
                    ]),
                ))
                if self.document_language:
                    link_elem.Lang = String(self.document_language)
                doc_elem.K.append(link_elem)

                annot.StructParent = next_key
                nums.append(next_key)
                nums.append(link_elem)
                next_key += 1
                result.links_tagged += 1

                result.changes.append(BlockChange(
                    block_id=f"link_p{page_idx}_k{next_key - 1}",
                    page_num=page_idx + 1,
                    change_type="link_tagged",
                    criterion="2.4.4",
                    before="(untagged link)",
                    after=contents[:60],
                    confidence=0.95,
                    role="Link",
                    wcag_level="A",
                    pdfua_rule="7.18.5",
                ))

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
    def _contents_for(annot: pikepdf.Dictionary) -> str:
        existing = annot.get("/Contents")
        if existing is not None:
            s = str(existing)
            if s.strip():
                return s.strip()
        action = annot.get("/A")
        if isinstance(action, pikepdf.Dictionary):
            uri = action.get("/URI")
            if uri is not None:
                return f"Enlace a {str(uri)}"
        if annot.get("/Dest") is not None:
            return "Enlace interno del documento"
        return "Enlace"
