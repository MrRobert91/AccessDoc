from dataclasses import dataclass, field

import pikepdf
import structlog

log = structlog.get_logger()


TEXT_SHOW_OPS = {"Tj", "TJ", "'", '"'}


@dataclass
class PageTagResult:
    page_index: int
    mcid_count: int = 0
    text_mcid_count: int = 0
    artifact_count: int = 0
    failed: bool = False
    error: str | None = None


@dataclass
class TagResult:
    pages: list[PageTagResult] = field(default_factory=list)

    @property
    def total_mcids(self) -> int:
        return sum(p.mcid_count for p in self.pages)

    @property
    def total_artifacts(self) -> int:
        return sum(p.artifact_count for p in self.pages)

    def mcids_for(self, page_idx: int) -> int:
        for p in self.pages:
            if p.page_index == page_idx:
                return p.mcid_count
        return 0


class ContentStreamTagger:
    """
    Rewrites each page's content stream so that text-showing operators are
    wrapped in BDC/EMC marked-content sections with sequential MCIDs.

    The mapping from MCIDs to StructElems is produced as side output; the
    PDF writer consumes it to build the ParentTree and populate the K
    arrays of each StructElem.

    v1 strategy: each text operator becomes one MCID with role /Span. The
    writer distributes the MCIDs to the classified blocks proportionally to
    block text length in reading order. This is approximate but satisfies
    PDF/UA invariants and improves NVDA reading order for simple layouts.
    """

    def tag(self, pdf: pikepdf.Pdf) -> TagResult:
        result = TagResult()
        for page_idx, page in enumerate(pdf.pages):
            page_result = self._tag_page(pdf, page, page_idx)
            result.pages.append(page_result)
        return result

    def _tag_page(self, pdf: pikepdf.Pdf, page, page_idx: int) -> PageTagResult:
        res = PageTagResult(page_index=page_idx)
        try:
            instructions = list(pikepdf.parse_content_stream(page))
        except Exception as e:
            log.warning("cs_parse_failed", page=page_idx, error=str(e))
            res.failed = True
            res.error = str(e)
            return res

        new_instructions = []
        mcid = 0
        for inst in instructions:
            op_name = self._op_name(inst)

            if op_name in TEXT_SHOW_OPS:
                bdc = pikepdf.ContentStreamInstruction(
                    [pikepdf.Name("/Span"), pikepdf.Dictionary(MCID=mcid)],
                    pikepdf.Operator("BDC"),
                )
                emc = pikepdf.ContentStreamInstruction(
                    [], pikepdf.Operator("EMC"),
                )
                new_instructions.append(bdc)
                new_instructions.append(inst)
                new_instructions.append(emc)
                mcid += 1
                res.text_mcid_count += 1
            else:
                new_instructions.append(inst)

        res.mcid_count = mcid

        if mcid == 0:
            return res

        try:
            new_bytes = pikepdf.unparse_content_stream(new_instructions)
            page.Contents = pdf.make_stream(new_bytes)
            page.StructParents = page_idx
        except Exception as e:
            log.warning("cs_unparse_failed", page=page_idx, error=str(e))
            res.failed = True
            res.error = str(e)
            res.mcid_count = 0

        return res

    @staticmethod
    def _op_name(inst) -> str:
        op = inst.operator
        try:
            return str(op)
        except Exception:
            return ""
