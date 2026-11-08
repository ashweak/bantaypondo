"""Registry of official public data sources.

Every record stored in BantayPondo must point back to one of these sources
AND carry its own record-level `source_url`. Nothing is accepted without a link.
"""

SOURCES = {
    "dpwh_transparency": {
        "name": "DPWH Transparency Portal",
        "publisher": "Department of Public Works and Highways",
        "url": "https://transparency.dpwh.gov.ph/",
        "covers": "All DPWH projects since 2016: cost, contractor, implementing office, progress, location, contract documents",
    },
    "sumbong_sa_pangulo": {
        "name": "Sumbong sa Pangulo - Flood Control Projects",
        "publisher": "Office of the President",
        "url": "https://sumbongsapangulo.ph/",
        "covers": "Flood control projects: location, contractor, cost, completion date",
    },
    "philgeps_open_data": {
        "name": "PhilGEPS Open Data Portal",
        "publisher": "Procurement Service - DBM",
        "url": "https://philgeps.gov.ph/CmsHomePages/open-data",
        "covers": "Bid notices and award notices (ABC, awardee, award amount, dates)",
    },
    "coa_audit_reports": {
        "name": "COA Annual Audit Reports",
        "publisher": "Commission on Audit",
        "url": "https://www.coa.gov.ph/",
        "covers": "Annual audit findings per agency (e.g., DPWH defective/delayed projects)",
    },
    "dbm_gaa": {
        "name": "General Appropriations Act (GAA)",
        "publisher": "Department of Budget and Management",
        "url": "https://www.dbm.gov.ph/",
        "covers": "Approved budget line items per agency",
    },
    "bettergov_export": {
        "name": "BetterGov.ph flood control export",
        "publisher": "BetterGov.ph (community-run portal) - NOT official; verify against DPWH portal",
        "url": "https://bettergov.ph/flood-control-projects",
        "covers": "Flood control projects exported with the site's Export Data button (same columns as the mirror)",
        "official": False,
    },
    "hf_flood_control_mirror": {
        "name": "DPWH Flood Control 2018-2025 (community mirror, CC BY-SA 4.0)",
        "publisher": "Hugging Face user chrisandrei - NOT an official source; verify against DPWH portal",
        "url": "https://huggingface.co/datasets/chrisandrei/DPWH_Flood_Control_2018-2025_Projects",
        "covers": "~10.9k flood control projects: contract ID, ABC, contract cost, contractor, dates, coordinates",
        "official": False,
    },
    "foi_dpwh": {
        "name": "FOI Portal - DPWH requests",
        "publisher": "Freedom of Information Program",
        "url": "https://foi.gov.ph/agencies/dpwh/",
        "covers": "Datasets released through FOI requests",
    },
}
