"""
Phase 15 TEST FIXTURES — synthetic PDFs, NOT official data.

Every institution name starts with "FIXTURE" and every registration number uses the letter Z
followed by 9xxx, so fixture content can never be mistaken for a real licensed institution.
The layouts mimic the official BCEAO list (summary table + country sections) and the BCEAO
fascicle (one statement page per institution) closely enough to exercise the parsers.
"""
from __future__ import annotations

import pymupdf

REGULAR, BOLD = "helv", "hebo"
COUNTRY_TITLES = {
    "BJ": "BÉNIN", "BF": "BURKINA", "CI": "CÔTE D'IVOIRE", "GW": "GUINÉE-BISSAU",
    "ML": "MALI", "NE": "NIGER", "SN": "SÉNÉGAL", "TG": "TOGO",
}


def fixture_banks(reference_label: str = "31 DÉCEMBRE 2025") -> dict[str, list[dict]]:
    """Per country: list of bank rows. Kept small but covering every parsing feature."""
    banks: dict[str, list[dict]] = {}
    for i, cc in enumerate(COUNTRY_TITLES):
        banks[cc] = [
            {"name": f"FIXTURE BANK ALPHA {COUNTRY_TITLES[cc]} (FBA-{cc})", "reg": f"Z 9{i}01 A", "form": "subsidiary"},
        ]
    # Multi-line name + former name + acronym (Côte d'Ivoire)
    banks["CI"].append({
        "name": "FIXTURE BANQUE INTERNATIONALE POUR LE COMMERCE ET LE DEVELOPPEMENT DE LA",
        "name2": "CÔTE D'IVOIRE (FBICD) ex FIXTURE BANQUE ANCIENNE",
        "reg": "Z 9202 B", "form": "subsidiary",
    })
    # Parent in Senegal + its branch in Mali
    banks["SN"].append({"name": "FIXTURE PARENT BANK SÉNÉGAL (FPB)", "reg": "Z 9602 C", "form": "subsidiary"})
    banks["ML"].append({"name": "FIXTURE PARENT BANK SÉNÉGAL, SUCCURSALE DU MALI", "reg": "Z 9402 D", "form": "branch"})
    return banks


def _text(page: pymupdf.Page, x: float, y: float, text: str, bold: bool = False, size: float = 8) -> None:
    page.insert_text((x, y), text, fontname=BOLD if bold else REGULAR, fontsize=size)


def build_reference_list_pdf(
    banks: dict[str, list[dict]] | None = None,
    *,
    reference_label: str = "31 DÉCEMBRE 2025",
    header_override: dict[str, int] | None = None,
    summary_override: dict[str, int] | None = None,
    history: dict[str, list[tuple[str, str]]] | None = None,
) -> bytes:
    """BCEAO-like list. ``header_override`` / ``summary_override`` inject inconsistencies."""
    banks = banks or fixture_banks(reference_label)
    header_override = header_override or {}
    summary_override = summary_override or {}
    doc = pymupdf.open()

    title = doc.new_page()
    _text(title, 60, 80, "LISTE DES ÉTABLISSEMENTS DE CRÉDIT", bold=True, size=12)
    _text(title, 60, 100, f"AGRÉÉS DANS L'UMOA AU {reference_label}", bold=True, size=12)

    summary = doc.new_page()
    _text(summary, 60, 100, f"ÉTABLISSEMENTS DE CRÉDIT AGRÉÉS DANS L'UMOA À FIN {reference_label.split(' ', 1)[1]}",
          bold=True, size=10)
    y = 160
    total = 0
    for cc, rows in banks.items():
        n = summary_override.get(cc, len(rows))
        total += n
        _text(summary, 60, y, COUNTRY_TITLES[cc], bold=True)
        _text(summary, 224, y, str(n), bold=True)
        _text(summary, 318, y, "0", bold=True)
        _text(summary, 453, y, str(n), bold=True)
        y += 15
    _text(summary, 96, y, "TOTAL UMOA", bold=True)
    _text(summary, 221, y, str(total), bold=True)
    _text(summary, 316, y, "0", bold=True)
    _text(summary, 450, y, str(total), bold=True)

    for cc, rows in banks.items():
        page = doc.new_page()
        _text(page, 58, 60, COUNTRY_TITLES[cc], bold=True)
        _text(page, 100, 85, "LISTES DES BANQUES ET DES ÉTABLISSEMENTS FINANCIERS À CARACTÈRE BANCAIRE AGRÉÉS",
              bold=True)
        _text(page, 230, 97, f"(Situation à fin {reference_label.split(' ', 1)[1].lower()})", bold=True)
        subs = [r for r in rows if r["form"] == "subsidiary"]
        branches = [r for r in rows if r["form"] == "branch"]
        _text(page, 58, 140, f"LISTE DES BANQUES ({header_override.get(cc, len(rows))})", bold=True)
        y = 160
        for label, group in (("- dont filiales", subs), ("- dont succursales", branches)):
            _text(page, 83, y, f"{label} ({len(group)})", bold=True)
            y += 18
            for row in group:
                if "name2" in row:
                    _text(page, 58, y, row["name"])
                    _text(page, 424, y + 5, row["reg"])
                    _text(page, 58, y + 10, row["name2"])
                    y += 28
                else:
                    _text(page, 58, y, row["name"])
                    _text(page, 424, y, row["reg"])
                    y += 18
        _text(page, 58, y + 10, "LISTE DES ÉTABLISSEMENTS FINANCIERS À CARACTÈRE BANCAIRE (0)", bold=True)
        _text(page, 58, y + 28, "NÉANT")
        y += 50
        _text(page, 58, y, "NOUVEL AGRÉMENT", bold=True)
        _text(page, 58, y + 18, "NÉANT")
        _text(page, 58, y + 40, "MODIFICATIONS INTERVENUES SUR LA PRÉCÉDENTE LISTE", bold=True)
        events = (history or {}).get(cc, [])
        if events:
            yy = y + 58
            for old, new in events:
                _text(page, 58, yy, f"*MODIFICATION DE LA DÉNOMINATION SOCIALE DE {old} EN {new}")
                yy += 14
        else:
            _text(page, 58, y + 58, "NÉANT")
    data = doc.tobytes()
    doc.close()
    return data


def build_fascicle_pdf(pages: list[dict]) -> bytes:
    """Fascicle-like PDF. Each dict: country, code, kind ('Bilans'|'Comptes de résultat'), label, rows.

    ``rows`` maps a printed line label to a list of 3 printed cells ("" = blank cell).
    """
    doc = pymupdf.open()
    for spec in pages:
        page = doc.new_page()
        _text(page, 53, 50, spec["country"], bold=True, size=10)
        _text(page, 53, 61, spec["code"], bold=True, size=10)
        _text(page, 53, 72, f"{spec['kind']} 2021-2023", bold=True, size=10)
        if spec.get("label"):
            _text(page, 250, 93, spec["label"], bold=True, size=10)
        for x, year in ((392, "2021"), (453, "2022"), (514, "2023")):
            _text(page, x, 132, year, bold=True, size=10)
        _text(page, 397, 150, "Millions de francs CFA", size=10)
        y = 175
        for label, cells in spec["rows"].items():
            _text(page, 53, y, label, size=10)
            for x, cell in zip((392, 453, 514), cells, strict=True):
                if cell:
                    _text(page, x, y, cell, size=10)
            y += 15
    data = doc.tobytes()
    doc.close()
    return data


def build_text_pdf(pages: list[list[str]]) -> bytes:
    """Phase 16 FIXTURE: one PDF page per list of text lines ([] = page without any text layer)."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        y = 60
        for line in lines:
            _text(page, 50, y, line, size=10)
            y += 16
    data = doc.tobytes()
    doc.close()
    return data


def build_synoptic_pdf(
    rows_left: dict[str, list[str]],
    rows_right: dict[str, list[str]],
    *,
    years: tuple[str, str] = ("2021", "2022"),
    unit_line: str | None = None,
    title: str = "FIXTURE BANK ALPHA",
    off_balance_rows: dict[str, list[str]] | None = None,
) -> bytes:
    """Phase 17 FIXTURE: BOA-like synoptic page — two comparative tables side by side (labels + two
    year columns each), optionally a unit line and a second header row (off-balance-sheet table)."""
    doc = pymupdf.open()
    page = doc.new_page()
    _text(page, 40, 40, title, bold=True, size=9)
    if unit_line:
        _text(page, 300, 40, unit_line, size=7)
    for x_label, x_years in ((40, (190, 240)), (300, (450, 500))):
        for x, year in zip(x_years, years, strict=True):
            _text(page, x, 70, year, bold=True, size=7)
    y = 82
    for (left, lv), (right, rv) in zip(
        list(rows_left.items()) + [("", ["", ""])] * max(0, len(rows_right) - len(rows_left)),
        list(rows_right.items()) + [("", ["", ""])] * max(0, len(rows_left) - len(rows_right)),
        strict=True,
    ):
        for x_label, x_vals, label, vals in ((40, (180, 230), left, lv), (300, (440, 490), right, rv)):
            if label:
                _text(page, x_label, y, label, size=6)
            for x, v in zip(x_vals, vals, strict=True):
                if v:
                    _text(page, x, y, v, size=6)
        y += 9
    if off_balance_rows:
        y += 20
        for x, year in zip((190, 240), years, strict=True):
            _text(page, x, y, year, bold=True, size=7)
        y += 12
        for label, vals in off_balance_rows.items():
            _text(page, 40, y, label, size=6)
            for x, v in zip((180, 230), vals, strict=True):
                if v:
                    _text(page, x, y, v, size=6)
            y += 9
    data = doc.tobytes()
    doc.close()
    return data


GARBLED_LINES = [
    "C5(A1C(6 ,17(5BA1CA,5(6 (7 A66,0,/((6 9 2 950 45 06 052 09",
    "CA,66(, BA148( C(175A/(, CCP 4 52 925 5 9 49 2",
    "OB/,*A7,O16 (7 A875(6 7,75(6 6 529 90 24 2",
    "P5O9,6,O16 2 02 26 46 69 0 05",
    "CO0P7(6 '( 5(*8/A5,6A7,O1 5 24 44 09 506 29 6",
]
