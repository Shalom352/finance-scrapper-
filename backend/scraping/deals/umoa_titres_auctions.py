"""
UMOA-Titres auction results -> sovereign_bond deals (OAT only).

Source of truth: the official "Compte rendu d'adjudication" PDF of each emission, published on
the emission page of www.umoatitres.org, cross-checked against the results printed on that page.
Announcements (avis d'appel d'offres, termes et conditions) never create a deal.

Rules (DATA MISSING > DATA WRONG):
  - one deal per OAT tranche whose retained amount ("Soumissions retenues") is > 0;
    a tranche at 0, "--" or without a result creates nothing (never a 0 amount);
  - every value is read as printed: amounts stay in millions of F CFA (unit "millions",
    currency XOF = ISO code of the F CFA), rates in percent; nothing is converted or computed,
    except the duration "N ans" expressed in months (N x 12);
  - the issuer is linked to one of the 8 sovereign_state entities only when the printed issuer
    ("ETAT DU MALI") and the ISIN country prefix designate the same country;
  - PDF / page contradiction on an attested value -> the whole auction is skipped and reported;
  - deals enter through the Phase 13 importer only: needs_review, field-level provenance,
    audit event, duplicate candidates. Idempotence: deterministic ingestion_key.
"""
from __future__ import annotations

import html as html_lib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pymupdf

INDEX_URL = "https://www.umoatitres.org/fr/emissions/"
EMISSION_URL_RE = re.compile(r"https://www\.umoatitres\.org/fr/emission/[^'\"\s<>]+?/(?=['\"])")
SLUG_DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})(?:-\d+)?/?$")
COMPTE_RENDU_RE = re.compile(r"""href=['"]([^'"]*Compte[-_ ]?Rendu[^'"]*\.pdf)['"]""", re.IGNORECASE)

ISIN = r"[A-Z]{2}[A-Z0-9]{9}\d"
ISIN_RE = re.compile(rf"^{ISIN}$")
# Some documents print a stray space before a hyphen ("NE0000002243 -OAT-11-2028"): tolerated there only.
DENOMINATION_RE = re.compile(rf"^({ISIN}) ?-(BAT|OAT)-\d{{2}}-\d{{4}}$")
# Issuance references (ADJ-...); the year may be printed truncated ("-202"): kept exactly as printed.
AUCTION_REF_RE = re.compile(r"^ADJ-[A-Z0-9]+(?: ?-[A-Z0-9]*)*$")
# Buyback references (RA-...): a buyback is never an issuance.
BUYBACK_REF_RE = re.compile(r"^RA-[A-Z0-9 -]+$")
DATE_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")
DURATION_RE = re.compile(r"^(\d+)\s*(jours|ans|an|mois)$", re.IGNORECASE)
PCT_RE = re.compile(r"^(\d+(?:[,.]\d+)?)\s*%$")
# A lone dash in a per-security list = no result for that security (kept as a placeholder, never 0).
PCT_OR_DASH_RE = re.compile(r"^(?:(\d+(?:[,.]\d+)?)\s*%|-+)$")
TRANCHE_AMOUNT_RE = re.compile(r"^(\d[\d ]*(?:,\d+)?)\s*millions de F ?CFA", re.IGNORECASE)
NUMBER_RE = re.compile(r"^:?\s*(\d[\d ]*(?:,\d+)?)$")
# Global retained amount, alone or followed by its unit on the same line ("10 000,21 millions de FCFA, ...").
GLOBAL_TOTAL_RE = re.compile(r"^:?\s*(\d[\d ]*(?:,\d+)?)(?:\s+millions\b.*)?$", re.IGNORECASE)

NBSP, NARROW_NBSP = chr(0xA0), chr(0x202F)
CURRENCY = "XOF"  # ISO 4217 code of the franc CFA (BCEAO) printed as "F CFA" / "FCFA"
UNIT = "millions"
YIELD_TOLERANCE = Decimal("0.01")  # the emission page rounds the PDF yield (7,3396 % -> 7,3400 %)

# Issuers exactly as UMOA-Titres prints them (normalized) -> country. Closed list, never fuzzy.
ISSUER_COUNTRIES = {
    "ETAT DU BENIN": "BJ",
    "ETAT DU BURKINA": "BF",
    "ETAT DU BURKINA FASO": "BF",
    "ETAT DE COTE D IVOIRE": "CI",
    "ETAT DE LA COTE D IVOIRE": "CI",
    "ETAT DE GUINEE BISSAU": "GW",
    "ETAT DE LA GUINEE BISSAU": "GW",
    "ETAT DU MALI": "ML",
    "ETAT DU NIGER": "NE",
    "ETAT DU SENEGAL": "SN",
    "ETAT DU TOGO": "TG",
}
# Labels printed truncated by the source. Accepted ONLY when every ISIN of the auction carries the
# same country prefix (checked for every issuer anyway); the deal gets the issuer_label_truncated flag
# and the rule is written in the provenance excerpt.
TRUNCATED_ISSUER_LABELS = {
    "ETAT DE GUINEE BISSA": "GW",
}

# Validation flags attached to a deal (closed list).
FLAG_GLOBAL_TOTAL_ROUNDED = "global_total_rounded"
FLAG_ISSUER_LABEL_TRUNCATED = "issuer_label_truncated"
FLAG_PAGE_LISTS_BUYBACK_SECURITIES = "page_lists_buyback_securities"


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())


def parse_amount(text: str) -> Decimal | None:
    """'13 199,54' -> Decimal('13199.54'); anything else -> None (never 0 for a missing value)."""
    cleaned = text.replace(" ", "").replace(",", ".").strip()
    if not cleaned or cleaned in ("-", "--"):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_date(text: str) -> date | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def slug_date(url: str) -> date | None:
    m = SLUG_DATE_RE.search(url)
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def emission_urls(index_html: str) -> list[str]:
    return sorted(set(EMISSION_URL_RE.findall(index_html)))


# =========================================================================== PDF (compte rendu)


@dataclass
class PdfTranche:
    isin: str
    instrument_type: str  # from the printed denomination (ISIN-OAT-mm-yyyy)
    auction_reference: str
    duration_text: str
    maturity_date: date | None
    retained_text: str | None
    retained: Decimal | None
    coupon: Decimal | None = None
    yield_rate: Decimal | None = None


@dataclass
class CompteRendu:
    page_number: int
    issuer_label: str
    auction_date: date | None
    value_date: date | None
    tranches: list[PdfTranche]
    flags: list[str] = field(default_factory=list)


class LayoutError(ValueError):
    """The document does not have the expected structure: nothing is extracted from it."""


def _tokens(text: str) -> list[str]:
    text = text.replace(NBSP, " ").replace(NARROW_NBSP, " ")
    return [" ".join(line.split()) for line in text.splitlines() if line.strip()]


def _label_index(tokens: list[str], prefix: str, start: int = 0) -> int | None:
    key = norm(prefix)
    for i in range(start, len(tokens)):
        if norm(tokens[i]).startswith(key):
            return i
    return None


def _collect(tokens: list[str], start: int, pattern: re.Pattern[str], limit: int | None = None,
             include_label: bool = False) -> list[re.Match[str]]:
    """Consecutive tokens after a label matching `pattern` (a lone ':' token is skipped)."""
    out: list[re.Match[str]] = []
    i = start if include_label else start + 1
    while i < len(tokens) and (limit is None or len(out) < limit):
        tok = tokens[i].lstrip(":").strip()
        if include_label and i == start:
            tok = tok.split(":", 1)[1].strip() if ":" in tok else ""
            if not tok:
                i += 1
                continue
        if not tok:
            i += 1
            continue
        m = pattern.match(tok)
        if not m:
            break
        out.append(m)
        i += 1
    return out


BUYBACK_TITLES = ("COMPTE RENDU DE RACHAT", "COMPTE RENDU D ADJUDICATION RACHAT")
# Labels of the compte rendu: never an issuer name.
KNOWN_LABELS = ("NATURE DES TITRES", "MONTANT", "DATE", "CODE ISIN", "DENOMINATION", "ADJUDICATION", "DUREE")


def _is_buyback_page(tokens: list[str], i_adj: int | None, n: int) -> bool:
    """Buyback page (securities bought back by the Treasury, never an issuance): RA-... references, or a
    "COMPTE RENDU (D'ADJUDICATION) (DE) RACHAT" title printed anywhere on the page (often at the bottom)
    when the page carries no ADJ-... issuance reference."""
    if i_adj is not None and len(_collect(tokens, i_adj, BUYBACK_REF_RE, n, include_label=True)) == n:
        return True
    has_issuance_ref = i_adj is not None and bool(_collect(tokens, i_adj, AUCTION_REF_RE, 1, include_label=True))
    return not has_issuance_ref and any(norm(t).startswith(BUYBACK_TITLES) for t in tokens)


@dataclass
class BuybackPage:
    """Securities bought back, as listed on the buyback page of a compte rendu (never a deal)."""

    page_number: int
    references: list[str]
    securities: list[tuple[str, date | None]]  # (type, maturity date); [] when unreadable


def parse_buyback_page(text: str, page_number: int) -> BuybackPage | None:
    """The buyback page of an 'EC' compte rendu; None for any other page."""
    tokens = _tokens(text)
    i_isin = _label_index(tokens, "Code ISIN")
    if i_isin is None:
        return None
    isins = [m.group(0) for m in _collect(tokens, i_isin, ISIN_RE, include_label=True)]
    n = len(isins)
    i_adj = _label_index(tokens, "Adjudication n")
    if not n or not _is_buyback_page(tokens, i_adj, n):
        return None
    refs = [m.group(0) for m in _collect(tokens, i_adj, BUYBACK_REF_RE, n, include_label=True)] \
        if i_adj is not None else []
    i_den = _label_index(tokens, "Dénomination de l'émission")
    dens = _collect(tokens, i_den, DENOMINATION_RE, n, include_label=True) if i_den is not None else []
    i_mat = _label_index(tokens, "Date d'échéance")
    mats = _collect(tokens, i_mat, re.compile(r"^\d{2}/\d{2}/\d{4}$"), n, include_label=True) \
        if i_mat is not None else []
    securities: list[tuple[str, date | None]] = []
    if len(dens) == n and len(mats) == n and [m.group(1) for m in dens] == isins:
        securities = [(d.group(2), parse_date(m.group(0))) for d, m in zip(dens, mats, strict=True)]
    return BuybackPage(page_number=page_number, references=refs, securities=securities)


def parse_compte_rendu_page(text: str, page_number: int) -> CompteRendu | None:
    """Parse one page; None when the page holds no issuance (no ISIN block, or a buyback page)."""
    tokens = _tokens(text)
    i_isin = _label_index(tokens, "Code ISIN")
    if i_isin is None:
        return None
    isins = [m.group(0) for m in _collect(tokens, i_isin, ISIN_RE, include_label=True)]
    if not isins:
        return None
    n = len(isins)
    flags: list[str] = []

    i_adj = _label_index(tokens, "Adjudication n")
    if _is_buyback_page(tokens, i_adj, n):
        return None

    i_issuer = _label_index(tokens, "Emetteur")
    if i_issuer is None:
        raise LayoutError("issuer label not found")
    issuer = tokens[i_issuer].split(":", 1)[1].strip() if ":" in tokens[i_issuer] else ""
    if not issuer:
        issuer = tokens[i_issuer + 1].lstrip(":").strip()
    if norm(issuer).startswith(KNOWN_LABELS):
        # The token after "Emetteur :" is another label: the issuer is not printed next to its label.
        # Never guessed from elsewhere on the page.
        raise LayoutError("issuer label not found")

    i_den = _label_index(tokens, "Dénomination de l'émission")
    dens = _collect(tokens, i_den, DENOMINATION_RE, n, include_label=True) if i_den is not None else []
    if len(dens) != n or [m.group(1) for m in dens] != isins:
        raise LayoutError("denominations do not match the ISIN list")
    types = [m.group(2) for m in dens]

    refs = _collect(tokens, i_adj, AUCTION_REF_RE, n, include_label=True) if i_adj is not None else []
    if len(refs) != n:
        raise LayoutError("auction references do not match the ISIN list")

    i_auction = _label_index(tokens, "Date d'adjudication")
    auction_date = None
    if i_auction is not None:
        auction_date = next((d for t in tokens[i_auction:i_auction + 4] if (d := parse_date(t))), None)
    elif i_adj is not None:  # single-security layout: "Adjudication N° ... du : 18/08/2025"
        i_du = _label_index(tokens, "du", i_adj)
        auction_date = parse_date(tokens[i_du]) if i_du is not None else None
    i_value = _label_index(tokens, "Date de valeur")
    value_date = next((d for t in tokens[i_value:i_value + 4] if (d := parse_date(t))), None) if i_value else None

    i_dur = _label_index(tokens, "Durée")
    durations = _collect(tokens, i_dur, DURATION_RE, n, include_label=True) if i_dur is not None else []
    if len(durations) != n:
        raise LayoutError("durations do not match the ISIN list")

    i_mat = _label_index(tokens, "Date d'échéance")
    maturities = _collect(tokens, i_mat, re.compile(r"^\d{2}/\d{2}/\d{4}$"), n, include_label=True) \
        if i_mat is not None else []
    if len(maturities) != n:
        raise LayoutError("maturity dates do not match the ISIN list")

    retained = _tranche_amounts(tokens, n)
    if retained is None:
        raise LayoutError("retained amounts per security not found")

    tranches = [
        PdfTranche(
            isin=isins[k], instrument_type=types[k], auction_reference=refs[k].group(0),
            duration_text=durations[k].group(0), maturity_date=parse_date(maturities[k].group(0)),
            retained_text=retained[k], retained=parse_amount(retained[k]) if retained[k] else None,
        )
        for k in range(n)
    ]

    # Announced fixed coupon: printed for the OAT only, in tranche order.
    oat = [t for t in tranches if t.instrument_type == "OAT"]
    i_cpn = _label_index(tokens, "Taux d'intérêt fixe annoncé")
    if i_cpn is not None and oat:
        coupons = _collect(tokens, i_cpn, PCT_OR_DASH_RE)
        if len(coupons) == len(oat):
            for t, m in zip(oat, coupons, strict=True):
                t.coupon = parse_amount(m.group(1)) if m.group(1) else None
        else:
            flags.append("coupon_count_mismatch")

    i_yield = _label_index(tokens, "Rendement moyen pondéré")
    if i_yield is not None:
        yields = _collect(tokens, i_yield, PCT_OR_DASH_RE, n, include_label=True)
        if len(yields) == n:
            for t, m in zip(tranches, yields, strict=True):
                t.yield_rate = parse_amount(m.group(1)) if m.group(1) else None
        else:
            flags.append("yield_count_mismatch")

    if _check_total(tokens, tranches, n) == "rounded":
        flags.append(FLAG_GLOBAL_TOTAL_ROUNDED)
    return CompteRendu(page_number=page_number, issuer_label=issuer, auction_date=auction_date,
                       value_date=value_date, tranches=tranches, flags=flags)


def _tranche_amounts(tokens: list[str], n: int) -> list[str | None] | None:
    """Per-security 'Soumissions retenues' (multi layout), or the single value (one security)."""
    start = 0
    while (i := _label_index(tokens, "Soumissions retenues", start)) is not None:
        block = tokens[i + 1:i + 1 + n]
        matches = [TRANCHE_AMOUNT_RE.match(t) for t in block]
        if len(block) == n and all(matches):
            return [m.group(1).strip() for m in matches]  # type: ignore[union-attr]
        start = i + 1
    if n == 1:  # single-security layout: "Soumissions retenues | : 15 000 | millions de FCFA"
        i = _label_index(tokens, "Soumissions retenues")
        if i is not None:
            for tok in tokens[i:i + 3]:
                rest = tok.split(":", 1)[1] if ":" in tok else tok
                m = NUMBER_RE.match(rest.strip())
                if m:
                    return [m.group(1).strip()]
    return None


def _check_total(tokens: list[str], tranches: list[PdfTranche], n: int) -> str | None:
    """Multi layout: the global retained amount must equal the sum of the tranches.

    Returns None (exact), or "rounded" when the printed total is an integer (no decimal part printed)
    equal to round(sum of the tranches) — the tranche amounts of the PDF are kept as printed. Any
    other difference refuses the document: the tolerance is never widened in general.
    """
    if n == 1:
        return None
    i = _label_index(tokens, "Soumissions retenues")
    total_text = None
    if i is not None:
        for tok in tokens[i + 1:i + 3]:
            m = GLOBAL_TOTAL_RE.match(tok.strip())
            if m:
                total_text = m.group(1).strip()
                break
    total = parse_amount(total_text) if total_text else None
    if total is None:
        raise LayoutError("global retained amount not found")
    parts = sum((t.retained or Decimal(0)) for t in tranches)
    if abs(parts - total) <= Decimal("0.01"):
        return None
    if "," not in total_text and total == parts.quantize(Decimal(1), rounding=ROUND_HALF_UP):
        return "rounded"
    raise LayoutError(f"tranche amounts ({parts}) do not add up to the global retained amount ({total})")


@dataclass
class CompteRenduDocument:
    reports: list[CompteRendu]  # issuance pages
    buybacks: list[BuybackPage]  # buyback pages (only used to justify the page rows bought back)


def parse_compte_rendu_document(pdf_bytes: bytes) -> CompteRenduDocument:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pages = [(n, page.get_text()) for n, page in enumerate(doc, start=1)]
    reports: list[CompteRendu] = []
    buybacks: list[BuybackPage] = []
    for n, text in pages:
        parsed = parse_compte_rendu_page(text, n)
        if parsed is not None:
            reports.append(parsed)
            continue
        buyback = parse_buyback_page(text, n)
        if buyback is not None:
            buybacks.append(buyback)
    return CompteRenduDocument(reports, buybacks)


def parse_compte_rendu(pdf_bytes: bytes) -> list[CompteRendu]:
    return parse_compte_rendu_document(pdf_bytes).reports


# =========================================================================== emission page (HTML)


@dataclass
class PageResult:
    instrument_type: str | None
    retained: Decimal | None
    yield_rate: Decimal | None
    maturity_date: date | None = None  # from the offer block, when it lists the securities in the same order


@dataclass
class EmissionPage:
    operation_date: date | None
    value_date: date | None
    compte_rendu_url: str | None
    results: list[PageResult]
    maturities: list[tuple[str, date | None]]  # (type, échéance) from "Caractéristiques de l'offre"


_RESULT_BLOCK_RE = re.compile(r"(?=\b(?:BAT|OAT)\s+Montant sollicit)")


def page_text(page_html: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", page_html, flags=re.IGNORECASE | re.DOTALL)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.replace(NBSP, " ").split())


def parse_emission_page(page_html: str) -> EmissionPage:
    text = page_text(page_html)
    links = COMPTE_RENDU_RE.findall(page_html)
    op = re.search(r"Date de l'op[ée]ration:\s*(\d{2}/\d{2}/\d{4})", text)
    val = re.search(r"Date de valeur:\s*(\d{2}/\d{2}/\d{4})", text)

    single = re.search(r"Instrument:\s*(BAT|OAT)\b", text)
    offer = text.split("Résultats Performances", 1)[0]
    maturities = [(m.group(1), parse_date(m.group(2))) for m in re.finditer(
        r"\b(BAT|OAT)\s+Durée:.*?[EÉ]ch[ée]ance:\s*(\d{2}/\d{2}/\d{4})", offer)]
    if not maturities and single:
        m = re.search(r"[EÉ]ch[ée]ance:\s*(\d{2}/\d{2}/\d{4})", offer)
        maturities = [(single.group(1), parse_date(m.group(1)) if m else None)]

    results: list[PageResult] = []
    if "Résultats Performances" in text:
        section = text.split("Résultats Performances", 1)[1].split("Plus d'infos", 1)[0]
        blocks = [b for b in _RESULT_BLOCK_RE.split(section) if "Soumissions retenues" in b]
        for b in blocks:
            t = re.match(r"\s*(BAT|OAT)\b", b)
            ret = re.search(r"Soumissions retenues\s+(--|\d[\d ]*(?:,\d+)?)\s*millions", b)
            yld = re.search(r"Rendement moyen pondéré\s+(--|\d+(?:,\d+)?)\s*%", b)
            results.append(PageResult(
                instrument_type=t.group(1) if t else (single.group(1) if single else None),
                retained=parse_amount(ret.group(1)) if ret else None,
                yield_rate=parse_amount(yld.group(1)) if yld else None,
            ))
    if len(maturities) == len(results):
        for r, (kind, mat) in zip(results, maturities, strict=True):
            if kind == r.instrument_type:
                r.maturity_date = mat
    return EmissionPage(
        operation_date=parse_date(op.group(1)) if op else None,
        value_date=parse_date(val.group(1)) if val else None,
        compte_rendu_url=links[0] if links else None,
        results=results,
        maturities=maturities,
    )


# =========================================================================== deals


@dataclass
class SkippedTranche:
    isin: str | None
    instrument_type: str | None
    reason: str


@dataclass
class AuctionDeals:
    records: list[dict]
    skipped: list[SkippedTranche]
    issue: str | None = None  # whole auction refused (contradiction, unknown issuer, ...)
    # Contradiction detail: field, isin, value printed on the page, value printed in the PDF.
    conflict: dict | None = None
    buyback_rows: int = 0  # page rows ignored as securities bought back (verified on the PDF)


def _refused(issue: str, *, field: str | None = None, isin: str | None = None, html: object = None,
             pdf: object = None) -> AuctionDeals:
    conflict = None if field is None else {"field": field, "isin": isin, "html": _show(html), "pdf": _show(pdf)}
    return AuctionDeals([], [], issue=issue, conflict=conflict)


def _show(value: object) -> object:
    if isinstance(value, Decimal | date):
        return str(value)
    if isinstance(value, list):
        return [_show(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_show(v) for v in value)
    return value


@dataclass
class Pairing:
    results: list[PageResult]  # page result of each PDF tranche, in PDF order ([] = page without results)
    buyback_rows: int = 0  # page rows ignored because they are securities bought back
    buyback_pages: list[BuybackPage] = field(default_factory=list)  # PDF pages justifying them


def _pair_page_results(tranches: list[tuple[CompteRendu, PdfTranche]], page: EmissionPage,
                       buybacks: list[BuybackPage] | None = None) -> Pairing | None:
    """Pair the page results with the PDF tranches; None when it cannot be done unambiguously.

    Same number of rows: paired on (type, maturity) when the page prints both, else on position.
    More rows on the page ('EC' emission + buyback): verified subset only — every PDF tranche has its
    own row (unique (type, maturity) keys on both sides), and every extra row has no retained amount
    AND its (type, maturity) is a security listed on a buyback page of the same PDF.
    """
    if not page.results:
        return Pairing([])
    if len(page.results) > len(tranches):
        return _pair_subset(tranches, page, buybacks or [])
    if len(page.results) != len(tranches):
        return None
    paired = _pair_same_size(tranches, page)
    return Pairing(paired) if paired is not None else None


def _pair_subset(tranches, page: EmissionPage, buybacks: list[BuybackPage]) -> Pairing | None:
    if not all(r.maturity_date is not None for r in page.results):
        return None
    page_keys = [(r.instrument_type, r.maturity_date) for r in page.results]
    pdf_keys = [(t.instrument_type, t.maturity_date) for _, t in tranches]
    if len(set(page_keys)) != len(page_keys) or len(set(pdf_keys)) != len(pdf_keys):
        return None  # duplicated (type, maturity) key: ambiguous
    by_key = dict(zip(page_keys, page.results, strict=True))
    matched = [by_key.get(k) for k in pdf_keys]
    if any(m is None for m in matched):
        return None
    justified: dict[tuple, BuybackPage] = {}
    for b in buybacks:
        for sec in b.securities:
            justified.setdefault(sec, b)
    used: list[BuybackPage] = []
    extra = [r for k, r in zip(page_keys, page.results, strict=True) if k not in set(pdf_keys)]
    for r in extra:
        if r.retained is not None and r.retained > 0:
            return None  # an extra row with an issued amount is not a buyback line
        b = justified.get((r.instrument_type, r.maturity_date))
        if b is None:
            return None  # not justified by the buyback page of the PDF
        if b not in used:
            used.append(b)
    return Pairing(matched, len(extra), used)  # type: ignore[arg-type]


def _pair_same_size(tranches, page: EmissionPage) -> list[PageResult] | None:
    if all(r.maturity_date is not None for r in page.results):
        keys = [(r.instrument_type, r.maturity_date) for r in page.results]
        if len(set(keys)) == len(keys):
            by_key = dict(zip(keys, page.results, strict=True))
            keyed = [by_key.get((t.instrument_type, t.maturity_date)) for _, t in tranches]
            if all(k is not None for k in keyed):
                return keyed  # type: ignore[return-value]
    if [r.instrument_type for r in page.results] == [t.instrument_type for _, t in tranches]:
        return list(page.results)
    return None


def months_from_duration(text: str) -> int | None:
    m = DURATION_RE.match(text.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit in ("ans", "an"):
        return n * 12
    if unit == "mois":
        return n
    return None  # days: no exact month count


def _fmt_amount(text: str) -> str:
    return f"{text} millions de F CFA"


def build_auction_deals(
    *,
    reports: list[CompteRendu],
    page: EmissionPage,
    buybacks: list[BuybackPage] | None = None,
    sovereign_entities: dict[str, tuple[str, str]],  # country code -> (entity id, canonical name)
    pdf_document_id: str,
    page_document_id: str,
    source_id: str,
    emission_url: str,
    compte_rendu_url: str,
) -> AuctionDeals:
    """Import records (Phase 13 schema) for the OAT tranches actually issued."""
    tranches = [(r, t) for r in reports for t in r.tranches]
    if not tranches:
        return AuctionDeals([], [], issue="no_security_in_compte_rendu")
    report = reports[0]
    if any(r.issuer_label != report.issuer_label or r.value_date != report.value_date for r in reports[1:]):
        return AuctionDeals([], [], issue="inconsistent_pages")

    auction_flags: list[dict] = []
    issuer_key = norm(report.issuer_label)
    country = ISSUER_COUNTRIES.get(issuer_key)
    issuer_rule = "exact_label"
    if country is None and issuer_key in TRUNCATED_ISSUER_LABELS:
        country = TRUNCATED_ISSUER_LABELS[issuer_key]
        issuer_rule = f"truncated_label_confirmed_by_isin_prefix_{country}"
        auction_flags.append({"code": FLAG_ISSUER_LABEL_TRUNCATED,
                              "detail": f"issuer printed '{report.issuer_label}'; country {country} confirmed by "
                                        f"the ISIN prefix of every security of the auction"})
    if country is None:
        return AuctionDeals([], [], issue=f"issuer_not_recognised: {report.issuer_label}")
    if any(t.isin[:2] != country for _, t in tranches):
        return AuctionDeals([], [], issue="issuer_and_isin_country_differ")
    if country not in sovereign_entities:
        return AuctionDeals([], [], issue=f"no_sovereign_entity_for_{country}")
    entity_id, _entity_name = sovereign_entities[country]
    if any(FLAG_GLOBAL_TOTAL_ROUNDED in r.flags for r in reports):
        auction_flags.append({"code": FLAG_GLOBAL_TOTAL_ROUNDED,
                              "detail": "the printed global retained amount is an integer equal to the rounded sum "
                                        "of the tranche amounts; tranche amounts kept as printed"})

    # Cross-check with the emission page. The page may list the securities in another order:
    # they are paired on (type, maturity date) when the page prints both, else on position.
    pairing = _pair_page_results(tranches, page, buybacks)
    if pairing is None:
        return _refused(
            "page_and_compte_rendu_list_different_securities", field="securities",
            html=[(r.instrument_type, r.maturity_date, r.retained) for r in page.results],
            pdf=[(t.instrument_type, t.maturity_date, t.retained) for _, t in tranches],
        )
    paired = pairing.results
    if paired:
        for (_, t), p in zip(tranches, paired, strict=True):
            pdf_issued = t.retained is not None and t.retained > 0
            page_issued = p.retained is not None and p.retained > 0
            if pdf_issued != page_issued or (pdf_issued and abs(t.retained - p.retained) > Decimal("0.01")):
                return _refused(f"retained_amount_differs_{t.isin}", field="amount", isin=t.isin,
                                html=p.retained, pdf=t.retained)
            if t.yield_rate is not None and p.yield_rate is not None and p.yield_rate > 0 and \
                    abs(t.yield_rate - p.yield_rate) > YIELD_TOLERANCE:
                return _refused(f"yield_differs_{t.isin}", field="yield_rate", isin=t.isin,
                                html=p.yield_rate, pdf=t.yield_rate)
            if p.maturity_date is not None and t.maturity_date is not None and p.maturity_date != t.maturity_date:
                return _refused(f"maturity_date_differs_{t.isin}", field="maturity_date", isin=t.isin,
                                html=p.maturity_date, pdf=t.maturity_date)
    if page.value_date and report.value_date and page.value_date != report.value_date:
        return _refused("value_date_differs", field="value_date", html=page.value_date, pdf=report.value_date)
    if page.operation_date and report.auction_date and page.operation_date != report.auction_date:
        return _refused("auction_date_differs", field="auction_date", html=page.operation_date,
                        pdf=report.auction_date)
    if pairing.buyback_rows:
        justification = "; ".join(
            f"p.{b.page_number} ({', '.join(b.references) or 'références RA non lues'})" for b in pairing.buyback_pages
        )
        auction_flags.append({"code": FLAG_PAGE_LISTS_BUYBACK_SECURITIES,
                              "detail": f"{pairing.buyback_rows} buyback line(s) of the emission page ignored "
                                        f"(no retained amount); securities listed on the buyback page of the "
                                        f"compte rendu {justification}"})

    records: list[dict] = []
    skipped: list[SkippedTranche] = []
    for k, (rep, t) in enumerate(tranches):
        if t.instrument_type != "OAT":
            skipped.append(SkippedTranche(t.isin, t.instrument_type, "not_oat"))
            continue
        if t.retained is None or t.retained <= 0:
            skipped.append(SkippedTranche(t.isin, t.instrument_type, "no_retained_amount"))
            continue
        page_result = paired[k] if paired else None
        page_maturity = page_result.maturity_date if page_result else None

        rec = {
            "title": f"OAT {t.duration_text} — {report.issuer_label} — {t.isin} — adjudication du "
                     f"{report.auction_date.strftime('%d/%m/%Y') if report.auction_date else 'date non publiée'}",
            "deal_type": "sovereign_bond",
            "country_code": country,
            "amount_original": _fmt_amount(t.retained_text or ""),
            "amount": t.retained,
            "currency": CURRENCY,
            "unit": UNIT,
            "interest_rate": t.coupon,
            "interest_rate_type": "fixed" if t.coupon is not None else None,
            "maturity_months": months_from_duration(t.duration_text),
            "instrument_type": "OAT",
            "isin": t.isin,
            "auction_reference": t.auction_reference,
            "auction_date": report.auction_date,
            "value_date": report.value_date,
            "maturity_date": t.maturity_date,
            "yield_rate": t.yield_rate,
            "ingestion_key": f"umoa_titres:{country}:{t.auction_reference}:{t.isin}:{report.value_date}",
        }
        rec = {key: v for key, v in rec.items() if v is not None}
        if auction_flags:
            rec["validation_flags"] = [dict(f) for f in auction_flags]
        pdf_fields = [f for f in (
            "title", "deal_type", "country_code", "amount_original", "amount", "currency", "unit", "interest_rate",
            "interest_rate_type", "maturity_months", "instrument_type", "isin", "auction_reference",
            "auction_date", "value_date", "maturity_date", "yield_rate",
        ) if f in rec]
        page_fields = ["instrument_type", "amount", "currency", "unit"]
        if page_result is not None and t.yield_rate is not None and page_result.yield_rate:
            page_fields.append("yield_rate")
        if page.value_date and "value_date" in rec:
            page_fields.append("value_date")
        if page.operation_date and "auction_date" in rec:
            page_fields.append("auction_date")
        if page_maturity is not None and "maturity_date" in rec:
            page_fields.append("maturity_date")
        rec["sources"] = [
            {
                "ref": "compte_rendu", "document_id": pdf_document_id, "source_id": source_id,
                "page": rep.page_number, "fields": pdf_fields,
                "excerpt": f"pdf_text · Compte rendu d'adjudication {compte_rendu_url} p.{rep.page_number} · "
                           f"{t.auction_reference} · ISIN {t.isin} · Soumissions retenues "
                           f"{_fmt_amount(t.retained_text or '')} · émetteur « {report.issuer_label} » "
                           f"(règle {issuer_rule})",
            },
        ]
        if page_result is not None:
            rec["sources"].append({
                "ref": "emission_page", "document_id": page_document_id, "source_id": source_id, "page": 1,
                "fields": page_fields,
                "excerpt": f"web_html · page d'émission {emission_url} · résultats (contrôle croisé)",
            })
        rec["participants"] = [{
            "role": "issuer", "name": report.issuer_label, "entity_id": entity_id, "source_ref": "compte_rendu",
        }]
        records.append(rec)
    return AuctionDeals(records, skipped, buyback_rows=pairing.buyback_rows)
