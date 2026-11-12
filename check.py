"""AISeeWhy GitHub Action: audit one URL through the AISeeWhy API, write a job summary, set outputs, and exit 1
when the policy (fail-on priority, min-score) is not met. Standard library only."""

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("ASW_API", "https://api.aiseewhy.com")


def main() -> int:
    url, key = os.environ["ASW_URL"], os.environ.get("ASW_KEY", "")
    fail_on, min_score = os.environ.get("ASW_FAIL_ON", "P1"), int(os.environ.get("ASW_MIN_SCORE") or 0)
    body = json.dumps({"url": url, "language": os.environ.get("ASW_LANG", "en"), "markdown": True}).encode()
    req = urllib.request.Request(f"{API}/v1/audit", data=body, method="POST",
                                 headers={"content-type": "application/json", "user-agent": "aiseewhy-action/1",
                                          **({"x-api-key": key} if key else {})})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        print(f"::error::AISeeWhy API answered HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")
        return 1
    c, score = d["counts"], d["score"]["value"]
    worst = {"P1": c["P1"], "P2": c["P1"] + c["P2"], "P3": c["P1"] + c["P2"] + c["P3"], "none": 0}.get(fail_on, c["P1"])
    failed = bool(worst) or score < min_score
    for k, v in (("score", score), ("p1", c["P1"]), ("p2", c["P2"]), ("p3", c["P3"])):
        with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
            f.write(f"{k}={v}\n")
    summary = [f"## AISeeWhy: {d['final_url']}", "", f"Score **{score}/100** · P1 {c['P1']} · P2 {c['P2']} · P3 {c['P3']}", ""]
    summary.append(d.get("markdown") or "")
    if not d.get("full", True):
        summary.append("\n_Add an AISeeWhy API key (input `api-key`) for every finding with its fix._")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
        f.write("\n".join(summary) + "\n")
    print(f"AISeeWhy score {score}/100, P1 {c['P1']}, P2 {c['P2']}, P3 {c['P3']}")
    if failed:
        print(f"::error::AI crawler check failed (fail-on {fail_on}, min-score {min_score}). See the job summary.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
