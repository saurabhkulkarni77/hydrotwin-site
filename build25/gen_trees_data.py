#!/usr/bin/env python3
"""Bake NLCD tree-canopy scatter points for the 3D station pages.

Source: NLCD 2021 Tree Canopy Cover (CONUS) via the MRLC GeoServer
WMS (layer mrlc_display:nlcd_tcc_conus_2021_v2021-4). The raster is
requested as a rendered PNG with a custom SLD colour map that encodes
canopy percent as greyscale (quantity q -> grey round(q * 2.54);
quantity 255 -> pure red = nodata), then decoded in pure Python
(stdlib only: urllib + zlib), so the values round-trip to ~0.4%.

For each station the request covers exactly the page's inner ground
block (the z15 4x4-tile frame the 3D scene builds from USGS 3DEP),
160x160 px (~30 m/px, the product's native resolution). Pixels with
canopy >= 25% become candidate tree spots; acceptance probability
rises with canopy so dense forest reads dense and open woodland
sparse. Positions are baked in the page's own ground coordinates
(metres east/south of the gauge, same mx/mz frame the scene uses),
with a deterministic hash jitter so rebuilds are stable.

Output: build25/trees_data.py -> HT_TREES = {site: [[x, z, s], ...]}
(x, z in metres, s = tree scale 0.85..1.6). Consumed by
build25/patch_realism_context.py. The runtime additionally drops any
baked point that lands on water at median flow, on steep ground, or
outside the inner block, so minor raster resampling error cannot put
a tree in the river.

Run from the repo root:  python3 build25/gen_trees_data.py
Network: www.mrlc.gov GeoServer. A station whose fetch fails is
baked as an empty list (with a loud warning) rather than failing the
whole bake.
"""
import base64
import hashlib
import json
import math
import re
import struct
import sys
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

WMS = "https://www.mrlc.gov/geoserver/ows"
LAYER = "mrlc_display:nlcd_tcc_conus_2021_v2021-4"
GRID = 160            # px across the inner block (~30 m/px, native TCC)
MIN_CANOPY = 25       # percent
CAP = 1600            # max baked trees per station
TS = 256
ZI = 15
CIRC = 40075016.68557849


def sld_body() -> str:
    entries = []
    for q in range(0, 101):
        g = round(q * 2.54)
        entries.append(f'<ColorMapEntry color="#{g:02X}{g:02X}{g:02X}" quantity="{q}"/>')
    entries.append('<ColorMapEntry color="#FF0000" quantity="255"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<StyledLayerDescriptor version="1.0.0" xmlns="http://www.opengis.net/sld" '
        'xmlns:ogc="http://www.opengis.net/ogc">'
        f"<NamedLayer><Name>{LAYER}</Name><UserStyle><FeatureTypeStyle><Rule>"
        '<RasterSymbolizer><ColorMap type="ramp">'
        + "".join(entries)
        + "</ColorMap></RasterSymbolizer>"
        "</Rule></FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>"
    )


SLD = sld_body()


def decode_png(data: bytes):
    """Minimal PNG decoder (8-bit, palette/RGB/RGBA/grey), stdlib only."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    idat = b""
    plte = None
    w = h = bitd = ctype = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        dd = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bitd, ctype = struct.unpack(">IIBB", dd[:10])
        elif typ == b"IDAT":
            idat += dd
        elif typ == b"PLTE":
            plte = dd
        pos += 12 + ln
    if bitd != 8:
        raise ValueError(f"unexpected PNG bit depth {bitd}")
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    bpp = max(1, ch)
    stride = w * bpp
    out = bytearray(w * h * bpp)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line
    vals = []
    for k in range(w * h):
        if ctype == 3:
            idx = out[k]
            r, g, b = plte[idx * 3], plte[idx * 3 + 1], plte[idx * 3 + 2]
        else:
            r, g, b = out[k * ch], out[k * ch + 1], out[k * ch + 2]
        if r > 200 and r > g + 30:      # nodata red (incl. ramp blends toward it)
            vals.append(-1)
        else:
            vals.append(round(g / 2.54))
    return w, h, vals


def lon2px(lon, z):
    return (lon + 180) / 360 * TS * 2 ** z


def lat2px(lat, z):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * TS * 2 ** z


def block_frame(lat, lon):
    """Replicates the page's inner-block frame exactly (see module code)."""
    m0 = 156543.03392 * math.cos(math.radians(lat))
    mpi = m0 / 2 ** ZI
    gxi, gyi = lon2px(lon, ZI), lat2px(lat, ZI)
    ipx0 = (round(gxi / TS) - 2) * TS
    ipy0 = (round(gyi / TS) - 2) * TS
    ix0 = (ipx0 - gxi) * mpi
    iz0 = (ipy0 - gyi) * mpi
    iwm = (4 * TS) * mpi
    # EPSG:3857 bounds of the same pixel block
    total = TS * 2 ** ZI
    x0 = ipx0 / total * CIRC - CIRC / 2
    x1 = (ipx0 + 4 * TS) / total * CIRC - CIRC / 2
    y1 = CIRC / 2 - ipy0 / total * CIRC
    y0 = CIRC / 2 - (ipy0 + 4 * TS) / total * CIRC
    return (x0, y0, x1, y1), ix0, iz0, iwm


def fetch_canopy(lat, lon):
    (x0, y0, x1, y1), ix0, iz0, iwm = block_frame(lat, lon)
    params = {
        "service": "WMS", "version": "1.1.1", "request": "GetMap",
        "layers": LAYER, "bbox": f"{x0},{y0},{x1},{y1}", "srs": "EPSG:3857",
        "width": str(GRID), "height": str(GRID), "format": "image/png",
        "sld_body": SLD,
    }
    url = WMS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "hydrotwin-build/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    w, h, vals = decode_png(data)
    if (w, h) != (GRID, GRID):
        raise ValueError(f"canopy raster {w}x{h}, expected {GRID}x{GRID}")
    return vals, ix0, iz0, iwm


def hash01(*parts) -> float:
    h = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:6], "big") / float(1 << 48)


def scatter(site, vals, ix0, iz0, iwm):
    cell = iwm / GRID
    pts = []
    for j in range(GRID):
        for i in range(GRID):
            c = vals[j * GRID + i]
            if c < MIN_CANOPY:
                continue
            # acceptance rises with canopy: 25% -> ~0.31, 100% -> ~0.87
            if hash01(site, i, j, "a") > 0.12 + c / 133.0:
                continue
            jx = (hash01(site, i, j, "x") - 0.5) * cell * 0.9
            jz = (hash01(site, i, j, "z") - 0.5) * cell * 0.9
            x = ix0 + (i + 0.5) / GRID * iwm + jx
            z = iz0 + (j + 0.5) / GRID * iwm + jz
            s = 0.85 + hash01(site, i, j, "s") * 0.75
            pts.append([round(x, 1), round(z, 1), round(s, 2)])
    if len(pts) > CAP:
        step = len(pts) / CAP
        pts = [pts[int(k * step)] for k in range(CAP)]
    return pts


def station_latlon():
    """Read (site, lat, lon) for every 3D page from HT3D in the pages."""
    root = Path("stations")
    out = {}
    for p in sorted(root.glob("USGS-*-3d.html")):
        s = p.read_text(encoding="utf-8")
        m = re.search(r'"site":\s*"(\d+)"', s)
        la = re.search(r'"lat":\s*(-?[\d.]+)', s)
        lo = re.search(r'"lon":\s*(-?[\d.]+)', s)
        if m and la and lo:
            out[m.group(1)] = (float(la.group(1)), float(lo.group(1)))
    return out


def main():
    stations = station_latlon()
    if not stations:
        print("no station pages found under stations/", file=sys.stderr)
        return 1
    data = {}
    for site, (lat, lon) in sorted(stations.items()):
        try:
            vals, ix0, iz0, iwm = fetch_canopy(lat, lon)
            pts = scatter(site, vals, ix0, iz0, iwm)
            cov = sum(1 for v in vals if v >= MIN_CANOPY) / len(vals)
            print(f"{site}: canopy>={MIN_CANOPY}% on {cov:.1%} of block -> {len(pts)} trees")
            data[site] = pts
        except Exception as e:  # loud but non-fatal: bake empty for this station
            print(f"{site}: WARNING canopy fetch failed ({e}); baking no trees", file=sys.stderr)
            data[site] = []
    out = Path(__file__).parent / "trees_data.py"
    body = (
        "# ht-nlcdtrees v1 baked data: instanced-tree scatter points per\n"
        "# station, [x, z, scale] in page ground coordinates (metres from\n"
        "# the gauge), sampled from NLCD 2021 Tree Canopy Cover (MRLC)\n"
        "# over the 3D inner block. Generated by build25/gen_trees_data.py.\n"
        "HT_TREES = " + json.dumps(data, separators=(",", ":")) + "\n"
    )
    out.write_text(body, encoding="utf-8")
    print(f"wrote {out} ({len(body)} bytes, {sum(len(v) for v in data.values())} trees total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
