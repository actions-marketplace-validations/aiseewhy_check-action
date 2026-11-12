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
    min-score: 70
```

Without a key the free tier gives the score and the counts (rate-limited per runner IP). Create a key at https://aiseewhy.com/account/.

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
