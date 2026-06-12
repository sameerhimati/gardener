# Render — Build-Ready Guide (Gardener stack, June 2026)

## 1. What It Is

Render is a fully managed cloud platform (PaaS) that runs web services, static sites, private services, background workers, cron jobs, and — since April 2026 — **Workflows** (durable, distributed task orchestration in public beta). It deploys from GitHub/GitLab/Bitbucket, wires services together over a private network, and supports Infrastructure-as-Code via `render.yaml` (called "Blueprints"). Think Heroku ergonomics with first-class support for async/background workloads.

---

## 2. Setup

### Account
1. Sign up at [render.com](https://render.com) — Hobby tier is free.
2. Connect your GitHub org under **Account Settings → GitHub**.

### CLI
```bash
brew install render-cli          # macOS/Linux
render login                     # opens browser, saves token
export RENDER_API_KEY="rnd_..."  # for CI / non-interactive use
```

Key commands:
```bash
render services                              # list all services
render deploys create SERVICE_ID --wait --confirm   # trigger deploy, block until done
render ssh SERVICE_ID                        # shell into a running instance
render validate render.yaml                  # lint Blueprint before push
```

### Deploy from Repo (Blueprint path)
1. Add `render.yaml` to repo root (see §3).
2. Render Dashboard → **New → Blueprint** → select repo → Render reads the file and provisions everything.
3. Auto-deploy fires on every push to the configured branch by default (`autoDeployTrigger: commit`).

Manual trigger via CLI:
```bash
render deploys create <SERVICE_ID> --wait --confirm
```

---

## 3. Config for Gardener

### Service topology
| Service | Render type | Notes |
|---------|-------------|-------|
| FastAPI chat + API | `web` | public HTTPS endpoint |
| Lint worker | **Workflows** or `cron` or `worker` | see comparison below |
| ClickHouse | external (ClickHouse Cloud) | Render doesn't host CH natively |
| Postgres (optional) | `databases` | for diff/accept state |

---

### Lint Worker: Workflows vs Cron vs Background Worker

| | **Render Workflows** (beta) | **Cron Job** | **Background Worker** |
|---|---|---|---|
| **Trigger** | SDK call, API, CLI, Dashboard — _no native schedule yet_ (roadmap) | Fixed cron expression (UTC) | Polls a queue (Redis/Valkey) |
| **Execution model** | Ephemeral instance per task run, spun up/down automatically | Ephemeral container per run | Continuously running process |
| **State + retry** | Built-in: managed queue, retry with backoff, chaining, 24h max | None; max 12h run, 1 active run guaranteed | Manual (Celery/BullMQ etc.) |
| **Cost** | $0.05–$0.20/hr prorated per second; no idle cost | $1/month minimum + per-second compute | Continuous billing even when idle |
| **Observability** | Unified dashboard: metrics, logs, traces | Basic logs | Basic logs |
| **Concurrency** | 20 runs (Hobby) to 100 runs (Scale) base | 1 at a time | As many workers as you run |
| **Schedule** | **Not yet** — use cron job as trigger | Native | External (you implement) |
| **Maturity** | Public beta (April 2026) | GA | GA |

**Recommendation for Gardener lint worker:**

Use a **Cron Job** now, with a `Workflows` migration path.

Why: The lint loop is periodic, bounded (audit vault, propose diffs, write results), and doesn't need 24h execution. A cron job is GA, costs $1/month minimum, and is trivially configured. Workflows adds zero value for a scheduled trigger today because _it has no native cron trigger_ — you'd still need a cron job to call it. Once Render ships cron triggers for Workflows (on roadmap), migrate to get better observability, retries, and pay-per-second billing. For the hackathon demo, **cron wins on simplicity**.

---

### `render.yaml` (minimal, Gardener stack)

```yaml
services:
  # Web service — FastAPI or Next.js
  - name: gardener-api
    type: web
    runtime: python
    repo: https://github.com/your-org/gardener
    branch: main
    autoDeployTrigger: commit
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    plan: starter          # $7/month — no cold starts
    region: oregon
    healthCheckPath: /health
    envVars:
      - key: CLICKHOUSE_URL
        sync: false        # you supply value in Dashboard
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: gardener-db
          property: connectionString

  # Lint worker — cron job
  - name: gardener-lint-worker
    type: cron
    runtime: python
    repo: https://github.com/your-org/gardener
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: python -m workers.lint_runner
    schedule: "0 */6 * * *"   # every 6 hours UTC
    plan: starter
    region: oregon
    envVars:
      - key: CLICKHOUSE_URL
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: DATABASE_URL
        fromDatabase:
          name: gardener-db
          property: connectionString

databases:
  - name: gardener-db
    plan: basic-1gb
    region: oregon
    postgresMajorVersion: "18"    # new default as of Jan 2026
```

> **Secrets**: Never set `value:` for API keys in this file. Use `sync: false` — Render prompts you for the value on first Blueprint deploy, then stores it encrypted. For later updates: Dashboard → Service → Environment.

---

### If you want to try Workflows for the lint worker

```python
# workers/lint_workflow.py
from render_sdk import Workflows

app = Workflows()

@app.task(
    timeout_seconds=3600,
    retries={"max_attempts": 3, "initial_delay_seconds": 10}
)
def run_lint_audit(vault_path: str) -> dict:
    # audit contradictions, staleness, redundancy
    # write proposed diffs to DB
    return {"diffs": [...]}

if __name__ == "__main__":
    app.start()
```

Trigger from a cron job (until native schedule lands):
```bash
# cron job startCommand
python -c "
from render_sdk import Workflows
client = Workflows()
client.run_task('run_lint_audit', args={'vault_path': '/vault'})
"
```

Workflow services are not yet definable in `render.yaml` Blueprints — create them manually in the Dashboard or via API.

---

## 4. Gotchas, Free Tier, Cold Starts, Pricing

**Free tier (Hobby):**
- 512 MB RAM, 0.1 CPU per service
- 750 instance-hours/month, 100 GB outbound bandwidth, 500 build minutes
- Free Postgres: 256 MB RAM, **expires after 30 days** (14-day grace period) — use paid for anything you want to keep
- Free Redis/Valkey: 25 MB only
- **Cold starts**: free web services spin down after **15 min** of inactivity (reduced from 30 min in Sept 2025); cold start takes 30–60 seconds

**Paid minimums (per service/month):**
| Instance | RAM | vCPU | $/month |
|----------|-----|------|---------|
| Starter | 512 MB | 0.5 | $7 |
| Standard | 2 GB | 1 | $25 |
| Pro | 4 GB | 2 | $85 |

**Cron job**: $1/month minimum + per-second compute while running.

**Workflows**: no free tier; `starter` instance = $0.05/hr prorated per second. A 10-minute lint run on starter = ~$0.008. Concurrent task limit: 20 runs on Hobby, 50 on Pro ($25/month workspace).

**Workspace plan (April 2026 restructure):**
- **Hobby**: free, 1 project, 2 environments
- **Pro**: $25/month, unlimited members, autoscaling, HIPAA
- **Scale**: $499/month

**For a hackathon demo:** Run API on Starter ($7/mo, no cold starts), lint cron on free or $1/mo minimum. Total: ~$8–10/month.

**Overlapping deploys**: As of July 2025, new workspaces default to "Wait" (not "Override") — a deploy won't clobber an in-progress one.

**SMTP blocked**: Free tier services cannot reach SMTP ports 25/465/587 (since Sept 2025).

---

## 5. What Changed Since Early 2025

| Date | Change |
|------|--------|
| Apr 2025 | Workspace plan restructure — Hobby/Pro/Scale/Enterprise; per-seat fees removed |
| Apr 2025 | Key Value instances now use Valkey 8.1 (not Redis) |
| Jul 2025 | Legacy service sharing deprecated |
| Aug 2025 | Outbound bandwidth price cut: $30 → $15 per 100 GB |
| Aug 2025 | Render MCP server GA |
| Sept 2025 | Free web service spin-down: 30 min → **15 min** |
| Sept 2025 | Free services blocked from SMTP ports |
| Feb 2026 | Blueprints support custom YAML filenames/paths; CLI `render validate` added |
| **Apr 2026** | **Render Workflows public beta** (TypeScript + Python SDKs) |
| Apr 2026 | CLI `services create` command added |
| May 2026 | Dedicated outbound IPs available ($100/month) |
| Jun 2026 | SSH into ephemeral instances for debugging |
| Jan 2026 | PostgreSQL 18 is new default |

Key naming note: "Redis" → **Valkey** for all new Key Value instances (Feb 2025). Blueprints YAML previously required a fixed `render.yaml` name — now any path works (Feb 2026).

---

## 6. Verdict

Render is **load-bearing** for Gardener's wedge — it's the only platform where a Python web service, a cron-triggered lint worker, and (soon) a durable Workflows task run share a private network and a single `render.yaml`, at hackathon-scale cost of ~$8–10/month with no cold-start anxiety on the API path.

---

## 7. Sources (fetched June 12, 2026)

- [Intro to Render Workflows — Render Docs](https://render.com/docs/workflows)
- [Durability as code: Introducing Workflows — Render Blog](https://render.com/blog/durability-as-code-introducing-render-workflows)
- [Render Workflows Limits & Pricing](https://render.com/docs/workflows-limits)
- [Workflows: Defining Tasks](https://render.com/docs/workflows-defining)
- [Blueprint YAML Reference — Render Docs](https://render.com/docs/blueprint-spec)
- [Background Workers — Render Docs](https://render.com/docs/background-workers)
- [Cron Jobs — Render Docs](https://render.com/docs/cronjobs)
- [Environment Variables and Secrets — Render Docs](https://render.com/docs/configure-environment-variables)
- [Service Types — Render Docs](https://render.com/docs/service-types)
- [Render Changelog](https://render.com/changelog)
- [Render CLI Docs](https://render.com/docs/cli)
- [How Render Handles Scheduled Tasks](https://render.com/articles/how-render-handles-scheduled-tasks)
- [Render Free Tier 2026 — AgentDeals](https://agentdeals.dev/vendor/render)
