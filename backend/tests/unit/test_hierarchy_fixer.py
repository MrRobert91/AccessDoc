import pytest
from app.services.analysis.hierarchy_fixer import HierarchyFixer


class TestHierarchyFixer:
    def setup_method(self):
        self.fixer = HierarchyFixer()

    def _pages(self, blocks):
        return [{"page_num": 0, "language": "es", "blocks": blocks}]

    def test_no_change_when_hierarchy_correct(self):
        pages = self._pages([
            {"role": "H1", "text": "Title", "id": "b0"},
            {"role": "H2", "text": "Section", "id": "b1"},
            {"role": "H3", "text": "Subsection", "id": "b2"},
            {"role": "P", "text": "Paragraph", "id": "b3"},
        ])
        result = self.fixer.consolidate(pages, 1)
        roles = [b["role"] for b in result.pages[0]["blocks"]]
        assert roles == ["H1", "H2", "H3", "P"]

    def test_fixes_h1_to_h3_skip(self):
        pages = self._pages([
            {"role": "H1", "text": "Title", "id": "b0"},
            {"role": "H3", "text": "Section", "id": "b1"},
        ])
        result = self.fixer.consolidate(pages, 1)
        roles = [b["role"] for b in result.pages[0]["blocks"]]
        assert "H3" not in roles
        assert "H2" in roles

    def test_only_one_h1_across_all_pages(self):
        pages = [
            {"page_num": 0, "language": "es",
             "blocks": [{"role": "H1", "text": "First H1", "id": "b0"}]},
            {"page_num": 1, "language": "es",
             "blocks": [{"role": "H1", "text": "Second H1", "id": "b1"}]},
        ]
        result = self.fixer.consolidate(pages, 2)
        all_h1 = [
            b for page in result.pages
            for b in page["blocks"] if b["role"] == "H1"
        ]
        assert len(all_h1) == 1

    def test_artifact_blocks_not_modified(self):
        pages = self._pages([
            {"role": "Artifact", "text": "Page 1", "id": "b0"},
            {"role": "H1", "text": "Title", "id": "b1"},
        ])
        result = self.fixer.consolidate(pages, 1)
        artifact = [b for b in result.pages[0]["blocks"] if b["role"] == "Artifact"]
        assert len(artifact) == 1
        assert artifact[0]["text"] == "Page 1"

    def test_document_title_extracted_from_first_h1(self):
        pages = self._pages([
            {"role": "H1", "text": "Annual Report 2024", "id": "b0"},
        ])
        result = self.fixer.consolidate(pages, 1)
        assert result.document_title == "Annual Report 2024"

    def test_language_detected_from_pages(self):
        pages = [
            {"page_num": 0, "language": "es", "blocks": []},
            {"page_num": 1, "language": "es", "blocks": []},
            {"page_num": 2, "language": "en", "blocks": []},
        ]
        result = self.fixer.consolidate(pages, 3)
        assert result.language == "es"

    def test_headings_hierarchy_built_correctly(self):
        pages = self._pages([
            {"role": "H1", "text": "Document", "id": "b0"},
            {"role": "H2", "text": "Chapter 1", "id": "b1"},
            {"role": "H3", "text": "Section 1.1", "id": "b2"},
        ])
        result = self.fixer.consolidate(pages, 1)
        assert len(result.headings_hierarchy) == 3
        levels = [h["level"] for h in result.headings_hierarchy]
        assert levels == [1, 2, 3]

    def test_fallback_title_when_no_h1(self):
        pages = self._pages([
            {"role": "P", "text": "Some paragraph text", "id": "b0"},
        ])
        result = self.fixer.consolidate(pages, 1)
        assert result.document_title == "Some paragraph text"

    def test_default_language_when_none_specified(self):
        pages = [{"page_num": 0, "blocks": []}]
        result = self.fixer.consolidate(pages, 1)
        assert result.language == "es"

    def test_demoted_h1_marked_as_changed(self):
        pages = [
            {"page_num": 0, "language": "es",
             "blocks": [{"role": "H1", "text": "Keep", "id": "b0"}]},
            {"page_num": 1, "language": "es",
             "blocks": [{"role": "H1", "text": "Demote", "id": "b1"}]},
        ]
        result = self.fixer.consolidate(pages, 2)
        demoted = result.pages[1]["blocks"][0]
        assert demoted["role"] == "H2"
        assert demoted.get("was_changed") is True
