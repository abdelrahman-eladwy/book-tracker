"""
Compare a fresh detect-secrets scan with the reviewed baseline.

Usage: python ci/check_secrets.py <new-scan.json> <.secrets.baseline>

Exit code 1 if the scan contains a secret that is not in the baseline. Findings
are matched on (file, hashed secret) only, so moving a line does not make a
reviewed finding "new" again. To accept a finding after reviewing it, regenerate
the baseline (see the Jenkinsfile 'Secrets scan' stage).
"""
import json
import sys


def keys(report):
    return {
        (path, item["hashed_secret"])
        for path, items in report.get("results", {}).items()
        for item in items
    }


def main(scan_path, baseline_path):
    with open(scan_path) as fh:
        scan = json.load(fh)
    with open(baseline_path) as fh:
        known = keys(json.load(fh))

    new = [
        (path, item)
        for path, items in scan.get("results", {}).items()
        for item in items
        if (path, item["hashed_secret"]) not in known
    ]

    if not new:
        print("detect-secrets: no new secrets (baseline entries: %d)." % len(known))
        return 0

    print("detect-secrets: %d potential secret(s) not in the baseline:" % len(new))
    for path, item in new:
        print("  %s:%s  %s" % (path, item["line_number"], item["type"]))
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
