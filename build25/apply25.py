#!/usr/bin/env python3
"""Apply the 25-year rebuild to every station page (dev only, idempotent).

For each stations/USGS-*.html:
  1. strip the previously baked drift panel (drift/patch_pages.py re-adds the
     fresh one later in the same workflow run),
  2. replace window.HT_DATA's start/n/series/pred with build25/payload/<site>
     (station metadata, openDay, trainLast etc. are preserved),
  3. date input min 2016-10-01 -> 2001-10-01.
Run from the repo root in the deploy-dev workflow, before patch_pages.py.
"""
import base64, gzip, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "build25" / "payload"
MODELS = ["Transformer", "GP Matérn", "GP RBF", "TFT", "LSTM",
          "ARIMA", "SARIMA", "PatchTST", "PILSTMv1", "GCN"]


def find_ht_data(html):
    """(start, end) slice of the HT_DATA JSON object (string-aware scan)."""
    i = html.find("window.HT_DATA=")
    if i == -1:
        return None
    j = html.find("{", i)
    depth, k, in_str, esc = 0, j, False, False
    while k < len(html):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j, k + 1
        k += 1
    return None


def strip_panel(html):
    i = html.find('<div id="ht-drift-panel">')
    if i == -1:
        return html
    start = html.rfind("<style>", 0, i)
    end = html.find("</script>", i)
    if start == -1 or end == -1 or "#ht-drift-panel" not in html[start:i]:
        return html
    return html[:start] + html[end + len("</script>"):]


def main():
    changed = 0
    for page in sorted((ROOT / "stations").glob("USGS-*.html")):
        site = page.stem.replace("-3d", "").replace("USGS-", "")
        pf = PAYLOAD / f"{site}.json.gz.b64"
        if pf.exists():
            blob = pf.read_text()
        else:
            # payload split into <1MB parts for the Contents API
            parts = sorted(PAYLOAD.glob(f"{site}.json.gz.b64.p*"))
            if not parts:
                print("skip (no payload):", page.name)
                continue
            blob = "".join(p.read_text() for p in parts)
        payload = json.loads(gzip.decompress(base64.b64decode(blob)))
        html = page.read_text(errors="ignore")
        html = strip_panel(html)
        span = find_ht_data(html)
        if span is None:
            print("no HT_DATA:", page.name)
            continue
        D = json.loads(html[span[0]:span[1]])
        assert D["models"] == MODELS, f"{page.name}: model list mismatch {D['models']}"
        daily = payload["daily"]
        D["start"] = daily["start"]; D["n"] = daily["n"]
        D["tmax"] = daily["tmax"]; D["tmin"] = daily["tmin"]; D["tmean"] = daily["tmean"]
        D["precip"] = daily["precip"]; D["flow"] = daily["flow"]; D["rising"] = daily["rising"]
        D["pred"] = payload["pred"]
        new_block = json.dumps(D, separators=(",", ":"), ensure_ascii=False)
        html = html[:span[0]] + new_block + html[span[1]:]
        html = html.replace('min="2016-10-01"', 'min="2001-10-01"')
        page.write_text(html)
        changed += 1
        print("25yr applied:", page.name)
    print(f"done, {changed} page(s) updated")


if __name__ == "__main__":
    main()
