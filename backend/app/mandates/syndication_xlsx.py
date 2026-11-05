"""
Reader of TOMASTEED's internal "Suivi de Syndication Deals" workbook (migration 0022, docs/syndication.md).

Pure function of the file bytes: nothing is written. Sheets are found by the TITLE printed in them and
columns by their LABEL (never by position), so a moved column is read correctly and a missing one is
reported, never read shifted.

    SUIVI SYNDICATION          -> mandates + counterparty events (+ contacts of the row)
    detail sheets ("Banques", "Etat du dossier", NDA dates, e.g. "Cité Administrative")
                               -> counterparty events of ONE mandate, mapped explicitly by the user
    CRM INTERNE                -> contacts
    Liste des personnes dataroom -> contacts with data-room access
    LENDER MAPPING, FUNDING TERMS DATABASE -> derived from SUIVI: not imported (recomputed by the platform)
    Cartographie des investisseurs -> reported (empty in the file of 27/07/2026)

Values are kept as written. A commitment becomes a number only when the text is ONE explicit amount
with its currency (no "jusqu'à", no range) — and FCFA only for a UMOA country (XOF); the Gabon uses XAF,
which is never assumed. Placeholders ("à confirmer", "A completer", "N/A"...) are not values.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import openpyxl

from scraping.deals.collect.amounts import fold, parse_money
from scraping.universe.normalize import normalize_name

# Country codes printed in the deal labels -> ISO 3166 alpha-2, UMOA countries only (the reference
# table holds the UMOA). Others (GAB, GNC, CH...) are kept raw, never mapped by guess.
UMOA_ISO3 = {"SEN": "SN", "CIV": "CI", "TOG": "TG", "TGO": "TG", "BFA": "BF", "BEN": "BJ", "MLI": "ML",
             "NER": "NE", "GNB": "GW"}
PLACEHOLDERS = {"a confirmer", "a completer", "non precisee", "non precise", "n/a", "na", "-", "--", "nd",
                "neant", "aucun", "aucune", "tbd"}
UNCERTAIN_AMOUNT = re.compile(r"jusqu|maximum|max\.?\b|environ|~|≈|\bentre\b|\d\s*[-–—/à]\s*\d|sollicit|recherch|"
                              r"tranche|\bdont\b|;|\+")


class WorkbookError(ValueError):
    """The file is not the expected workbook (a sheet or a column is missing)."""


# An .xlsx is a zip: a few hundred KB can expand to hundreds of MB and keep the API busy for a minute
# (security tests of 22/10/2026: 422 KB -> 200 MB took 40 s). The tracker of 27/07/2026 expands to
# 4.6 MB: 60 MB leaves a wide margin and is checked BEFORE anything is decompressed.
MAX_UNCOMPRESSED_BYTES = 60_000_000
MAX_ARCHIVE_MEMBERS = 2_000


def check_archive(content: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
    except zipfile.BadZipFile as err:
        raise WorkbookError("not a readable .xlsx workbook (BadZipFile)") from err
    total = sum(m.file_size for m in members)
    if len(members) > MAX_ARCHIVE_MEMBERS or total > MAX_UNCOMPRESSED_BYTES:
        raise WorkbookError(f"workbook too large once decompressed ({total // 1_000_000} MB, "
                            f"{len(members)} parts; limit {MAX_UNCOMPRESSED_BYTES // 1_000_000} MB)")


def key(label: Any) -> str:
    """Comparison key of a label: accents, case, spaces and punctuation removed."""
    text = unicodedata.normalize("NFKD", str(label or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("\xa0", " ").split()) if not isinstance(value, str) or "\n" not in value \
        else "\n".join(" ".join(line.replace("\xa0", " ").split()) for line in value.splitlines())
    text = text.strip()
    return text or None


def is_placeholder(text: str | None) -> bool:
    return text is None or fold(text).strip(" .:") in PLACEHOLDERS


def lines(value: Any) -> list[str]:
    """'- Odile X\\n- Guilo Y' -> ['Odile X', 'Guilo Y'] (bullets and empty lines removed)."""
    text = clean(value)
    if not text:
        return []
    out = []
    for line in re.split(r"\n|\s/\s(?=\+|\d)", text):
        line = re.sub(r"^[-•*]\s*", "", line.strip()).strip()
        if line and not is_placeholder(line):
            out.append(line)
    return out


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float) and 20000 < value < 80000:  # Excel serial number
        return date.fromordinal(date(1899, 12, 30).toordinal() + int(value))
    return None


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", fold(text))).strip("-")


# =========================================================================== drafts
@dataclass
class MandateDraft:
    code: str
    title: str
    client_name: str
    country_code: str | None
    country_code_raw: str | None
    stage_raw: str | None = None
    status: str = "active"
    rows: list[int] = field(default_factory=list)

    def values(self) -> dict[str, Any]:
        return {"title": self.title, "client_name": self.client_name, "country_code": self.country_code,
                "country_code_raw": self.country_code_raw, "stage_raw": self.stage_raw, "status": self.status}


@dataclass
class EventDraft:
    mandate_code: str
    counterparty_name: str
    stage: str
    lender_type: str | None = None
    appetite: bool | None = None
    amount: str | None = None  # Decimal as text (JSON-able); only from ONE explicit amount
    currency: str | None = None
    amount_text: str | None = None
    rate_text: str | None = None
    arrangement_fee_text: str | None = None
    commitment_fee_text: str | None = None
    maturity_text: str | None = None
    dossier_status_raw: str | None = None
    nda_sent_on: str | None = None
    nda_received_on: str | None = None
    next_steps: str | None = None
    notes: str | None = None
    sheet: str = ""
    row: int = 0

    def fingerprint(self) -> tuple:
        """What makes two events the same (an identical line re-imported is not a new event)."""
        return (self.mandate_code, normalize_name(self.counterparty_name), self.stage, self.appetite,
                self.amount_text, self.rate_text, self.arrangement_fee_text, self.commitment_fee_text,
                self.maturity_text, self.dossier_status_raw, self.nda_sent_on, self.nda_received_on, self.next_steps)


@dataclass
class ContactDraft:
    institution_name: str
    full_name: str | None = None
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    last_interaction_on: str | None = None
    context: str | None = None
    mandate_code: str | None = None
    dataroom_access: bool = False
    notes: str | None = None
    sources: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        inst = normalize_name(self.institution_name) or "?"
        if self.email:
            return f"{inst}|{self.email.lower()}"
        return f"{inst}|name:{normalize_name(self.full_name or '')}"

    def values(self) -> dict[str, Any]:
        return {"institution_name": self.institution_name, "full_name": self.full_name, "job_title": self.job_title,
                "email": self.email, "phone": self.phone, "last_interaction_on": self.last_interaction_on,
                "context": self.context, "mandate_code": self.mandate_code, "dataroom_access": self.dataroom_access,
                "notes": self.notes}


@dataclass
class ParsedWorkbook:
    file_updated_on: str | None
    mandates: dict[str, MandateDraft]
    events: list[EventDraft]
    contacts: list[ContactDraft]
    detail_sheets: dict[str, str | None]  # sheet title -> mapped mandate code (None = not mapped)
    ignored_sheets: dict[str, str]
    warnings: list[str]

    def as_json(self) -> dict[str, Any]:
        return {
            "file_updated_on": self.file_updated_on,
            "mandates": {k: asdict(v) for k, v in self.mandates.items()},
            "events": [asdict(e) for e in self.events],
            "contacts": [{**asdict(c), "key": c.key} for c in self.contacts],
            "detail_sheets": self.detail_sheets,
            "ignored_sheets": self.ignored_sheets,
            "warnings": self.warnings,
        }


# =========================================================================== sheet / column finding
SHEET_TITLES = {
    "suivi": "syndicationdesdealstomasteed",
    "crm": "crminterne",
    "lenders": "lendermapping",
    "terms": "fundingtermsdatabase",
    "investors": "cartographiedesinvestisseurs",
}


def sheet_title(ws) -> str:
    """Concatenated keys of the first cells (where the title of the sheet is printed)."""
    parts = []
    for row in ws.iter_rows(min_row=1, max_row=6, max_col=12, values_only=True):
        parts.extend(key(v) for v in row if isinstance(v, str))
    return " ".join(parts)


def find_header(ws, wanted: dict[str, tuple[str, ...]], required: tuple[str, ...], *, max_row: int = 25
                ) -> tuple[int, dict[str, int]]:
    """(header row, {field: column}) — a column matches when its label key STARTS with a wanted prefix."""
    for row in ws.iter_rows(min_row=1, max_row=max_row):
        found: dict[str, int] = {}
        for cell in row:
            k = key(cell.value) if isinstance(cell.value, str) else ""
            if not k:
                continue
            for name, prefixes in wanted.items():
                if name not in found and any(k.startswith(p) for p in prefixes):
                    found[name] = cell.column
                    break
        if all(r in found for r in required):
            return row[0].row, found
    raise WorkbookError(f"sheet '{ws.title}': header not found (expected columns: {', '.join(required)})")


def cell(ws, row: int, cols: dict[str, int], name: str) -> Any:
    col = cols.get(name)
    return ws.cell(row=row, column=col).value if col else None


def merged_value(ws, row: int, col: int) -> Any:
    """Value of a cell, or of the top-left cell of the merged range that covers it."""
    value = ws.cell(row=row, column=col).value
    if value is not None:
        return value
    for rng in ws.merged_cells.ranges:
        if rng.min_col <= col <= rng.max_col and rng.min_row <= row <= rng.max_row:
            return ws.cell(row=rng.min_row, column=rng.min_col).value
    return None


# =========================================================================== field rules
def lender_type(text: str | None) -> str | None:
    f = fold(text or "").strip()
    if not f:
        return None
    if f.startswith("dfi"):
        return "dfi"
    if f.startswith("banque") or f.startswith("bank"):
        return "bank"
    if f.startswith("garant") or f.startswith("guarant"):
        return "guarantor"
    if f.startswith("investisseur") or f.startswith("investor"):
        return "investor"
    return "other"


def appetite(text: Any) -> bool | None:
    f = fold(str(text or "")).strip()
    if f.startswith("oui") or f == "yes":
        return True
    if f.startswith("non") or f == "no":
        return False
    return None


def stage_of(appetite_value: bool | None, dossier: str | None, has_amount: bool) -> str:
    """Documented rule (docs/syndication.md §3). The raw wording is always kept next to it."""
    d = fold(dossier or "")
    if "engagement" in d and ("prelim" in d or "ferme" in d):
        return "interested" if "prelim" in d else "committed"
    if "term sheet" in d or "termsheet" in d:
        return "term_sheet"
    if "decaiss" in d:
        return "disbursed"
    if "cours d'etude" in d or "en cours" in d or "etude" in d:
        return "approached"
    if appetite_value is False:
        return "declined"
    if appetite_value is True or has_amount:
        return "interested"
    return "approached"


def commitment(text: str | None, country_code: str | None) -> tuple[str | None, str | None]:
    """(amount, currency) only for ONE explicit amount; FCFA only for a UMOA country (XOF)."""
    if is_placeholder(text) or UNCERTAIN_AMOUNT.search((text or "").lower()) or UNCERTAIN_AMOUNT.search(fold(text or "")):
        return None, None
    money = parse_money(text or "", allow_cfa=country_code is not None)
    if money is None or money.amount <= 0:
        return None, None
    return str(money.amount), money.currency


def text_value(value: Any) -> str | None:
    """Kept as written (placeholders included: 'à confirmer' is information for the team)."""
    return clean(value)


def split_label(label: str) -> tuple[str | None, str, str]:
    """'SEN | Etat du Sénégal - Campagne d'arachide 24-25' -> ('SEN', client, title)."""
    title = " ".join(label.split())
    raw, _, rest = title.partition("|")
    country = raw.strip().upper() if rest and re.fullmatch(r"[A-Za-z]{2,3}", raw.strip()) else None
    body = rest.strip() if country else title
    client = body.split(" - ")[0].strip(" -") or body
    return country, client[:255], title


def mandate_code(label: str, taken: dict[str, str]) -> str:
    """Stable code from the label; two different labels never share a code."""
    country, _, title = split_label(label)
    base = slug(title)[:46].strip("-") or "deal"
    code, n = base, 2
    while code in taken and taken[code] != title:
        code = f"{base[:43]}-{n}"
        n += 1
    taken[code] = title
    return code


def contacts_from_cells(institution: str, names: Any, functions: Any, phones: Any, emails: Any, *,
                        mandate_code_: str | None, source: str) -> list[ContactDraft]:
    """Multi-line cells paired line by line ONLY when the counts match; otherwise kept unpaired."""
    n, f, p, e = lines(names), lines(functions), lines(phones), [x for x in lines(emails) if "@" in x]
    out: list[ContactDraft] = []
    if not n and not e:
        return out
    if n:
        for i, name in enumerate(n):
            c = ContactDraft(institution_name=institution, full_name=name[:255], mandate_code=mandate_code_,
                             sources=[source])
            c.job_title = f[i] if len(f) == len(n) else None
            c.email = e[i].lower() if len(e) == len(n) else None
            c.phone = p[i] if len(p) == len(n) else None
            out.append(c)
        unpaired = [x for x, lst in (("e-mails", e), ("téléphones", p), ("fonctions", f)) if lst and len(lst) != len(n)]
        if unpaired:
            out[0].notes = "Non appariés (nombre de lignes différent) : " + "; ".join(
                f"{label}: {', '.join(lst)}" for label, lst in (("e-mails", e), ("téléphones", p), ("fonctions", f))
                if label in unpaired)
    else:
        out = [ContactDraft(institution_name=institution, email=x.lower(), mandate_code=mandate_code_, sources=[source])
               for x in e]
    return out


# =========================================================================== sheets
SUIVI_COLUMNS = {
    "deal": ("nomdudeal",), "stage": ("stade",), "institution": ("banques", "banque"), "appetite": ("appetit",),
    "lender_type": ("typedepreteur",), "amount": ("montantsdesengagements", "montantdesengagements", "engagement"),
    "rate": ("taux",), "arr_fee": ("commissiondarrangement",), "commit_fee": ("commissiondengagement",),
    "maturity": ("maturite",), "names": ("interlocuteur",), "functions": ("fonction",), "phones": ("telephone",),
    "emails": ("mail", "adressesemail", "email"),
}
DETAIL_COLUMNS = {
    "institution": ("banques", "banque"), "appetite": ("appetit",), "commitment": ("engagement",),
    "dossier": ("etatdudossier",), "feedback": ("retourobtenu", "retour"), "names": ("interlocuteur",),
    "functions": ("fonction",), "emails": ("adressesemail", "email", "mail"), "phones": ("telephone",),
    "nda_sent": ("datedetransmission",), "nda_received": ("datedereception",), "next": ("prochainesetapes",),
}
CRM_COLUMNS = {
    "institution": ("institution",), "name": ("nomducontact",), "function": ("fonction",), "email": ("email",),
    "phone": ("telephone",), "last": ("derniereinteraction",), "context": ("contexte",),
}


BLOCK_COLUMNS = {
    "institution": ("banques", "banque"), "amount": ("montantsdesengagements", "montantdesengagements", "engagement"),
    "rate": ("taux",), "maturity": ("maturite",), "appetite": ("appetit",), "dossier": ("etatdudossier",),
}
# A line holding only a label is a section title when it reads like a status ("LOI reçus", "LOI à
# recevoir", "Prêteurs"); otherwise it is a counterparty with nothing recorded yet.
SECTION_WORDS = re.compile(r"\b(loi|lettres?|recus?|recevoir|en attente|preteurs|garants?)\b")
BLANK_ROWS_END_A_DEAL = 3  # rows without any value: what follows is not a continuation of the last deal


def block_key(ws, row: int) -> str:
    """Name of a second table found inside a sheet (mapped to a mandate like a detail sheet)."""
    return f"{ws.title}!{row}"


def parse_suivi(ws, taken: dict[str, str], parsed: ParsedWorkbook) -> list[int]:
    """Main table. Returns the header rows of the other tables found below it (e.g. the LOI received
    for one deal): they are never read with the main table's columns."""
    for row in ws.iter_rows(min_row=1, max_row=8):
        for c in row:
            if key(c.value).startswith("date") and parsed.file_updated_on is None:
                nxt = next((x.value for x in row if x.column > c.column and as_date(x.value)), None)
                if nxt:
                    parsed.file_updated_on = as_date(nxt).isoformat()
    header, cols = find_header(ws, SUIVI_COLUMNS, ("deal", "institution", "appetite"))
    last_label: str | None = None
    blank_run = 0
    # The header label itself ("Banques / Institution"), never a bank name that starts like it ("Banque X").
    header_labels = {key(ws.cell(row=header, column=cols["institution"]).value), "banques", "banque",
                     "banquesinstitution", "banquesinstitutions", "institution", "institutions"}
    for r in range(header + 1, ws.max_row + 1):
        label = clean(cell(ws, r, cols, "deal"))
        institution = clean(cell(ws, r, cols, "institution"))
        if institution and not label and key(institution) in header_labels:
            # A header repeated below the table: a second table starts (its columns differ).
            parsed.warnings.append(f"{block_key(ws, r)}: second table below the main one — imported only once "
                                   "mapped to a mandate")
            return [r]
        if not any(clean(ws.cell(row=r, column=c).value) for c in cols.values()):
            blank_run += 1
            if blank_run >= BLANK_ROWS_END_A_DEAL:
                last_label = None
            continue
        blank_run = 0
        if label:
            last_label = label
        if not last_label or (not label and not institution):
            continue
        country_raw, client, title = split_label(last_label)
        code = mandate_code(last_label, taken)
        draft = parsed.mandates.get(code)
        if draft is None:
            draft = parsed.mandates[code] = MandateDraft(
                code=code, title=title, client_name=client, country_code=UMOA_ISO3.get(country_raw or ""),
                country_code_raw=country_raw)
        draft.rows.append(r)
        stage = clean(cell(ws, r, cols, "stage"))
        if stage:
            draft.stage_raw = stage
            if "mandat execute" in fold(stage):
                draft.status = "closed_won"
        if not institution:
            continue
        amount_text = text_value(cell(ws, r, cols, "amount"))
        amount, currency = commitment(amount_text, draft.country_code)
        app = appetite(cell(ws, r, cols, "appetite"))
        parsed.events.append(EventDraft(
            mandate_code=code, counterparty_name=institution[:255], stage=stage_of(app, None, amount is not None),
            lender_type=lender_type(clean(cell(ws, r, cols, "lender_type"))), appetite=app, amount=amount,
            currency=currency, amount_text=amount_text, rate_text=text_value(cell(ws, r, cols, "rate")),
            arrangement_fee_text=text_value(cell(ws, r, cols, "arr_fee")),
            commitment_fee_text=text_value(cell(ws, r, cols, "commit_fee")),
            maturity_text=text_value(cell(ws, r, cols, "maturity")), sheet=ws.title, row=r,
        ))
        if re.search(r"/\s*autres?\b", fold(institution)):
            parsed.warnings.append(f"{ws.title}!{r}: '{institution}' names several counterparties — kept as one "
                                   "line, to split by hand")
        parsed.contacts.extend(contacts_from_cells(
            institution, cell(ws, r, cols, "names"), cell(ws, r, cols, "functions"), cell(ws, r, cols, "phones"),
            cell(ws, r, cols, "emails"), mandate_code_=code, source=f"{ws.title}!{r}"))
    return []


def parse_block(ws, header: int, code: str, parsed: ParsedWorkbook) -> None:
    """A second table inside a sheet (institution, amount, rate, maturity), mapped by the user to one
    mandate. A line holding only a label ("LOI reçus", "LOI à recevoir") titles the lines below it."""
    found: dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        k = key(ws.cell(row=header, column=c).value)
        for name, prefixes in BLOCK_COLUMNS.items():
            if k and name not in found and k.startswith(prefixes):
                found[name] = c
    section: str | None = None
    country = parsed.mandates[code].country_code
    for r in range(header + 1, ws.max_row + 1):
        institution = clean(cell(ws, r, found, "institution"))
        others = [clean(ws.cell(row=r, column=c).value) for n, c in found.items() if n != "institution"]
        if not institution:
            continue
        if not any(others) and SECTION_WORDS.search(fold(institution)):
            section = institution  # "LOI reçus": a title, not a counterparty
            continue
        amount_raw = cell(ws, r, found, "amount")
        amount_text = text_value(amount_raw)
        amount, currency = None, None
        if isinstance(amount_raw, int | float):
            # Sheet header: "Montant en XOF Millions". A number only for a UMOA country (XOF); otherwise
            # (e.g. Guinea) the currency is not assumed and the figure stays text.
            amount_text = f"{amount_raw:g} (millions, unité de l'en-tête de la feuille)"
            if amount_raw > 0 and country:
                amount, currency = str(Decimal(str(amount_raw)) * 10**6), "XOF"
        elif amount_text:
            amount, currency = commitment(amount_text, country)
        rate_raw = cell(ws, r, found, "rate")
        rate_text = (f"{(Decimal(str(rate_raw)) * 100).normalize():f} %" if isinstance(rate_raw, int | float)
                     else text_value(rate_raw))
        received = section is not None and "recu" in fold(section) and "recevoir" not in fold(section)
        parsed.events.append(EventDraft(
            mandate_code=code, counterparty_name=institution[:255],
            stage="interested" if received or amount is not None else "approached",
            appetite=True if received else None, amount=amount, currency=currency, amount_text=amount_text,
            rate_text=rate_text, maturity_text=text_value(cell(ws, r, found, "maturity")),
            dossier_status_raw=section, sheet=ws.title, row=r,
        ))


def is_detail_sheet(ws) -> bool:
    try:
        find_header(ws, DETAIL_COLUMNS, ("institution", "dossier"), max_row=15)
        return True
    except WorkbookError:
        return False


def parse_detail(ws, code: str, parsed: ParsedWorkbook) -> None:
    header, cols = find_header(ws, DETAIL_COLUMNS, ("institution", "dossier"), max_row=15)
    section_type: str | None = None
    country = parsed.mandates[code].country_code
    for r in range(header + 1, ws.max_row + 1):
        first = " ".join(key(ws.cell(row=r, column=c).value) for c in range(1, min(ws.max_column, 12) + 1)
                         if isinstance(ws.cell(row=r, column=c).value, str))
        if first.startswith("total") or " total" in f" {first}":
            break
        if key(first) in ("preteurs",) or first.strip() == "preteurs":
            section_type = "bank"
            continue
        if first.strip() in ("garants", "garant"):
            section_type = "guarantor"
            continue
        institution = clean(cell(ws, r, cols, "institution"))
        app = appetite(cell(ws, r, cols, "appetite"))
        dossier = clean(cell(ws, r, cols, "dossier"))
        if not institution:
            if app is not None or dossier:
                parsed.warnings.append(f"{ws.title}!{r}: line without an institution name — not imported")
            continue
        commitment_raw = cell(ws, r, cols, "commitment")
        commitment_text = clean(commitment_raw)
        nda_sent, nda_received = cell(ws, r, cols, "nda_sent"), cell(ws, r, cols, "nda_received")
        notes = [f"NDA : {clean(x)}" for x in (nda_sent, nda_received) if x is not None and as_date(x) is None
                 and clean(x)]
        header_label = clean(ws.cell(row=header, column=cols["commitment"]).value) if "commitment" in cols else None
        parsed.events.append(EventDraft(
            mandate_code=code, counterparty_name=institution[:255],
            stage=stage_of(app, dossier, False), lender_type=section_type, appetite=app,
            # The unit of this column ("GXAF") contradicts the sheet header ("XOF Millions"): text only.
            amount_text=f"{commitment_text} ({header_label})" if commitment_text and header_label else commitment_text,
            dossier_status_raw=dossier, nda_sent_on=as_date(nda_sent).isoformat() if as_date(nda_sent) else None,
            nda_received_on=as_date(nda_received).isoformat() if as_date(nda_received) else None,
            next_steps=clean(cell(ws, r, cols, "next")), notes="; ".join(dict.fromkeys(notes)) or None,
            sheet=ws.title, row=r,
        ))
        parsed.contacts.extend(contacts_from_cells(
            institution, cell(ws, r, cols, "names"), cell(ws, r, cols, "functions"), cell(ws, r, cols, "phones"),
            cell(ws, r, cols, "emails"), mandate_code_=code, source=f"{ws.title}!{r}"))
        _ = country


def parse_crm(ws, parsed: ParsedWorkbook) -> None:
    header, cols = find_header(ws, CRM_COLUMNS, ("institution", "name", "email"))
    for r in range(header + 1, ws.max_row + 1):
        institution = clean(merged_value(ws, r, cols["institution"]))
        name = clean(cell(ws, r, cols, "name"))
        email = clean(cell(ws, r, cols, "email"))
        if not institution or (not name and not email):
            continue
        last = cell(ws, r, cols, "last")
        parsed.contacts.append(ContactDraft(
            institution_name=institution[:255], full_name=name[:255] if name and not is_placeholder(name) else None,
            job_title=None if is_placeholder(clean(cell(ws, r, cols, "function"))) else clean(cell(ws, r, cols, "function")),
            email=email.lower() if email and "@" in email else None,
            phone=None if is_placeholder(clean(cell(ws, r, cols, "phone"))) else clean(cell(ws, r, cols, "phone")),
            last_interaction_on=as_date(last).isoformat() if as_date(last) else None,
            context=None if is_placeholder(clean(cell(ws, r, cols, "context"))) else clean(cell(ws, r, cols, "context")),
            sources=[f"{ws.title}!{r}"],
        ))


def parse_dataroom(ws, parsed: ParsedWorkbook) -> int:
    """Blocks: an institution name (merged over two columns) and, below, rows 'name | e-mail'."""
    found = 0
    for col in range(1, ws.max_column + 1):
        institution: str | None = None
        for r in range(1, ws.max_row + 1):
            name = clean(ws.cell(row=r, column=col).value)
            right = clean(ws.cell(row=r, column=col + 1).value)
            if name and "@" not in name and right is None:
                below = clean(ws.cell(row=r + 1, column=col + 1).value)
                institution = name if below and "@" in below else None
                continue
            if institution and name and right and "@" in right:
                parsed.contacts.append(ContactDraft(institution_name=institution[:255], full_name=name[:255],
                                                    email=right.lower(), dataroom_access=True,
                                                    sources=[f"{ws.title}!{ws.cell(row=r, column=col).coordinate}"]))
                found += 1
            elif not name:
                institution = None if not right else institution
    return found


def merge_contacts(contacts: list[ContactDraft]) -> list[ContactDraft]:
    """One contact per person: same institution and e-mail, or same institution and name."""
    by_key: dict[str, ContactDraft] = {}
    name_to_key: dict[str, str] = {}
    for c in contacts:
        if c.email and c.full_name:
            name_to_key[f"{normalize_name(c.institution_name)}|name:{normalize_name(c.full_name)}"] = c.key
    for c in contacts:
        k = name_to_key.get(c.key, c.key)
        if k not in by_key:
            by_key[k] = c
            continue
        kept = by_key[k]
        for f in ("full_name", "job_title", "email", "phone", "last_interaction_on", "context", "mandate_code"):
            if getattr(kept, f) is None and getattr(c, f) is not None:
                setattr(kept, f, getattr(c, f))
        kept.dataroom_access = kept.dataroom_access or c.dataroom_access
        kept.notes = "; ".join(x for x in (kept.notes, c.notes) if x) or None
        kept.sources = list(dict.fromkeys(kept.sources + c.sources))
    return list(by_key.values())


def read_workbook(content: bytes, *, sheet_mapping: dict[str, str] | None = None) -> ParsedWorkbook:
    """``sheet_mapping``: detail sheet title -> mandate code (or label), chosen by the user."""
    check_archive(content)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    except Exception as err:  # not an xlsx
        raise WorkbookError(f"not a readable .xlsx workbook ({type(err).__name__})") from err
    parsed = ParsedWorkbook(None, {}, [], [], {}, {}, [])
    taken: dict[str, str] = {}
    titles = {ws.title: sheet_title(ws) for ws in wb.worksheets}
    suivi = [ws for ws in wb.worksheets if SHEET_TITLES["suivi"] in titles[ws.title]]
    if len(suivi) != 1:
        raise WorkbookError("sheet 'SYNDICATION DES DEALS TOMASTEED' not found exactly once")
    blocks = parse_suivi(suivi[0], taken, parsed)
    mapping = sheet_mapping or {}
    by_title = {m.title: c for c, m in parsed.mandates.items()}
    for row in blocks:
        name = block_key(suivi[0], row)
        target = mapping.get(name)
        code = target if target in parsed.mandates else by_title.get(" ".join((target or "").split()))
        parsed.detail_sheets[name] = code
        if code:
            parse_block(suivi[0], row, code, parsed)
    for ws in wb.worksheets:
        if ws is suivi[0]:
            continue
        t = titles[ws.title]
        if SHEET_TITLES["crm"] in t:
            parse_crm(ws, parsed)
        elif SHEET_TITLES["lenders"] in t or SHEET_TITLES["terms"] in t:
            parsed.ignored_sheets[ws.title] = "derived from SUIVI SYNDICATION: recomputed by the platform"
        elif SHEET_TITLES["investors"] in t:
            parsed.ignored_sheets[ws.title] = "no investor recorded in the file"
        elif is_detail_sheet(ws):
            target = mapping.get(ws.title)
            code = target if target in parsed.mandates else by_title.get(" ".join((target or "").split()))
            parsed.detail_sheets[ws.title] = code
            if code:
                parse_detail(ws, code, parsed)
        elif parse_dataroom(ws, parsed):
            pass
        else:
            parsed.ignored_sheets[ws.title] = "structure not recognised"
    parsed.contacts = merge_contacts(parsed.contacts)
    for c in parsed.contacts:
        if c.email and not valid_email(c.email):
            parsed.warnings.append(f"{', '.join(c.sources)}: e-mail '{c.email}' looks invalid — not imported, "
                                   "kept in the notes")
            c.notes = "; ".join(x for x in (c.notes, f"E-mail invalide dans le fichier : {c.email}") if x)
            c.email = None
    return parsed


EMAIL = re.compile(r"[a-z0-9._%+'-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,24}")
TLD_TYPOS = {"ccom", "comm", "con", "cmo", "ocm", "frr", "orgg"}


def valid_email(email: str) -> bool:
    """Format check plus the usual top-level-domain typos ('.ccom'). Never corrected by guess."""
    return bool(EMAIL.fullmatch(email)) and email.rsplit(".", 1)[-1] not in TLD_TYPOS


def amount_decimal(text: str | None) -> Decimal | None:
    return Decimal(text) if text else None
