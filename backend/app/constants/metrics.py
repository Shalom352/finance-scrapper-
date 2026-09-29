"""
UMOA Banking Intelligence — Official V1 metric catalogue.

Single source of truth for the 26 V1 metrics.
Seeded into ``metric_definitions`` by the Phase-2 Alembic migration.

Reference: docs/specification-v1.md sections 7, 8, 9.
Do NOT invent, rename or re-classify a metric here without a
documented revision of the specification.

All V1 metrics have ``is_calculated = False`` (published values only).
"""

from typing import Any

# Canonical enumerations (mirror docs/specification-v1.md section 14)
STATEMENT_TYPES = (
    "balance_sheet",
    "income_statement",
    "cash_flow_statement",
    "off_balance_sheet",
    "not_applicable",
)

CATEGORIES = (
    "assets",
    "liabilities",
    "equity",
    "income_statement",
    "cash_flow",
    "debt_indicator",
)

VALUE_TYPES = ("amount", "percentage", "ratio", "rate")

CURRENCY_TYPES = ("monetary", "non_monetary")


# The 26 V1 metrics. Keys map 1:1 to ``MetricDefinition`` columns.
V1_METRICS: list[dict[str, Any]] = [
    # --- Actifs (assets) ---
    {
        "code": "total_actifs",
        "label_fr": "Total actifs",
        "label_en": "Total assets",
        "definition_fr": (
            "Somme totale des actifs telle que publiée au bilan. "
            "Exclut : engagements hors bilan, postes de passif."
        ),
        "definition_en": (
            "Total assets as published in the balance sheet. "
            "Excludes: off-balance-sheet commitments, liability items."
        ),
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 1,
        "description_synth": "Total des actifs publiés au bilan.",
    },
    {
        "code": "tresorerie",
        "label_fr": "Trésorerie",
        "label_en": "Cash and cash equivalents",
        "definition_fr": (
            "Disponibilités, caisse et comptes auprès d'instituts d'émission/"
            "correspondants, tels que publiés. Exclut : créances interbancaires "
            "classées en creances_banques."
        ),
        "definition_en": (
            "Cash, balances with central banks/correspondents as published. "
            "Excludes: interbank claims recorded under creances_banques."
        ),
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 2,
        "description_synth": "Trésorerie et équivalents publiés.",
    },
    {
        "code": "creances_clients",
        "label_fr": "Créances clients",
        "label_en": "Customer loans",
        "definition_fr": (
            "Créances sur la clientèle telles que publiées (brut ou net selon "
            "le libellé source, précisé dans notes). Exclut : créances sur banques."
        ),
        "definition_en": (
            "Loans and receivables from customers as published (gross or net per "
            "source label, noted in notes). Excludes: claims on banks."
        ),
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 3,
        "description_synth": "Créances sur la clientèle publiées.",
    },
    {
        "code": "creances_banques",
        "label_fr": "Créances banques",
        "label_en": "Interbank claims",
        "definition_fr": (
            "Créances sur les établissements de crédit (interbancaire actif) "
            "telles que publiées."
        ),
        "definition_en": "Claims on credit institutions (interbank assets) as published.",
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 4,
        "description_synth": "Créances interbancaires actives publiées.",
    },
    {
        "code": "immobilisations",
        "label_fr": "Immobilisations",
        "label_en": "Fixed assets",
        "definition_fr": (
            "Immobilisations corporelles et incorporelles publiées. "
            "Exclut : actifs financiers."
        ),
        "definition_en": (
            "Property, plant, equipment and intangibles as published. "
            "Excludes: financial assets."
        ),
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 5,
        "description_synth": "Immobilisations corporelles et incorporelles publiées.",
    },
    {
        "code": "autres_actifs",
        "label_fr": "Autres actifs",
        "label_en": "Other assets",
        "definition_fr": "Actifs publiés ne relevant d'aucune autre catégorie d'actif.",
        "definition_en": "Published assets not covered by any other asset category.",
        "statement_type": "balance_sheet",
        "category": "assets",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 6,
        "description_synth": "Autres actifs publiés.",
    },
    # --- Passifs (liabilities) ---
    {
        "code": "total_passifs",
        "label_fr": "Total passifs",
        "label_en": "Total liabilities",
        "definition_fr": "Somme totale des passifs telle que publiée.",
        "definition_en": "Total liabilities as published.",
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 7,
        "description_synth": "Total des passifs publiés.",
    },
    {
        "code": "depots_clients",
        "label_fr": "Dépôts clients",
        "label_en": "Customer deposits",
        "definition_fr": "Dépôts et comptes créditeurs de la clientèle publiés.",
        "definition_en": "Customer deposits and credit balances as published.",
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 8,
        "description_synth": "Dépôts de la clientèle publiés.",
    },
    {
        "code": "depots_banques",
        "label_fr": "Dépôts banques",
        "label_en": "Interbank deposits",
        "definition_fr": "Dépôts et emprunts interbancaires reçus, publiés.",
        "definition_en": "Interbank deposits received, as published.",
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 9,
        "description_synth": "Dépôts interbancaires reçus publiés.",
    },
    {
        "code": "emprunts_bancaires",
        "label_fr": "Emprunts bancaires",
        "label_en": "Bank borrowings",
        "definition_fr": (
            "Montant des emprunts contractés auprès d'établissements de crédit ou "
            "d'autres contreparties financières, tel que présenté dans les états "
            "financiers ou les notes annexes. Exclut : dépôts clientèle, dépôts "
            "interbancaires, titres de créance émis, capitaux propres."
        ),
        "definition_en": (
            "Borrowings from credit institutions or other financial counterparties, "
            "as presented in financial statements or notes. Excludes: customer "
            "deposits, interbank deposits, issued debt securities, equity."
        ),
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 10,
        "description_synth": "Emprunts auprès d'établissements de crédit publiés.",
    },
    {
        "code": "obligations_emises",
        "label_fr": "Obligations émises",
        "label_en": "Debt securities issued",
        "definition_fr": "Titres de créance émis (obligations, BMT/BTA émis) publiés.",
        "definition_en": "Debt securities issued (bonds, issued T-bills/bonds) as published.",
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 11,
        "description_synth": "Titres de créance émis publiés.",
    },
    {
        "code": "dettes_totales",
        "label_fr": "Dettes totales",
        "label_en": "Total debt",
        "definition_fr": (
            "Total des dettes financières publiées (emprunts et titres de créance émis)."
        ),
        "definition_en": (
            "Total financial debt as published (borrowings and issued debt securities)."
        ),
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 12,
        "description_synth": "Dettes financières totales publiées.",
    },
    {
        "code": "autres_passifs",
        "label_fr": "Autres passifs",
        "label_en": "Other liabilities",
        "definition_fr": "Passifs publiés ne relevant d'aucune autre catégorie de passif.",
        "definition_en": "Published liabilities not covered by any other liability category.",
        "statement_type": "balance_sheet",
        "category": "liabilities",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 13,
        "description_synth": "Autres passifs publiés.",
    },
    # --- Capitaux propres (equity) ---
    {
        "code": "capitaux_propres",
        "label_fr": "Capitaux propres",
        "label_en": "Equity",
        "definition_fr": (
            "Capitaux propres publiés (capital, réserves, report à nouveau, résultat). "
            "Exclut : dettes subordonnées classées en dettes."
        ),
        "definition_en": (
            "Published equity (share capital, reserves, retained earnings, result). "
            "Excludes: subordinated debt classified as debt."
        ),
        "statement_type": "balance_sheet",
        "category": "equity",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 14,
        "description_synth": "Capitaux propres publiés.",
    },
    # --- Compte de résultat (income statement) ---
    {
        "code": "produit_net_bancaire",
        "label_fr": "Produit net bancaire",
        "label_en": "Net banking income",
        "definition_fr": (
            "Produit net bancaire publié. Exclut : produits accessoires non inclus "
            "dans le PNB publié."
        ),
        "definition_en": (
            "Net banking income as published. Excludes: ancillary income not "
            "included in published NBI."
        ),
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 15,
        "description_synth": "Produit net bancaire publié.",
    },
    {
        "code": "produits_totaux",
        "label_fr": "Produits totaux",
        "label_en": "Total income",
        "definition_fr": "Total des produits publiés.",
        "definition_en": "Total income as published.",
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 16,
        "description_synth": "Total des produits publiés.",
    },
    {
        "code": "charges_totales",
        "label_fr": "Charges totales",
        "label_en": "Total expenses",
        "definition_fr": "Total des charges publiées.",
        "definition_en": "Total expenses as published.",
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 17,
        "description_synth": "Total des charges publiées.",
    },
    {
        "code": "resultat_exploitation",
        "label_fr": "Résultat d'exploitation",
        "label_en": "Operating result",
        "definition_fr": "Résultat d'exploitation publié.",
        "definition_en": "Operating result as published.",
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 18,
        "description_synth": "Résultat d'exploitation publié.",
    },
    {
        "code": "resultat_net",
        "label_fr": "Résultat net",
        "label_en": "Net result",
        "definition_fr": "Résultat net publié (part du groupe si précisé).",
        "definition_en": "Net result as published (group share where specified).",
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 19,
        "description_synth": "Résultat net publié.",
    },
    {
        "code": "chiffre_affaires",
        "label_fr": "Chiffre d'affaires",
        "label_en": "Revenue",
        "definition_fr": (
            "Chiffre d'affaires publié explicitement et identifié comme tel. "
            "Interdiction de dériver le chiffre d'affaires du produit net bancaire. "
            "Le PNB et le CA restent deux métriques distinctes."
        ),
        "definition_en": (
            "Revenue explicitly published and identified as such. Deriving revenue "
            "from net banking income is forbidden. NBI and revenue remain two "
            "distinct metrics."
        ),
        "statement_type": "income_statement",
        "category": "income_statement",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 20,
        "description_synth": "Chiffre d'affaires publié explicitement.",
    },
    # --- Flux de trésorerie (cash flow) ---
    {
        "code": "flux_exploitation",
        "label_fr": "Flux exploitation",
        "label_en": "Operating cash flow",
        "definition_fr": "Flux net de trésorerie lié aux activités d'exploitation.",
        "definition_en": "Net cash flow from operating activities.",
        "statement_type": "cash_flow_statement",
        "category": "cash_flow",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 21,
        "description_synth": "Flux net de trésorerie d'exploitation publié.",
    },
    {
        "code": "flux_investissement",
        "label_fr": "Flux investissement",
        "label_en": "Investing cash flow",
        "definition_fr": "Flux net de trésorerie lié aux activités d'investissement.",
        "definition_en": "Net cash flow from investing activities.",
        "statement_type": "cash_flow_statement",
        "category": "cash_flow",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 22,
        "description_synth": "Flux net de trésorerie d'investissement publié.",
    },
    {
        "code": "flux_financement",
        "label_fr": "Flux financement",
        "label_en": "Financing cash flow",
        "definition_fr": "Flux net de trésorerie lié aux activités de financement.",
        "definition_en": "Net cash flow from financing activities.",
        "statement_type": "cash_flow_statement",
        "category": "cash_flow",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": False,
        "display_order": 23,
        "description_synth": "Flux net de trésorerie de financement publié.",
    },
    # --- Dette / indicateurs publiés (debt indicators) ---
    {
        "code": "facilities_de_change",
        "label_fr": "Facilités de change",
        "label_en": "FX facilities",
        "definition_fr": (
            "Montant publié sous un libellé source explicite de facilités/engagements "
            "de change. Collecte uniquement lorsqu'un document publie un poste "
            "explicitement intitulé comme tel ; aucun mapping automatique approximatif. "
            "Le libellé source exact est conservé dans notes. Limitation documentée : "
            "si les sources V1 ne permettent pas une identification fiable et "
            "reproductible, la métrique reste au catalogue sans collecte ; aucune "
            "donnée n'est produite."
        ),
        "definition_en": (
            "Amount published under an explicit source label for foreign-exchange "
            "facilities/commitments. Collected only when a document publishes a line "
            "explicitly labelled as such; no approximate automatic mapping. The exact "
            "source label is kept in notes. Documented limitation: if V1 sources do "
            "not allow reliable, reproducible identification, the metric stays in the "
            "catalogue without collection; no data is produced."
        ),
        "statement_type": "off_balance_sheet",
        "category": "debt_indicator",
        "value_type": "amount",
        "currency_type": "monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 24,
        "description_synth": "Facilités de change publiées sous libellé explicite.",
    },
    {
        "code": "taux_interet_moyen",
        "label_fr": "Taux d'intérêt moyen",
        "label_en": "Average interest rate",
        "definition_fr": (
            "Taux d'intérêt moyen publié, exprimé en pourcentage. Aucun calcul en V1."
        ),
        "definition_en": (
            "Average interest rate as published, expressed as a percentage. "
            "No computation in V1."
        ),
        "statement_type": "not_applicable",
        "category": "debt_indicator",
        "value_type": "rate",
        "currency_type": "non_monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 25,
        "description_synth": "Taux d'intérêt moyen publié.",
    },
    {
        "code": "endettement_actifs",
        "label_fr": "Endettement sur actifs",
        "label_en": "Debt-to-assets ratio",
        "definition_fr": (
            "Ratio d'endettement sur actifs publié, exprimé en ratio. Collecté "
            "uniquement lorsqu'il est explicitement publié ; aucun recalcul."
        ),
        "definition_en": (
            "Debt-to-assets ratio as published, expressed as a ratio. Collected only "
            "when explicitly published; no recomputation."
        ),
        "statement_type": "not_applicable",
        "category": "debt_indicator",
        "value_type": "ratio",
        "currency_type": "non_monetary",
        "is_calculated": False,
        "is_active": True,
        "is_debt_related": True,
        "display_order": 26,
        "description_synth": "Ratio d'endettement sur actifs publié.",
    },
]

# Stable tuple of the 26 metric codes (order = display_order).
V1_METRIC_CODES: tuple[str, ...] = tuple(m["code"] for m in V1_METRICS)

# Convenience lookup.
V1_METRICS_BY_CODE: dict[str, dict[str, Any]] = {m["code"]: m for m in V1_METRICS}