"""Download UN M49 country names in all 6 official UN languages.

Usage: uv run python3 m49.py

Fetches https://unstats.un.org/unsd/methodology/m49/overview/ once and parses
all 6 language tables (EN, AR, ZH, FR, RU, ES), writing a single joined Parquet
to data/m49.parquet with columns: iso2, iso3, m49, name_en, name_ar, name_zh,
name_fr, name_ru, name_es.
"""

import html.parser
import logging
import urllib.request
from pathlib import Path

import duckdb

logging.basicConfig(format="%(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

_URL = "https://unstats.un.org/unsd/methodology/m49/overview/"
_LANGUAGES = ["EN", "AR", "ZH", "FR", "RU", "ES"]
_OUT = Path("data/m49.parquet")

# Column indices are identical across all language tables
_COL_NAME = 8
_COL_M49 = 9
_COL_ISO2 = 10
_COL_ISO3 = 11


class _TableParser(html.parser.HTMLParser):
    def __init__(self, table_id: str) -> None:
        super().__init__()
        self._table_id = table_id
        self._active = False
        self._nested = 0
        self._in_cell = False
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        d = dict(attrs)
        if tag == "table":
            if d.get("id") == self._table_id:
                self._active = True
            elif self._active:
                self._nested += 1
        if not self._active or self._nested:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("th", "td"):
            self._in_cell, self._cell = True, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self._active:
            if self._nested:
                self._nested -= 1
            else:
                self._active = False
        if not self._active or self._nested:
            return
        if tag == "tr" and self._row:
            self.rows.append(self._row)
        elif tag in ("th", "td") and self._in_cell:
            self._in_cell = False
            self._row.append("".join(self._cell).strip())

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)


def main() -> None:
    log.info("Fetching %s...", _URL)
    req = urllib.request.Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r:
        content = r.read().decode("utf-8")

    names: dict[str, dict[str, str]] = {}
    iso_meta: dict[str, tuple[str, str]] = {}  # iso3 -> (iso2, m49)

    for lang in _LANGUAGES:
        parser = _TableParser(f"downloadTable{lang}")
        parser.feed(content)
        rows = parser.rows
        if len(rows) < 2:
            log.warning("%s: table not found or empty", lang)
            names[lang] = {}
            continue
        lang_names: dict[str, str] = {}
        for row in rows[1:]:
            if len(row) <= _COL_ISO3:
                continue
            iso3 = row[_COL_ISO3].strip()
            name = row[_COL_NAME].strip()
            if not iso3:
                continue
            if name:
                lang_names[iso3] = name
            if lang == "EN":
                iso_meta[iso3] = (row[_COL_ISO2].strip(), row[_COL_M49].strip())
        names[lang] = lang_names
        log.info("  %s: %d countries", lang, len(lang_names))

    records = [
        (iso2, iso3, m49, *(names[lang].get(iso3, "") for lang in _LANGUAGES))
        for iso3, (iso2, m49) in sorted(iso_meta.items())
    ]

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    col_defs = "iso2 VARCHAR, iso3 VARCHAR, m49 VARCHAR, " + ", ".join(
        f"name_{lang.lower()} VARCHAR" for lang in _LANGUAGES
    )
    con = duckdb.connect()
    con.execute(f"CREATE TABLE m49 ({col_defs})")
    con.executemany(f"INSERT INTO m49 VALUES ({', '.join(['?'] * (3 + len(_LANGUAGES)))})", records)
    con.execute(
        f"COPY m49 TO '{_OUT}' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 15)"
    )
    log.info("Wrote %d rows → %s", len(records), _OUT)


if __name__ == "__main__":
    main()
