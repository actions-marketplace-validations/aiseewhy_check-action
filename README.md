# AISeeWhy: GitHub Action and MCP server

[![mcptry](https://mcptry.com/badge/com.aiseewhy/aiseewhy)](https://mcptry.com/servers/com.aiseewhy/aiseewhy)

AISeeWhy (https://aiseewhy.com) checks whether AI crawlers and AI search (ChatGPT, Claude, Gemini, Perplexity) can read and cite a web page.

## GitHub Action

Fails a build when AI crawlers are blocked or the AI-readability score drops. It calls the AISeeWhy API, writes the report into the job summary and sets `score` and `p1` outputs.

```yaml
- uses: aiseewhy/check-action@v1
  with:
    url: ${{ steps.deploy.outputs.preview-url }}
    api-key: ${{ secrets.AISEEWHY_API_KEY }}  # optional: full report with fixes
    fail-on: P1        # P1, P2, P3 or none
    fail-under: 70     # fail when the score is below 70
```

### Failing the build

The build fails (exit 1) when either rule is broken. The job summary and the error line say which.

| Input | Default | Meaning |
| --- | --- | --- |
| `fail-on` | `P1` | Fail when a finding of this priority **or worse** exists: `P1` fails on P1 only, `P2` on P1 or P2, `P3` on any finding, `none` never fails on findings. Case does not matter. |
| `fail-under` | `""` (off) | Fail when the 0-100 score is below this number. |
| `min-score` | `"0"` | The older name of `fail-under`, kept so existing workflows keep working. `fail-under` wins when both are set. |

The defaults are what the action always did: fail on a P1 finding, no score threshold. A value that is not valid (`fail-on: P4`, `fail-under: high`, a score over 100) fails the step before the API is called, so a typo cannot quietly pass a build.

| Output | Meaning |
| --- | --- |
| `score` | The 0-100 score |
| `p1` | Number of P1 findings |
| `failed` | `"true"` when `fail-on` or `fail-under` failed the build, otherwise `"false"` |

To report without failing (for example on pull requests from forks), use `fail-on: none` and leave `fail-under` empty, then read the outputs.

Without a key the free tier gives the score and the counts (rate-limited per runner IP). Create a key at https://aiseewhy.com/account/.

### Fix mode: a robots.txt change for review

Optional. When `fix-search-bots` is `"true"` and `robots-path` points at an existing file, the action edits that file in the runner's workspace so the AI **search and user** crawlers can read the site: OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Claude-User, PerplexityBot and Perplexity-User.

| Input | Default | Meaning |
| --- | --- | --- |
| `robots-path` | `""` (off) | Path of robots.txt in the repository, e.g. `public/robots.txt` |
| `fix-search-bots` | `"false"` | `"true"` turns the fix on |

| Output | Meaning |
| --- | --- |
| `fixed` | `"true"` when the file was changed, otherwise `"false"` |
| `fix-summary` | Path to a short Markdown file that lists each change (made for a pull request body) |

What it changes, and only this:

- A search or user crawler with its own group that says `Disallow: /`: that group's rules become `Allow: /`. If the group is shared with other crawlers, only the search crawler's `User-agent` line is moved out (left as a comment) into a new `Allow: /` group at the end, so the others keep their rules.
- A search or user crawler blocked only by `User-agent: *` with `Disallow: /`: an explicit `Allow: /` group for it is added at the end. The `*` group is not edited.
- Training crawlers (GPTBot, ClaudeBot, Google-Extended, Applebot-Extended, CCBot, Bytespider, Meta-ExternalAgent) are **never** changed. Comments, order and every other line stay byte-for-byte. Groups follow RFC 9309 (consecutive `User-agent` lines share a group, names match case-insensitively).

The change is a **proposal for a person to review**. The action never commits, pushes or opens a pull request; your workflow decides that. A common pattern opens a pull request with the summary as its body:

```yaml
name: AI crawler check
on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  aiseewhy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - id: aiseewhy
        uses: aiseewhy/check-action@v1
        with:
          url: https://example.com/
          api-key: ${{ secrets.AISEEWHY_API_KEY }}
          fail-on: P1
          robots-path: public/robots.txt
          fix-search-bots: "true"

      # Runs even when the check above failed (a blocked crawler is usually why it failed).
      - if: ${{ !cancelled() && steps.aiseewhy.outputs.fixed == 'true' }}
        uses: peter-evans/create-pull-request@v7.0.8
        with:
          add-paths: public/robots.txt
          branch: aiseewhy/robots-search-bots
          commit-message: "robots.txt: allow AI search and user crawlers"
          title: "robots.txt: allow AI search and user crawlers (review)"
          body-path: ${{ steps.aiseewhy.outputs.fix-summary }}
```

The audit checks the live `url`, so the check keeps failing until the reviewed change is merged and deployed.

### Tests

`python3 -m unittest` in this folder (standard library only): `test_fixrobots.py` for fix mode, `test_check.py` for the `fail-on` / `fail-under` policy (the API call is mocked).

## MCP server

Remote MCP server (streamable HTTP) at `https://api.aiseewhy.com/mcp`, listed in the official MCP Registry as `com.aiseewhy/aiseewhy` (`mcp/server.json` is the registry entry).

```json
{
  "mcpServers": {
    "aiseewhy": {
      "type": "http",
      "url": "https://api.aiseewhy.com/mcp",
      "headers": { "x-api-key": "asw_…" }
    }
  }
}
```

Tools: `audit_url`, `audit_sitemap`, `compare_urls`, `explain_finding`, `watch_site`, `list_watched_sites`. Without a key you get the free tier (the score and the first finding). Docs: https://aiseewhy.com/docs/#mcp

Support: support@aiseewhy.com
