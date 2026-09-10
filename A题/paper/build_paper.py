from html import escape
from datetime import datetime
import json
import os
from pathlib import Path
import re

from PIL import Image as PillowImage
from reportlab.lib import colors, textsplit
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.platypus import paragraph as paragraph_engine


PROJECT = Path(__file__).resolve().parents[1]
PAPER = PROJECT / "paper"
WIDTH = A4[0] - 144
SOURCES = ["src/data_io.py", "src/model.py", "src/experiments.py", "src/plots.py",
           "src/export_fallback.py", "src/render_equations.py", "src/audit_model.py",
           "src/audit_workbooks.py", "src/package_release.py", "paper/build_paper.py", "src/verify_pdf.py"]


def load(name):
    return json.loads((PROJECT / "results" / name).read_text(encoding="utf-8"))


def decimal(value, digits=4):
    return "--" if value is None else f"{value:.{digits}f}"


def manuscript_data():
    production = load("production.json")
    summaries, records = production["summaries"], production["tables"]
    sensitivity = {(row["configuration"]["case"], row["name"]): row for row in load("sensitivity.json")}
    values = {}
    for case in (3, 4):
        summary = summaries[f"result{case}"]
        values[f"t{case}"] = decimal(summary["critical_time_h"])
        values[f"stop{case}"] = decimal(summary["stop_time_h"])
        values[f"max{case}"] = decimal(summary["final_max_moisture"], 10)
        values[f"joint{case}"] = decimal(sensitivity[case, "joint_adverse"]["critical_time_h"])
    values["no_shrink"] = decimal(sensitivity[4, "no_shrinkage"]["critical_time_h"])
    values["balance"] = f"{max(row['balance_error'] for row in summaries.values()):.2e}"
    values["q1_center_t"] = decimal(records["result1"]["temperature"][-1][0])
    values["q1_surface_t"] = decimal(records["result1"]["temperature"][-1][-1])
    values["q2_center_c"] = decimal(records["result2"]["moisture"][-1][0])
    values["q2_surface_c"] = decimal(records["result2"]["moisture"][-1][-1])
    values["stop4_radius"] = decimal(records["result4"]["surface"][-1][0])
    values["shrink_reduction"] = decimal(100 * (1 - sensitivity[4, "baseline"]["critical_time_h"] / sensitivity[4, "no_shrinkage"]["critical_time_h"]), 2)
    finest = [row for row in load("convergence.json") if row["intervals"] == 2048]
    values["fine_moisture"] = f"{max(row['moisture_difference'] for row in finest):.2e}"
    values["fine_event"] = f"{max(row.get('critical_time_difference_s', 0) for row in finest):.3f}"
    values["heat_error"] = f"{load('heat_benchmark.json')[-1]['maximum_absolute_error_C']:.2e}"
    tables = {}
    for key, record_name, field in (("q1t", "result1", "temperature"), ("q1c", "result1", "moisture"),
                                    ("q2t", "result2", "temperature"), ("q2c", "result2", "moisture"),
                                    ("q3c", "result3", "moisture")):
        record = records[record_name]
        first_question = record_name == "result1"
        headings = ["时间/s" if first_question else "时间/h", "0 cm", "0.5 cm", "1 cm", "1.5 cm", "2 cm"]
        body = [[str(int(time)) if first_question else decimal(time / 3600), *map(decimal, row)]
                for time, row in zip(record["time_s"], record[field])]
        tables[key] = [headings, *body]
    record = records["result4"]
    tables["q4c"] = [["时间/h", "0 cm", "0.5 cm", "1 cm", "1.5 cm", "表面", "半径/cm"],
                      *[[decimal(time / 3600), *map(decimal, row[:4]), decimal(surface[2]), decimal(surface[0])]
                        for time, row, surface in zip(record["time_s"], record["moisture"], record["surface"])]]
    tables["benchmark"] = [["径向子区间数", "级数项数", "最大温度误差/℃"],
                            *[[str(row["intervals"]), str(row["series_terms"]), f"{row['maximum_absolute_error_C']:.3e}"]
                              for row in load("heat_benchmark.json")]]
    tables["convergence"] = [["问题", "粗/细网格", "温度最大差/℃", "含水率最大差", "临界时间差/s"],
                              *[[str(row["case"]), f"{row['intervals'] // 2}/{row['intervals']}",
                                 f"{row['temperature_difference_C']:.3e}", f"{row['moisture_difference']:.3e}",
                                 "--" if row["case"] == 1 else f"{row['critical_time_difference_s']:.5f}"]
                                for row in load("convergence.json") if "moisture_difference" in row]]
    integrators = [row for row in load("method_comparison.json") if row["configuration"]["intervals"] == 128]
    tables["integrators"] = [["问题", "BDF时长/h", "Radau时长/h", "绝对时间差/s"]]
    for case in (3, 4):
        matched = {row["configuration"]["method"]: row for row in integrators if row["configuration"]["case"] == case}
        tables["integrators"].append([str(case), decimal(matched["BDF"]["critical_time_h"], 8),
                                       decimal(matched["Radau"]["critical_time_h"], 8),
                                       decimal(abs(matched["BDF"]["critical_time_s"] - matched["Radau"]["critical_time_s"]), 6)])
    tables["axial"] = [["问题", "二维网格", "一维时长/h", "二维时长/h", "相对变化/%"],
                        *[[str(row["summary"]["configuration"]["case"]),
                           f"{row['summary']['configuration']['intervals']}×{row['summary']['configuration']['axial_intervals']}",
                           decimal(row["matched_1d_summary"]["critical_time_h"], 6), decimal(row["summary"]["critical_time_h"], 6),
                           decimal(100 * row["relative_time_change"], 6)] for row in load("axial_comparison.json")]]
    scenarios = [("baseline", "基准"), ("air_T_minus1", "平台温度降低1℃"), ("air_T_plus1", "平台温度升高1℃"),
                 ("air_C_minus_001", "平台浓度降低0.001"), ("air_C_plus_001", "平台浓度升高0.001"),
                 ("mass_transfer_minus10pct", "传质系数降低10%"), ("mass_transfer_plus10pct", "传质系数升高10%"),
                 ("diffusivity_minus10pct", "扩散系数降低10%"), ("diffusivity_plus10pct", "扩散系数升高10%"),
                 ("last_observation_plateau", "末点平台"), ("tail_mean_plateau", "末小时均值平台"),
                 ("linear_radius", "半径线性插值"), ("no_shrinkage", "同物性固定半径"), ("joint_adverse", "联合不利情景")]
    tables["sensitivity"] = [["情景", "第三问时长/h", "第四问时长/h"],
                              *[[label, *[decimal(sensitivity[case, name]["critical_time_h"]) if (case, name) in sensitivity else "不适用"
                                          for case in (3, 4)]] for name, label in scenarios]]
    return values, tables


def markdown_table(rows):
    return "\n".join(["| " + " | ".join(rows[0]) + " |", "|" + "---|" * len(rows[0]),
                      *["| " + " | ".join(row) + " |" for row in rows[1:]]])


def appendix_markdown():
    listing = ["### 附录A 支撑文件清单与复现", "",
               "支撑材料不重复收录赛题及原始附件。复算时，将题目文件A题.pdf及附件1.xlsx、附件2.xlsx放回README所列位置，再执行所列命令。计算平台为Python，线性代数与隐式积分使用CPU。", "",
               markdown_table([["目录或文件", "用途"], ["src/", "输入读取、模型、实验、导出、绘图和核验程序"],
                               ["results/workbooks/result1.xlsx至result4.xlsx", "四问完整结果；第二问为全程逐秒结果"],
                               ["results/*.json", "参数、收敛、对照、敏感性与数据来源散列"], ["figures/", "九组论文图及矢量版"],
                               ["paper/", "论文模板、可编辑正文、公式图及排版程序"], ["requirements.txt、README.md", "依赖与完整复现命令"]]), "",
               "### 附录B AI辅助使用说明", "",
               "本文研究过程中使用了AI辅助进行模型推导讨论、程序实现、数值结果整理、图表制作及论文草稿编写。数值由随附程序计算，未将生成内容当作实测数据。最终使用者须逐项理解并独立复算，对模型假设、文献、程序和结论负责；此处为事实性使用说明，不替代赛事规定的专门AI使用报告。", "",
               "### 附录C 完整程序", "",
               "下列代码按文件完整列出。PDF中长行仅作显示折行，行号不是程序内容；支撑包中的同名文件可直接运行。", ""]
    for name in SOURCES:
        path = PROJECT / name
        if not path.exists():
            raise FileNotFoundError(f"缺少应附程序：{name}")
        listing.extend(["### " + name, "", "```python", path.read_text(encoding="utf-8").rstrip(), "```", ""])
    return "\n".join(listing)


def register_fonts():
    textsplit.ALL_CANNOT_START += "，；：！？】”’"
    paragraph_engine.ALL_CANNOT_START = textsplit.ALL_CANNOT_START
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    regular = Path(os.environ.get("CJK_FONT_REGULAR", str(fonts / "simsun.ttc")))
    bold = Path(os.environ.get("CJK_FONT_BOLD", str(fonts / "simhei.ttf")))
    symbols = Path(os.environ.get("MATH_SYMBOL_FONT", str(fonts / "seguisym.ttf")))
    pdfmetrics.registerFont(TTFont("CJK", str(regular)))
    pdfmetrics.registerFont(TTFont("CJK-Bold", str(bold)))
    pdfmetrics.registerFont(TTFont("MathSymbols", str(symbols)))
    pdfmetrics.registerFontFamily("CJK", normal="CJK", bold="CJK-Bold", italic="CJK", boldItalic="CJK-Bold")


def text_markup(text):
    text = escape(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    for tag in ("sub", "sup"):
        reportlab_tag = "super" if tag == "sup" else tag
        text = text.replace(f"&lt;{tag}&gt;", f"<{reportlab_tag}>").replace(f"&lt;/{tag}&gt;", f"</{reportlab_tag}>")
    regular = pdfmetrics.getFont("CJK").face.charToGlyph
    symbols = pdfmetrics.getFont("MathSymbols").face.charToGlyph
    return "".join(f'<font name="MathSymbols">{character}</font>' if ord(character) not in regular and ord(character) in symbols else character for character in text)


def styles():
    base = dict(fontName="CJK", fontSize=11, leading=17.6, wordWrap="CJK", textColor=colors.black, rightIndent=6)
    return {
        "body": ParagraphStyle("body", **base, firstLineIndent=22, spaceAfter=6),
        "plain": ParagraphStyle("plain", **base, spaceAfter=6),
        "title": ParagraphStyle("title", fontName="CJK-Bold", fontSize=17, leading=24, alignment=TA_CENTER, spaceAfter=14, wordWrap="CJK"),
        "abstract": ParagraphStyle("abstract", fontName="CJK-Bold", fontSize=13, leading=20, alignment=TA_CENTER, spaceAfter=10),
        "h1": ParagraphStyle("h1", fontName="CJK-Bold", fontSize=13, leading=21, spaceBefore=10, spaceAfter=7, keepWithNext=True, wordWrap="CJK"),
        "h2": ParagraphStyle("h2", fontName="CJK-Bold", fontSize=11.5, leading=18, spaceBefore=7, spaceAfter=5, keepWithNext=True, wordWrap="CJK"),
        "caption": ParagraphStyle("caption", fontName="CJK", fontSize=9.5, leading=14, alignment=TA_CENTER, spaceAfter=6, wordWrap="CJK"),
        "cell": ParagraphStyle("cell", fontName="CJK", fontSize=9.1, leading=13, alignment=TA_CENTER, wordWrap="CJK"),
        "code": ParagraphStyle("code", fontName="CJK", fontSize=7.2, leading=8.8, alignment=TA_LEFT, spaceAfter=6),
    }


def table_flowable(rows, appearance):
    column_count = len(rows[0])
    widths = [WIDTH / column_count] * column_count
    if column_count == 2:
        widths = [WIDTH * 0.40, WIDTH * 0.60]
    if column_count == 3 and len(rows) > 9:
        widths = [WIDTH * 0.48, WIDTH * 0.26, WIDTH * 0.26]
    converted = [[Paragraph(text_markup(cell), appearance["cell"]) for cell in row] for row in rows]
    table = Table(converted, colWidths=widths, repeatRows=1, hAlign="CENTER")
    table.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
                               ("LINEBELOW", (0, 0), (-1, 0), 0.45, colors.black),
                               ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F3F4F5")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    if rows[0][0] == "符号":
        table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return table


def fit_image(path, max_width=WIDTH, max_height=240, scale_cap=float("inf")):
    with PillowImage.open(path) as picture:
        width, height = picture.size
    ratio = min(max_width / width, max_height / height, scale_cap)
    return Image(str(path), width=width * ratio, height=height * ratio, hAlign="CENTER")


def code_lines(source):
    result = []
    for number, line in enumerate(source.splitlines(), 1):
        segment = f"{number:4}  "
        for character in line.expandtabs(4):
            if pdfmetrics.stringWidth(segment + character, "CJK", 7.2) > WIDTH - 15:
                result.append(segment)
                segment = "      "
            segment += character
        result.append(segment)
    return "\n".join(result)


class AppendixBoundary(Flowable):
    def __init__(self, record):
        super().__init__()
        self.record = record
        self.width = 0
        self.height = 0

    def draw(self):
        self.record["main_pages_including_abstract"] = self.canv.getPageNumber()


def build_pdf(markdown, metadata):
    register_fonts()
    appearance = styles()
    story = []
    lines = markdown.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == "## 附录":
            story.extend([AppendixBoundary(metadata), PageBreak(), Paragraph("附录", appearance["h1"])])
        elif line.startswith("## 1 "):
            story.extend([PageBreak(), Paragraph(text_markup(line[3:]), appearance["h1"])])
        elif line.startswith("### "):
            story.append(Paragraph(text_markup(line[4:]), appearance["h2"]))
        elif line == "## 摘要":
            story.append(Paragraph("摘要", appearance["abstract"]))
        elif line.startswith("## "):
            story.append(Paragraph(text_markup(line[3:]), appearance["h1"]))
        elif line.startswith("# "):
            story.append(Paragraph(text_markup(line[2:]), appearance["title"]))
        elif line.startswith("```"):
            source = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                source.append(lines[index])
                index += 1
            formatted = code_lines("\n".join(source)).splitlines()
            story.append(Preformatted("\n".join(formatted[:8]), appearance["code"], dedent=0))
            if len(formatted) > 8:
                story.append(Preformatted("\n".join(formatted[8:]), appearance["code"], dedent=0))
        elif line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                    rows.append(cells)
                index += 1
            story.extend([table_flowable(rows, appearance), Spacer(1, 8)])
            continue
        elif re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line):
            label, target = re.fullmatch(r"!\[(.*?)\]\((.*?)\)", line).groups()
            maximum_height = 270 if "01_boundaries" in target else 222
            if target.startswith("equations/"):
                picture = fit_image(PAPER / target, WIDTH - 42, 40, 72 / 240 * 0.8)
                equation = Table([[picture, Paragraph(label, appearance["caption"])]], colWidths=[WIDTH - 35, 35])
                equation.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
                story.extend([equation, Spacer(1, 8)])
            else:
                story.append(KeepTogether([Spacer(1, 5), fit_image(PAPER / target, WIDTH, maximum_height),
                                           Spacer(1, 5), Paragraph(text_markup(label), appearance["caption"])]))
        elif re.match(r"^表\d+ ", line):
            caption = Paragraph(text_markup(line), appearance["caption"])
            caption.keepWithNext = True
            story.append(caption)
        else:
            paragraph = [line]
            while index + 1 < len(lines) and lines[index + 1].strip() and not lines[index + 1].startswith(("#", "|", "![", "```")) and not re.match(r"^\d+\.", lines[index + 1]):
                index += 1
                paragraph.append(lines[index].strip())
            plain = line.startswith(("[", "**关键词", "1.", "2.", "3.", "4.", "5."))
            story.append(Paragraph(text_markup(" ".join(paragraph)), appearance["plain" if plain else "body"]))
        index += 1
    output = PROJECT / "output/pdf/论文.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(".paper_building.pdf")
    document = SimpleDocTemplate(str(temporary), pagesize=A4, leftMargin=72, rightMargin=72,
                                 topMargin=72, bottomMargin=72, title="考虑非线性扩散与径向收缩的药材烘干建模及误差验证",
                                 author="", subject="A题药材烘干的数值建模与验证", creator="", pageCompression=1)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("CJK", 9)
        canvas.drawCentredString(A4[0] / 2, 38, str(document.page))
        canvas.restoreState()
        metadata["total_pages"] = document.page

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    for candidate in (output, output.with_name("论文_审阅版.pdf"), output.with_name("论文_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".pdf")):
        try:
            temporary.replace(candidate)
            output = candidate
            break
        except PermissionError:
            continue
    else:
        raise PermissionError("PDF目标文件均被占用，请关闭查看器后重试")
    metadata["pdf_path"] = output.relative_to(PROJECT).as_posix()
    metadata["pdf_bytes"] = output.stat().st_size
    assert metadata["main_pages_including_abstract"] <= 30
    assert metadata["pdf_bytes"] <= 20_000_000
    return output


def main():
    values, tables = manuscript_data()
    template = (PAPER / "manuscript_template.md").read_text(encoding="utf-8")
    filled = re.sub(r"\[\[VAL:(\w+)\]\]", lambda match: values[match[1]], template)
    filled = re.sub(r"\[\[TABLE:(\w+)\|(.+?)\]\]", lambda match: match[2] + "\n\n" + markdown_table(tables[match[1]]), filled)
    filled = re.sub(r"\[\[EQ:(\d+)\|(.+)\]\]", lambda match: f"![（{match[1]}）](equations/equation_{match[1]}.png)", filled)
    filled = filled.replace("[[APPENDIX]]", appendix_markdown())
    filled = filled.replace("\u2014", "-").replace("\u2013", "-")
    (PAPER / "论文.md").write_text(filled, encoding="utf-8")
    metadata = {"anonymous_author": True, "margins_mm": 25.4, "source_files_in_appendix": SOURCES}
    output = build_pdf(filled, metadata)
    (PROJECT / "results/paper_build.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output.relative_to(PROJECT), metadata, flush=True)


if __name__ == "__main__":
    main()
