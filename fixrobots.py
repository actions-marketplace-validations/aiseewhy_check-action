"""AISeeWhy GitHub Action, fix mode: propose a robots.txt change that lets AI *search and user* crawlers in.

Only these crawlers are ever changed: OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot,
Perplexity-User. Training crawlers (GPTBot, ClaudeBot, Google-Extended, ...) and the `*` group are never edited.
Grouping follows RFC 9309: consecutive User-agent lines share a group, product tokens match case-insensitively.
All untouched lines are kept byte-for-byte. The action never commits, pushes or opens a pull request itself.
Standard library only."""

import os
import re
import sys
import tempfile

SEARCH_BOTS = ("OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User")
TRAINING_BOTS = ("GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot", "Bytespider",
                 "Meta-ExternalAgent")
MARK = "# AISeeWhy:"


def _record(line):
    """(key, value) of a robots.txt line with comment removed, or (None, None) for blank/comment lines."""
    text = line.lstrip("﻿").split("#", 1)[0].strip()
    if ":" not in text:
        return None, None
    key, value = text.split(":", 1)
    return key.strip().lower(), value.strip()


def _token(value):
    """Product token of a User-agent value, lower-cased (RFC 9309 matching is case-insensitive)."""
    return value.split()[0].split("/")[0].lower() if value.split() else ""


class Group:
    def __init__(self):
        self.agents = []  # (line index, token)
        self.rules = []   # (line index, "allow"/"disallow", pattern)


def parse(lines):
    """Split lines into RFC 9309 groups. A User-agent line after any other record starts a new group."""
    groups, cur, in_agents = [], None, False
    for i, line in enumerate(lines):
        key, value = _record(line)
        if key is None:
            continue  # blank lines and comments do not end a group
        if key == "user-agent":
            if not in_agents:
                cur = Group()
                groups.append(cur)
                in_agents = True
            cur.agents.append((i, _token(value)))
            continue
        in_agents = False
        if cur is not None and key in ("allow", "disallow"):
            cur.rules.append((i, key, value))
    return groups


def _matches_root(pattern):
    if not pattern:
        return False  # an empty rule matches nothing
    rx = re.escape(pattern.rstrip("$")).replace(r"\*", ".*") + ("$" if pattern.endswith("$") else "")
    return re.match(rx, "/") is not None


def root_blocked(rules):
    """True when "/" is disallowed: the longest matching rule wins, Allow wins a tie (RFC 9309 2.2.2)."""
    best = None
    for _, kind, pattern in rules:
        if _matches_root(pattern):
            cand = (len(pattern), kind == "allow")
            best = cand if best is None or cand > best else best
    return best is not None and not best[1]


def fix(text):
    """Return (new_text, changes). changes is a list of (bot, what was done) for the summary."""
    lines = text.splitlines(keepends=True)
    nl = "\r\n" if lines and lines[0].endswith("\r\n") else "\n"
    groups = parse(lines)
    wanted = {b.lower(): b for b in SEARCH_BOTS}
    replace_rules, drop_agent_lines, new_group, changes = set(), set(), [], []

    for low, bot in wanted.items():
        own = [g for g in groups if any(t == low for _, t in g.agents)]
        if own:
            if not root_blocked([r for g in own for r in g.rules]):
                continue
            for g in own:
                if not root_blocked(g.rules):
                    continue
                if all(t in wanted for _, t in g.agents):
                    replace_rules.add(id(g))
                else:  # shared with other crawlers: take only this bot out, the others keep their rules
                    drop_agent_lines.update(i for i, t in g.agents if t == low)
                    if bot not in new_group:
                        new_group.append(bot)
            changes.append((bot, "had its own `Disallow: /` group; now allowed"))
        else:
            star = [g for g in groups if any(t == "*" for _, t in g.agents)]
            if root_blocked([r for g in star for r in g.rules]):
                new_group.append(bot)
                changes.append((bot, "was blocked only by `User-agent: *`; added an explicit `Allow: /` group"))

    if not changes:
        return text, []

    for g in groups:
        if id(g) in replace_rules:
            first = g.rules[0][0]
            for i, _, _ in g.rules:
                lines[i] = None
            lines[first] = "Allow: /" + nl
    for i in drop_agent_lines:
        lines[i] = f"{MARK} moved to its own group at the end: {lines[i].rstrip(chr(13) + chr(10))}{nl}"
    out = [l for l in lines if l is not None]
    if new_group:
        if out and not out[-1].endswith(("\n", "\r")):
            out[-1] += nl
        if out and out[-1].strip():
            out.append(nl)
        out.append(f"{MARK} allow AI search and user crawlers (proposed change, review before merging){nl}")
        out.extend(f"User-agent: {b}{nl}" for b in new_group)
        out.append(f"Allow: /{nl}")
    return "".join(out), changes


def summary(path, changes):
    md = ["## AISeeWhy: robots.txt change for review", ""]
    if not changes:
        md.append(f"`{path}` already lets the AI search and user crawlers in. Nothing changed.")
        return "\n".join(md) + "\n"
    md += [f"This is a **proposal** for `{path}`. Review it before merging.", "",
           "| Crawler | Change |", "| --- | --- |"]
    md += [f"| {bot} | {what} |" for bot, what in changes]
    md += ["", "Training crawlers (" + ", ".join(TRAINING_BOTS) + ") and the `User-agent: *` group were not changed. "
           "All other lines are kept as they were."]
    return "\n".join(md) + "\n"


def _out(key, value):
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as f:
        f.write(f"{key}={value}\n")


def main() -> int:
    rel = os.environ.get("ASW_ROBOTS_PATH", "").strip()
    on = os.environ.get("ASW_FIX_SEARCH_BOTS", "false").strip().lower() == "true"
    if not (rel and on):
        if on:
            print("::warning::fix-search-bots is true but robots-path is empty; nothing to fix.")
        _out("fixed", "false")
        _out("fix-summary", "")
        return 0
    path = os.path.join(os.environ.get("GITHUB_WORKSPACE", "."), rel)
    if not os.path.isfile(path):
        print(f"::warning::robots-path {rel} does not exist; nothing to fix.")
        _out("fixed", "false")
        _out("fix-summary", "")
        return 0
    with open(path, "rb") as f:
        text = f.read().decode("utf-8", errors="surrogateescape")
    new, changes = fix(text)
    if changes:
        with open(path, "wb") as f:
            f.write(new.encode("utf-8", errors="surrogateescape"))
    md = summary(rel, changes)
    out_md = os.path.join(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir(),
                          "aiseewhy-robots-fix.md")
    with open(out_md, "w") as f:
        f.write(md)
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
        f.write(md + "\n")
    _out("fixed", "true" if changes else "false")
    _out("fix-summary", out_md)
    print(f"AISeeWhy robots.txt fix: {len(changes)} crawler(s) changed in {rel}" if changes
          else f"AISeeWhy robots.txt fix: {rel} needs no change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
