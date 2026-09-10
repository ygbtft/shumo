import argparse
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw


PROJECT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--preview-only", action="store_true")
    arguments = parser.parse_args()
    selected = arguments.input or json.loads((PROJECT / "results/paper_build.json").read_text(encoding="utf-8")).get("pdf_path", "output/pdf/论文.pdf")
    path = PROJECT / selected
    destination = PROJECT / "tmp/pdfs" / path.stem
    destination.mkdir(parents=True, exist_ok=True)
    document = fitz.open(path)
    pages, thumbnails = [], []
    for index, page in enumerate(document):
        text = page.get_text()
        if not arguments.preview_only:
            assert text.strip(), f"空白页：{index + 1}"
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
        output = destination / f"page_{index + 1:03}.png"
        pixmap.save(output)
        with Image.open(output) as rendered:
            thumbnail = rendered.copy()
            thumbnail.thumbnail((240, 330))
        tile = Image.new("RGB", (260, 360), "#E9EDF0")
        tile.paste(thumbnail, ((260 - thumbnail.width) // 2, 12))
        ImageDraw.Draw(tile).text((10, 340), str(index + 1), fill="black")
        thumbnails.append(tile)
        outside = []
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if span["bbox"][3] > page.rect.height - 60:
                        continue
                    if span["bbox"][0] < 71 or span["bbox"][2] > page.rect.width - 71:
                        outside.append(span["text"])
        pages.append({"page": index + 1, "characters": len(text), "horizontal_margin_violations": outside})
    for start in range(0, len(thumbnails), 12):
        contact = Image.new("RGB", (1040, 1080), "white")
        for offset, thumbnail in enumerate(thumbnails[start:start + 12]):
            contact.paste(thumbnail, ((offset % 4) * 260, (offset // 4) * 360))
        contact.save(destination / f"contact_{start // 12 + 1:02}.png")
    report = {"pages": len(document), "metadata": document.metadata, "page_checks": pages,
              "visual_review_required": "还需人工查看各页渲染；自动文字边界检查不代替图表版式核验"}
    if not arguments.preview_only:
        (PROJECT / "results/pdf_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        assert not document.metadata.get("author")
        assert not any(page["horizontal_margin_violations"] for page in pages)
    print(path.relative_to(PROJECT), "rendered_pages", len(document), "preview_directory", destination.relative_to(PROJECT), flush=True)


if __name__ == "__main__":
    main()
