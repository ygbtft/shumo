from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
import zipfile

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
RESULTS = PROJECT / "results"
CACHE = PROJECT / "cache"
FIGURES = PROJECT / "figures"
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def read_workbook(path):
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join(node.text or "" for node in item.iter(XML_NS + "t"))
                       for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))]
        relations = {item.get("Id"): item.get("Target") for item in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
        sheets = {}
        for sheet in ElementTree.fromstring(archive.read("xl/workbook.xml")).find(XML_NS + "sheets"):
            relation = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            target = relations[relation]
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            populated = {}
            for cell in ElementTree.fromstring(archive.read(target)).iter(XML_NS + "c"):
                value_node = cell.find(XML_NS + "v")
                if cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(XML_NS + "t"))
                elif value_node is None:
                    continue
                elif cell.get("t") == "s":
                    value = strings[int(value_node.text)]
                elif cell.get("t") == "str":
                    value = value_node.text
                else:
                    value = float(value_node.text)
                letters, row_label = re.fullmatch(r"([A-Z]+)([0-9]+)", cell.get("r")).groups()
                column = 0
                for character in letters:
                    column = column * 26 + ord(character) - 64
                populated[(int(row_label) - 1, column - 1)] = value
            height = max(position[0] for position in populated) + 1
            width = max(position[1] for position in populated) + 1
            rows = [[None] * width for unused in range(height)]
            for (row_index, column_index), value in populated.items():
                rows[row_index][column_index] = value
            sheets[sheet.get("name")] = rows
        return sheets


def inputs():
    air = np.asarray(read_workbook(PROJECT / "附件/附件1.xlsx")["Sheet1"][1:])
    radii = np.asarray(read_workbook(PROJECT / "附件/附件2.xlsx")["Sheet1"][1:])
    radii[:, 1] /= 100
    assert air.shape == (241, 3) and radii.shape == (145, 2)
    assert np.all(np.diff(air[:, 0]) > 0) and np.all(np.diff(radii[:, 0]) > 0)
    assert np.isfinite(air).all() and np.isfinite(radii).all()
    return air, radii


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
