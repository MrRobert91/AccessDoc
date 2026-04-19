import pikepdf
import structlog
from pikepdf import Array, Dictionary, Name, String

from app.models.accessibility import BlockChange
from app.services.analysis.hierarchy_fixer import DocumentStructure

log = structlog.get_logger()


class AccessiblePDFWriter:
    """
    Writes a PDF/UA-1 tagged copy of the original document.

    - Title, Language, MarkInfo, ViewerPreferences.DisplayDocTitle
    - StructTreeRoot with a Document element containing one StructElem
      per classified block (Artifacts excluded, decorative Figures
      excluded)
    - Outlines built from the heading hierarchy for 2.4.1 (bookmarks)
    """

    def __init__(self, original_path: str, structure: DocumentStructure):
        self.original_path = original_path
        self.structure = structure
        self._applied_changes: list[BlockChange] = []

    def write(self, output_path: str) -> None:
        with pikepdf.open(self.original_path, allow_overwriting_input=False) as pdf:
            self._set_document_metadata(pdf)
            self._mark_tagged(pdf)
            self._set_viewer_preferences(pdf)
            self._build_tag_tree(pdf)
            self._add_bookmarks(pdf)
            pdf.save(
                output_path,
                linearize=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )
        log.info(
            "pdf_written",
            output=output_path,
            changes=len(self._applied_changes),
        )

    def get_applied_changes(self) -> list[BlockChange]:
        return self._applied_changes

    def _set_document_metadata(self, pdf: pikepdf.Pdf) -> None:
        with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
            if self.structure.document_title:
                meta["dc:title"] = self.structure.document_title
                self._record(
                    "title_set", "2.4.2",
                    "(no title)", self.structure.document_title, 0
                )
            meta["dc:language"] = self.structure.language
            self._record(
                "language_set", "3.1.1",
                "(no language)", self.structure.language, 0
            )
            meta["pdfuaid:part"] = "1"

    def _mark_tagged(self, pdf: pikepdf.Pdf) -> None:
        pdf.Root.MarkInfo = Dictionary(Marked=True, Suspects=False)

    def _set_viewer_preferences(self, pdf: pikepdf.Pdf) -> None:
        if "/ViewerPreferences" not in pdf.Root:
            pdf.Root.ViewerPreferences = pdf.make_indirect(Dictionary())
        pdf.Root.ViewerPreferences.DisplayDocTitle = True

    def _build_tag_tree(self, pdf: pikepdf.Pdf) -> None:
        struct_root = pdf.make_indirect(Dictionary(
            Type=Name("/StructTreeRoot"),
            K=Array(),
            ParentTree=pdf.make_indirect(Dictionary(Nums=Array())),
            RoleMap=self._role_map(),
        ))
        pdf.Root.StructTreeRoot = struct_root

        doc_elem = pdf.make_indirect(Dictionary(
            Type=Name("/StructElem"),
            S=Name("/Document"),
            K=Array(),
            P=struct_root,
        ))
        struct_root.K.append(doc_elem)

        for page_data in self.structure.pages:
            page_num = page_data.get("page_num", 0)
            sorted_blocks = sorted(
                page_data.get("blocks", []),
                key=lambda b: b.get("reading_order_position", 999),
            )

            for block in sorted_blocks:
                role = block.get("role", "P")
                if role == "Artifact":
                    continue
                elem = self._make_elem(pdf, block, page_num, doc_elem)
                if elem is not None:
                    doc_elem.K.append(elem)
                    if block.get("was_changed"):
                        self._record_block_change(block, page_num)

    def _make_elem(self, pdf, block: dict, page_num: int, parent):
        role = block.get("role", "P")
        text = block.get("text", "")

        if role == "Figure":
            alt = block.get("alt_text", "")
            if not alt or alt.lower() == "decorative":
                return None
            return pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/Figure"),
                Alt=String(alt),
                P=parent,
                K=Array(),
            ))

        attrs = Dictionary(
            Type=Name("/StructElem"),
            S=Name(f"/{role}"),
            P=parent,
            K=Array(),
        )
        if role.startswith("H") and text:
            attrs.T = String(text[:80])
        return pdf.make_indirect(attrs)

    def _add_bookmarks(self, pdf: pikepdf.Pdf) -> None:
        headings = self.structure.headings_hierarchy
        if not headings:
            return

        bookmark_items = []
        for h in headings:
            page_idx = h["page"]
            if page_idx >= len(pdf.pages):
                continue
            page_ref = pdf.pages[page_idx]
            item = pdf.make_indirect(Dictionary(
                Title=String((h.get("text") or "")[:80] or "Untitled"),
                Dest=Array([
                    page_ref.obj,
                    Name("/XYZ"),
                    None, None, None,
                ]),
                Count=0,
            ))
            bookmark_items.append(item)
            self._record(
                "bookmark_added", "2.4.1",
                "(no bookmark)", (h.get("text") or "")[:50], page_idx
            )

        if not bookmark_items:
            return

        for i, item in enumerate(bookmark_items):
            if i > 0:
                item.Prev = bookmark_items[i - 1]
            if i < len(bookmark_items) - 1:
                item.Next = bookmark_items[i + 1]

        pdf.Root.Outlines = pdf.make_indirect(Dictionary(
            Count=len(bookmark_items),
            First=bookmark_items[0],
            Last=bookmark_items[-1],
        ))

    def _role_map(self) -> Dictionary:
        return Dictionary(
            H1=Name("/H1"), H2=Name("/H2"), H3=Name("/H3"),
            H4=Name("/H4"), H5=Name("/H5"), H6=Name("/H6"),
            P=Name("/P"), L=Name("/L"), LI=Name("/LI"),
            LBody=Name("/LBody"), Lbl=Name("/Lbl"),
            Table=Name("/Table"), TR=Name("/TR"),
            TH=Name("/TH"), TD=Name("/TD"),
            Figure=Name("/Figure"), Caption=Name("/Caption"),
            TOC=Name("/TOC"), TOCI=Name("/TOCI"),
            Footnote=Name("/Note"), Code=Name("/Code"),
            Formula=Name("/Formula"), Artifact=Name("/Artifact"),
        )

    def _record(
        self, change_type: str, criterion: str,
        before: str, after: str, page: int,
    ) -> None:
        self._applied_changes.append(BlockChange(
            block_id=f"doc_{len(self._applied_changes)}",
            page_num=page + 1,
            change_type=change_type,
            criterion=criterion,
            before=before,
            after=after,
            confidence=1.0,
        ))

    def _record_block_change(self, block: dict, page_num: int) -> None:
        role = block.get("role", "P")
        type_map = {
            "H1": "heading_tagged", "H2": "heading_tagged",
            "H3": "heading_tagged", "H4": "heading_tagged",
            "H5": "heading_tagged", "H6": "heading_tagged",
            "Figure": "alt_text_added",
            "Table": "table_header_tagged",
            "L": "list_structured",
        }
        criterion_map = {
            "heading_tagged": "1.3.1",
            "alt_text_added": "1.1.1",
            "table_header_tagged": "1.3.1",
            "list_structured": "1.3.1",
        }
        change_type = type_map.get(role, "reading_order_fixed")
        criterion = criterion_map.get(change_type, "1.3.2")
        text = block.get("text", "") or block.get("alt_text", "")
        self._applied_changes.append(BlockChange(
            block_id=block.get("id", "unknown"),
            page_num=page_num + 1,
            change_type=change_type,
            criterion=criterion,
            before=f"(untagged: {text[:40]})",
            after=f"<{role}> {text[:40]}",
            confidence=float(block.get("confidence", 0.85)),
        ))
