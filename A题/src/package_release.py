import hashlib
import json
from pathlib import Path
import zipfile


PROJECT = Path(__file__).resolve().parents[1]


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    root_files = ["README.md", "requirements.txt", "AI_USAGE.md", "COMPLIANCE.md"]
    files = [PROJECT / name for name in root_files]
    files += sorted((PROJECT / "src").glob("*.py"))
    files += sorted((PROJECT / "figures").glob("*.png")) + sorted((PROJECT / "figures").glob("*.pdf"))
    files += [PROJECT / "paper" / name for name in ("build_paper.py", "manuscript_template.md", "论文.md")]
    files += sorted((PROJECT / "paper/equations").glob("*.png"))
    files += [path for path in sorted((PROJECT / "results").glob("*.json")) if path.name != "release_manifest.json"]
    files += [PROJECT / "results/workbooks" / f"result{case}.xlsx" for case in (1, 2, 3, 4)]
    for path in files:
        assert path.is_file() and path.resolve().is_relative_to(PROJECT.resolve())
        assert not path.is_symlink()
        assert "附件" not in path.relative_to(PROJECT).parts
    build = json.loads((PROJECT / "results/paper_build.json").read_text(encoding="utf-8"))
    pdf = PROJECT / build.get("pdf_path", "output/pdf/论文.pdf")
    assert build["main_pages_including_abstract"] <= 30
    assert pdf.stat().st_size < 20_000_000
    manifest = {"files": {path.relative_to(PROJECT).as_posix(): {"bytes": path.stat().st_size, "sha256": checksum(path)} for path in files},
                "paper": {"path": pdf.relative_to(PROJECT).as_posix(), "bytes": pdf.stat().st_size, "sha256": checksum(pdf)},
                "excluded": ["原始赛题与附件", "缓存、日志与渲染预览", "node_modules及其他运行时", "Git元数据", "前三小时便捷节选"],
                "publication": "仅生成本地材料；不代表已提交竞赛或推送远程仓库"}
    manifest_path = PROJECT / "results/release_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    output = PROJECT / "output/支撑材料.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in [*files, manifest_path]:
            archive.write(path, path.relative_to(PROJECT).as_posix())
    assert output.stat().st_size < 20_000_000
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        for name, entry in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == entry["sha256"]
    print(json.dumps({"pdf_bytes": pdf.stat().st_size, "support_zip_bytes": output.stat().st_size,
                      "support_files": len(files) + 1, "main_pages_including_abstract": build["main_pages_including_abstract"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
