"""Automated deal collection from official / institutional sources (migration 0020).

One module of pure parsers + one collector per source; every deal is written through the Phase 13
importer (``import_deals``): needs_review, field-level provenance, audit event, duplicate candidates.
"""
