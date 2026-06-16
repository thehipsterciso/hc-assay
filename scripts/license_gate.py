"""License gate (#147): fail if any installed dependency carries a strong-copyleft license.

Reads a pip-licenses JSON report (path as argv[1], default ``licenses.json``) and exits non-zero
if any package's license matches a denied strong-copyleft family that would be incompatible with
the Apache-2.0 distribution. LGPL (weak copyleft, dynamic linking) is permitted. Advisory
monitoring of the rest is handled by Dependabot (.github/dependabot.yml).
"""

from __future__ import annotations

import json
import sys

# Strong-copyleft families denied in the distributed dependency set.
_DENY = ("GPL", "AGPL", "SSPL", "EUPL")


def main(path: str = "licenses.json") -> int:
    packages = json.load(open(path, encoding="utf-8"))
    bad = []
    for pkg in packages:
        lic = (pkg.get("License") or "").upper()
        if "LGPL" in lic:  # weak copyleft — permitted for dynamically-linked libraries
            continue
        if any(tok in lic for tok in _DENY):
            bad.append(f"{pkg.get('Name')} {pkg.get('Version')}: {pkg.get('License')}")
    if bad:
        print("::error::strong-copyleft licenses found:\n" + "\n".join(bad))
        return 1
    print(f"license gate OK ({len(packages)} packages checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "licenses.json"))
