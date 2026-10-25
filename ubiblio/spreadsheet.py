import csv
import io
import re
import zipfile
from xml.etree import ElementTree

SPREADSHEET_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
HEADER_WORDS = ("autoria", "autoría", "titulo", "título", "editorial", "pagina", "página", "cantidad")


def _column_index(cell_ref: str) -> int:
    letters = "".join(character for character in cell_ref if character.isalpha())
    index = 0
    for character in letters:
        index = index * 26 + (ord(character.upper()) - 64)
    return index - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    values = []
    for item in root.findall("m:si", SPREADSHEET_NS):
        values.append("".join(node.text or "" for node in item.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return values


def _sheet_rows(archive: zipfile.ZipFile, shared: list[str]) -> list[list[str]]:
    sheet_name = "xl/worksheets/sheet1.xml"
    if sheet_name not in archive.namelist():
        sheets = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
        if not sheets:
            return []
        sheet_name = sorted(sheets)[0]
    root = ElementTree.fromstring(archive.read(sheet_name))
    rows = []
    for row in root.findall("m:sheetData/m:row", SPREADSHEET_NS):
        values = {}
        for cell in row.findall("m:c", SPREADSHEET_NS):
            ref = cell.attrib.get("r", "")
            column = _column_index(ref) if ref else len(values)
            kind = cell.attrib.get("t")
            if kind == "inlineStr":
                text = "".join(node.text or "" for node in cell.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
            else:
                node = cell.find("m:v", SPREADSHEET_NS)
                text = "" if node is None or node.text is None else node.text
                if kind == "s" and text.isdigit():
                    text = shared[int(text)] if int(text) < len(shared) else ""
            values[column] = text.strip()
        if not values:
            continue
        width = max(values) + 1
        rows.append([values.get(index, "") for index in range(width)])
    return rows


def _csv_rows(payload: bytes) -> list[list[str]]:
    text = payload.decode("utf-8-sig")
    sample = text.splitlines()[0] if text.splitlines() else ""
    delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def read_table(filename: str, payload: bytes) -> list[list[str]]:
    lower = filename.lower()
    if lower.endswith(".xlsx"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return _sheet_rows(archive, _shared_strings(archive))
    if lower.endswith(".csv"):
        return _csv_rows(payload)
    raise ValueError("Use un archivo .xlsx o .csv")


def _plain(value: str) -> str:
    text = (value or "").strip().casefold()
    text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    return re.sub(r"\s+", " ", text)


def _number(value: str):
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def catalog_rows(rows: list[list[str]]) -> list[dict]:
    if not rows:
        return []
    start = 0
    first = " ".join(_plain(cell) for cell in rows[0][:5])
    if any(word in first for word in ("autoria", "titulo", "editorial", "pagina", "cantidad")):
        start = 1
    books = []
    for row in rows[start:]:
        cells = (row + ["", "", "", "", ""])[:5]
        author, title, publisher, pages, quantity = [cell.strip() for cell in cells]
        if not title and not author:
            continue
        books.append({
            "author": author,
            "title": title,
            "publisher": publisher,
            "pages": _number(pages),
            "quantity": _number(quantity),
        })
    return books
