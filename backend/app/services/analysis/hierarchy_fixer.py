from dataclasses import dataclass, field


@dataclass
class DocumentStructure:
    pages: list[dict]
    document_title: str
    language: str
    headings_hierarchy: list[dict] = field(default_factory=list)
    page_count: int = 0


class HierarchyFixer:
    """
    Consolidates heading hierarchy across all pages.
    Fixes: multiple H1s, skipped heading levels, missing title/language.
    """

    def consolidate(
        self, page_structures: list[dict], page_count: int
    ) -> DocumentStructure:
        document_title = self._find_document_title(page_structures)
        language = self._detect_language(page_structures)
        fixed_pages = self._fix_heading_levels(page_structures)

        headings = [
            {
                "text": block.get("text", ""),
                "level": int(block["role"][1]),
                "page": page_idx,
            }
            for page_idx, page in enumerate(fixed_pages)
            for block in page.get("blocks", [])
            if (
                isinstance(block.get("role"), str)
                and block["role"].startswith("H")
                and len(block["role"]) == 2
                and block["role"][1].isdigit()
                and block.get("text")
            )
        ]

        return DocumentStructure(
            pages=fixed_pages,
            document_title=document_title,
            language=language,
            headings_hierarchy=headings,
            page_count=page_count,
        )

    def _find_document_title(self, pages: list[dict]) -> str:
        if not pages:
            return "Document"
        first_page_blocks = pages[0].get("blocks", [])
        h1_blocks = [b for b in first_page_blocks if b.get("role") == "H1"]
        if h1_blocks:
            return (h1_blocks[0].get("text") or "Document")[:200]
        for b in first_page_blocks:
            if b.get("role") != "Artifact" and b.get("text"):
                return b["text"][:200]
        return "Document"

    def _detect_language(self, pages: list[dict]) -> str:
        langs = [p.get("language") for p in pages if p.get("language")]
        if not langs:
            return "es"
        return max(set(langs), key=langs.count)

    def _fix_heading_levels(self, pages: list[dict]) -> list[dict]:
        # Pass 1: normalize multiple H1 occurrences.
        h1_seen = False
        for page in pages:
            for block in page.get("blocks", []):
                if block.get("role") == "H1":
                    if h1_seen:
                        block["role"] = "H2"
                        block["was_changed"] = True
                    else:
                        h1_seen = True

        # Pass 2: fix skipped heading levels (e.g., H1 → H3 becomes H1 → H2).
        current_level = 0
        for page in pages:
            for block in page.get("blocks", []):
                role = block.get("role", "")
                if not (
                    isinstance(role, str)
                    and role.startswith("H")
                    and len(role) == 2
                    and role[1].isdigit()
                ):
                    continue
                level = int(role[1])
                if level > current_level + 1 and current_level > 0:
                    corrected = current_level + 1
                    block["role"] = f"H{corrected}"
                    block["was_changed"] = True
                current_level = int(block["role"][1])

        return pages
