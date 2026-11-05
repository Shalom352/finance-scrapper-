"""
Syndication tracker reader (migration 0022) — pure functions, no database. Synthetic workbook only.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.mandates.syndication_xlsx import (
    WorkbookError,
    as_date,
    commitment,
    read_workbook,
    split_label,
    stage_of,
)
from app.services.syndication import merge_fields
from tests.fixtures_syndication import DEAL_CI, DEAL_GA, DEAL_SN, DEAL_TG, build_workbook


def code_of(parsed, label: str) -> str:
    return next(c for c, m in parsed.mandates.items() if m.title == label)


def test_mandates_events_and_merged_deal_cells():
    p = read_workbook(build_workbook())
    assert p.file_updated_on == "2026-09-08" and len(p.mandates) == 5
    sn = parsed_mandate = p.mandates[code_of(p, DEAL_SN)]
    assert (parsed_mandate.country_code, parsed_mandate.country_code_raw, parsed_mandate.status) == ("SN", "SEN",
                                                                                                    "closed_won")
    assert sn.client_name == "Etat du Sénégal"
    # The second lender row has an empty (merged) deal cell: it belongs to the deal above.
    sn_events = [e for e in p.events if e.mandate_code == sn.code]
    assert [e.counterparty_name for e in sn_events] == ["BOAD", "Banque X"]
    ga = p.mandates[code_of(p, DEAL_GA)]
    assert (ga.country_code, ga.country_code_raw) == (None, "GAB")  # outside UMOA: kept raw, never mapped
    assert p.mandates[code_of(p, DEAL_TG)].status == "active"
    assert set(p.ignored_sheets) == {"Cartographie des prêteurs", "Cartographie des investisseurs"}


def test_amounts_only_when_one_explicit_amount():
    p = read_workbook(build_workbook())
    by_name = {e.counterparty_name: e for e in p.events}
    assert (by_name["Banque X"].amount, by_name["Banque X"].currency) == ("27800000000", "XOF")
    assert by_name["BOAD"].amount is None and by_name["BOAD"].amount_text == "Jusqu'à 300 M€"  # ceiling
    assert by_name["ISDB"].amount is None and by_name["ISDB"].amount_text == "300–500 M€"  # range
    assert by_name["BGFIBank Gabon"].amount is None  # FCFA in Gabon is XAF: never assumed
    assert by_name["BOAD"].rate_text == "4,25 % p.a. + EURIBOR applicable"  # terms kept as written
    assert commitment("500 M€", None) == ("500000000", "EUR")
    assert commitment("À confirmer", "SN") == (None, None)
    assert commitment("53,709 Md FCFA\n- Tranche 1 : 20,957 Md", "CI") == (None, None)


def test_stage_rules():
    p = read_workbook(build_workbook())
    by_name = {e.counterparty_name: e for e in p.events}
    assert by_name["ISDB"].stage == "declined" and by_name["ISDB"].appetite is False
    assert by_name["BOAD"].stage == "interested" and by_name["BOAD"].lender_type == "dfi"
    assert by_name["Banque X"].lender_type == "bank"
    assert stage_of(False, "En cours d'étude", False) == "approached"  # the dossier wording prevails
    assert stage_of(True, "Engagement préliminaire", False) == "interested"
    assert stage_of(None, None, False) == "approached"


def test_detail_sheet_needs_an_explicit_mapping():
    p = read_workbook(build_workbook())
    assert p.detail_sheets == {"Projet Beta (1)": None}
    assert not any(e.sheet == "Projet Beta (1)" for e in p.events)
    mapped = read_workbook(build_workbook(), sheet_mapping={"Projet Beta (1)": DEAL_TG})
    tg = code_of(mapped, DEAL_TG)
    assert mapped.detail_sheets == {"Projet Beta (1)": tg}
    events = [e for e in mapped.events if e.sheet == "Projet Beta (1)"]
    assert [(e.counterparty_name, e.stage, e.dossier_status_raw) for e in events] == [
        ("BANQUE TOGO", "interested", "Engagement préliminaire"), ("Banque Y Togo", "approached", "En cours d'étude")]
    assert events[0].nda_sent_on == "2023-07-11" and events[0].nda_received_on == "2023-07-12"
    assert events[0].amount is None and events[0].amount_text.startswith("1 (Engagements")  # GXAF vs XOF: text only
    assert events[1].notes and "NDA Global" in events[1].notes
    assert any("without an institution name" in w for w in mapped.warnings)


def test_contacts_paired_merged_and_dataroom():
    p = read_workbook(build_workbook())
    by_email = {c.email: c for c in p.contacts if c.email}
    awa = by_email["awa@boad.example"]  # SUIVI + CRM (upper-case e-mail) = one person
    assert (awa.full_name, awa.job_title, awa.last_interaction_on) == ("Awa FICTIVE", "Directrice", "2026-09-01")
    assert by_email["fred@boad.example"].dataroom_access is True
    assert by_email["hugo@tomasteed.example"].institution_name == "TOMASTEED"
    assert by_email["carl@bankx.example"].phone is None  # "À confirmer" is not a phone number
    assert by_email["gina@isdb.example"].institution_name == "ISDB"


def test_columns_are_found_by_label_and_missing_sheet_is_an_error():
    shifted = read_workbook(build_workbook(shift_columns=True))
    assert len(shifted.events) == len(read_workbook(build_workbook()).events)
    with pytest.raises(WorkbookError, match="SYNDICATION DES DEALS TOMASTEED"):
        read_workbook(build_workbook(with_suivi=False))
    with pytest.raises(WorkbookError, match="not a readable"):
        read_workbook(b"not an excel file")


def test_helpers():
    assert split_label(DEAL_CI) == ("CIV", "Société Alpha", DEAL_CI)
    assert split_label("Deal sans pays") == (None, "Deal sans pays", "Deal sans pays")
    assert as_date(45147) == datetime(2023, 8, 9).date() and as_date("N/A") is None


def test_three_way_merge():
    snap = {"title": "A", "status": "active"}
    # Unchanged in the platform -> the Excel value is taken.
    assert merge_fields({"title": "A", "status": "active"}, snap, {"title": "B", "status": "active"},
                        ("title", "status")) == ({"title": "B"}, [])
    # Edited in the platform, unchanged in the Excel -> the platform value stays.
    assert merge_fields({"title": "P", "status": "active"}, snap, {"title": "A", "status": "active"},
                        ("title", "status")) == ({}, [])
    # Changed on both sides -> conflict, nothing taken.
    updates, conflicts = merge_fields({"title": "P"}, snap, {"title": "B"}, ("title",))
    assert updates == {} and conflicts == [{"field": "title", "platform": "P", "excel_before": "A", "excel_now": "B"}]


def test_second_table_below_the_main_one_is_never_read_with_its_columns():
    """Audit 22/10/2026: the LOI table under SUIVI produced fake counterparties ("Banques / Institution",
    "LOI reçus") and lost the amounts, read with the main table's columns."""
    p = read_workbook(build_workbook(audit_cases=True))
    names = {e.counterparty_name for e in p.events}
    assert not {"Banques / Institution", "LOI reçus", "LOI à recevoir", "BANQUE TOGO", "Banque Z"} & names
    assert p.detail_sheets["SUIVI SYNDICATION!30"] is None  # offered for mapping, imported only once mapped

    tg = code_of(p, DEAL_TG)
    p = read_workbook(build_workbook(audit_cases=True), sheet_mapping={"SUIVI SYNDICATION!30": tg})
    block = {e.counterparty_name: e for e in p.events if e.row >= 30}
    assert set(block) == {"BANQUE TOGO", "Banque Z"}
    received = block["BANQUE TOGO"]
    assert (received.mandate_code, received.stage, received.appetite) == (tg, "interested", True)
    assert (received.amount, received.currency) == ("5000000000", "XOF")  # header: XOF millions, UMOA country
    assert (received.rate_text, received.maturity_text, received.dossier_status_raw) == ("8 %", "10 ans", "LOI reçus")
    pending = block["Banque Z"]
    assert (pending.stage, pending.amount, pending.dossier_status_raw) == ("approached", None, "LOI à recevoir")


def test_invalid_email_is_never_imported_and_is_reported():
    p = read_workbook(build_workbook(audit_cases=True))
    ivy = next(c for c in p.contacts if c.full_name == "Ivy FICTIVE")
    assert ivy.email is None and "ivy@tomasteed.ccom" in ivy.notes
    assert any("ivy@tomasteed.ccom" in w for w in p.warnings)


def test_a_decompression_bomb_is_refused_before_being_read():
    """Security tests of 22/10/2026: a 422 KB .xlsx expanding to ~200 MB kept the API busy for 40 s."""
    import io
    import time
    import zipfile

    from app.mandates.syndication_xlsx import MAX_UNCOMPRESSED_BYTES

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", "<row/>" * (MAX_UNCOMPRESSED_BYTES // 6 + 10))
    started = time.time()
    with pytest.raises(WorkbookError, match="too large once decompressed"):
        read_workbook(buf.getvalue())
    assert time.time() - started < 2
