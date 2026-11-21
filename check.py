"""AISeeWhy GitHub Action: audit one URL through the AISeeWhy API, write a job summary, set outputs, and exit 1
when the policy is not met: a finding of the `fail-on` priority or worse exists, or the score is below `fail-under`
(`min-score` is its older name; `fail-under` wins when both are set). Standard library only."""

import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("ASW_API", "https://api.aiseewhy.com")
PRIORITIES = ("P1", "P2", "P3")


class PolicyError(ValueError):
    pass


def policy(env) -> tuple[str, int]:
    """(fail_on, threshold) from the inputs. A bad value is an error: a typo must not quietly pass a build."""
    fail_on = (env.get("ASW_FAIL_ON") or "P1").strip()
    fail_on = "none" if fail_on.lower() == "none" else fail_on.upper()
    if fail_on not in PRIORITIES + ("none",):
        raise PolicyError(f"fail-on must be P1, P2, P3 or none (got {fail_on!r})")
    raw = (env.get("ASW_FAIL_UNDER") or "").strip() or (env.get("ASW_MIN_SCORE") or "").strip() or "0"
    try:
        threshold = float(raw)
    except ValueError:
        raise PolicyError(f"fail-under must be a number from 0 to 100 (got {raw!r})") from None
    if not 0 <= threshold <= 100:
        raise PolicyError(f"fail-under must be from 0 to 100 (got {raw})")
    return fail_on, int(threshold) if threshold.is_integer() else threshold


def verdict(counts: dict, score: int, fail_on: str, threshold) -> list[str]:
    """Why the build fails; empty when it passes."""
    reasons = []
    if fail_on != "none":
        worst = sum(counts.get(p) or 0 for p in PRIORITIES[:PRIORITIES.index(fail_on) + 1])
        if worst:
            reasons.append(f"{worst} finding(s) of priority {fail_on} or worse")
    if score < threshold:
        reasons.append(f"score {score} is below {threshold}")
    return reasons


def main() -> int:
    url, key = os.environ["ASW_URL"], os.environ.get("ASW_KEY", "")
    try:
        fail_on, threshold = policy(os.environ)
    except PolicyError as e:
        print(f"::error::{e}")
        return 1
    body = json.dumps({"url": url, "language": os.environ.get("ASW_LANG", "en"), "markdown": True,
                       "ref": "action"}).encode()  # ref: only for the service's checks-by-source count
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
    reasons = verdict(c, score, fail_on, threshold)
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        for k, v in (("score", score), ("p1", c["P1"]), ("p2", c["P2"]), ("p3", c["P3"]),
                     ("failed", "true" if reasons else "false")):
            f.write(f"{k}={v}\n")
    summary = [f"## AISeeWhy: {d['final_url']}", "", f"Score **{score}/100** · P1 {c['P1']} · P2 {c['P2']} · P3 {c['P3']}", ""]
    if reasons:
        summary += [f"**Failed** (fail-on {fail_on}, fail-under {threshold}): {'; '.join(reasons)}.", ""]
    summary.append(d.get("markdown") or "")
    if not d.get("full", True):
        summary.append("\n_Add an AISeeWhy API key (input `api-key`) for every finding with its fix._")
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
        f.write("\n".join(summary) + "\n")
    print(f"AISeeWhy score {score}/100, P1 {c['P1']}, P2 {c['P2']}, P3 {c['P3']}")
    if reasons:
        print(f"::error::AI crawler check failed (fail-on {fail_on}, fail-under {threshold}): {'; '.join(reasons)}. "
              "See the job summary.")
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
