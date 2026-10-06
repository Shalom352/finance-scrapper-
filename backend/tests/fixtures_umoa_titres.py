"""FIXTURES — synthetic UMOA-Titres auction documents (layout copied from the real compte rendu /
emission pages, every value fictitious). Never loaded outside the tests."""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf


@dataclass
class FxTranche:
    isin: str
    kind: str  # BAT | OAT
    duration: str  # "364 jours" | "3 ans"
    maturity: str  # dd/mm/yyyy
    retained: str  # "10 345" | "0"
    yield_pct: str  # "9,22%" | "-"
    coupon: str | None = None  # "6,15%" (OAT only)
    ref_code: str = "OT3A"


def compte_rendu_lines(issuer: str, auction: str, value: str, tranches: list[FxTranche],
                       coupon_tokens: list[str] | None = None, total: str | None = None) -> list[str]:
    """Multi-security layout of the real 'Compte rendu d'adjudication' (one token per line)."""
    lines = ["COMPTE RENDU D'ADJUDICATION DE BONS ET D'OBLIGATIONS ASSIMILABLES DU TRESOR",
             "Emetteur :", issuer, "Nature des titres", ": Bons et d'Obligations Assimilables du Trésor",
             "Date d'adjudication", ":", auction, "Date de valeur", ":", value, "Code ISIN"]
    lines += [(": " if k == 0 else "") + t.isin for k, t in enumerate(tranches)]
    lines += ["Dénomination de l'émission"]
    lines += [(": " if k == 0 else "") + f"{t.isin}-{t.kind}-{t.maturity[3:5]}-{t.maturity[6:]}"
              for k, t in enumerate(tranches)]
    lines += ["Adjudication n°"]
    lines += [(": " if k == 0 else "") + f"ADJ-{t.isin}-{t.ref_code}-2025" for k, t in enumerate(tranches)]
    lines += ["Durée"] + [(": " if k == 0 else "") + t.duration for k, t in enumerate(tranches)]
    lines += ["Date d'échéance"] + [(": " if k == 0 else "") + t.maturity for k, t in enumerate(tranches)]
    lines += ["Taux d'intérêt fixe annoncé"]
    lines += coupon_tokens if coupon_tokens is not None else [t.coupon for t in tranches if t.coupon]
    lines += ["Taux coupon couru", "Soumissions retenues", ":",
              total if total is not None else _sum([t.retained for t in tranches]), "millions de FCFA, dont ONC :", "-",
              "Nombre de soumissions"] + ["3" for _ in tranches]
    lines += ["Soumissions retenues"] + [f"{t.retained} millions de F CFA, dont ONC :0" for t in tranches]
    lines += ["Rendement moyen pondéré"] + [t.yield_pct for t in tranches]
    lines += ["Dakar, FIXTURE"]
    return lines


def _sum(values: list[str]) -> str:
    total = sum(float(v.replace(" ", "").replace(",", ".")) for v in values)
    return f"{total:.2f}".replace(".", ",")


def compte_rendu_pdf(*args, **kwargs) -> bytes:
    """One tall page (the real compte rendu is a dense single page): every line stays on the page."""
    lines = compte_rendu_lines(*args, **kwargs)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=60 + 12 * len(lines))
    for n, line in enumerate(lines):
        page.insert_text((40, 40 + 12 * n), line, fontname="helv", fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def emission_page_html(*, operation: str, value: str, compte_rendu_url: str | None,
                       results: list[tuple[str, str, str, str]] | None) -> str:
    """results: (kind, maturity dd/mm/yyyy, retained '10 345,0000' | '--', yield '9,2156' | '--')."""
    offer = " ".join(
        f"<p>{kind} Durée: 36 mois Différé: -- an(s) Echéance: {mat} Taux d'intérêt: 6,0000 %</p>"
        for kind, mat, _, _ in (results or [])
    )
    res = ""
    if results is not None:
        res = "<h3>Résultats</h3><h4>Performances</h4>" + " ".join(
            f"<p>{kind} Montant sollicité: 30 000 millions de FCFA Soumissions retenues {ret} millions de FCFA "
            f"Rendement moyen pondéré {yld} %</p>"
            for kind, _, ret, yld in results
        )
    link = f"<a href='{compte_rendu_url}'><button>Télécharger</button></a>" if compte_rendu_url else ""
    return (f"<html><body><h2>Caractéristiques de l'offre</h2><p>Date de l'opération: {operation} "
            f"Montant mis en adjudication: 30 000 millions de FCFA Date de valeur: {value}</p>{offer}{res}"
            f"<p>Plus d'infos</p><h3>Compte rendu</h3>{link}</body></html>")


def buyback_lines(issuer: str, auction: str, value: str, securities: list[tuple[str, str, str]]) -> list[str]:
    """Buyback page of an 'EC' compte rendu: (isin, type, maturity dd/mm/yyyy); title at the bottom."""
    lines = ["Emetteur :", issuer, "Date d'adjudication", ":", auction, "Date de valeur", ":", value, "Code ISIN"]
    lines += [(": " if k == 0 else "") + isin for k, (isin, _, _) in enumerate(securities)]
    lines += ["Dénomination de l'émission"]
    lines += [(": " if k == 0 else "") + f"{isin}-{kind}-{mat[3:5]}-{mat[6:]}"
              for k, (isin, kind, mat) in enumerate(securities)]
    lines += ["Adjudication n°"] + [(": " if k == 0 else "") + f"RA-{isin}-14-2025"
                                   for k, (isin, _, _) in enumerate(securities)]
    lines += ["Date d'échéance"] + [(": " if k == 0 else "") + mat for k, (_, _, mat) in enumerate(securities)]
    lines += ["COMPTE RENDU DE RACHAT DE BONS ET D'OBLIGATIONS"]
    return lines


def pdf_from_pages(pages: list[list[str]]) -> bytes:
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page(width=595, height=60 + 12 * len(lines))
        for n, line in enumerate(lines):
            page.insert_text((40, 40 + 12 * n), line, fontname="helv", fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data
