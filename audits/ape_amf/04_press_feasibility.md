# Feasibility Assessment: Press and Communiqué Sources for UMOA Deals

## 1. Financial Afrik (financialafrik.com)
*   **robots.txt & Terms of Use:** Typical media site restrictions. Direct crawling often requires compliance with rate limits or specific user-agent approval. Scraping full articles for commercial use is generally restricted by standard terms of use, but factual data extraction (amounts, dates, names) is generally acceptable under fair use.
*   **Content Structure:** Natural language articles. No structured metadata (like JSON-LD for transactions). Extraction requires NLP or LLM-based parsing.
*   **Publication Frequency:** High. They regularly cover syndicated loans and bond issuances in UMOA/CEMAC.
*   **Quality of Role Information:** Good for lead roles (Arrangeur, Chef de file) such as Impaxis Securities or Coris Bourse. The purpose of funds is frequently discussed, especially for thematic bonds (e.g., GSS Bonds).
*   **Examples:**
    *   *BIDC GSS Bond:* Mentions Impaxis Securities, Coris Bourse, and EDC Investment Corporation as part of the consortium.
    *   *Oragroup / Sonatel:* Coverage of non-sovereign issuances highlighting SGI roles.

## 2. Agence Ecofin (agenceecofin.com)
*   **robots.txt & Terms of Use:** Standard journalistic copyright. Automated scraping may be blocked or require rate-limiting.
*   **Content Structure:** Free-text articles in the finance/banking section.
*   **Publication Frequency:** Very frequent updates on West African finance.
*   **Quality of Role Information:** Consistently names the "arrangeur".
*   **Examples:**
    *   *Baobab Côte d'Ivoire (2026):* 20 billion FCFA sustainability-linked bond. Arrangeur: CGF Bourse.
    *   *NSIA Banque CI (2023):* 60 billion FCFA. Arrangeur: Africa Link Capital.
    *   *Sonatel (2020):* 100 billion FCFA. Arrangeur: Impaxis.

## 3. Sika Finance (sikafinance.com)
*   **robots.txt & Terms of Use:** Similar to above. Focused heavily on BRVM data and regional markets.
*   **Content Structure:** Articles often include detailed breakdowns of bond market operations.
*   **Publication Frequency:** Daily coverage of BRVM and UEMOA market activities.
*   **Quality of Role Information:** Excellent for bond issuances, precisely naming SGIs acting as arrangeurs and chefs de file.
*   **Examples:**
    *   *Sénégal (2025):* 300 billion FCFA. Arrangeur: Impaxis Securities.
    *   *Burkina Faso (2024):* 130 billion FCFA. Arrangeur: SA2IF.
    *   *Mali (2022):* 123.3 billion FCFA. Arrangeur: SGI-Mali.

## 4. UMOA Treasury / Ministry of Finance websites (e.g., tresor.sn)
*   **Availability:** Websites like the Senegalese Ministry of Finance publish communiqués for Appel Public à l'Épargne (APE).
*   **Content Structure:** Mostly PDFs (avis d'appel d'offres, communiqués).
*   **Alternative:** The majority of structured "notes d'information" are actually hosted centrally on UMOA-Titres (umoatitres.org) rather than individual treasury sites.

## 5. Major UMOA Bank Websites (Ecobank, BOA, Société Générale)
*   **Content Structure:** Press release sections exist but are sporadically updated compared to news outlets. Announcements are often in PDF format.
*   **Viability:** Low yield for automated scraping due to diverse site structures and low frequency of specific deal PRs on their own domains (they rely on press like Ecofin to spread the news).

---

## Proposed Confidence Classification System for Deal Data

To ensure data integrity when populating the UMOA Banking Intelligence database, we propose the following tier system:

### Tier 1: High Confidence (Official Primary Sources)
*   **Sources:** AMF-UMOA visas, Notes d'information from UMOA-Titres, Official Term Sheets.
*   **Verification:** None required. Serves as the ground truth.

### Tier 2: Medium-High Confidence (Official Secondary Sources)
*   **Sources:** Treasury communiqués (tresor.sn), Official bank press releases.
*   **Verification:** Reliable for amounts and lead roles. May omit full syndicate breakdown.

### Tier 3: Medium Confidence (Specialized Press)
*   **Sources:** Sika Finance, Financial Afrik, Agence Ecofin.
*   **Verification:** Press data is excellent for discovery and real-time alerts. However, journalists may simplify technical roles (e.g., confusing "co-arrangeur" with "chef de file"). 
*   **Rule:** Data extracted from Tier 3 must be flagged for manual review or automatically cross-referenced with Tier 1 documents before being marked as "verified" in the database.
