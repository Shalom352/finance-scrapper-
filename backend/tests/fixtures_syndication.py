"""Synthetic syndication workbook — the STRUCTURE of TOMASTEED's tracker (titles, label rows, merged cells,
Excel dates, multi-line contact cells, detail sheet, CRM, data-room blocks) with FICTITIOUS deals and people.
The real file is internal and personal data: it never goes into the repository or the tests."""
from __future__ import annotations

import io
from datetime import datetime

import openpyxl

DEAL_SN = "SEN | Etat du Sénégal - Campagne fictive 25-26"
DEAL_CI = "CIV | Société Alpha - Refinancement fictif"
DEAL_GA = "GAB | Etat du Gabon - Ligne fictive"
DEAL_TG = "TOG | Etat du Togo - Projet Beta"
DEAL_EMPTY = "BEN | Gamma Industries - Usine fictive"
SUIVI_HEADERS = ["#", "Nom du Deal", "Stade opporrtunité ", "Banques / Institution ", "Appétit\n/Participation",
                 "Type de prêteurs", "Montants des Engagements ", "Taux", "Commission d'arrangement",
                 "Commission d'engagement", "Maturité", "Interlocuteurs", "Fonctions", "Téléphone", "Mail"]


def suivi_rows(*, bank_x_amount: str = "27,8 Md FCFA", bank_x_rate: str = "7 % HT") -> list[list]:
    return [
        [1, DEAL_SN, "0 - Mandat exécuté", "BOAD", "Oui", "DFI ", "Jusqu'à 300 M€", "4,25 % p.a. + EURIBOR applicable",
         "1,00 %", "30 % de la marge sur les montants non tirés", "12 mois", "- Awa FICTIVE\n- Ben FICTIF",
         "- Directrice\n- Analyste", "+221 00 00 00 01\n+221 00 00 00 02", "awa@boad.example\nben@boad.example"],
        [None, None, None, "Banque X", "Oui", "Banque ", bank_x_amount, bank_x_rate, "20 M FCFA flat HT",
         "Non précisée", "10 ans, dont 5 ans de différé partiel", "Carl FICTIF", "Directeur", "À confirmer",
         "carl@bankx.example"],
        [2, DEAL_CI, None, "ISDB", "Non", "DFI", "300–500 M€", "Taux de référence + marge à confirmer", "À confirmer",
         "À confirmer", "Minimum 15 ans", None, None, None, None],
        [3, DEAL_GA, None, "BGFIBank Gabon", "Oui", "Banque ", "10 Md FCFA", "8,75 % p.a.", "1,75 % HT",
         "0,50 % HT par trimestre", "72 mois", None, None, None, None],
        [4, DEAL_TG, None, None, None, None, None, None, None, None, None, None, None, None, None],
        [5, DEAL_EMPTY, None, None, None, None, None, None, None, None, None, None, None, None, None],
    ]


def build_workbook(*, rows: list[list] | None = None, date_maj: datetime = datetime(2026, 9, 8),
                   with_suivi: bool = True, shift_columns: bool = False, audit_cases: bool = False) -> bytes:
    """``audit_cases``: the structures found in the real file on 22/10/2026 — a second table (LOI received
    / to receive, its own columns) below the main one, and an e-mail with a typo ('.ccom')."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    # ---------------------------------------------------------------- detail sheet (one mandate)
    d = wb.create_sheet("Projet Beta (1)")
    d["D2"], d["E2"] = "Date de MAJ ", datetime(2023, 8, 9)
    d["D3"] = "Montant en XOF Millions"
    for col, label in zip("DEFGHIJKLMNOP", ["#", "Banques", "Appétit\n/Participation", "Engagements \n(GXAF)",
                                             "Etat du dossier ", "Retour obtenu \n", "Interlocuteurs", "Fonctions",
                                             "Adresses Email", "Téléphone", "Date de transmission \ndu NDA",
                                             "Date de réception\ndu NDA", "Prochaines étapes"], strict=True):
        d[f"{col}7"] = label
    d["I8"] = "Prêteurs "
    d.merge_cells("I8:K8")
    lines = [
        (1, "BANQUE TOGO", "Oui", 1, "Engagement préliminaire", "Dina FICTIVE", "Directrice", "dina@btg.example",
         "+228 00", datetime(2023, 7, 11), datetime(2023, 7, 12), "- Création de la Data room"),
        (2, "Banque Y Togo", "Non", 0, "En cours d'étude ", "Eli FICTIF", "Directeur", "eli@by.example", "+228 01",
         datetime(2023, 7, 11), "N/A \nNous disposons d'un NDA Global", None),
        (3, None, "Non", 0, "En cours d'étude ", None, None, None, None, None, None, None),
    ]
    for i, line in enumerate(lines, start=9):
        for col, value in zip("DEFGHJKLMNOP", line, strict=True):
            d[f"{col}{i}"] = value
    d["I13"] = "Garants "
    d["D16"], d["G16"] = "Total des Engagements Prêteurs ", 1

    # ---------------------------------------------------------------- SUIVI SYNDICATION
    if with_suivi:
        s = wb.create_sheet("SUIVI SYNDICATION")
        s["D2"] = "SYNDICATION DES DEALS TOMASTEED"
        s["D3"], s["G3"] = "Date ", date_maj
        s["D4"] = "Montant en XOF Millions"
        s["E10"], s["G10"] = "1 - Transactions", "2-Institutions et engagements"
        first_col = 5 if shift_columns else 4
        for j, label in enumerate(SUIVI_HEADERS):
            s.cell(row=12, column=first_col + j, value=label)
        for i, row in enumerate(rows or suivi_rows(), start=13):
            for j, value in enumerate(row):
                s.cell(row=i, column=first_col + j, value=value)
        s.merge_cells(start_row=13, start_column=first_col, end_row=14, end_column=first_col)
        if audit_cases:  # second table, institution column aligned with the main one, other columns differ
            inst = first_col + 3
            for j, label in enumerate(["Banques / Institution ", "Montants des Engagements ", "Taux", "Maturité"]):
                s.cell(row=30, column=inst + j, value=label)
            s.cell(row=32, column=inst, value="LOI reçus")
            for j, value in enumerate(["BANQUE TOGO", 5000, 0.08, "10 ans"]):
                s.cell(row=33, column=inst + j, value=value)
            s.cell(row=35, column=inst, value="LOI à recevoir")
            s.cell(row=36, column=inst, value="Banque Z")

    # ---------------------------------------------------------------- derived / empty sheets
    lm = wb.create_sheet("Cartographie des prêteurs")
    lm["D4"] = "LENDER MAPPING - TOMASTEED"
    inv = wb.create_sheet("Cartographie des investisseurs")
    inv["D4"] = "Cartographie des investisseurs - TOMASTEED"

    # ---------------------------------------------------------------- CRM
    c = wb.create_sheet("CRM Interne")
    c["D4"] = "CRM INTERNE - CONTACTS INSTITUTIONNELS"
    for col, label in zip("DEFGHIJ", ["Institution", "Nom du contact", "Fonction", "Email", "Telephone",
                                      "Derniere interaction connue", "Contexte / Deal associe"], strict=True):
        c[f"{col}7"] = label
    c["D8"] = "BOAD"
    c.merge_cells("D8:D9")
    c["E8"], c["F8"], c["G8"], c["H8"], c["I8"] = "Awa FICTIVE", "Directrice", "AWA@boad.example", "A completer", \
        datetime(2026, 9, 1)
    c["E9"], c["F9"], c["G9"] = "Fred FICTIF", "Chargé d'affaires", "fred@boad.example"
    c["D10"], c["E10"], c["G10"] = "ISDB", "Gina FICTIVE", "gina@isdb.example"

    # ---------------------------------------------------------------- data room blocks
    r = wb.create_sheet("Liste des personnes dataroom")
    r["D3"], r["H3"] = "TOMASTEED", "BOAD"
    r.merge_cells("D3:E3")
    r.merge_cells("H3:I3")
    r["D4"], r["E4"] = "Hugo FICTIF", "hugo@tomasteed.example"
    r["H4"], r["I4"] = "Fred FICTIF", "fred@boad.example"
    if audit_cases:
        r["D5"], r["E5"] = "Ivy FICTIVE", "ivy@tomasteed.ccom"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
