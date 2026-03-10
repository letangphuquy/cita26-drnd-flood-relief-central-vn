from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "ref"
OUT = ROOT / "tmp" / "ref_extract"
OUT.mkdir(parents=True, exist_ok=True)

candidates = [
    "A tabu-search based heuristic for the hub covering problem over incomplete hub networks j.cor.2008.11.023.pdf",
    "Design of multimodal hub-and-spoke transportation network for emergency relief under COVID-19 pandemic A meta-heuristic approach 1-s2.0-S1568494622009747-main.pdf",
    "NSGA-II 4235.996017.pdf",
    "coin.12374.pdf",
]

for name in candidates:
    p = REF / name
    if not p.exists():
        continue
    reader = PdfReader(str(p))
    text = []
    for i, page in enumerate(reader.pages[:20]):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        text.append(f"\n--- PAGE {i+1} ---\n{t}\n")
    out = OUT / (p.stem[:80].replace("/", "_") + ".txt")
    out.write_text("\n".join(text), encoding="utf-8")
    print(name, "->", out)
