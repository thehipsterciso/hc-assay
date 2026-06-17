"""License gate (#147): fail if any installed dependency carries a strong-copyleft license.

Reads a pip-licenses JSON report (path as argv[1], default ``licenses.json``) and exits non-zero
if any package's license matches a denied strong-copyleft family that would be incompatible with
the Apache-2.0 distribution. LGPL (weak copyleft, dynamic linking) is permitted. Advisory
monitoring of the rest is handled by Dependabot (.github/dependabot.yml).
"""

from __future__ import annotations

import json
import sys

# Strong-copyleft families denied in the distributed dependency set. Both the SPDX-style short
# tokens AND the full prose names must be listed (pass 3, #F-015): a package reporting
# "Server Side Public License" or "European Union Public Licence 1.2" contains neither the "SSPL"
# nor "EUPL" token, so the short tokens alone let those families bypass the gate.
_DENY = (
    "GPL",
    "AGPL",
    "SSPL",
    "EUPL",
    "SERVER SIDE PUBLIC",  # SSPL prose form
    "EUROPEAN UNION PUBLIC",  # EUPL prose form
    "AFFERO",  # AGPL prose form ("GNU Affero General Public License")
)


def main(path: str = "licenses.json") -> int:
    with open(path, encoding="utf-8") as f:  # context manager — no leaked fd (#F-050)
        packages = json.load(f)
    bad = []
    unknown = []
    for pkg in packages:
        raw = (pkg.get("License") or "").strip()
        lic = raw.upper()
        # A package whose license is empty / UNKNOWN / unspecified could be hiding a copyleft the
        # deny-substring scan can't see. Don't fail on it (pip-licenses reports UNKNOWN for many
        # legitimate packages with incomplete metadata), but SURFACE it as a CI warning so a
        # reviewer checks it instead of it passing silently (#H-007).
        if not raw or lic in ("UNKNOWN", "UNKNOWN LICENSE", "NONE"):
            unknown.append(f"{pkg.get('Name')} {pkg.get('Version')}")
            continue
        if "LGPL" in lic:  # weak copyleft — permitted for dynamically-linked libraries
            continue
        if any(tok in lic for tok in _DENY):
            bad.append(f"{pkg.get('Name')} {pkg.get('Version')}: {pkg.get('License')}")
    if unknown:
        print(
            "::warning::license gate: "
            + str(len(unknown))
            + " package(s) report no/UNKNOWN license — review for hidden copyleft: "
            + ", ".join(sorted(unknown))
        )
    if bad:
        print("::error::strong-copyleft licenses found:\n" + "\n".join(bad))
        return 1
    print(f"license gate OK ({len(packages)} packages checked, {len(unknown)} unknown)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "licenses.json"))
