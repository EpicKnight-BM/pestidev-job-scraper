#!/usr/bin/env python3
"""Deterministic change-check for the `due` sites — no model involved (added 2026-11-21).

Why: on 2026-11-20 a run spent ~30 of its 40 minutes on 67 `site-change-check` dispatches, 56 of
which came back "unchanged"; new-company discovery got the leftover minutes. Re-fetching a listing
and diffing its links against `storedListingUrls` is mechanical work, so this script does it first
and only hands the LLM the sites it cannot decide.

Usage (right after prep-run.py, from the repo root):
  timeout 600 python3 scripts/quick-check.py [--run-dir /tmp/pestidev-run]

For each `due` entry in plan.json it fetches the dispatch file's `url` with curl (same egress as the
agents), extracts every link, keeps the ones that look like the stored posting URLs (same host +
same directory prefix), and compares on a normalized key (no fragment, no tracking query, rotated
hash tail stripped). Outcomes:

  confident, nothing new   -> writes the result file itself, exactly in site-change-check's format
                              (`changed` true only when postings disappeared). No agent needed.
  confident, new URLs      -> writes the same result file with `changed: true` and `newUrls`; the
                              orchestrator dispatches `site-processor` with `evaluateOnly` = those
                              URLs directly, skipping `site-change-check`.
  not confident            -> writes nothing; the site stays in plan.json `needsAgentCheck` for the
                              usual `site-change-check` dispatch (fetch failed, JS-rendered,
                              paginated, too few stored URLs to learn a pattern, low overlap).

It rewrites plan.json with `quickChecked` (slug -> {changed, newUrls}) and `needsAgentCheck`
(list of due slugs still needing the agent). Never touches anything outside the run dir.
"""

import argparse
import concurrent.futures as cf
import os
import posixpath
import re
import subprocess
import sys
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pestidev_lib as lib  # noqa: E402

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TRACKING = re.compile(r"^(utm_|gclid|fbclid|ref$|source$|src$|domain$|lang$|locale$|page$|_ga)", re.I)
LINK_RE = re.compile(r"""(?:href|src|data-href|data-url)\s*=\s*["']([^"'#][^"']*)["']|<loc>\s*([^<\s]+)\s*</loc>|"(https?://[^"\s]+)"|'(https?://[^'\s]+)'""", re.I)
HASH_TAIL = re.compile(r"-([a-z0-9]{3,8})$")
MIN_STORED = 3          # fewer stored URLs than this: no reliable pattern -> agent
MIN_OVERLAP = 0.6       # share of stored URLs that must still be found for "confident"


def strip_tail(seg):
    for _ in range(2):
        m = HASH_TAIL.search(seg)
        if m and re.search(r"\d", m.group(1)):
            seg = seg[: m.start()]
        else:
            break
    return seg


def norm_key(url, keep_query):
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", p.path or "")
    if path:
        head, _, last = path.rpartition("/")
        path = head + "/" + strip_tail(last.lower())
    q = ""
    if keep_query:
        q = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if not TRACKING.match(k)))
    return host + path + ("?" + q if q else "")


def dir_prefix(urls):
    """host + the longest common directory of the stored URLs' paths (None if not one host)."""
    parsed = [urlparse(u) for u in urls]
    hosts = {(p.hostname or "").lower().removeprefix("www.") for p in parsed}
    if len(hosts) != 1:
        return None, None
    dirs = [posixpath.dirname(re.sub(r"/+$", "", p.path or "/")) for p in parsed]
    common = posixpath.commonpath(dirs) if dirs else "/"
    return hosts.pop(), common


def fetch(url):
    try:
        out = subprocess.run(
            ["curl", "-sS", "-L", "--compressed", "--connect-timeout", "10", "--max-time", "40",
             "-A", UA, "-w", "\n__HTTP__%{http_code}", url],
            capture_output=True, timeout=55)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    body = out.stdout.decode("utf-8", "replace")
    m = re.search(r"\n__HTTP__(\d{3})$", body)
    code = int(m.group(1)) if m else 0
    body = body[: m.start()] if m else body
    if out.returncode != 0 or code >= 400 or code == 0:
        return None, "http %s / curl %s" % (code, out.returncode)
    return body, "http %s" % code


def check_site(entry, run_dir):
    slug = entry["slug"]
    d = lib.read_json(entry["dispatchFile"])
    url, stored = d.get("url") or "", list(d.get("storedListingUrls") or [])
    if len(stored) < MIN_STORED or not url:
        return slug, None, "too few stored URLs (%d) to learn a pattern" % len(stored)
    host, prefix = dir_prefix(stored)
    if not host or prefix in ("", "/"):
        return slug, None, "stored URLs share no host/directory pattern"
    paths = [urlparse(u).path.rstrip("/") for u in stored]
    keep_query = len(set(paths)) < len(paths)      # postings differ only in the query string
    body, how = fetch(url)
    if body is None:
        return slug, None, "fetch failed (%s)" % how
    found = {}
    for m in LINK_RE.finditer(body):
        raw = next(g for g in m.groups() if g)
        raw = raw.replace("&amp;", "&").replace("\\/", "/")
        absu = urljoin(url, raw)
        p = urlparse(absu)
        h = (p.hostname or "").lower().removeprefix("www.")
        if h != host or not (p.path or "").startswith(prefix.rstrip("/") + "/"):
            continue
        found.setdefault(norm_key(absu, keep_query), absu.split("#", 1)[0])
    stored_by_key = {norm_key(u, keep_query): u for u in stored}
    if not found:
        return slug, None, "no posting-like links in the fetched page (%s) — JS-rendered or moved?" % how
    still = [k for k in stored_by_key if k in found]
    overlap = len(still) / len(stored_by_key)
    if overlap < MIN_OVERLAP:
        return slug, None, "only %d/%d stored URLs still visible — pagination/rotation, let the agent judge" % (
            len(still), len(stored_by_key))
    new_keys = [k for k in found if k not in stored_by_key]
    if len(new_keys) > max(10, len(stored_by_key)):
        return slug, None, "%d new links vs %d stored — pattern too broad, let the agent judge" % (
            len(new_keys), len(stored_by_key))
    current = [stored_by_key[k] for k in still] + [found[k] for k in new_keys]
    removed = len(stored_by_key) - len(still)
    result = {
        "source": "site-change-check",
        "slug": slug,
        "url": url,
        "company": d.get("company") or slug,
        "previousStatus": d.get("previousStatus") or "",
        "status": "ok",
        "listingUrls": current,
        "newUrls": [found[k] for k in new_keys],
        "changed": bool(new_keys) or removed > 0,
        "suspectExtraction": False,
        "postingsFound": len(current),
        "note": "quick-check.py (%s): %d still listed, %d new, %d gone" % (how, len(still), len(new_keys), removed),
    }
    lib.write_json(d["resultFile"], result)
    return slug, result, result["note"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default=lib.RUN_DIR_DEFAULT)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    plan_path = os.path.join(a.run_dir, "plan.json")
    plan = lib.read_json(plan_path)
    quick, needs = {}, []
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(check_site, e, a.run_dir) for e in plan.get("due", [])]
        for f in cf.as_completed(futs):
            try:
                slug, res, note = f.result()
            except Exception as exc:  # one broken site must not stop the rest
                print("  ERR  %s" % exc)
                continue
            if res is None:
                needs.append(slug)
                print("  AGENT %-28s %s" % (slug, note))
            else:
                quick[slug] = {"changed": res["changed"], "newUrls": res["newUrls"]}
                print("  %-5s %-28s %s" % ("NEW" if res["newUrls"] else "same", slug, note))
    due_slugs = [e["slug"] for e in plan.get("due", [])]
    plan["quickChecked"] = quick
    plan["needsAgentCheck"] = [s for s in due_slugs if s in set(needs) or (s not in quick)]
    lib.write_json(plan_path, plan)
    with_new = sum(1 for v in quick.values() if v["newUrls"])
    print("quick-check: %d due -> %d decided here (%d with new URLs -> site-processor), %d need site-change-check"
          % (len(due_slugs), len(quick), with_new, len(plan["needsAgentCheck"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
