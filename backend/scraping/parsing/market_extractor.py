"""
UMOA Financial Intelligence — Market & Sovereign Debt Financial Extractor

Specialized extractor for:
1. Bourse Régionale des Valeurs Mobilières (BRVM) — Bulletins Officiels de la Cote (BOC)
   - indice_brvm_composite
   - indice_brvm_30
   - capitalisation_actions
   - capitalisation_obligations
   - valeur_transactions_actions
   - per_moyen_marche
   - rendement_moyen_dividende

2. Agence UMOA-Titres — Comptes-Rendus d'adjudication & Bulletins Statistiques
   - montant_emis_titres_publics
   - taux_couverture_adjudications
   - taux_moyen_adjudication_bat
   - taux_moyen_adjudication_oat
   - encours_titres_publics

Strictly respects: DATA MISSING > DATA WRONG.
Every extracted point carries full provenance, proper observation_level and consolidation_scope.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf

from app.core.logging import get_logger
from scraping.parsing.table_models import ExtractedMetricPoint

logger = get_logger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize unicode and strip combining diacritics for robust matching."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _clean_decimal(raw_str: str) -> Decimal | None:
    """Clean formatted numeric string into a Decimal."""
    if not raw_str:
        return None
    cleaned = (
        raw_str.replace(" ", "")
        .replace("\xa0", "")
        .replace("%", "")
        .replace(",", ".")
        .strip()
    )
    # Remove leading/trailing non-numeric punctuation except minus
    cleaned = re.sub(r"^[^\d\-]+|[^\d]+$", "", cleaned)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


# Country code to Canonical Sovereign Treasury name mapping in Entity Hub
SOVEREIGN_COUNTRY_MAP = {
    "CI": ("COTE D'IVOIRE", "Trésor Public de Côte d'Ivoire"),
    "SN": ("SENEGAL", "Trésor Public du Sénégal"),
    "BJ": ("BENIN", "Trésor Public du Bénin"),
    "BF": ("BURKINA", "Trésor Public du Burkina Faso"),
    "ML": ("MALI", "Trésor Public du Mali"),
    "NE": ("NIGER", "Trésor Public du Niger"),
    "TG": ("TOGO", "Trésor Public du Togo"),
    "GW": ("GUINEE-BISSAU", "Trésor Public de Guinée-Bissau"),
}


class MarketExtractor:
    """Extracts market data and sovereign public debt metrics from PDF publications."""

    def extract_brvm_boc(
        self,
        pdf_path: str | Path,
        document_id: str,
        source_id: str,
        entity_id: str | None,
        period_year: int,
    ) -> list[ExtractedMetricPoint]:
        """
        Extract the 7 official BRVM market metrics from Page 1 of a BOC document.
        """
        path = Path(pdf_path)
        if not path.is_file():
            return []

        doc = pymupdf.open(str(path))
        points: list[ExtractedMetricPoint] = []

        try:
            if doc.page_count < 1:
                return []

            raw_p1 = doc[0].get_text("text")
            p1_norm = _normalize_text(raw_p1)

            # 1. Indice BRVM Composite
            m_comp = re.search(r"BRVM\s+COMPOSITE\s*\n\s*([\d\s]+[,.]\d+)", p1_norm, re.IGNORECASE)
            if m_comp:
                val = _clean_decimal(m_comp.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="indice_brvm_composite",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_comp.group(1).strip(),
                            unit_original="point",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="point",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.98,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="BRVM COMPOSITE",
                            table_context="Indices & Marché BRVM",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 2. Indice BRVM 30
            m_30 = re.search(r"BRVM\s+30\s*\n\s*([\d\s]+[,.]\d+)", p1_norm, re.IGNORECASE)
            if m_30:
                val = _clean_decimal(m_30.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="indice_brvm_30",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_30.group(1).strip(),
                            unit_original="point",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="point",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.98,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="BRVM 30",
                            table_context="Indices & Marché BRVM",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 3. Capitalisation Boursière Actions
            m_cap_act = re.search(
                r"Capitalisation\s+boursiere[^\n]*Actions[^\n]*\n[^\S\r\n]*([0-9\xa0 ]+)",
                p1_norm,
                re.IGNORECASE,
            )
            if not m_cap_act:
                m_cap_act = re.search(
                    r"Capitalisation\s+boursiere[^\n]*\n[^\S\r\n]*([0-9\xa0 ]+)",
                    p1_norm,
                    re.IGNORECASE,
                )

            if m_cap_act:
                val = _clean_decimal(m_cap_act.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="capitalisation_actions",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_cap_act.group(1).strip(),
                            unit_original="FCFA",
                            currency_original="XOF",
                            value_normalized=val,
                            unit_normalized="XOF",
                            currency_normalized="XOF",
                            extraction_method="pdf_text",
                            confidence_score=0.95,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Capitalisation boursière (FCFA)(Actions & Droits)",
                            table_context="Marché des Actions",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 4. Capitalisation Boursière Obligations
            m_cap_ob = re.search(
                r"Obligations.*?Capitalisation\s+boursiere[^\n]*\n[^\S\r\n]*([0-9\xa0 ]+)",
                p1_norm,
                re.IGNORECASE | re.DOTALL,
            )
            if m_cap_ob:
                val = _clean_decimal(m_cap_ob.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="capitalisation_obligations",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_cap_ob.group(1).strip(),
                            unit_original="FCFA",
                            currency_original="XOF",
                            value_normalized=val,
                            unit_normalized="XOF",
                            currency_normalized="XOF",
                            extraction_method="pdf_text",
                            confidence_score=0.95,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Capitalisation boursière (FCFA)(Obligations)",
                            table_context="Marché des Obligations",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 5. Valeur des Transactions sur Actions
            m_val_act = re.search(
                r"Valeur\s+transigee\s*\(FCFA\)\s*\(Actions[^\)]*\)\s*\n[^\S\r\n]*([0-9\xa0 ]+)",
                p1_norm,
                re.IGNORECASE,
            )
            if not m_val_act:
                m_val_act = re.search(
                    r"Valeur\s+transigee[^\n]*\n[^\S\r\n]*([0-9\xa0 ]+)",
                    p1_norm,
                    re.IGNORECASE,
                )
            if m_val_act:
                val = _clean_decimal(m_val_act.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="valeur_transactions_actions",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_val_act.group(1).strip(),
                            unit_original="FCFA",
                            currency_original="XOF",
                            value_normalized=val,
                            unit_normalized="XOF",
                            currency_normalized="XOF",
                            extraction_method="pdf_text",
                            confidence_score=0.95,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Valeur transigée (FCFA) (Actions & Droits)",
                            table_context="Marché des Actions",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 6. PER moyen du marché
            m_per = re.search(
                r"PER\s+moyen\s+du\s+marche[^\n]*\n\s*([\d\s]+[,.]\d+)",
                p1_norm,
                re.IGNORECASE,
            )
            if m_per:
                val = _clean_decimal(m_per.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="per_moyen_marche",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_per.group(1).strip(),
                            unit_original="ratio",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="ratio",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.92,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="PER moyen du marché",
                            table_context="Indicateurs de Marché",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

            # 7. Rendement moyen du dividende
            m_rend = re.search(
                r"Taux\s+de\s+rendement\s+moyen\s+du\s+marche\s*\n\s*([\d\s]+[,.]\d+)",
                p1_norm,
                re.IGNORECASE,
            )
            if m_rend:
                val = _clean_decimal(m_rend.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="rendement_moyen_dividende",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=period_year,
                            period_type="annual",
                            value_original=m_rend.group(1).strip(),
                            unit_original="%",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="%",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.92,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Taux de rendement moyen du marché",
                            table_context="Indicateurs de Marché",
                            notes="Extracted from BRVM BOC Summary",
                            metadata={
                                "entity_id": entity_id,
                                "observation_level": "market",
                                "consolidation_scope": "not_applicable",
                            },
                        )
                    )

        finally:
            doc.close()

        return points

    def extract_umoa_titres_auction(
        self,
        pdf_path: str | Path,
        document_id: str,
        source_id: str,
        entity_map: dict[str, str],  # country_code -> sovereign_entity_id
        period_year: int,
    ) -> list[ExtractedMetricPoint]:
        """
        Extract sovereign debt auction metrics from a UMOA-Titres Compte Rendu document.
        """
        path = Path(pdf_path)
        if not path.is_file():
            return []

        doc = pymupdf.open(str(path))
        points: list[ExtractedMetricPoint] = []

        try:
            if doc.page_count < 1:
                return []

            raw_text = "\n".join(page.get_text("text") for page in doc)
            full_text = _normalize_text(raw_text)

            # Detect Issuer country
            issuer_country_code: str | None = None
            for code, (c_name, _) in SOVEREIGN_COUNTRY_MAP.items():
                if c_name in full_text.upper():
                    issuer_country_code = code
                    break

            sovereign_entity_id = entity_map.get(issuer_country_code or "") if issuer_country_code else None

            # Detect adjudication date / year
            m_date = re.search(r"Date\s+d[\'’]adjudication\s*:\s*([0-3]?\d/[01]?\d/(20\d{2}))", full_text, re.IGNORECASE)
            extracted_year = int(m_date.group(2)) if m_date else period_year

            # 1. Montant émis en titres publics (Soumissions retenues / Adjugé)
            m_ret = re.search(
                r"Soumissions\s+retenues\s*:\s*\n?\s*([\d\s]+(?:[,\.]\d+)?)\s*\n?\s*millions\s+de\s+FCFA",
                full_text,
                re.IGNORECASE,
            )
            if m_ret:
                val_m = _clean_decimal(m_ret.group(1))
                if val_m is not None:
                    val_xof = val_m * Decimal("1000000")
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="montant_emis_titres_publics",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=extracted_year,
                            period_type="annual",
                            value_original=f"{m_ret.group(1).strip()} millions de FCFA",
                            unit_original="millions FCFA",
                            currency_original="XOF",
                            value_normalized=val_xof,
                            unit_normalized="XOF",
                            currency_normalized="XOF",
                            extraction_method="pdf_text",
                            confidence_score=0.96,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Soumissions retenues (Adjudications)",
                            table_context="Compte Rendu d'Adjudication",
                            notes=f"Adjudication UMOA-Titres {issuer_country_code or 'UMOA'}",
                            metadata={
                                "entity_id": sovereign_entity_id,
                                "observation_level": "country" if sovereign_entity_id else "regional",
                                "consolidation_scope": "consolidated",
                                "country_code": issuer_country_code,
                            },
                        )
                    )

            # 2. Taux de couverture des adjudications
            m_couv = re.search(
                r"Taux\s+de\s+couverture[^\n:]*:\s*\n?\s*([\d\s]+[,\.]\d+)\s*%",
                full_text,
                re.IGNORECASE,
            )
            if m_couv:
                val = _clean_decimal(m_couv.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="taux_couverture_adjudications",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=extracted_year,
                            period_type="annual",
                            value_original=f"{m_couv.group(1).strip()} %",
                            unit_original="%",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="%",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.96,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Taux de couverture du montant mis en adjudication",
                            table_context="Compte Rendu d'Adjudication",
                            notes=f"Adjudication UMOA-Titres {issuer_country_code or 'UMOA'}",
                            metadata={
                                "entity_id": sovereign_entity_id,
                                "observation_level": "country" if sovereign_entity_id else "regional",
                                "consolidation_scope": "consolidated",
                                "country_code": issuer_country_code,
                            },
                        )
                    )

            # 3. Taux moyen pondéré d'adjudication BAT
            m_bat = re.search(
                r"BAT.*?Taux/Prix\s+moyen\s+pond[eéè]?r[eéè]?\s*\n?\s*([\d\s]+[,\.]\d+)\s*%",
                full_text,
                re.IGNORECASE | re.DOTALL,
            )
            if not m_bat:
                m_bat = re.search(r"Taux/Prix\s+moyen\s+pond[eéè]?r[eéè]?\s*\n?\s*([\d\s]+[,\.]\d+)\s*%", full_text, re.IGNORECASE)

            if m_bat:
                val = _clean_decimal(m_bat.group(1))
                if val is not None and val < 30:  # Yield rate is < 30%
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="taux_moyen_adjudication_bat",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=extracted_year,
                            period_type="annual",
                            value_original=f"{m_bat.group(1).strip()} %",
                            unit_original="%",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="%",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.92,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Taux moyen pondéré BAT",
                            table_context="Compte Rendu d'Adjudication",
                            notes=f"Adjudication BAT {issuer_country_code or 'UMOA'}",
                            metadata={
                                "entity_id": sovereign_entity_id,
                                "observation_level": "country" if sovereign_entity_id else "regional",
                                "consolidation_scope": "consolidated",
                                "country_code": issuer_country_code,
                            },
                        )
                    )

            # 4. Taux moyen pondéré / Rendement d'adjudication OAT
            m_oat = re.search(
                r"Rendement\s+moyen\s+pond[eéè]?r[eéè]?\s*\n?\s*([\d\s]+[,\.]\d+)\s*%",
                full_text,
                re.IGNORECASE,
            )
            if m_oat:
                val = _clean_decimal(m_oat.group(1))
                if val is not None:
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="taux_moyen_adjudication_oat",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=extracted_year,
                            period_type="annual",
                            value_original=f"{m_oat.group(1).strip()} %",
                            unit_original="%",
                            currency_original=None,
                            value_normalized=val,
                            unit_normalized="%",
                            currency_normalized=None,
                            extraction_method="pdf_text",
                            confidence_score=0.92,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Rendement moyen pondéré OAT",
                            table_context="Compte Rendu d'Adjudication",
                            notes=f"Adjudication OAT {issuer_country_code or 'UMOA'}",
                            metadata={
                                "entity_id": sovereign_entity_id,
                                "observation_level": "country" if sovereign_entity_id else "regional",
                                "consolidation_scope": "consolidated",
                                "country_code": issuer_country_code,
                            },
                        )
                    )

            # 5. Encours des titres publics (dans les bulletins / synthèses)
            m_enc = re.search(
                r"Encours\s+(?:total\s+)?des\s+titres\s+publics[^\n:]*:\s*\n?\s*([\d\s]+(?:[,\.]\d+)?)\s*(?:milliards|millions)?",
                full_text,
                re.IGNORECASE,
            )
            if m_enc:
                val_raw = _clean_decimal(m_enc.group(1))
                if val_raw is not None:
                    multiplier = Decimal("1000000000") if "milliard" in m_enc.group(0).lower() else Decimal("1000000")
                    val_xof = val_raw * multiplier
                    points.append(
                        ExtractedMetricPoint(
                            metric_code="encours_titres_publics",
                            document_id=document_id,
                            source_id=source_id,
                            page_number=1,
                            period_year=extracted_year,
                            period_type="annual",
                            value_original=m_enc.group(0).strip(),
                            unit_original="XOF",
                            currency_original="XOF",
                            value_normalized=val_xof,
                            unit_normalized="XOF",
                            currency_normalized="XOF",
                            extraction_method="pdf_text",
                            confidence_score=0.90,
                            confidence_level="high_confidence",
                            status="needs_review",
                            matched_label="Encours des titres publics",
                            table_context="Bulletin Statistiques MTP",
                            notes=f"Encours Titres Publics {issuer_country_code or 'UMOA'}",
                            metadata={
                                "entity_id": sovereign_entity_id,
                                "observation_level": "country" if sovereign_entity_id else "regional",
                                "consolidation_scope": "consolidated",
                                "country_code": issuer_country_code,
                            },
                        )
                    )

        finally:
            doc.close()

        return points
