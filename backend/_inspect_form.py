import sys
from collections import Counter
import pikepdf

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/form_out.pdf"
with pikepdf.open(path) as pdf:
    sr = pdf.Root.get("/StructTreeRoot")
    print("AcroForm:", "/AcroForm" in pdf.Root)
    widgets = 0
    for p in pdf.pages:
        tabs = p.get("/Tabs")
        for a in (p.get("/Annots") or []):
            if isinstance(a, pikepdf.Dictionary) and str(a.get("/Subtype", "")) == "/Widget":
                widgets += 1
                print("widget:", {"TU": str(a.get("/TU", "")), "T": str(a.get("/T", "")),
                                   "StructParent": a.get("/StructParent", None)})
        print("Tabs:", tabs)
    print("widgets_total:", widgets)

    def walk(e, out=None):
        out = out if out is not None else []
        s = e.get("/S")
        if s is not None:
            out.append(str(s))
        k = e.get("/K")
        if k is None:
            return out
        try:
            iter(k)
        except TypeError:
            return out
        for c in k:
            if isinstance(c, pikepdf.Dictionary):
                walk(c, out)
        return out

    if sr is not None:
        print("struct_types:", dict(Counter(walk(sr))))
    else:
        print("no StructTreeRoot")
