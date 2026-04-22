import sys
sys.path.insert(0, "/app")

from app.services.analysis.hierarchy_fixer import DocumentStructure
from app.services.writing.pdf_writer import AccessiblePDFWriter

struct = DocumentStructure(
    pages=[{"page_num": 0, "language": "es", "blocks": []}],
    document_title="Formulario",
    language="es",
    headings_hierarchy=[],
    page_count=1,
)

w = AccessiblePDFWriter("/app/tests/fixtures/form.pdf", struct)
w.write("/tmp/writer_out.pdf")
print("stats:", w.get_write_stats())
print("changes:", [(c.change_type, c.page_num) for c in w.get_applied_changes()])
