"""
UMOA Banking Intelligence — Institution financial profile (Phase 10).

Single backend source of the qualification rules for an institution page:
orchestrates EligibilityEngine (via rankings.eligibility.qualify_metric),
AnalyticsService ratios / growth, CoverageAnalyzer and the Phase 6 quality
counters. Descriptive only: missing data stays unavailable, no score is produced.
"""
