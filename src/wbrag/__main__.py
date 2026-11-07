"""CLI: python -m wbrag <command> --agency fmwd [--limit N]"""
import argparse
import json
import shutil
import requests
from . import config, crawl, export, verify, state


def preflight(agency):
    c = config.AGENCIES[agency]
    free = shutil.disk_usage(config.ROOT).free / 1e9
    print(f"free disk: {free:.1f} GB (need 20)")
    for host in c["hosts"]:
        try:
            r = requests.get(f"https://{host}/", timeout=15, headers={"User-Agent": config.USER_AGENT})
            print(f"{host}: HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"{host}: BLOCKED/UNREACHABLE {e}")


def main():
    ap = argparse.ArgumentParser(prog="wbrag")
    ap.add_argument("command", choices=["preflight", "discover", "smoke", "enumerate", "download", "verify", "export"])
    ap.add_argument("--agency", required=True, choices=list(config.AGENCIES))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--refresh", action="store_true", help="download: revalidate ok rows via HEAD, add versions")
    ap.add_argument("--no-head", action="store_true", help="enumerate: skip HEAD size estimates")
    a = ap.parse_args()
    if a.command == "preflight":
        preflight(a.agency)
    elif a.command == "discover":
        print(f"see sources/{a.agency}.yaml (discovery is recorded by hand from fetched pages)")
    elif a.command == "enumerate":
        print("new pending rows:", crawl.enumerate_agency(a.agency, a.limit, heads=not a.no_head))
    elif a.command == "smoke":
        res, rows = crawl.smoke(a.agency)
        print(res)
        for r in rows:
            print(json.dumps(r))
    elif a.command == "download":
        print(crawl.download_agency(a.agency, a.limit, a.refresh))
    elif a.command == "export":
        print(export.export(a.agency))
    elif a.command == "verify":
        before = state.connect().execute("SELECT COUNT(*) FROM docs WHERE agency=? AND status='ok'", (a.agency,)).fetchone()[0]
        res = crawl.download_agency(a.agency)
        fetched = sum(v for k, v in res.items() if k in ("ok", "invalid", "duplicate"))
        idem = f"re-ran download: {fetched} new files fetched ({res or 'nothing pending'}); ok rows before: {before}"
        print(verify.report(a.agency, idem))
        print(export.export(a.agency))


if __name__ == "__main__":
    main()
