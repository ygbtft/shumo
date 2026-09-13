"""Read original documents without modification; write complete text/math/media to B/."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "CUMCM2026Problems" / "B题"
OUT = ROOT / "inputs_readonly_extract"
OUT.mkdir(exist_ok=True)
manifest = {}
for path in [SOURCE / "B题.pdf", *sorted((SOURCE / "附件").glob("*.docx"))]:
    manifest[str(path.relative_to(ROOT.parent))] = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.suffix == ".pdf":
        reader = PdfReader(path)
        text = "\n\n".join(f"--- PAGE {i+1} ---\n{p.extract_text(extraction_mode='layout')}" for i, p in enumerate(reader.pages))
        for i, page in enumerate(reader.pages):
            for j, im in enumerate(page.images):
                (OUT / f"pdf_page{i+1}_image{j}_{im.name}").write_bytes(im.data)
    else:
        with zipfile.ZipFile(path) as z:
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            doc = ET.fromstring(z.read("word/document.xml"))
            def paragraph(p):
                parts = []
                for element in p.iter():
                    tag = element.tag.rsplit("}", 1)[-1]
                    if tag == "t":
                        parts.append(element.text or "")
                    elif tag == "tab":
                        parts.append("\t")
                    elif tag in ("br", "cr"):
                        parts.append("\n")
                return "".join(parts)
            text = "\n".join(paragraph(p) for p in doc.findall(".//w:p", ns))
            for name in z.namelist():
                if name.startswith("word/media/"):
                    (OUT / (path.stem + "_" + Path(name).name)).write_bytes(z.read(name))
                if name in ["word/_rels/document.xml.rels", "word/document.xml"]:
                    (OUT / (path.stem + "_" + Path(name).name)).write_bytes(z.read(name))
    (OUT / (path.stem + ".txt")).write_text(text, encoding="utf-8")
    print(f"{path.name}: {len(text)} characters")
(OUT / "input_sha256.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
