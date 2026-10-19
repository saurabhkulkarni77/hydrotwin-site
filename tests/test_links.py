"""Internal link/asset references: every relative href/src in the baked
pages must resolve to a file that exists in the repo (i.e. will exist on
GitHub Pages). External URLs, anchors, and JS template placeholders
(${...}, filled at runtime) are out of scope by construction.
"""
import re
import urllib.parse

import pytest

from conftest import STATIONS

ATTR = re.compile(r'(?:href|src)\s*=\s*"([^"]+)"')
SKIP_PREFIXES = ("http://", "https://", "//", "#", "data:", "mailto:",
                 "javascript:")

PAGES = ["index.html"] + [
    f"stations/USGS-{s}{kind}.html" for s in STATIONS for kind in ("", "-3d")
]


@pytest.mark.parametrize("page", PAGES)
def test_relative_references_resolve(repo_root, page):
    html = (repo_root / page).read_text(encoding="utf-8", errors="replace")
    base = (repo_root / page).parent
    broken = []
    for ref in ATTR.findall(html):
        if ref.startswith(SKIP_PREFIXES) or "${" in ref:
            continue
        target = ref.split("#")[0].split("?")[0]
        if not target:
            continue
        resolved = base / urllib.parse.unquote(target)
        if not resolved.exists():
            broken.append(ref)
    assert not broken, f"{page}: unresolved relative references {broken}"
