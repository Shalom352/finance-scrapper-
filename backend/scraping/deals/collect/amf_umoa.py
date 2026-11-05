"""
AMF-UMOA — operations index (public API) -> deals of class ``regulator_index``.

Source: https://www.amf-umoa.org/service/api/elastic/operation (JSON, the whole index with ?size=).
The audit of 05/10/2026 (audits/ape_amf/01_ape_profile.md) and decision D2 apply in full:
  - the API is a DISCOVERY INDEX: it attests only title, deal type, country and the raw
    "SGI déclarante" (``acteurLib`` -> ``filing_agent_raw``), never a role, an amount or a rate
    (enforced by the import schema for the class ``regulator_index``);
  - the issuer of the API is wrong for ~130 operations (generic "Trésor Public de Côte d'Ivoire"):
    it is never read; a country is read only when the operation label itself names ONE UMOA country;
  - the information notes are not served (0-byte files): nothing is read from ``noteInfo``.
A deal attested only by this class cannot be verified until a primary source is attached.

Deal type from the AMF nature AND the label: when they contradict (nature "EOP" — private placement —
with a label "par APE"), the type is left NULL and the page is flagged.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from scraping.deals.collect.amounts import fold, parse_day, umoa_countries
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
    in_window,
)
from scraping.universe.http import FetchResult

API_PAGE_SIZE = 2000
API_URL = f"https://www.amf-umoa.org/service/api/elastic/operation?size={API_PAGE_SIZE}"
PUBLISHER = "AMF-UMOA"
STATE_RE = re.compile(r"\b(etat|tresor|republique|tp(ci|bf|bj|ne|ml|sn|tg|gb)|tcpi)\b")
TREASURY_CODES = {"tpci": "CI", "tcpi": "CI", "tpbf": "BF", "tpbj": "BJ", "tpne": "NE", "tpml": "ML", "tpsn": "SN",
                  "tptg": "TG", "tpgb": "GW"}
PUBLIC_LABEL_RE = re.compile(r"\bape\b|appel public")
PRIVATE_LABEL_RE = re.compile(r"placement prive|\bprive\b")
NEW_SHARES_RE = re.compile(r"actions nouvelles|augmentation de capital")
COLLECTED_NATURES = ("APE", "EOP", "OPV", "OPA")


def operation_url(op_id: object) -> str:
    return f"{API_URL}#operation-{op_id}"


def canonical(op: dict) -> bytes:
    return json.dumps(op, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def deal_type_of(nature: str, label: str) -> tuple[str | None, str | None]:
    """(deal_type, flag) from the AMF nature code and the operation label (both published)."""
    folded = fold(label)
    state = bool(STATE_RE.search(folded))
    if nature == "APE":
        if PRIVATE_LABEL_RE.search(folded):
            return None, "amf_nature_contradicts_label"
        return ("sovereign_bond_ape" if state else "corporate_bond_ape"), None
    if nature == "EOP":
        if PUBLIC_LABEL_RE.search(folded):
            return None, "amf_nature_contradicts_label"
        return (None, "amf_sovereign_private_placement") if state else ("corporate_bond_private", None)
    if nature == "OPV":
        # A public offer of NEW shares is a capital increase; of existing shares, a public sale.
        return ("capital_increase" if NEW_SHARES_RE.search(folded) else "share_sale_public"), None
    if nature == "OPA":
        return "takeover_offer", None
    return None, None


def label_country(label: str) -> str | None:
    folded = fold(label)
    codes = set(umoa_countries(label))
    codes |= {code for word, code in TREASURY_CODES.items() if re.search(rf"\b{word}\b", folded)}
    return codes.pop() if len(codes) == 1 else None


class AmfUmoaCollector(DealCollector):
    source_key = "amf-umoa"
    source_short_name = "AMF-UMOA"
    actor = "amf_umoa_index_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        res = await self.fetcher.get(API_URL)
        if not res.ok:
            raise RuntimeError(f"AMF-UMOA operations API unavailable: {res.error}")
        try:
            ops = json.loads(res.text)
        except ValueError as err:
            raise RuntimeError(f"AMF-UMOA operations API: not JSON ({err})") from err
        if not isinstance(ops, list):
            raise RuntimeError("AMF-UMOA operations API: unexpected structure (list expected)")
        if len(ops) >= API_PAGE_SIZE:  # the API returned its maximum: older operations may be missing
            self.discovery_warnings.append(f"AMF-UMOA API returned {len(ops)} operations (its page size): "
                                           "the list may be truncated")
        out = []
        for op in ops:
            if not isinstance(op, dict) or op.get("id") is None:
                continue
            visa = parse_day(op.get("dateVisa") or "")
            if not in_window(visa, since, until):
                continue
            body = canonical(op)
            out.append(Candidate(url=operation_url(op["id"]), lastmod=hashlib.sha1(body).hexdigest(),
                                 hint={"body": body, "visa": visa.isoformat() if visa else ""}))
        return sorted(out, key=lambda c: c.hint["visa"])

    async def fetch(self, candidate: Candidate) -> FetchResult:
        # The index was fetched once by discover(); each operation is read from it, not re-requested.
        return FetchResult(url=candidate.url, final_url=candidate.url, status_code=200,
                           content=candidate.hint["body"], content_type="application/json")

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_operation(candidate.url, res.content or b"")


def read_operation(url: str, content: bytes) -> Reading:
    try:
        op = json.loads(content.decode("utf-8"))
    except ValueError:
        return Reading.skip("refused", "operation is not JSON")
    nature = (op.get("natureCode") or "").strip()
    label = " ".join((op.get("nomination") or "").split())
    if nature not in COLLECTED_NATURES:
        return Reading.skip("out_of_scope", f"nature {nature or 'not published'} ({op.get('natureLib')}) not collected")
    if not label:
        return Reading.skip("not_a_deal", "operation without a label")
    deal_type, flag = deal_type_of(nature, label)
    flags = [flag] if flag else []
    country = label_country(label)
    agent = " ".join((op.get("acteurLib") or "").split()) or None
    visa_day = parse_day(op.get("dateVisa") or "")
    summary = (f"API AMF-UMOA, opération {op.get('id')} · visa {op.get('visa') or 'non publié'} du "
               f"{op.get('dateVisa') or 'date non publiée'} · nature « {op.get('natureLib')} » · « {label} »")

    def build(document_id: str, source_id: str) -> list[dict]:
        ev = Evidence("amf_index", source_class="regulator_index", url=url, publisher=PUBLISHER, title=label,
                      published_at=visa_day, excerpt=summary)
        ev.put("title", label, f"nomination : « {label} »")
        ev.put("deal_type", deal_type, f"nature : « {op.get('natureLib')} » ({nature}) · nomination : « {label} »")
        ev.put("country_code", country, f"nomination : « {label} »")
        ev.put("filing_agent_raw", agent[:255] if agent else None, f"acteurLib : « {agent} »")
        return [assemble([ev], document_id=document_id, source_id=source_id,
                         ingestion_key=f"amf-umoa:operation:{op.get('id')}")]

    document = DocumentToRegister(url=url, content=content, file_format="json", document_type="other",
                                  title=f"AMF-UMOA — opération {op.get('id')} — {label}"[:500],
                                  period_year=visa_day.year if visa_day else None,
                                  original_filename=f"amf_operation_{op.get('id')}.json")
    return Reading(document=document, build=build, flags=flags)
