"""
Financial press (Sika Finance, Agence Ecofin, Financial Afrik) -> deals of class ``press_reported``.

Decision D4 (audits/ape_amf/04b_press_feasibility_sourced.md), applied in full:
  - discovery through the PUBLIC RSS feeds only; a pre-filter on title + summary keeps UMOA deal news
    (Treasury auction reports are excluded: UMOA-Titres is their primary source);
  - the article body is read in memory and NEVER stored: the registered document is a small JSON
    evidence record (URL, title, publisher, date and the short quotations used as proof);
  - a paywalled article ("réservé aux abonnés", "Sika Premium"...) gives nothing (outcome
    ``restricted``): its title / date / URL cannot attest a field, and no paywall is bypassed;
  - roles only when NAMED ("Chef de file et Arrangeur : X", "arrangé par X", "Investisseur d'ancrage :
    X", "X, investisseur de référence"); "avec l'appui de" / "en partenariat avec" give no role;
  - amount only from the TITLE when it carries exactly one explicit amount; coupon and maturity only
    when the article gives a single value and no tranches; FCFA = XOF only for a UMOA deal;
  - such a deal stays ``needs_review`` and cannot be verified until a primary source is attached
    (409 ``secondary_source_only``); the duplicate criteria link it to the AMF / BRVM / DFI deal.
Rate: at most one request every 5 s per press site (PoliteFetcher host delays).
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlparse

from scraping.deals.collect.amounts import fold, parse_day, parse_money, umoa_countries
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
    in_window,
    quote,
)
from scraping.universe.http import FetchResult, html_to_text

FEEDS = (
    "https://www.sikafinance.com/rss/actualites_bourse_brvm",
    "https://www.agenceecofin.com/component/obrss/agence-ecofin-full",
    "https://www.financialafrik.com/feed/",
)
PUBLISHERS = {"www.sikafinance.com": "Sika Finance", "www.agenceecofin.com": "Agence Ecofin",
              "www.financialafrik.com": "Financial Afrik"}
HOST_DELAYS = {host: 5.0 for host in PUBLISHERS}
# Main article container per site (the whole page is never stored).
BODY_MARKERS = {
    "www.sikafinance.com": 'class="inarticle',
    "www.agenceecofin.com": 'class="itemBody',
    "www.financialafrik.com": 'class="post-content cf entry-content',
}
PAYWALL_RE = re.compile(r"r[ée]serv[ée]e? aux abonn[ée]s|sika premium|contenu premium|abonnez-vous pour lire|"
                        r"pour lire la suite|swpm-|pmpro_content_message", re.IGNORECASE)
DEAL_WORDS = re.compile(r"emprunt|obligat|\bbonds?\b|sukuk|\bpr[eê]t\b|pr[eê]ts syndiqu|financement|l[eè]ve|lev[ée]e|"
                        r"mobilise|[ée]mission|augmentation de capital|introduction en bourse", re.IGNORECASE)
UMOA_WORDS = re.compile(r"\bu[ée]moa\b|\bumoa\b|\bbrvm\b|\bboad\b|\bfcfa\b|\bf cfa\b", re.IGNORECASE)
AUCTION_RE = re.compile(r"adjug|adjudication|bons? (?:et obligations )?du tr[ée]sor|bons assimilables", re.IGNORECASE)
# Countries that use the franc CFA without being UMOA members, or that are often in the same feeds.
OTHER_COUNTRIES = re.compile(
    r"\b(congo|rdc|cameroun|gabon|tchad|centrafrique|guin[ée]e [ée]quatoriale|guin[ée]e(?!-bissau| bissau)|"
    r"nig[ée]ria|ghana|kenya|maroc|tunisie|alg[ée]rie|[ée]gypte|afrique du sud|rwanda|ouganda|tanzanie|"
    r"[ée]thiopie|angola|mozambique|madagascar|maurice|zambie|liberia|sierra leone|gambie|mauritanie|"
    r"cap-vert|zimbabwe|botswana|namibie)\b", re.IGNORECASE)
STATE_RE = re.compile(r"\b(etat|tresor|republique)\b|\b(niger|mali|senegal|benin|togo|burkina|cote d.ivoire|"
                      r"guinee.bissau) (signe|lance|leve|mobilise|emet|revient)")
NAME = r"(?P<name>[A-ZÀ-Ý][\w&'’.\-]*(?: (?:[&\-]|[A-ZÀ-Ý0-9][\w&'’.\-]*|de|du|des|la|le|et|d['’][\w\-]+)){0,7})"
ROLE_PATTERNS = (
    (re.compile(r"(?:Chef de file et (?:Arrangeur|arrangeur)|(?:Arrangeur|arrangeur)s? et (?:[Cc]hefs?) de [Ff]ile)\s*:\s*"
                + NAME), ("arranger", "lead_manager")),
    (re.compile(r"[Cc]o-arrangeurs?\s*:\s*" + NAME), ("co_arranger",)),
    (re.compile(r"(?<![Cc]o-)[Aa]rrangeurs?\s*:\s*" + NAME), ("arranger",)),
    (re.compile(r"[Cc]hefs? de [Ff]ile\s*:\s*" + NAME), ("lead_manager",)),
    (re.compile(r"[Aa]rrang[ée]e?s? par (?:la |le |l['’])?" + NAME + r"(?P<lead>,? qui en est (?:aussi |également )?le chef de file)?"),
     ("arranger",)),
    (re.compile(r"[Ii]nvestisseur d['’]ancrage\s*:\s*" + NAME), ("anchor_investor",)),
    (re.compile(r"[Ii]nvestisseur de r[ée]f[ée]rence\s*:\s*" + NAME), ("anchor_investor",)),
    (re.compile(NAME + r",? (?:figure parmi les )?investisseurs? de r[ée]f[ée]rence\b"), ("anchor_investor",)),
    (re.compile(r"[Gg]arant\s*:\s*" + NAME), ("guarantor",)),
)
# Where a captured name stops: end of sentence, next field label of a fact sheet, "À propos" blocks.
NAME_END_RE = re.compile(r"\.\s|\s(?=(?:Investisseur|Arrangeur|Chefs? de|Co-arrangeur|Garant|Montant|Taux|Maturit|"
                         r"Période|Valeur|Visa|À PROPOS|À propos)\b)")
MONEY_SPAN_RE = re.compile(r"\d[\d\s ]*(?:[.,]\d+)?\s*(?:milliards?|millions?|mds?|M)?\s*(?:de\s+)?"
                           r"(?:FCFA|F\s?CFA|francs CFA|USD|EUR|euros?|dollars?|\$)", re.IGNORECASE)
AMOUNT_FIELD_RE = re.compile(r"\bMontant(?: de l['’][ée]mission| de l['’]op[ée]ration)?\s*:\s*([^;:]{3,40}?)(?=\s+[A-ZÀ-Ý][a-zé]+\s*:|;|$)")
NAME_STOPWORDS = {"Le", "La", "Les", "Cette", "Ce", "Une", "Un", "Il", "Elle", "Selon", "Pour", "Dans", "Avec"}
RATE_RE = re.compile(r"(?i)\btaux(?: d['’]int[ée]r[êe]t| nominal| facial| de r[ée]mun[ée]ration)?\s*(?::|de|fix[ée] à)?\s*"
                     r"(\d{1,2}(?:[.,]\d{1,4})?)\s*%")
MATURITY_RE = re.compile(r"(?:\bmaturit[ée]|\bdur[ée]e)\s*(?::|de)?\s*(\d{1,2})\s*ans\b|\bsur (\d{1,2}) ans\b", re.IGNORECASE)
# Audit 22/10/2026 (H4): figures that are NOT the amount of a deal, even in a title with a deal word.
NOT_A_DEAL_AMOUNT = re.compile(r"b[ée]n[ée]fice|r[ée]sultat|chiffre d.affaires|produit net|programme|budget|encours|"
                               r"dette publique|capitalisation|dividende|plan de financement|besoins? de financement|"
                               r"enveloppe globale|portefeuille|d[ée]ficit|recettes", re.IGNORECASE)
# A rate that is not the deal's coupon ("taux de couverture de 150 %", "taux directeur de la BCEAO").
NOT_A_COUPON = re.compile(r"couverture|souscription|participation|croissance|inflation|ch[ôo]mage|directeur|"
                          r"bceao|absorption|endettement|change", re.IGNORECASE)
# "sur N ans" is a maturity only in a sentence about the instrument (not "sur 5 ans, le chiffre d'affaires...").
INSTRUMENT_WORDS = re.compile(r"emprunt|obligat|\bpr[eê]t\b|sukuk|titres?|maturit|rembours", re.IGNORECASE)
# Sentences about the exchange itself ("cotée à la BRVM d'Abidjan") never give the deal's country.
EXCHANGE_SENTENCE = re.compile(r"[^.]*\b(?:brvm|bourse r[ée]gionale|bourse d.abidjan|si[eè]ge)\b[^.]*\.?", re.IGNORECASE)
ISIN_RE = re.compile(r"\b((?:SN|CI|BJ|BF|ML|NE|TG|GW)\d{10})\b")
PROCEEDS_RE = re.compile(r"[^.]*\b(?:serviront? à|financeront|destin[ée]e?s? à financer|permettra de financer|"
                         r"afin de financer|servira à financer|serviront à financer|utilis[ée]e?s? pour financer)\b[^.]*\.")


def tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)
    if not m:
        return None
    value = m.group(1).strip()
    if value.startswith("<![CDATA["):
        value = value[9:-3]
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", value)).split())


def feed_items(xml: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        link = tag(block, "link")
        if link:
            items.append({"title": tag(block, "title") or "", "link": link.strip(),
                          "published": tag(block, "pubDate"), "summary": tag(block, "description") or ""})
    return items


def is_candidate(title: str, summary: str) -> bool:
    """Pre-filter on what the feed itself publishes (no article is fetched for the others)."""
    text = f"{title} {summary}"
    if AUCTION_RE.search(title) or not DEAL_WORDS.search(title):
        return False
    if umoa_countries(title):
        return True
    if OTHER_COUNTRIES.search(fold(title)):
        return False
    return bool(umoa_countries(text) or UMOA_WORDS.search(text))


def balanced_div(page_html: str, start: int) -> str:
    """The element opened at ``start`` (a <div>), with its nested divs."""
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b", page_html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            i = start + m.end()
            return page_html[start:page_html.find(">", i) + 1]
    return page_html[start:]


def article_body(page_html: str, host: str) -> str | None:
    marker = BODY_MARKERS.get(host)
    if not marker:
        return None
    i = page_html.find(marker)
    if i < 0:
        return None
    return html_to_text(balanced_div(page_html, page_html.rfind("<div", 0, i)))


def meta(page_html: str, prop: str) -> str | None:
    m = re.search(rf'<meta (?:property|name)="{re.escape(prop)}" content="([^"]*)"', page_html)
    return html_lib.unescape(m.group(1)).strip() if m else None


def published_day(page_html: str, fallback: str | None) -> date | None:
    for raw in (meta(page_html, "article:published_time"),
                (m.group(1) if (m := re.search(r'"datePublished"\s*:\s*"([^"]+)"', page_html)) else None),
                fallback):
        if raw and (d := parse_day(raw)):
            return d
    if fallback and (m := re.search(r"(\d{1,2}) ([A-Za-z]{3}) (\d{4})", fallback)):  # RFC 822 pubDate
        return parse_day(f"{m.group(2)} {m.group(1)}, {m.group(3)}")
    return None


def clean_name(raw: str, *, name_before: bool) -> str:
    """Cut a captured name at the end of its sentence / at the next label. A name written BEFORE its
    role ("X, investisseur de référence") keeps the last sentence piece, otherwise the first."""
    parts = [p for p in NAME_END_RE.split(raw) if p and p.strip()]
    if not parts:
        return ""
    return (parts[-1] if name_before else parts[0]).strip(" .,;:")


def sentence_at(text: str, pos: int) -> str:
    """The sentence of ``text`` that contains position ``pos``."""
    start = text.rfind(".", 0, pos) + 1
    end = text.find(".", pos)
    return text[start: end if end >= 0 else len(text)]


def money_in(text: str) -> object | None:
    """The single explicit amount of a short text (title, fact-sheet field); two amounts -> None."""
    spans = [m.group(0) for m in MONEY_SPAN_RE.finditer(text)]
    if len(spans) != 1:
        return None
    return parse_money(spans[0], allow_cfa=True)


def named_roles(text: str) -> list[tuple[str, str, str]]:
    """(role, name, quotation) for every role NAMED in the text. 'X et Y' gives two participants."""
    out: list[tuple[str, str, str]] = []
    for rx, roles in ROLE_PATTERNS:
        name_before = rx.pattern.startswith("(?P<name>")
        for m in rx.finditer(text):
            raw = clean_name(m.group("name"), name_before=name_before)
            names = [n.strip(" .,;:") for n in re.split(r" et |, ", raw) if n.strip(" .,;:")]
            for name in names:
                if name in NAME_STOPWORDS or len(name) < 2:
                    continue
                these = roles + (("lead_manager",) if m.groupdict().get("lead") else ())
                for role in these:
                    item = (role, name, quote(text[max(0, m.start() - 20): m.end() + 20], 300))
                    if not any(o[0] == role and o[1] == name for o in out):
                        out.append(item)
    return out


def single(values: list) -> object | None:
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else None


class PressCollector(DealCollector):
    source_key = "press"
    parser_version = 3  # safe backfill for records already imported by earlier parser versions
    source_short_name = "Presse financière"  # migration 0021
    actor = "press_rss_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        out: dict[str, Candidate] = {}
        failures = []
        for feed in FEEDS:
            res = await self.fetcher.get(feed)
            if not res.ok:
                failures.append(f"{feed}: {res.error}")
                continue
            for it in feed_items(res.text):
                day = published_day("", it["published"])
                if not in_window(day, since, until) or not is_candidate(it["title"], it["summary"]):
                    continue
                if urlparse(it["link"]).netloc not in PUBLISHERS:
                    continue
                out.setdefault(it["link"], Candidate(url=it["link"], lastmod=it["published"],
                                                     hint={"title": it["title"], "published": it["published"]}))
        if failures and len(failures) == len(FEEDS):
            raise RuntimeError("press feeds unavailable: " + "; ".join(failures))
        self.discovery_warnings.extend(f"feed unavailable: {f}" for f in failures)
        return sorted(out.values(), key=lambda c: (published_day("", c.lastmod) or date.min).isoformat())

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_article(candidate.url, res.content or b"", candidate.hint.get("published"))


def read_article(url: str, content: bytes, feed_date: str | None = None) -> Reading:
    host = urlparse(url).netloc
    publisher = PUBLISHERS.get(host)
    if publisher is None:
        return Reading.skip("out_of_scope", f"not a collected press site ({host})")
    page_html = content.decode("utf-8", errors="replace")
    title = (meta(page_html, "og:title") or "").split(" | ")[0].strip()
    body = article_body(page_html, host)
    if not title or body is None:
        return Reading.skip("not_a_deal", "article title or body not found (layout changed?)")
    if PAYWALL_RE.search(body):  # the body only: site menus carry "S'abonner" / "Premium" links everywhere
        return Reading.skip("restricted", "paywalled article: title, date and link only — nothing extracted")
    if AUCTION_RE.search(title):
        return Reading.skip("out_of_scope", "Treasury auction report (UMOA-Titres is the primary source)")
    title_codes = umoa_countries(title)
    if not title_codes and OTHER_COUNTRIES.search(fold(title)):
        return Reading.skip("out_of_scope", f"not a UMOA deal ({title})")
    body_codes = umoa_countries(EXCHANGE_SENTENCE.sub(" ", body))
    if not (title_codes or body_codes or UMOA_WORDS.search(body)):
        return Reading.skip("out_of_scope", "no UMOA country, UEMOA, BRVM or FCFA in the article")
    day = published_day(page_html, feed_date)
    money, money_quote = (None if NOT_A_DEAL_AMOUNT.search(title) else money_in(title)), f"titre : « {title} »"
    if money is None:
        fields = [m.group(1) for m in AMOUNT_FIELD_RE.finditer(body)]
        field_money = [(f, x) for f in fields if (x := money_in(f)) is not None]
        if len(field_money) == 1:  # quoted from the field the amount was read in
            money, money_quote = field_money[0][1], f"fiche de l'opération : « Montant : {field_money[0][0].strip()} »"
    roles = named_roles(body)
    if money is None and not roles:
        return Reading.skip("not_a_deal", "no explicit amount in the title and no named role")
    folded_body, folded_title = fold(body), fold(title)
    multi_tranche = "tranche" in folded_body
    rates = [m.group(1).replace(",", ".") for m in RATE_RE.finditer(body)
             if not NOT_A_COUPON.search(body[max(0, m.start() - 10): m.end()])]
    rate = None if multi_tranche else single([Decimal(r).normalize() for r in rates])
    maturities = [int(m.group(1) or m.group(2)) for m in MATURITY_RE.finditer(body)
                  if m.group(1) or INSTRUMENT_WORDS.search(sentence_at(body, m.start()))]
    maturity = None if multi_tranche else single(maturities)
    proceeds = PROCEEDS_RE.search(body)
    # The security named in the article: links it to the primary deal (one ISIN only, never chosen).
    isins = set(ISIN_RE.findall(body))
    isin = isins.pop() if len(isins) == 1 else None
    country = single(title_codes) if title_codes else single(body_codes)
    deal_type = None
    if "sukuk" in folded_title or "sukuk" in folded_body:
        deal_type = "sukuk"
    elif "appel public" in folded_body:
        deal_type = "sovereign_bond_ape" if STATE_RE.search(folded_title) else "corporate_bond_ape"
    elif "placement prive" in folded_body:
        deal_type = "corporate_bond_private"
    flags = ["press_multi_tranche_terms_not_read"] if multi_tranche and (rates or maturities) else []
    quotations: dict[str, str] = {}

    def build(document_id: str, source_id: str) -> list[dict]:
        ev = Evidence("press", source_class="press_reported", url=url, publisher=publisher, title=title,
                      published_at=day, excerpt=f"press · {publisher} · « {title} »")
        ev.put("title", title, f"titre : « {title} »")
        ev.put("country_code", country, f"titre : « {title} »" if title_codes else "article : pays nommé")
        if isin is not None:
            ev.put("isin", isin, quote(sentence_at(body, body.find(isin)), 300))
        ev.put("deal_type", deal_type, "article : " + ("sukuk" if deal_type == "sukuk" else
                                                       "appel public à l'épargne" if deal_type and "ape" in deal_type
                                                       else "placement privé"))
        if money is not None:
            for name, value in (("amount", money.figure), ("amount_original", money.original),
                                ("currency", money.currency), ("unit", money.unit)):
                ev.put(name, value, money_quote)
        if rate is not None:
            m = next(m for m in RATE_RE.finditer(body))
            ev.put("interest_rate", rate, quote(body[max(0, m.start() - 40): m.end() + 20], 200))
        if maturity is not None:
            m = next(m for m in MATURITY_RE.finditer(body))
            ev.put("maturity_months", maturity * 12, quote(body[max(0, m.start() - 40): m.end() + 10], 200))
        if proceeds:
            ev.put("use_of_proceeds", quote(proceeds.group(0).strip(), 300), quote(proceeds.group(0).strip(), 300))
        participants = [{"role": role, "name": name[:255], "source_ref": "press", "excerpt": q,
                         "extraction_method": "text"} for role, name, q in roles]
        quotations.update({k: q for k, (_, q) in ev.values.items()})
        key = f"press:{host}:{hashlib.sha1(url.encode()).hexdigest()[:16]}"
        return [assemble([ev], document_id=document_id, source_id=source_id, ingestion_key=key,
                         participants=participants)]

    build("pending", "pending")  # fills the quotations of the evidence record below
    evidence_record = {
        "url": url, "title": title, "publisher": publisher, "published_at": day.isoformat() if day else None,
        "note": "Evidence record only (decision D4): the article body is not stored.",
        "quotations": quotations, "roles": [{"role": r, "name": n, "quotation": q} for r, n, q in roles],
    }
    document = DocumentToRegister(
        url=url, content=json.dumps(evidence_record, ensure_ascii=False, indent=1).encode("utf-8"),
        title=f"{publisher} — {title}"[:500], file_format="json", document_type="press_release",
        period_year=day.year if day else None, original_filename="press_evidence.json",
    )
    return Reading(document=document, build=build, flags=flags)
