# CI/CD — chatbot WB Digital Solutions

Two GitHub Actions workflows in `.github/workflows/`:

- **CI** (`ci.yml`) — runs on every push and PR to `main`. Installs
  `requirements-dev.txt` and runs the pytest suite (45 tests, all mocked: no
  network, no LLM calls, no real keys). This is the gate.
- **CD** (`deploy.yml`) — runs `ansible-playbook` against the VPS **only after CI
  passes green on `main`**, and **only after manual approval** of the `production`
  environment. Matches the existing deploy model (Ansible → root → `/root/chatbot`).

## One-time setup (required before CD can run)

CD is intentionally inert until you complete all three steps. Missing any of them
makes the CD job fail fast with a clear message instead of half-deploying.

### 1. Repository secrets

`Settings → Secrets and variables → Actions → New repository secret`:

| Secret | Value |
| --- | --- |
| `SSH_DEPLOY_KEY` | Private SSH key that logs into the VPS as `root` (the whole PEM, including the BEGIN/END lines). |
| `VPS_HOST` | `45.90.123.190` |
| `DEEPSEEK_API_KEY` | The real DeepSeek key. |
| `LANGFUSE_PUBLIC_KEY` | The real Langfuse public key (optional; blank disables tracing). |
| `LANGFUSE_SECRET_KEY` | The real Langfuse secret key (optional). |

Secrets are per-repository — the ones on the `calendar` repo do not carry over.

> The `qdrant_api_key`, `redis_password` and `admin_api_token` are **not** secrets
> here: the playbook generates them on the server on first deploy and persists them
> under `/root/chatbot/.secrets/` (mode 0600). See `ansible/playbook.yml`.

### 2. `production` environment (the manual-approval gate)

`Settings → Environments → New environment → production`, then under
**Deployment protection rules** enable **Required reviewers** and add yourself.
Every CD run then pauses until you click **Approve** — this is what stops an
accidental push to `main` from redeploying production unattended.

### 3. Pin the VPS host key

CD refuses to connect on trust-on-first-use. From a machine that already trusts the
VPS:

```bash
ssh-keyscan -t ed25519 45.90.123.190
```

Confirm the fingerprint, then paste the resulting line into
[`known_hosts`](./known_hosts) (below the comment block) and commit it.

## How CD decides to run

```
push to main ──▶ CI ──green──▶ CD (workflow_run) ──▶ ⏸ wait for approval ──▶ ansible-playbook ──▶ GET /health == 200
                   │
                   └─red──▶ CD does not start
```

You can also trigger CD manually from the Actions tab (`workflow_dispatch`); it
still requires `production` approval.

## Notes

- The playbook is idempotent, so a full run per deploy is fine: `certbot --nginx`
  no-ops on a valid certificate (no Let's Encrypt rate-limit risk), and the secret
  generation step only creates `.secrets/*` on the first run.
- The CD job builds the Ansible inventory from the secrets above into
  `$RUNNER_TEMP` and deletes it afterwards, so no inventory or secret is ever
  written into the repo tree or the build artifacts.
