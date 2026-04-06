# MCP Reviewer — High-Level Design

**Status:** Draft  
**Version:** V1  
**Owner:** Founder (Solo)

---

## 1. System Overview

MCP Reviewer is a GitHub App that analyzes MCP-related changes in pull requests and posts an approval recommendation comment. It also ships as a CLI for local testing.

The system is stateless. It receives a PR event, analyzes the diff, scores the risk, and posts a comment. There is no database, no user accounts, and no persistent state beyond what GitHub already stores.

```
┌──────────────┐       webhook        ┌──────────────────┐
│   GitHub PR  │ ───────────────────► │  MCP Reviewer    │
│   (event)    │                      │  (GitHub App)    │
└──────────────┘                      └────────┬─────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │  Analysis Engine  │
                                      │  (shared core)   │
                                      └────────┬─────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │  GitHub PR       │
                                      │  Comment Output  │
                                      └──────────────────┘

┌──────────────┐                      ┌──────────────────┐
│  Developer   │ ── CLI invocation ─► │  Analysis Engine  │
│  (local)     │                      │  (shared core)   │
└──────────────┘                      └────────┬─────────┘
                                               │
                                      ┌────────▼─────────┐
                                      │  stdout / JSON   │
                                      └──────────────────┘
```

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Fast to ship solo, rich GitHub/YAML/JSON ecosystem |
| Web framework | FastAPI | Lightweight webhook receiver, async-ready |
| GitHub integration | PyGithub + webhooks | Receive events, read diffs, post comments |
| Hosting | Single cloud VM or container (e.g., Railway, Fly.io, or a small VPS) | Minimal ops for a solo founder |
| CLI | Click | Standard Python CLI framework, easy to package |
| Config parsing | PyYAML / tomllib | Parse policy files and MCP manifests |
| CI packaging | Docker | Single image serves both the webhook app and CLI |
| Testing | pytest | Unit + integration tests for the analysis engine |

**No database.** The system is request-in / response-out. All state lives in GitHub.

---

## 3. Component Architecture

### 3.1 Components

```
mcpreviewer/
├── app/                    # FastAPI webhook server
│   ├── main.py             # App entrypoint, webhook routes
│   ├── github_client.py    # GitHub API interactions (read diff, post comment)
│   └── webhook_handler.py  # PR event handling, orchestration
├── core/                   # Shared analysis engine (used by app + CLI)
│   ├── detector.py         # MCP file detection
│   ├── parser.py           # MCP manifest/tool definition parsing
│   ├── differ.py           # Capability diffing (old vs new)
│   ├── classifier.py       # Capability classification
│   ├── scorer.py           # Rule-based risk scoring
│   ├── recommender.py      # Approval recommendation logic
│   ├── summarizer.py       # Plain-English blast radius summary
│   └── policy.py           # Repo policy file loading and application
├── cli/                    # CLI interface
│   └── main.py             # Click CLI, calls into core/
├── models/                 # Data models
│   └── types.py            # Dataclasses for tools, capabilities, risk, recommendation
├── tests/
│   ├── test_detector.py
│   ├── test_differ.py
│   ├── test_classifier.py
│   ├── test_scorer.py
│   ├── test_recommender.py
│   └── fixtures/           # Sample MCP files for testing
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 3.2 Component Responsibilities

| Component | Responsibility |
|---|---|
| **Detector** | Given a list of changed files, filter to MCP-relevant files using configurable path patterns (e.g., `**/mcp.json`, `**/tools/*.yaml`). |
| **Parser** | Parse MCP manifest and tool definition files into a normalized internal model (list of tools with name, description, capabilities, scopes). |
| **Differ** | Compare the old (base) and new (head) parsed models. Output: added tools, removed tools, modified tools, scope changes. |
| **Classifier** | For each new or changed tool, assign capability classes: Read, Write, Delete, Send/Notify, Execute, Admin, Sensitive System Access, Unknown. |
| **Scorer** | Apply deterministic rules to the classified changes and produce a risk level: Low, Medium, High, Critical. |
| **Recommender** | Map risk level to recommendation (Safe to merge / Review recommended / Manual approval required). Attach reason strings. |
| **Summarizer** | Generate a 2–5 sentence plain-English blast radius summary from the classified diff. |
| **Policy** | Load the optional repo policy file (e.g., `.mcpreviewer.yml`). Override default scoring/recommendation thresholds. |
| **GitHub Client** | Fetch PR diff via GitHub API, fetch base/head file contents, post/update the review comment. |
| **Webhook Handler** | Receive `pull_request` events, orchestrate the full pipeline, handle errors gracefully. |
| **CLI** | Accept a local git diff or repo path, run the same core pipeline, output text or JSON to stdout. |

---

## 4. Data Flow

### 4.1 GitHub App Flow

```
1. GitHub sends pull_request webhook (opened / synchronize)
2. Webhook Handler receives event
3. GitHub Client fetches list of changed files
4. Detector filters to MCP-relevant files
5. GitHub Client fetches base and head versions of each MCP file
6. Parser normalizes both versions into internal tool models
7. Differ computes capability changes
8. Classifier assigns capability classes to each change
9. Policy loader reads .mcpreviewer.yml from the repo (if present)
10. Scorer computes risk level using rules + policy overrides
11. Recommender maps risk to recommendation + reasons
12. Summarizer generates plain-English summary
13. GitHub Client posts (or updates) PR comment
```

### 4.2 CLI Flow

```
1. User runs: mcpreviewer diff --base <ref> --head <ref>
2. CLI resolves local git diff or reads provided files
3. Steps 4–12 from above (Detector → Summarizer)
4. CLI outputs text or JSON to stdout
5. CLI exits with code based on recommendation (0 = safe, 1 = review, 2 = manual approval)
```

---

## 5. MCP File Detection Strategy

V1 uses configurable glob patterns to identify MCP-related files. Defaults:

```
patterns:
  - "**/mcp.json"
  - "**/mcp.yaml"
  - "**/mcp.yml"
  - "**/.mcp.json"
  - "**/.mcp.yaml"
  - "**/.mcp.yml"
  - "**/mcp-config.*"
  - "**/tools/**"
```

These defaults can be overridden in the repo policy file. If no MCP files are found, the system skips analysis and does not post a comment.

---

## 6. Capability Classification Logic

Classification is rule-based using keyword and pattern matching on tool names, descriptions, and declared operations.

| Class | Signal Examples |
|---|---|
| Read | `get_*`, `list_*`, `fetch_*`, `read_*`, description contains "retrieve", "query" |
| Write | `create_*`, `update_*`, `set_*`, `put_*`, description contains "write", "modify", "add" |
| Delete | `delete_*`, `remove_*`, description contains "delete", "destroy", "drop" |
| Send / Notify | `send_*`, `notify_*`, `email_*`, `post_message`, description contains "send", "notify", "email" |
| Execute | `run_*`, `exec_*`, `execute_*`, description contains "execute", "invoke", "deploy" |
| Admin | `configure_*`, `admin_*`, `manage_*`, description contains "admin", "config", "permission", "role" |
| Sensitive System Access | Tool targets a sensitive domain (see §6.1) |
| Unknown | No confident classification possible |

### 6.1 Sensitive Domain Detection

Match tool names, descriptions, and target URIs against domain keywords:

| Domain | Keywords |
|---|---|
| Email | email, smtp, mailbox, inbox |
| Ticketing | ticket, issue, jira, servicenow |
| Source control | repo, repository, branch, commit, git |
| Database | database, db, sql, query, table, collection |
| Cloud infrastructure | aws, azure, gcp, cloud, vm, instance, cluster, k8s |
| Billing / payments | billing, payment, invoice, charge, stripe |
| CRM / customer records | customer, crm, contact, salesforce, hubspot |
| Identity / auth | auth, oauth, token, identity, iam, saml, sso, credential |
| File storage | storage, s3, blob, bucket, file, drive |

---

## 7. Risk Scoring Rules

Scoring is deterministic. Each change contributes points. The total maps to a risk level.

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
| Tool removed | +0 (informational) |

### Risk Level Mapping

| Total Points | Risk Level | Recommendation |
|---|---|---|
| 0 | Low | Safe to merge |
| 1–3 | Medium | Review recommended |
| 4–6 | High | Manual approval required |
| 7+ | Critical | Manual approval required |

Policy file overrides can force specific signals to escalate (e.g., "any Delete → Critical").

---

## 8. Policy File Design

Repo-level file: `.mcpreviewer.yml`

```yaml
# Example policy file
version: 1

patterns:
  - "**/mcp.json"
  - "**/tools/**"

rules:
  - capability: Delete
    min_risk: Critical
  - capability: Send
    min_risk: High
  - domain: Email
    min_risk: High
  - domain: Billing
    min_risk: Critical

options:
  ignore_description_only: true
  fail_ci_threshold: High     # CLI exits non-zero at this level or above
```

**Parsing rules:**
- If the file is missing, use defaults.
- If the file is malformed, log a warning and use defaults (fail safe).
- Unknown keys are ignored in V1.

---

## 9. GitHub App Design

### 9.1 App Registration

- Register as a GitHub App (not an OAuth App).
- Required permissions: `pull_requests: write`, `contents: read`.
- Subscribe to events: `pull_request` (opened, synchronize, reopened).

### 9.2 Webhook Endpoint

Single POST endpoint: `/webhook`

- Verify webhook signature (HMAC-SHA256) on every request.
- Parse the event payload.
- Ignore events that are not `pull_request` or irrelevant actions.
- Run analysis pipeline asynchronously (respond 200 immediately, process in background).

### 9.3 Comment Strategy

- Post a single comment per PR.
- On subsequent pushes (synchronize), update the existing comment rather than posting a new one.
- If no MCP files are found, do not post or silently delete any prior comment.
- Comment is posted under the app's identity (bot account).

---

## 10. CLI Design

```
mcpreviewer analyze [OPTIONS]

Options:
  --base TEXT        Base git ref (default: origin/main)
  --head TEXT        Head git ref (default: HEAD)
  --repo PATH        Path to repo (default: current directory)
  --format TEXT      Output format: text | json (default: text)
  --policy PATH      Path to policy file (default: auto-detect)
  --fail-on TEXT     Exit non-zero at this risk level: low | medium | high | critical
```

Exit codes:
- `0` — Safe to merge (or below fail threshold)
- `1` — Review recommended (at or above fail threshold)
- `2` — Manual approval required (at or above fail threshold)

---

## 11. PR Comment Format

```
## MCP Reviewer

**Recommendation:** Manual approval required  
**Risk:** High

This PR adds one new write-capable tool and expands OAuth scope to write access.
The MCP server can now create tickets in an external system.
This increases the agent's blast radius beyond read-only access.

### Key Changes

| Change | Detail |
|---|---|
| Added tool | `create_ticket` |
| New capability | Write |
| Sensitive domain | Ticketing |
| Scope change | `read` → `read/write` |

### Reasons

- Introduces write access
- Expands external system impact
- Increases approval risk

---
*MCP Reviewer v1 · [Docs](https://github.com/mazong1123/mcpreviewer)*
```

---

## 12. Deployment Architecture

```
┌─────────────────────────────────┐
│   Single Container (Fly.io /    │
│   Railway / small VPS)          │
│                                 │
│   ┌───────────────────────┐     │
│   │  FastAPI App          │     │
│   │  - POST /webhook      │     │
│   │  - Health check GET / │     │
│   └───────────────────────┘     │
│                                 │
│   No database                   │
│   No queue                      │
│   No cache                      │
└─────────────────────────────────┘
         │
         │ HTTPS (TLS terminated by platform)
         │
    GitHub Webhooks
```

**Solo founder considerations:**
- Single container deployment. No microservices.
- Use platform-managed TLS (Fly.io / Railway handle this).
- Environment variables for secrets: `GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`.
- Logging to stdout (platform captures it).
- No separate worker process in V1. Webhook handler processes inline or with a simple background task in FastAPI.
- If volume grows, move to a task queue later. Not in V1.

---

## 13. Security Considerations

| Concern | Mitigation |
|---|---|
| Webhook authenticity | Verify GitHub HMAC-SHA256 signature on every request |
| Secret storage | Secrets in environment variables, never in code or config files |
| GitHub token scope | Minimal permissions: PR write + contents read |
| Input parsing | Defensive parsing — malformed MCP files must not crash the system |
| Dependency supply chain | Pin dependencies, use `pip-audit` in CI |
| Rate limiting | Respect GitHub API rate limits; add basic request throttling |

---

## 14. Testing Strategy

| Level | Scope | Approach |
|---|---|---|
| Unit | Each core component (detector, parser, differ, classifier, scorer, recommender, summarizer, policy) | pytest with fixture MCP files covering common and edge cases |
| Integration | Full pipeline (diff → comment text) | Feed sample diffs through the engine, assert on recommendation and comment content |
| Contract | GitHub webhook parsing | Test against recorded webhook payloads |
| CLI | End-to-end CLI runs | Invoke CLI on test repos, check stdout and exit codes |
| Manual | GitHub App installed on a test repo | Open real PRs with MCP changes, verify comment posted correctly |

---

## 15. V1 Milestones

| # | Milestone | Description |
|---|---|---|
| 1 | Core engine | Detector + Parser + Differ + Classifier + Scorer + Recommender + Summarizer working end-to-end with test fixtures |
| 2 | CLI | CLI wrapping core engine, text + JSON output, exit codes |
| 3 | Policy file | Policy file loading and override logic |
| 4 | GitHub App | Webhook receiver, GitHub API integration, PR comment posting |
| 5 | Deployment | Dockerized, deployed to a single platform, webhook registered |
| 6 | Pilot | Installed on 1–2 real repos, validate with real PRs |

---

## 16. Key Design Decisions

| Decision | Rationale |
|---|---|
| Stateless, no database | Simplest possible architecture for a solo founder. GitHub is the system of record. |
| Single container | No orchestration overhead. Scale later if needed. |
| Rule-based scoring, no LLM in V1 | Deterministic, explainable, no API cost, no latency. LLM summarization can be added later. |
| Python | Fastest to ship for a solo dev. Rich ecosystem for GitHub/YAML/JSON. |
| GitHub App (not Action) | App receives webhooks automatically. Doesn't require the repo owner to add a workflow file. Easier onboarding. |
| Keyword-based classification | Good enough for V1. Can layer ML/LLM classification on top later. |
| Update comment, don't re-post | Avoids comment spam. Single source of truth per PR. |
