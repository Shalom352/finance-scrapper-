"""Builds pilot_manifest.json (kept in Python so that every entry stays readable and commented).

Every quotation below was located on its page in the local copies of audits/ape_amf
(pilot_load --files checks them again before writing anything). Roles are recorded ONLY
where the document names them; nothing is deduced. Run: python pilot/build_manifest.py
"""
import json
from pathlib import Path

OBS = "2026-10-05"
FA = "https://www.financialafrik.com"
SOURCES = [
    {"key": "tresor_ci", "name": "Direction Générale du Trésor et de la Comptabilité Publique (Côte d'Ivoire)",
     "url": "https://tresor.gouv.ci", "source_type": "government", "country_code": "CI", "priority": 1},
    {"key": "fgi", "name": "FGI Bourse — Finance Gestion et Intermédiation (SGI)", "url": "https://www.fgi-bourse.com",
     "source_type": "financial_market", "country_code": "SN"},
    {"key": "africabourse", "name": "Africabourse (SGI)", "url": "https://www.africabourse.com",
     "source_type": "financial_market", "country_code": "BJ"},
    {"key": "sgibenin", "name": "SGI Bénin", "url": "https://sgibenin.com", "source_type": "financial_market",
     "country_code": "BJ"},
    {"key": "brvm", "name": "BRVM", "url": "https://www.brvm.org", "source_type": "financial_market", "priority": 1},
    {"key": "afinhab", "name": "AFINHAB (ex-CRRH-UEMOA)", "url": "https://afinhab.org", "source_type": "regional_body"},
    {"key": "diaspora_bf", "name": "Diaspora Bonds Burkina Faso (site de l'opération)",
     "url": "https://www.diaspora-bond-burkina.com", "source_type": "government", "country_code": "BF"},
    {"key": "umoatitres", "name": "Agence UMOA-Titres", "url": "https://www.umoatitres.org",
     "source_type": "financial_market", "priority": 1},
    {"key": "amf", "name": "AMF-UMOA — API des opérations (index)", "url": "https://www.amf-umoa.org",
     "source_type": "market_authority", "priority": 1},
    {"key": "ecofin", "name": "Agence Ecofin", "url": "https://www.agenceecofin.com", "source_type": "secondary",
     "priority": 3},
    {"key": "sika", "name": "Sika Finance", "url": "https://www.sikafinance.com", "source_type": "secondary", "priority": 3},
    {"key": "fa", "name": "Financial Afrik", "url": FA, "source_type": "secondary", "priority": 3},
]


def doc(key, source, title, url, local=None, dtype="other", pages=None, published=None):
    d = {"key": key, "source": source, "title": title, "url": url, "document_type": dtype}
    if local:
        d["local_file"] = local
    if pages:
        d["page_count"] = pages
    if published:
        d["published_at"] = published
    return d


N = "notes/"
DOCUMENTS = [
    doc("n01", "tresor_ci", "Note d'information — TPCI 5,80 % 2021-2028 & 5,90 % 2021-2031",
        "https://tresor.gouv.ci/tres/wp-content/uploads/2021/06/NOTE-DINFO-TRESOR-16-06.pdf",
        N + "tresor.gouv.ci_tres_wp-content_uploads_2021_06_NOTE-DINFO-TRESOR-16-06.pdf"),
    doc("n02", "fgi", "Note d'information — État du Sénégal, APE juin 2025",
        "https://www.fgi-bourse.com/wp-content/uploads/2025/06/Note-dinformation_Ape-Tresor-Public-SN.pdf",
        N + "www.fgi-bourse.com_wp-content_uploads_2025_06_Note-dinformation_Ape-Tresor-Public-SN.pdf"),
    doc("n03", "africabourse", "Note d'information — TPTG 6,45 % 2025-2030 & 6,60 % 2025-2032",
        "https://www.africabourse.com/uploads/opportunite/34e14a00c02791123e74ed452c80a9f9.pdf",
        N + "www.africabourse.com_uploads_opportunite_34e14a00c02791123e74ed452c80a9f9.pdf"),
    doc("n04", "africabourse", "Note d'information — OPV BIIC (cession par l'État du Bénin)",
        "https://www.africabourse.com/uploads/opportunite/8330f0533e80a60db70e6d274099be60.pdf",
        N + "www.africabourse.com_uploads_opportunite_8330f0533e80a60db70e6d274099be60.pdf"),
    doc("n06", "sgibenin", "Note d'information — PAD 6,60 % 2020-2027",
        "https://sgibenin.com/opportunites/2020/sn/APE_PAD2020/Note_Information__APE_PAD_6.60_2020_2027.pdf",
        N + "sgibenin.com_opportunites_2020_sn_APE_PAD2020_Note_Information__APE_PAD_6.60_2020_2027.pdf"),
    doc("n07", "fgi", "Note d'information — PETRO IVOIRE 6,80 % 2022-2029",
        "https://www.fgi-bourse.com/wp-content/uploads/2024/08/Emprunt-Obligataire-PETRO-IVOIRE-680-2022-2029.pdf",
        N + "www.fgi-bourse.com_wp-content_uploads_2024_08_Emprunt-Obligataire-PETRO-IVOIRE-680-2022-2029.pdf"),
    doc("n08", "brvm", "Note d'information — augmentation de capital SAFCA CI (Alios Finance CI)",
        "https://www.brvm.org/sites/default/files/20260413_-_note_dinformation_-_augmentation_de_capital_-_safca_ci.pdf",
        N + "www.brvm.org_sites_default_files_20260413_-_note_dinformation_-_augmentation_de_capital_-_safca_ci.pdf"),
    doc("n09", "afinhab", "Note d'information — CRRH-UEMOA 6,10 % 2022-2037 (9e emprunt)",
        "https://afinhab.org/sites/default/files/documents/note%20d'info%209e%20emprunt-avec%20compression.pdf",
        N + "afinhab.org_sites_default_files_documents_note_d_info_9e_emprunt-avec_compression.pdf"),
    doc("n11", "diaspora_bf", "Note d'information — TPBF Diaspora Bonds 2026",
        "https://www.diaspora-bond-burkina.com/docs/note-information.pdf",
        N + "www.diaspora-bond-burkina.com_docs_note-information.pdf"),
    doc("cr_ci_ec_20250109", "umoatitres", "Compte rendu — rachat et émission simultanée CI du 09/01/2025",
        "https://www.umoatitres.org/wp-content/uploads/2025/01/Compte-rendu-CI-EC-09.01.2025-1.pdf",
        "umoatitres/CR-CI-EC-09.01.2025.pdf", published="2025-01-09"),
    doc("amf_api", "amf", "API AMF-UMOA — liste des opérations (métadonnées)",
        "https://www.amf-umoa.org/service/api/elastic/operation", dtype="web_page", pages=1),
    doc("eco_baobab", "ecofin", "Baobab Côte d'Ivoire lance le premier Sustainability-Linked Bond d'une IMF dans l'UMOA",
        "https://www.agenceecofin.com/actualites-finance/1409-141527-baobab-cote-d-ivoire-lance-le-premier-sustainability-linked-bond-d-une-imf-dans-l-umoa",
        "press/eco_baobab.html", dtype="web_page", pages=1, published="2026-09-14"),
    doc("eco_afinhab", "ecofin", "AFINHAB clôture son émission de Social Bond de 40 milliards FCFA",
        "https://www.agenceecofin.com/actualites-finance/2807-140577-afinhab-cloture-son-emission-de-social-bond-de-40-milliards-fcfa-et-franchit-le-cap-des-100-milliards-fcfa-d-obligations-sociales",
        "press/eco_afinhab.html", dtype="web_page", pages=1, published="2026-07-28"),
    doc("sika_emergence", "sika", "Côte d'Ivoire : Emergence Plaza prépare un Green Bond de 10 milliards FCFA",
        "https://www.sikafinance.com/marches/cote-divoire-emergence-plaza-prepare-un-green-bond-de-10-milliards-fcfa_29107",
        "press/sika_emergence.html", dtype="web_page", pages=1, published="2021-07-06"),
    doc("fa_pad", "fa", "Le Port Autonome de Dakar lance une émission de 60 milliards de FCFA",
        FA + "/2020/10/01/le-port-autonome-de-dakar-lance-une-emission-de-60-milliards-de-fcfa-pour-decongestionner-son-trafic/",
        dtype="web_page", pages=1, published="2020-10-01"),
]


def src(ref, document, page, cls, fields, excerpt=None, **press):
    s = {"ref": ref, "document": document, "page": page, "source_class": cls, "fields": fields}
    if excerpt:
        s["excerpt"] = excerpt
    s.update(press)
    return s


def part(role, name, ref, page=None, excerpt=None, method="text", institution=None):
    p = {"role": role, "name": name, "source_ref": ref, "extraction_method": method}
    if page:
        p["page"] = page
    if excerpt:
        p["excerpt"] = excerpt
    if institution:
        p["institution_name"] = institution
    return p


def arranger_and_lead(name, ref, page, excerpt, institution=None):
    """'Arrangeur et chef de file : X' gives TWO participations sharing the same quotation (D1)."""
    return [part("arranger", name, ref, page, excerpt, institution=institution),
            part("lead_manager", name, ref, page, excerpt, institution=institution)]


BASE = ["title", "deal_type", "country_code", "sector"]
DEALS = [
    {"key": "D01_TPCI_2021_06", "case": "A1",
     "title": "TPCI 5,80 % 2021-2028 & 5,90 % 2021-2031 (EE/21-07, EE/21-08)", "deal_type": "sovereign_bond_ape",
     "country_code": "CI", "sector": "public_finance",
     "amount_original": "130 milliards FCFA et 20 milliards FCFA (deux tranches)",
     "use_of_proceeds": "financement des investissements prévus au budget de l'Etat au titre de l'année 2021",
     "use_of_proceeds_categories": ["budget_financing"],
     "guarantees": "garantie souveraine de l'État de Côte d'Ivoire",
     "sources": [
         src("p10", "n01", 10, "primary_regulatory", BASE + ["amount_original", "use_of_proceeds",
             "use_of_proceeds_categories"], "de montant respectif 130 milliards FCFA et 20 milliards FCFA"),
         src("p12", "n01", 12, "primary_regulatory", ["guarantees"],
             "Cette émission bénéficie de la garantie souveraine de l'État de Côte d'Ivoire"),
         src("p13", "n01", 13, "primary_regulatory", []),
     ],
     "participants": [
         part("lead_manager", "EDC INVESTMENT CORPORATION", "p13", 13,
              "EDC INVESTMENT CORPORATION a été mandaté par l'Emetteur en qualité de Chef de file"),
         *[part("co_lead_manager", n, "p13", 13, "BNI FINANCES - MAC AFRICAN - BIIC FINANCIAL SERVICES - FINANCE "
                "GESTION ET INTERMEDIATION ont été mandatés par l'Etat en qualité de co-chefs de file")
           for n in ("BNI FINANCES", "MAC AFRICAN", "BIIC FINANCIAL SERVICES", "FINANCE GESTION ET INTERMEDIATION")],
         part("guarantor", "État de Côte d'Ivoire", "p12", 12, "garantie souveraine de l'État de Côte d'Ivoire"),
     ]},
    {"key": "D06_SN_APE_2025_06", "case": "A6",
     "title": "État du Sénégal — APE juin 2025, 4 tranches (EE/25-13 à 16)", "deal_type": "sovereign_bond_ape",
     "country_code": "SN", "sector": "public_finance", "amount": "300000000000", "currency": "XOF", "unit": "units",
     "amount_original": "trois cent (300) milliards FCFA",
     "use_of_proceeds": "financer les besoins de trésorerie prévus dans la Loi de Finances 2025 et soutenir les "
                        "projets stratégiques de l'Agenda national de transformation",
     "use_of_proceeds_categories": ["budget_financing"],
     "sources": [
         src("p11", "n02", 11, "primary_regulatory", BASE + ["amount", "currency", "unit", "amount_original",
             "use_of_proceeds", "use_of_proceeds_categories"], "un montant global de trois cent (300) milliards FCFA"),
         src("p15", "n02", 15, "primary_regulatory", []),
         src("p52", "n02", 52, "primary_regulatory", []),
     ],
     "participants": [
         *arranger_and_lead("CGF Bourse", "p15", 15, "CGF Bourse est arrangeur et chef de file du placement de l'opération"),
         part("co_arranger", "Société Générale Sénégal", "p52", 52,
              "PRÉSENTATION DU CO-ARRANGEUR Banque de référence au Sénégal, Société Générale Sénégal",
              institution="SOCIETE GENERALE SENEGAL"),
         part("co_lead_manager", "Société Générale Capital Securities West Africa", "p52", 52,
              "PRÉSENTATION DU CO-CHEF DE FILE Société Générale Capital Securities West Africa"),
     ]},
    {"key": "D07_TPTG_2025", "case": "A7",
     "title": "TPTG 6,45 % 2025-2030 & 6,60 % 2025-2032 (EE/25-05, EE/25-06)", "deal_type": "sovereign_bond_ape",
     "country_code": "TG", "sector": "public_finance",
     "use_of_proceeds": "le financement de certains investissements prévus au budget de l'Etat au titre de l'année 2025",
     "use_of_proceeds_categories": ["budget_financing"],
     "notes": "Corps du texte en police non décodable : rôles lus sur les logos de couverture (p.1) et sur "
              "l'image des pages 12, 15 et 20 (audits/ape_amf/roles_raw/N03_*.png). Revue humaine requise.",
     "sources": [
         src("p1", "n03", 1, "primary_regulatory", BASE),
         src("p12", "n03", 12, "primary_regulatory", ["use_of_proceeds", "use_of_proceeds_categories"]),
         src("p15", "n03", 15, "primary_regulatory", []),
     ],
     "participants": [
         part("arranger", "SGI Togo", "p1", 1, method="visual_logo"),
         part("lead_manager", "SGI Togo", "p1", 1, method="visual_logo"),
         *[part("co_lead_manager", n, "p1", 1, method="visual_logo") for n in (
             "AGI", "SGI Bénin", "SGI Niger", "SA2IF", "Coris Bourse", "Oragroup Securities",
             "BIIC Financial Services", "United Capital for Africa")],
         part("guarantor", "État du Togo", "p15", 15, "garantie souveraine de l'Etat du Togo", method="visual_scan"),
     ]},
    {"key": "D09_TPBF_DIASPORA_2026", "case": "A9",
     "title": "TPBF Diaspora Bonds 6,75 % 2026-2031 & 6,85 % 2026-2033 (EE/26-09, EE/26-10)",
     "deal_type": "sovereign_bond_ape", "country_code": "BF", "sector": "public_finance",
     "project_name": "Centrale hydroélectrique de Bagré-Aval",
     "use_of_proceeds_categories": ["infrastructure_project"],
     "guarantees": "garantie souveraine de l'État du Burkina Faso",
     "sources": [
         src("p14", "n11", 14, "primary_regulatory", BASE + ["project_name", "use_of_proceeds_categories"],
             "projet de construction de la centrale hydroélectrique de Bagré-Aval"),
         src("p8", "n11", 8, "primary_regulatory", []),
         src("p19", "n11", 19, "primary_regulatory", ["guarantees"],
             "bénéficient de la garantie souveraine de l'État du Burkina Faso"),
     ],
     "participants": [
         *[part("co_arranger", n, "p14", 14, "aux co-arrangeurs Vista Bank, la Société Burkinabè d'Intermédiation "
                "Financière (SBIF)") for n in ("Vista Bank", "SBIF")],
         part("co_arranger", "SGI Oragroup Securities", "p14", 14,
              "(SBIF) et la SGI Oragroup Securities"),
         part("lead_manager", "SBIF", "p8", 8, "rédigée par la SBIF, Chef de file"),
         part("guarantor", "État du Burkina Faso", "p19", 19, "garantie souveraine de l'État du Burkina Faso"),
     ]},
    {"key": "D13_PAD_2020", "case": "B13 / P2",
     "title": "PAD 6,60 % 2020-2027 (EOP/20-02)", "deal_type": "corporate_bond_ape", "country_code": "SN",
     "sector": "infrastructure_public", "project_name": "Infrastructures terrestres du Port de Ndayane",
     "amount": "60000000000", "currency": "XOF", "unit": "units", "amount_original": "60 milliards de FCFA",
     "use_of_proceeds": "serviront au financement des infrastructures terrestres du port de Ndayane",
     "use_of_proceeds_categories": ["infrastructure_project"], "filing_agent_raw": "INVICTUS CAPITAL FINANCE",
     "sources": [
         src("p49", "n06", 49, "primary_regulatory", BASE + ["amount", "currency", "unit", "amount_original"],
             "par appel public à l'Epargne de 60 milliards de FCFA"),
         src("p52", "n06", 52, "primary_regulatory", ["project_name", "use_of_proceeds", "use_of_proceeds_categories"],
             "serviront au financement des infrastructures terrestres du port de Ndayane"),
         src("p55", "n06", 55, "primary_regulatory", []),
         src("amf", "amf_api", 1, "regulator_index", ["filing_agent_raw"],
             "opération 359 (EOP/20-02) — acteurLib : INVICTUS CAPITAL FINANCE"),
         src("fa", "fa_pad", 1, "press_reported", [], "la SGI Invictus Capital & Finance, en tant qu'arrangeur "
             "et chef de file du syndicat de placement", publisher="Financial Afrik",
             url=FA + "/2020/10/01/le-port-autonome-de-dakar-lance-une-emission-de-60-milliards-de-fcfa-pour-decongestionner-son-trafic/",
             published_at="2020-10-01"),
     ],
     "participants": arranger_and_lead("Invictus Capital & Finance", "p55", 55,
                                       "la SGI Invictus Capital & Finance est arrangeur et chef de file du placement"),
     },
    {"key": "D14_PETRO_IVOIRE_2022", "case": "B14",
     "title": "PETRO IVOIRE 6,80 % 2022-2029 (EP/22-03)", "deal_type": "corporate_bond_ape", "country_code": "CI",
     "sector": "energy", "amount": "30000000000", "currency": "XOF", "unit": "units",
     "amount_original": "30 milliards de F CFA",
     "use_of_proceeds": "Financement des projets d'investissement de PISA et Refinancement d'une partie de la dette existante",
     "use_of_proceeds_categories": ["infrastructure_project", "refinancing"],
     "sources": [
         src("p2", "n07", 2, "primary_regulatory", BASE + ["amount", "currency", "unit", "amount_original"],
             "Montant de l'émission : 30 milliards de F CFA"),
         src("p3", "n07", 3, "primary_regulatory", []),
         src("p14", "n07", 14, "primary_regulatory", ["use_of_proceeds", "use_of_proceeds_categories"],
             "Financement des projets d'investissement de PISA et Refinancement d'une partie de la dette existante"),
         src("p16", "n07", 16, "primary_regulatory", []),
     ],
     "participants": [
         *arranger_and_lead("Société Générale Capital Securities West Africa", "p3", 3,
                            "arrangeur principal et chef de file du syndicat de placement"),
         *[part("co_lead_manager", n, "p16", 16, "co-chefs de file CGF Bourse et UCA")
           for n in ("CGF Bourse", "United Capital for Africa (UCA)")],
     ]},
    {"key": "D16_SAFCA_AK_2026", "case": "B16",
     "title": "Augmentation de capital Alios Finance CI / SAFCA (OA/26-02)", "deal_type": "capital_increase",
     "country_code": "CI", "sector": "financial_services",
     "use_of_proceeds": "renforcer la structure financière d'Alios Finance CI",
     "use_of_proceeds_categories": ["capital_adequacy"],
     "sources": [
         src("p13", "n08", 13, "primary_regulatory", BASE, "Arrangeur et chef de file GEK CAPITAL"),
         src("p54", "n08", 54, "primary_regulatory", ["use_of_proceeds", "use_of_proceeds_categories"],
             "vise à renforcer la structure financière d'Alios Finance CI"),
     ],
     "participants": arranger_and_lead("GEK CAPITAL", "p13", 13, "Arrangeur et chef de file GEK CAPITAL")},
    {"key": "D17_BIIC_OPV_2024", "case": "B17",
     "title": "OPV BIIC — cession par l'État du Bénin (OA/24-02)", "deal_type": "share_sale_public",
     "country_code": "BJ", "sector": "financial_services",
     "use_of_proceeds": "Mobiliser de la ressource sans endettement pour l'État",
     "use_of_proceeds_categories": ["privatisation"],
     "sources": [
         src("p9", "n04", 9, "primary_regulatory", BASE,
             "ACTIONS DETENUES PAR L'ETAT DU BENIN DANS LE CAPITAL DE LA BIIC"),
         src("p14", "n04", 14, "primary_regulatory", []),
         src("p47", "n04", 47, "primary_regulatory", ["use_of_proceeds", "use_of_proceeds_categories"],
             "Mobiliser de la ressource sans endettement pour l'État"),
     ],
     "participants": [
         *arranger_and_lead("EDC Investment Corporation (EIC)", "p14", 14,
                            "Arrangeur et chef de file EDC Investment Corporation (EIC)"),
         part("selling_shareholder", "État du Bénin", "p9", 9,
              "ACTIONS DETENUES PAR L'ETAT DU BENIN DANS LE CAPITAL DE LA BIIC"),
     ]},
    {"key": "D18_CRRH_2022", "case": "B18",
     "title": "CRRH-UEMOA 6,10 % 2022-2037 — 9e emprunt (EOP/22-02)", "deal_type": "corporate_bond_ape",
     "sector": "financial_services",
     "use_of_proceeds": "refinancement de prêts au logement en faveur des banques de l'UEMOA qui en sont actionnaires",
     "use_of_proceeds_categories": ["housing_refinancing"],
     "notes": "« Dix (10) banques actionnaires » bénéficiaires, non nommées : aucune participation créée.",
     "sources": [
         src("p7", "n09", 7, "primary_regulatory", ["title", "deal_type", "sector"]),
         src("p14", "n09", 14, "primary_regulatory", ["use_of_proceeds", "use_of_proceeds_categories"],
             "Dix (10) banques actionnaires"),
         src("p19", "n09", 19, "primary_regulatory", []),
     ],
     "participants": [
         *arranger_and_lead("Société Générale Capital Securities West Africa", "p7", 7,
                            "l'arrangeur et chef de file du syndicat de placement"),
         part("co_lead_manager", "Atlantique Finance", "p19", 19, "ATLANTIQUE FINANCE (CO-CHEF DE FILE)"),
     ]},
    {"key": "D20_BAOBAB_SLB_2026", "case": "C20 (presse seule)",
     "title": "Baobab CI Sustainability-Linked Bond 6,80 % 2026-2031 (EOP/26-06)", "deal_type": "corporate_bond_ape",
     "country_code": "CI", "sector": "financial_services", "amount": "20000000000", "currency": "XOF",
     "unit": "units", "amount_original": "20 milliards FCFA",
     "use_of_proceeds": "Les ressources levées financeront les micro, petites et moyennes entreprises dirigées par des femmes",
     "use_of_proceeds_categories": ["sme_financing", "social"],
     "sources": [src("eco", "eco_baobab", 1, "press_reported", BASE + ["amount", "currency", "unit", "amount_original",
                     "use_of_proceeds", "use_of_proceeds_categories"], "Montant : 20 milliards FCFA",
                     publisher="Agence Ecofin", published_at="2026-09-14",
                     url="https://www.agenceecofin.com/actualites-finance/1409-141527-baobab-cote-d-ivoire-lance-le-premier-sustainability-linked-bond-d-une-imf-dans-l-umoa")],
     "participants": [
         *arranger_and_lead("CGF Bourse", "eco", 1, "Chef de file et Arrangeur : CGF Bourse"),
         part("anchor_investor", "IFC", "eco", 1, "Investisseur d'ancrage : IFC"),
     ]},
    {"key": "D21_AFINHAB_SOCIAL_2026", "case": "C21 (presse seule)",
     "title": "AFINHAB Social Bond 2026 (EOP/26-01)", "deal_type": "corporate_bond_ape", "sector": "financial_services",
     "amount": "40000000000", "currency": "XOF", "unit": "units", "amount_original": "40 milliards FCFA",
     "use_of_proceeds_categories": ["housing_refinancing", "social"],
     "sources": [src("eco", "eco_afinhab", 1, "press_reported", ["title", "deal_type", "sector", "amount", "currency",
                     "unit", "amount_original", "use_of_proceeds_categories"], "Social Bond de 40 milliards FCFA",
                     publisher="Agence Ecofin", published_at="2026-07-28",
                     url="https://www.agenceecofin.com/actualites-finance/2807-140577-afinhab-cloture-son-emission-de-social-bond-de-40-milliards-fcfa-et-franchit-le-cap-des-100-milliards-fcfa-d-obligations-sociales")],
     "participants": [
         *arranger_and_lead("SGCS", "eco", 1, "Arrangeurs et Chefs de File : SGCS et FGI"),
         *arranger_and_lead("FGI", "eco", 1, "Arrangeurs et Chefs de File : SGCS et FGI"),
         part("anchor_investor", "Société Générale Côte d'Ivoire", "eco", 1,
              "Investisseur de référence : Société Générale Côte d'Ivoire", institution="SOCIETE GENERALE COTE D'IVOIRE"),
     ]},
    {"key": "D23_EMERGENCE_PLAZA_2021", "case": "C23 (presse seule)",
     "title": "Emergence Plaza S.A. 7,50 % 2021-2029 (Green Bond)", "deal_type": "corporate_bond_private",
     "country_code": "CI", "sector": "real_estate", "amount": "10000000000", "currency": "XOF", "unit": "units",
     "amount_original": "10 milliards FCFA",
     "use_of_proceeds": "l'emprunt servira à refinancer à hauteur de 8,21 milliards FCFA le prêt senior conclu avec "
                        "NSIA Banque Côte d'Ivoire",
     "use_of_proceeds_categories": ["refinancing", "green"],
     "sources": [src("sika", "sika_emergence", 1, "press_reported", BASE + ["amount", "currency", "unit",
                     "amount_original", "use_of_proceeds", "use_of_proceeds_categories"],
                     "un \" Green Bond \" de 10 milliards FCFA, arrangé par la SGI HUDSON & Cie",
                     publisher="Sika Finance", published_at="2021-07-06",
                     url="https://www.sikafinance.com/marches/cote-divoire-emergence-plaza-prepare-un-green-bond-de-10-milliards-fcfa_29107")],
     "participants": [
         part("arranger", "SGI HUDSON & Cie", "sika", 1, "arrangé par la SGI HUDSON & Cie"),
         part("refinanced_lender", "NSIA Banque Côte d'Ivoire", "sika", 1,
              "le prêt senior conclu avec NSIA Banque Côte d'Ivoire", institution="NSIA BANQUE COTE D'IVOIRE"),
     ]},
    {"key": "D25_CI_RACHAT_20250109", "case": "D25 (gestion de la dette, sans banque)",
     "title": "Rachat de titres publics — Côte d'Ivoire, 09/01/2025 (8 lignes RA-)", "deal_type": "debt_buyback",
     "country_code": "CI", "sector": "public_finance", "amount": "80507.1", "currency": "XOF", "unit": "millions",
     "amount_original": "80 507,100 millions de FCFA", "auction_date": "2025-01-09", "value_date": "2025-01-10",
     "sources": [src("p2", "cr_ci_ec_20250109", 2, "primary_market", BASE + ["amount", "currency", "unit",
                     "amount_original", "auction_date", "value_date"],
                     "Soumissions retenues : 80 507,100 millions de FCFA")],
     "participants": [part("issuer", "ETAT DE CÔTE D'IVOIRE", "p2", 2, "Emetteur : ETAT DE CÔTE D'IVOIRE")]},
]

LINKS = [
    {"from_name": "BNI FINANCES SA", "link_level": "documented_bank", "relation": "subsidiary",
     "to_institution_name": "BANQUE NATIONALE D'INVESTISSEMENT", "source_url": "https://www.bni.ci/groupe-bni/bni-finances",
     "excerpt": "BNI FINANCES, filiale de la Banque Nationale d'Investissement de Côte d'Ivoire (BNI)", "observed_at": OBS},
    {"from_name": "BICI BOURSE", "link_level": "documented_bank", "relation": "subsidiary", "pct": 70,
     "to_institution_name": "BANQUE INTERNATIONALE POUR LE COMMERCE ET L'INDUSTRIE DE LA COTE D'IVOIRE",
     "source_url": "https://www.bicibourse.ci/nous-connaitre/bici-bourse/",
     "excerpt": "Son capital se reparti entre BICI de Côte d'Ivoire (70,0%), BICI Sénégal (20%), SUNU ASSURANCE-VIE (5%), "
                "AXA ASSURANCES COTE D'IVOIRE (5%)", "observed_at": OBS},
    {"from_name": "SOCIÉTÉ GÉNÉRALE CAPITAL SECURITIES WEST AFRICA", "link_level": "documented_group_only",
     "relation": "subsidiary", "group_label": "Groupe Société Générale",
     "source_url": "https://www.fgi-bourse.com/wp-content/uploads/2025/06/Note-dinformation_Ape-Tresor-Public-SN.pdf",
     "excerpt": "Société Générale Capital Securities West Africa est la filiale du groupe Société Générale (note SN 06/2025, p.52)",
     "observed_at": OBS},
    {"from_name": "CORIS BOURSE", "link_level": "documented_group_only", "relation": "subsidiary",
     "group_label": "Groupe Coris", "source_url": "https://coris-bourse.com/en/coris-bourse/presentation",
     "excerpt": "Filiale du groupe Coris, Coris Bourse…", "observed_at": OBS},
    {"from_name": "ATLANTIQUE FINANCE", "link_level": "documented_group_only", "relation": "subsidiary",
     "group_label": "Groupe Banque Centrale Populaire (BCP) du Maroc",
     "source_url": "https://www.atlantiquefinance.net/presentation/",
     "excerpt": "filiale du Groupe Banque Centrale Populaire (BCP) du Maroc", "observed_at": OBS},
]

if __name__ == "__main__":
    out = Path(__file__).with_name("pilot_manifest.json")
    out.write_text(json.dumps({"sources": SOURCES, "documents": DOCUMENTS, "deals": DEALS,
                               "institution_links": LINKS}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{out.name}: {len(DEALS)} deals, {len(DOCUMENTS)} documents, {len(LINKS)} links")
