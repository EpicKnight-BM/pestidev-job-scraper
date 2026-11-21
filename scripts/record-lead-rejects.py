#!/usr/bin/env python3
"""Turn company-discovery's `leadsRejected` into result files, so Step 4's assembler sends them as
`rejected` records and the server stops offering the same lead again (added 2026-11-21).

Usage: timeout 30 python3 scripts/record-lead-rejects.py <discovery-json-file> [--run-dir /tmp/pestidev-run]

<discovery-json-file> is the agent's return (or its checkpoint /tmp/pestidev-discovery-candidates.json).
Each `leadsRejected` item needs `company` and `reason`; `slug` and `domain` are optional (a domain is
only written when it is a real host). Existing result files are never overwritten.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pestidev_lib as lib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("discovery")
    ap.add_argument("--run-dir", default=lib.RUN_DIR_DEFAULT)
    a = ap.parse_args()
    data = lib.read_json(a.discovery)
    items = data.get("leadsRejected") or []
    results = os.path.join(a.run_dir, "results")
    os.makedirs(results, exist_ok=True)
    n = 0
    for it in items:
        company = (it.get("company") or "").strip()
        if not company:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (it.get("slug") or company).lower()).strip("-")[:60]
        path = os.path.join(results, slug + ".json")
        if not slug or os.path.exists(path):
            continue
        domain = (it.get("domain") or "").strip().lower()
        lib.write_json(path, {
            "source": "site-processor", "slug": slug, "company": company,
            "listingUrl": ("https://" + domain) if lib.looks_like_host(domain) else "",
            "status": "reject_permanent",
            "rejectReason": "company lead: " + (it.get("reason") or "no own career page"),
            "postingsFound": 0, "itRelevant": 0, "passedLevel": 0, "listingUrls": [], "findings": [],
        })
        n += 1
    print("lead rejects written: %d" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
