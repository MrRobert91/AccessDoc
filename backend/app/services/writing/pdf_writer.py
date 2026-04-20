import pikepdf
import structlog
from pikepdf import Array, Dictionary, Name, String

from app.config import settings
from app.models.accessibility import BlockChange
from app.services.analysis.hierarchy_fixer import DocumentStructure
from app.services.writing.content_stream_tagger import (
    ContentStreamTagger,
    TagResult,
)

log = structlog.get_logger()


class AccessiblePDFWriter:
    """
    Writes a PDF/UA-1 tagged copy of the original document.

    When ENABLE_MCID_TAGGING is true, the page content streams are rewritten
    with BDC/EMC markers so each text fragment has an MCID, and those MCIDs
    are wired back to the StructElems via /K and /ParentTree.Nums.
    """

    def __init__(self, original_path: str, structure: DocumentStructure):
        self.original_path = original_path
        self.structure = structure
        self._applied_changes: list[BlockChange] = []
        self._tag_result: TagResult | None = None
        self._stats: dict = {
            "mcid_total": 0,
            "mcid_linked": 0,
            "struct_elems": 0,
            "per_page": {},
        }

    def write(self, output_path: str) -> None:
        with pikepdf.open(self.original_path, allow_overwriting_input=False) as pdf:
            self._set_document_metadata(pdf)
            self._mark_tagged(pdf)
            self._set_viewer_preferences(pdf)

            if settings.enable_mcid_tagging:
                try:
                    tagger = ContentStreamTagger()
                    self._tag_result = tagger.tag(pdf)
                    self._stats["mcid_total"] = self._tag_result.total_mcids
                    self._stats["per_page"] = {
                        p.page_index: p.mcid_count for p in self._tag_result.pages
                    }
                except Exception as e:
                    log.error("cs_tagging_failed", error=str(e))
                    self._tag_result = None

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
            mcid_total=self._stats["mcid_total"],
            mcid_linked=self._stats["mcid_linked"],
        )

    def get_applied_changes(self) -> list[BlockChange]:
        return self._applied_changes

    def get_write_stats(self) -> dict:
        return dict(self._stats)

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
        parent_tree_nums = Array()
        struct_root = pdf.make_indirect(Dictionary(
            Type=Name("/StructTreeRoot"),
            K=Array(),
            ParentTree=pdf.make_indirect(Dictionary(Nums=parent_tree_nums)),
            ParentTreeNextKey=len(pdf.pages),
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

        pages_by_idx: dict[int, dict] = {
            p.get("page_num", i): p
            for i, p in enumerate(self.structure.pages)
        }

        for page_idx in range(len(pdf.pages)):
            page_data = pages_by_idx.get(page_idx, {"blocks": []})
            sorted_blocks = sorted(
                page_data.get("blocks", []),
                key=lambda b: b.get("reading_order_position", 999),
            )

            pdf_page = pdf.pages[page_idx]
            mcid_count = (
                self._tag_result.mcids_for(page_idx)
                if self._tag_result else 0
            )

            extracted_tables = page_data.get("extracted_tables") or []
            table_blocks_idx = [
                i for i, b in enumerate(sorted_blocks)
                if b.get("role") == "Table"
            ]

            leaf_elems: list[tuple[dict, object]] = []
            for block_i, block in enumerate(sorted_blocks):
                role = block.get("role", "P")
                if role == "Artifact":
                    continue

                if role == "Table":
                    idx_in_tables = table_blocks_idx.index(block_i)
                    table_data = (
                        extracted_tables[idx_in_tables]
                        if idx_in_tables < len(extracted_tables)
                        else None
                    )
                    table_elem, leaves = self._make_table_elem(
                        pdf, block, table_data, page_idx, doc_elem,
                    )
                    if table_elem is not None:
                        doc_elem.K.append(table_elem)
                        self._stats["struct_elems"] += 1 + len(leaves)
                        leaf_elems.extend(leaves)
                        if block.get("was_changed") or table_data:
                            self._record_block_change(block, page_idx)
                    continue

                if role in ("L", "List"):
                    list_elem, leaves = self._make_list_elem(
                        pdf, block, page_idx, doc_elem,
                    )
                    if list_elem is not None:
                        doc_elem.K.append(list_elem)
                        self._stats["struct_elems"] += 1 + len(leaves)
                        leaf_elems.extend(leaves)
                        if block.get("was_changed"):
                            self._record_block_change(block, page_idx)
                    continue

                elem = self._make_elem(pdf, block, page_idx, doc_elem)
                if elem is not None:
                    doc_elem.K.append(elem)
                    leaf_elems.append((block, elem))
                    self._stats["struct_elems"] += 1
                    if block.get("was_changed"):
                        self._record_block_change(block, page_idx)

            # Append extracted tables that Gemma didn't identify as Table.
            leftover_tables = extracted_tables[len(table_blocks_idx):]
            for table_data in leftover_tables:
                synthetic_block = {
                    "id": f"table_synth_p{page_idx}_{id(table_data)}",
                    "role": "Table",
                    "confidence": 0.8,
                    "was_changed": True,
                }
                table_elem, leaves = self._make_table_elem(
                    pdf, synthetic_block, table_data, page_idx, doc_elem,
                )
                if table_elem is not None:
                    doc_elem.K.append(table_elem)
                    self._stats["struct_elems"] += 1 + len(leaves)
                    leaf_elems.extend(leaves)
                    self._record_block_change(synthetic_block, page_idx)

            page_parent_map = self._distribute_mcids(
                mcid_count, leaf_elems, pdf, doc_elem, page_idx, pdf_page,
            )

            if mcid_count > 0:
                entry = Array()
                for mcid_index in range(mcid_count):
                    owner = page_parent_map.get(mcid_index, doc_elem)
                    entry.append(owner)
                parent_tree_nums.append(page_idx)
                parent_tree_nums.append(entry)

    def _distribute_mcids(
        self,
        mcid_count: int,
        page_elems: list[tuple[dict, object]],
        pdf: pikepdf.Pdf,
        doc_elem,
        page_idx: int,
        pdf_page,
    ) -> dict[int, object]:
        """
        Distribute sequential MCIDs to StructElems proportionally to block
        text length in reading order. Each elem gets its share of MCIDs
        appended to K as MCR dicts referencing the page.

        Returns a map: mcid -> elem (used to build ParentTree.Nums entry).
        """
        mcid_to_elem: dict[int, object] = {}
        if mcid_count <= 0 or not page_elems:
            return mcid_to_elem

        weights: list[float] = []
        for block, _elem in page_elems:
            text = (block.get("text") or block.get("alt_text") or "").strip()
            weight = max(len(text), 1)
            if block.get("role") == "Figure":
                weight = max(weight, 4)
            weights.append(float(weight))

        total_w = sum(weights) or 1.0
        raw_shares = [w / total_w * mcid_count for w in weights]
        shares = [max(0, int(round(r))) for r in raw_shares]

        assigned = sum(shares)
        diff = mcid_count - assigned
        i = 0
        while diff != 0 and page_elems:
            idx = i % len(page_elems)
            if diff > 0:
                shares[idx] += 1
                diff -= 1
            else:
                if shares[idx] > 0:
                    shares[idx] -= 1
                    diff += 1
            i += 1
            if i > 10_000:
                break

        next_mcid = 0
        for (block, elem), share in zip(page_elems, shares):
            if share <= 0:
                continue
            k_array = elem.K
            for _ in range(share):
                if next_mcid >= mcid_count:
                    break
                k_array.append(pdf.make_indirect(Dictionary(
                    Type=Name("/MCR"),
                    Pg=pdf_page.obj,
                    MCID=next_mcid,
                )))
                mcid_to_elem[next_mcid] = elem
                self._stats["mcid_linked"] += 1
                next_mcid += 1

        while next_mcid < mcid_count:
            mcid_to_elem[next_mcid] = doc_elem
            doc_elem.K.append(pdf.make_indirect(Dictionary(
                Type=Name("/MCR"),
                Pg=pdf_page.obj,
                MCID=next_mcid,
            )))
            next_mcid += 1

        return mcid_to_elem

    def _make_table_elem(
        self,
        pdf,
        block: dict,
        table_data: dict | None,
        page_idx: int,
        parent,
    ):
        """
        Build /Table > /TR > (/TH with /Scope | /TD) tree.

        - First row becomes /TH with /Scope /Column when has_header_row.
        - First column becomes /TH with /Scope /Row when the shape looks
          like a matrix (>= 2 cols and >= 2 rows) so that NVDA announces
          column AND row headers during cell navigation.
        - For tables with BOTH row and column headers, /TH elems get /ID +
          data cells get /Headers pointing to their owning /TH ids.
        """
        rows = (table_data or {}).get("rows") or []
        has_header_row = bool((table_data or {}).get("has_header_row"))

        if not rows:
            table_elem = pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/Table"),
                P=parent,
                K=Array(),
            ))
            return table_elem, []

        num_cols = max((len(r) for r in rows), default=0)
        num_rows = len(rows)
        has_row_header = num_cols >= 2 and num_rows >= 2
        dual_header = has_header_row and has_row_header

        table_elem = pdf.make_indirect(Dictionary(
            Type=Name("/StructElem"),
            S=Name("/Table"),
            P=parent,
            K=Array(),
            A=Dictionary(O=Name("/Table"), Summary=String("")),
        ))

        leaves: list[tuple[dict, object]] = []
        col_header_ids: list[str | None] = [None] * num_cols
        row_header_ids: list[str | None] = [None] * num_rows

        for r_idx, row in enumerate(rows):
            tr_elem = pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/TR"),
                P=table_elem,
                K=Array(),
            ))
            table_elem.K.append(tr_elem)

            for c_idx in range(num_cols):
                cell_text = str(row[c_idx] if c_idx < len(row) else "") or ""
                is_col_header = has_header_row and r_idx == 0
                is_row_header = has_row_header and c_idx == 0 and r_idx > 0
                is_th = is_col_header or is_row_header

                cell_role = "TH" if is_th else "TD"
                cell_id: str | None = None
                cell_dict = Dictionary(
                    Type=Name("/StructElem"),
                    S=Name(f"/{cell_role}"),
                    P=tr_elem,
                    K=Array(),
                )

                if is_th:
                    scope = "Column" if is_col_header else "Row"
                    cell_dict.A = Dictionary(
                        O=Name("/Table"),
                        Scope=Name(f"/{scope}"),
                    )
                    if dual_header:
                        cell_id = f"th_p{page_idx}_r{r_idx}_c{c_idx}"
                        cell_dict.ID = String(cell_id)
                elif dual_header:
                    header_ids: list[str] = []
                    if c_idx < num_cols and col_header_ids[c_idx]:
                        header_ids.append(col_header_ids[c_idx])  # type: ignore[arg-type]
                    if r_idx < num_rows and row_header_ids[r_idx]:
                        header_ids.append(row_header_ids[r_idx])  # type: ignore[arg-type]
                    if header_ids:
                        cell_dict.A = Dictionary(
                            O=Name("/Table"),
                            Headers=Array([String(h) for h in header_ids]),
                        )

                cell_elem = pdf.make_indirect(cell_dict)
                tr_elem.K.append(cell_elem)

                if is_col_header and cell_id:
                    col_header_ids[c_idx] = cell_id
                if is_row_header and cell_id:
                    row_header_ids[r_idx] = cell_id

                leaf_block = {
                    "id": f"{block.get('id','t')}_r{r_idx}c{c_idx}",
                    "role": cell_role,
                    "text": cell_text,
                    "confidence": block.get("confidence", 0.85),
                }
                leaves.append((leaf_block, cell_elem))

        return table_elem, leaves

    def _make_list_elem(self, pdf, block: dict, page_idx: int, parent):
        """
        Build /L > /LI > (/Lbl + /LBody) tree.

        Strategy: split block text by newlines; for each line, peel off a
        leading marker token (•, -, *, digit, roman) into /Lbl and keep the
        rest as /LBody. Items without a marker are wrapped as /LI /LBody.
        """
        raw_text = (block.get("text") or "").strip()
        items: list[dict] = block.get("items") or []

        if not items and raw_text:
            items = [{"raw": ln} for ln in raw_text.splitlines() if ln.strip()]

        if not items:
            list_elem = pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/L"),
                P=parent,
                K=Array(),
                A=Dictionary(O=Name("/List"), ListNumbering=Name("/None")),
            ))
            return list_elem, []

        list_elem = pdf.make_indirect(Dictionary(
            Type=Name("/StructElem"),
            S=Name("/L"),
            P=parent,
            K=Array(),
            A=Dictionary(
                O=Name("/List"),
                ListNumbering=_list_numbering(items),
            ),
        ))

        leaves: list[tuple[dict, object]] = []
        for idx, item in enumerate(items):
            lbl_text, body_text = _split_list_item(item)

            li_elem = pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/LI"),
                P=list_elem,
                K=Array(),
            ))
            list_elem.K.append(li_elem)

            if lbl_text:
                lbl_elem = pdf.make_indirect(Dictionary(
                    Type=Name("/StructElem"),
                    S=Name("/Lbl"),
                    P=li_elem,
                    K=Array(),
                ))
                li_elem.K.append(lbl_elem)
                leaves.append((
                    {
                        "id": f"{block.get('id','l')}_i{idx}_lbl",
                        "role": "Lbl",
                        "text": lbl_text,
                        "confidence": block.get("confidence", 0.85),
                    },
                    lbl_elem,
                ))

            body_elem = pdf.make_indirect(Dictionary(
                Type=Name("/StructElem"),
                S=Name("/LBody"),
                P=li_elem,
                K=Array(),
            ))
            li_elem.K.append(body_elem)
            leaves.append((
                {
                    "id": f"{block.get('id','l')}_i{idx}_body",
                    "role": "LBody",
                    "text": body_text or lbl_text or "",
                    "confidence": block.get("confidence", 0.85),
                },
                body_elem,
            ))

        return list_elem, leaves

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
            Span=Name("/Span"),
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
            "List": "list_structured",
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
            role=role,
            pdfua_rule=_pdfua_rule_for(change_type),
            wcag_level="A",
        ))


def _pdfua_rule_for(change_type: str) -> str | None:
    return {
        "heading_tagged": "7.1-1",
        "alt_text_added": "7.18.1",
        "list_structured": "7.6",
        "table_header_tagged": "7.5",
    }.get(change_type)


_BULLET_CHARS = {"•", "◦", "●", "-", "–", "—", "*", "‣", "▪", "▫", "·"}
_BULLET_RE_PREFIX = tuple(_BULLET_CHARS)


def _list_numbering(items: list[dict]) -> Name:
    for item in items:
        raw = (item.get("raw") or item.get("label") or "").strip()
        if not raw:
            continue
        head = raw.split(None, 1)[0].rstrip(".)")
        if head.isdigit():
            return Name("/Decimal")
        if head and all(ch in "IVXLCDMivxlcdm" for ch in head):
            return Name("/UpperRoman") if head.isupper() else Name("/LowerRoman")
        if len(head) == 1 and head.isalpha():
            return Name("/UpperAlpha") if head.isupper() else Name("/LowerAlpha")
        break
    return Name("/Disc")


def _split_list_item(item: dict) -> tuple[str, str]:
    if "label" in item or "body" in item:
        return (item.get("label") or "").strip(), (item.get("body") or "").strip()

    raw = (item.get("raw") or "").strip()
    if not raw:
        return "", ""

    first = raw[0]
    if first in _BULLET_CHARS:
        return first, raw[1:].lstrip()

    if raw.startswith(_BULLET_RE_PREFIX):
        for marker in _BULLET_CHARS:
            if raw.startswith(marker):
                return marker, raw[len(marker):].lstrip()

    parts = raw.split(None, 1)
    if parts:
        head = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        stripped = head.rstrip(".)")
        if stripped.isdigit() or (
            stripped and all(ch in "IVXLCDMivxlcdm" for ch in stripped)
        ) or (len(stripped) == 1 and stripped.isalpha()):
            return head, tail

    return "", raw
