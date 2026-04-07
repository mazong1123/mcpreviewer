# MCP Reviewer

**Automated risk analysis for MCP configuration changes in pull requests.**

MCP Reviewer is a GitHub Actions bot that analyzes MCP (Model Context Protocol) configuration changes and tells reviewers whether a PR is safe to merge. Instead of manually reading raw manifests and tool definitions, reviewers get a clear, actionable recommendation.

---

## What is MCP Reviewer?

MCP Reviewer analyzes MCP configuration changes and produces a clear recommendation:

- **Safe to merge** — no significant capability expansion
- **Review recommended** — moderate changes worth a closer look
- **Manual approval required** — the PR introduces meaningful new agent power

MCP Reviewer works as a **GitHub Actions workflow** that posts comments on pull requests, and as a **CLI** for local testing.

## See It in Action

Every example below is a **real PR** in this repo with a **real bot comment** — click through to see them live.

### 🟡 Medium Risk — Unknown tool added

> **PR:** [Example: Add weather MCP server (Low Risk)](https://github.com/mazong1123/mcpreviewer/pull/7)

Adding a weather server that can't be confidently classified:

> ## 🟡 MCP Reviewer
>
> **Recommendation:** Review recommended
> **Risk:** Medium (2 points)
>
> This PR adds 1 new tool in the MCP configuration. Reviewer attention is recommended before merging.
>
> | Change | Tool | Capabilities | Sensitive Domains |
> |--------|------|-------------|------------------|
> | added | `weather` | Unknown | - |
>
> **Reasons:** Contains unknown or ambiguous capability

### 🟠 High Risk — Database access with production credentials

> **PR:** [Example: Add postgres manager MCP server (High Risk)](https://github.com/mazong1123/mcpreviewer/pull/8)

Adding a postgres server pointing at a production database:

> ## 🟠 MCP Reviewer
>
> **Recommendation:** Manual approval required
> **Risk:** High (5 points)
>
> This PR adds 1 new tool in the MCP configuration. This affects sensitive systems: Database, Identity / authentication. Manual approval is required due to the scope of capability expansion.
>
> | Change | Tool | Capabilities | Sensitive Domains |
> |--------|------|-------------|------------------|
> | added | `postgres-manager` | Admin / Configuration, Sensitive System Access | Database, Identity / authentication |
>
> **Reasons:** Introduces admin/configuration capability · Affects sensitive systems: Database, Identity / authentication

### 🔴 Critical Risk — Shell execution + billing access

> **PR:** [Example: Add shell executor and Stripe billing (Critical Risk)](https://github.com/mazong1123/mcpreviewer/pull/9)

Adding a shell executor (arbitrary commands) and a Stripe billing server:

> ## 🟠 MCP Reviewer
>
> **Recommendation:** Manual approval required
> **Risk:** High (5 points)
>
> This PR adds 2 new tools in the MCP configuration. Among the changes, 1 tool can execute commands. This affects sensitive systems: Billing / payments, Identity / authentication. Manual approval is required due to the scope of capability expansion.
>
> | Change | Tool | Capabilities | Sensitive Domains |
> |--------|------|-------------|------------------|
> | added | `shell-executor` | Execute | - |
> | added | `stripe-billing` | Sensitive System Access | Billing / payments, Identity / authentication |
>
> **Reasons:** Introduces execute capability · Affects sensitive systems: Billing / payments, Identity / authentication

---

## Quick Start

### Install the CLI

```bash
pip install mcpreviewer
```

### Run locally

```bash
mcpreviewer analyze --base origin/main --head HEAD
```

---

## Setup: Automatic PR Reviews (GitHub Actions)

The easiest way to get MCP Reviewer running on your repository is with GitHub Actions. **No server, no GitHub App registration needed** — just add one workflow file.

### Step 1: Add the workflow file

Copy this file into your repository at `.github/workflows/mcpreviewer.yml`:

```yaml
name: MCP Reviewer

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Fetch PR head and base refs
        run: |
          git fetch origin ${{ github.base_ref }}
          git fetch origin pull/${{ github.event.pull_request.number }}/head:pr-head

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install MCP Reviewer
        run: pip install mcpreviewer

      - name: Run MCP Reviewer
        run: |
          python -m mcpreviewer.cli.main \
            --base origin/${{ github.base_ref }} \
            --head pr-head \
            --format json > /tmp/mcpreviewer_result.json 2>/dev/null || true

          python -m mcpreviewer.cli.main \
            --base origin/${{ github.base_ref }} \
            --head pr-head \
            --format text > /tmp/mcpreviewer_comment.txt 2>/dev/null || true

      - name: Post or update PR comment
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const marker = '<!-- mcpreviewer-bot -->';

            let textOutput = '';
            let jsonOutput = '';
            try { textOutput = fs.readFileSync('/tmp/mcpreviewer_comment.txt', 'utf8').trim(); } catch (e) {}
            try { jsonOutput = fs.readFileSync('/tmp/mcpreviewer_result.json', 'utf8').trim(); } catch (e) {}

            if (!textOutput || textOutput.includes('No MCP-related changes') || textOutput.includes('No changed files')) {
              return;
            }

            let body = marker + '\n';
            let result = null;
            try { result = JSON.parse(jsonOutput); } catch (e) {}

            if (result && result.recommendation) {
              const riskEmoji = { 'Low': '🟢', 'Medium': '🟡', 'High': '🟠', 'Critical': '🔴' };
              const emoji = riskEmoji[result.risk_level] || '⚪';
              body += `## ${emoji} MCP Reviewer\n\n`;
              body += `**Recommendation:** ${result.recommendation}\n`;
              body += `**Risk:** ${result.risk_level} (${result.total_points} points)\n\n`;
              body += `${result.summary}\n\n`;

              if (result.tool_changes && result.tool_changes.length > 0) {
                body += '### Key Changes\n\n';
                body += '| Change | Tool | Capabilities | Sensitive Domains |\n';
                body += '|--------|------|-------------|------------------|\n';
                for (const tc of result.tool_changes) {
                  const caps = tc.capabilities.join(', ') || '-';
                  const domains = tc.sensitive_domains.join(', ') || '-';
                  body += `| ${tc.change_type} | \`${tc.tool_name}\` | ${caps} | ${domains} |\n`;
                }
                body += '\n';
              }

              if (result.reasons && result.reasons.length > 0) {
                body += '### Reasons\n\n';
                for (const r of result.reasons) {
                  body += `- ${r}\n`;
                }
                body += '\n';
              }

              body += `\n<details><summary>Analyzed files</summary>\n\n`;
              for (const f of (result.analyzed_files || [])) {
                body += `- \`${f}\`\n`;
              }
              body += `\n</details>\n\n---\n*MCP Reviewer v1*\n`;
            } else {
              body += '## MCP Reviewer\n\n```\n' + textOutput + '\n```\n';
            }

            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: context.issue.number,
            });
            const existing = comments.find(c => c.body.includes(marker));
            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner, repo: context.repo.repo,
                comment_id: existing.id, body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner, repo: context.repo.repo,
                issue_number: context.issue.number, body,
              });
            }
```

### Step 2 (optional): Add a policy file

Create `.mcpreviewer.yml` in your repo root to customize behavior:

```yaml
version: 1
rules:
  - capability: Delete
    min_risk: Critical
  - domain: Billing
    min_risk: Critical
options:
  ignore_description_only: true
  fail_ci_threshold: Medium
```

### Step 3: Open a PR

Any PR that touches MCP config files (e.g., `mcp.json`, `.vscode/mcp.json`, `mcp.yaml`) will automatically get a review comment posted by MCP Reviewer.

The comment is updated on each push — no duplicates.

---

## How It Works

When a pull request touches MCP-related files, MCP Reviewer:

1. **Detects** which changed files are MCP configurations
2. **Parses** the old (base) and new (head) versions
3. **Diffs** the tool and scope definitions
4. **Classifies** each change by capability type (Read, Write, Delete, Execute, etc.)
5. **Scores** the risk using deterministic, rule-based logic
6. **Recommends** an action and explains why in plain English
7. **Posts** a structured comment on the PR (or outputs to your terminal)

The entire process is deterministic — the same input always produces the same recommendation.

---

## Supported MCP File Formats

MCP Reviewer detects files matching these default patterns:

- `**/mcp.json`
- `**/mcp.yaml` / `**/mcp.yml`
- `**/.mcp.json` / `**/.mcp.yaml` / `**/.mcp.yml`
- `**/mcp-config.*`

### Format A — mcpServers (VS Code / Claude Desktop style)

```json
{
  "mcpServers": {
    "github-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "..." }
    }
  }
}
```

### Format B — Tool manifest (explicit tool list)

```json
{
  "tools": [
    {
      "name": "create_ticket",
      "description": "Creates a new ticket in the ticketing system",
      "inputSchema": {
        "type": "object",
        "properties": { "title": { "type": "string" } }
      }
    }
  ]
}
```

### Format C — Tool manifest with annotations

```json
{
  "tools": [
    {
      "name": "delete_record",
      "description": "Deletes a database record",
      "annotations": {
        "readOnlyHint": false,
        "destructiveHint": true
      }
    }
  ]
}
```

YAML equivalents are also supported.

---

## Capability Classification

Each tool is classified into one or more categories based on its name, description, and annotations:

| Category | What it means | Example tools |
|---|---|---|
| **Read** | Retrieves data without side effects | `get_users`, `list_items`, `search_records` |
| **Write** | Creates or modifies data | `create_ticket`, `update_record`, `set_config` |
| **Delete** | Removes or destroys data | `delete_record`, `remove_user`, `drop_table` |
| **Send / Notify** | Sends messages, emails, or notifications | `send_email`, `post_message`, `notify_team` |
| **Execute** | Runs commands, deploys, or invokes processes | `run_query`, `execute_script`, `deploy_app` |
| **Admin / Configuration** | Manages permissions, roles, or settings | `configure_permissions`, `grant_access` |
| **Sensitive System Access** | Touches a sensitive domain (see below) | Tools targeting email, billing, auth, etc. |
| **Unknown** | Cannot be confidently classified | Treated conservatively |

### Sensitive Domains

If a tool targets one of these domains, it gets flagged:

- Email
- Ticketing (Jira, ServiceNow, Zendesk)
- Source control (GitHub, Git)
- Database (SQL, MongoDB, Redis)
- Cloud infrastructure (AWS, Azure, GCP, Kubernetes)
- Billing / payments (Stripe, invoicing)
- CRM / customer records (Salesforce, HubSpot)
- Identity / authentication (OAuth, IAM, SSO)
- File storage (S3, blob storage)

---

## Risk Scoring

Scoring is deterministic and point-based:

| Signal | Points |
|---|---|
| New read-only tool | 0 |
| Description-only change | 0 |
| New Write capability | +2 |
| New Delete capability | +3 |
| New Send/Notify capability | +2 |
| New Execute capability | +3 |
| New Admin capability | +3 |
| Auth scope expansion | +3 |
| Sensitive system access | +2 |
| Unknown capability | +2 |

### Risk Levels

| Points | Risk Level | Recommendation |
|---|---|---|
| 0 | Low | Safe to merge |
| 1–3 | Medium | Review recommended |
| 4–6 | High | Manual approval required |
| 7+ | Critical | Manual approval required |

---

## PR Comment Format

When MCP Reviewer detects changes, it posts a comment like this:

```
## MCP Reviewer

**Recommendation:** Manual approval required
**Risk:** High

This PR adds 1 new tool in the MCP configuration. Among the changes,
1 tool can write data. This affects sensitive systems: Ticketing.
Manual approval is required due to the scope of capability expansion.

### Key Changes

| Change | Detail |
|---|---|
| Added tool | `create_ticket` |
| New capability | Write |
| Sensitive domain | Ticketing |

### Reasons

- Introduces write access
- Affects sensitive systems: Ticketing

---
*MCP Reviewer v1*
```

On subsequent pushes to the same PR, the existing comment is updated (not duplicated).

---

## CLI Usage

### Basic usage

```bash
# Analyze changes between main and your current branch
mcpreviewer analyze

# Analyze with specific refs
mcpreviewer analyze --base origin/main --head feature-branch

# Output as JSON
mcpreviewer analyze --format json

# Fail CI if risk is High or above
mcpreviewer analyze --fail-on high
```

### Options

| Option | Default | Description |
|---|---|---|
| `--base` | `origin/main` | Base git ref to compare against |
| `--head` | `HEAD` | Head git ref (your changes) |
| `--repo` | `.` (current directory) | Path to the git repository |
| `--format` | `text` | Output format: `text` or `json` |
| `--policy` | auto-detect | Path to a policy file |
| `--fail-on` | (none) | Exit non-zero at this risk level: `low`, `medium`, `high`, `critical` |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Safe to merge (or below `--fail-on` threshold) |
| 1 | Review recommended (at or above threshold) |
| 2 | Manual approval required (at or above threshold) |
| 3 | Error (e.g., git command failed) |

### JSON output example

```json
{
  "recommendation": "Manual approval required",
  "risk_level": "High",
  "total_points": 5,
  "summary": "This PR adds 1 new tool...",
  "tool_changes": [
    {
      "change_type": "added",
      "tool_name": "create_ticket",
      "capabilities": ["Write", "Sensitive System Access"],
      "sensitive_domains": ["Ticketing"],
      "description_only": false
    }
  ],
  "scope_changes": [],
  "reasons": ["Introduces write access", "Affects sensitive systems: Ticketing"],
  "analyzed_files": ["mcp.json"]
}
```

---

## Policy File

You can customize MCP Reviewer's behavior per repository by adding a `.mcpreviewer.yml` file to your repo root.

### Example

```yaml
version: 1

# Override which files are analyzed
patterns:
  - "**/mcp.json"
  - "**/tools/**"

# Escalation rules
rules:
  - capability: Delete
    min_risk: Critical        # Any Delete → Critical
  - capability: Send
    min_risk: High            # Any Send → at least High
  - domain: Email
    min_risk: High
  - domain: Billing
    min_risk: Critical        # Billing tools always require manual approval

# Global options
options:
  ignore_description_only: true   # Don't flag description-only changes
  fail_ci_threshold: High         # CLI default --fail-on level
```

### Policy rules

| Field | Description |
|---|---|
| `capability` | Capability name: `Read`, `Write`, `Delete`, `Send`, `Execute`, `Admin`, `Unknown` |
| `domain` | Sensitive domain name: `Email`, `Ticketing`, `Database`, `Billing`, etc. |
| `min_risk` | Floor risk level when this rule matches: `Low`, `Medium`, `High`, `Critical` |

### Behavior

- If the file is missing → default behavior is used
- If the file is malformed → defaults are used (fail-safe)
- Unknown keys are ignored

---

## Architecture Overview

```
GitHub PR Event
      │
      ▼
  GitHub Actions Workflow
      │
      ▼
  CLI / Analysis Engine
      │
      ├── Detector  → finds MCP files
      ├── Parser    → normalizes manifests
      ├── Differ    → computes changes
      ├── Classifier → assigns capability labels
      ├── Scorer    → calculates risk points
      ├── Recommender → maps risk to recommendation
      └── Summarizer → generates plain-English summary
      │
      ▼
  PR Comment (posted via GitHub Actions)
```

No database, no persistent state — GitHub is the system of record.

---

## FAQ

**Q: What if MCP Reviewer can't understand a tool?**
A: It marks the tool as "Unknown" and treats it conservatively (+2 risk points). Unknown capabilities always trigger at least a "Review recommended" result.

**Q: Does it use AI/LLM for classification?**
A: No. V1 uses deterministic keyword-based classification and rule-based scoring. This makes results predictable, explainable, and free of API costs.

**Q: Will it post multiple comments on a PR?**
A: No. It posts one comment and updates it on subsequent pushes.

**Q: What if there are no MCP files in the PR?**
A: MCP Reviewer stays silent — no comment is posted.

**Q: Can I use it in CI?**
A: Yes! The recommended approach is the [GitHub Actions workflow](#setup-automatic-pr-reviews-github-actions) — no server needed. You can also use the CLI with `--fail-on` to gate your CI pipeline:
```bash
mcpreviewer analyze --fail-on high
```

**Q: Does it support monorepos?**
A: Yes. The detector scans all changed files across the entire repo using glob patterns.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| No comment posted on PR | Check that the workflow file exists at `.github/workflows/mcpreviewer.yml`, the PR touches MCP config files, and the workflow has `pull-requests: write` permission |
| CLI says "No changed files found" | Make sure `--base` and `--head` are valid git refs with actual differences |
| False positive (flagged as risky but safe) | Add a `.mcpreviewer.yml` policy file to tune thresholds, or use `ignore_description_only: true` |
| False negative (missed risky change) | Add a policy rule to escalate specific capabilities or domains |

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
