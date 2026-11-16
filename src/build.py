"""Insert data/data.json into src/app.html and write the compiled app.

Usage:
    python3 src/build.py            # writes index.html and syncs site/index.html
    python3 src/build.py --root     # writes index.html only

Run from the repository root.

Why both paths are written by default: GitHub Pages can publish either from
`/ (root)` or from `/site`, and the two copies silently drifting apart means the
deployed page is not the page that was tested. Writing both keeps whichever
folder Pages is configured to serve in step with this build. Check the real
setting under Settings -> Pages before the final push; if Pages serves `/site`
and the copy were stale, the published app would be an older build.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "src" / "app.html"
DATA = ROOT / "data" / "data.json"
OUT = ROOT / "index.html"
SITE = ROOT / "site" / "index.html"

root_only = "--root" in sys.argv[1:]

template = APP.read_text(encoding="utf-8")
# Escaping "</" keeps a "</script>" inside the data from closing the script tag.
data = DATA.read_text(encoding="utf-8").replace("</", "<\\/")

if template.count("__DATA__") != 1:
    raise SystemExit(f"expected exactly one __DATA__ placeholder in {APP}, found {template.count('__DATA__')}")

out = template.replace("__DATA__", data)
blob = out.encode("utf-8")
digest = hashlib.sha256(blob).hexdigest()[:12]

OUT.write_text(out, encoding="utf-8")
print(f"index.html {len(blob) // 1024} kB  sha256:{digest}")

if root_only:
    print("site/index.html left untouched (--root)")
elif SITE.parent.is_dir():
    SITE.write_text(out, encoding="utf-8")
    print(f"site/index.html synced  sha256:{digest}")
else:
    print("site/ does not exist; nothing to sync")
