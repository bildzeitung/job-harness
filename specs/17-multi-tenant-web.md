# Job Harness Multi-User Evolution Part 2 — Multi-Tenant Web, Auth & Cloud

> Status: **DRAFT FOR REVIEW.** Nothing in here is built yet. This spec is the
> "what & phases"; the "how & why" lives in
> [`docs/multi-tenant-architecture.md`](../docs/multi-tenant-architecture.md) and
> the deployment design in [`docs/deployment-oci.md`](../docs/deployment-oci.md).
> Critique those three together.

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%**

## Goal

Spec 12 made every user-facing **input** data-driven and per-user, but kept a
single shared corpus and a single local SQLite file: the system is still
operated by one person on one machine. This phase turns the **web app** into a
real multi-tenant SaaS:

- Anyone can **register** (email + magic link, or OAuth via Google / GitHub /
  Facebook) and **log in**. Email is always verified.
- The web app is **bifurcated**: the public account/identity surface (landing,
  sign-up, login, verify, account) is a separate concern from the authenticated
  product app, but both render from **one shared design system** so they look
  like one product.
- Tenancy is **hybrid**: the crawled postings/company corpus stays shared and
  platform-owned; everything a tenant produces or selects (scores, statuses,
  config, outputs) is private to that tenant.
- The datastore moves from a single SQLite file to **managed PostgreSQL +
  pgvector** so a concurrent web service is actually supported.
- Deployment is **cloud-first on Oracle Cloud (OCI)**, provisioned with
  **Terraform**, with identity, an API gateway, transactional email, and secrets
  management as first-class infrastructure.

The **TUI stays single-user and local** (SQLite, the active-user dotfile). It is
explicitly *not* made multi-tenant. The shared `harness-db` library must keep
working in both worlds (local single-tenant SQLite for the TUI/pipeline; cloud
multi-tenant Postgres for the web app).

## Decisions already made (see architecture doc for rationale)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Tenant data boundary | **Hybrid** — shared crawled postings + company facts (read-only to tenants); private per-tenant scores, statuses, JD enrichment, config, and outputs |
| D2 | Identity provider | **Self-hosted Keycloak** as the OIDC IdP; apps are OIDC relying parties; Keycloak brokers Google/GitHub/Facebook and owns email verification + magic-link |
| D3 | Cloud datastore | **Managed PostgreSQL + pgvector** (replaces SQLite + sqlite-vec in the cloud); TUI keeps SQLite locally |
| D4 | Compute (v1) | **OCI Container Instances** behind **OCI API Gateway**; OKE is the documented scale-up path, not v1 |
| D5 | Email | **OCI Email Delivery** for magic-link + verification mail (Keycloak SMTP relay) |
| D6 | Secrets | **OCI Vault** for OIDC client secrets, social-app secrets, DB creds, and the platform Anthropic credential |

Open questions that still need an answer before building are collected at the
bottom of the architecture doc.

## Scope of this phase

### In scope

1. **Identity & registration** (Keycloak realm, flows, app integration).
2. **Web bifurcation** — an `account` front-end (public) and the existing
   product app (authenticated), plus a **shared asset/design package** both import.
3. **Tenant data model** — `harness-db` gains a tenant dimension and a
   Postgres backend; shared vs. private tables per D1.
4. **Per-request tenant scoping** — the web app resolves the caller's tenant
   from the OIDC session and scopes every DB read/write to it.
5. **Tenant-aware agent runs** — `agent-runner` runs a tenant's score/prepare
   against that tenant's data and resume, not a single global mount.
6. **Cloud deployment** — Dockerized services, OCIR images, Terraform for the
   full OCI stack, API gateway, TLS, email, secrets.

### Out of scope (this phase)

- Billing / subscriptions / plan tiers (hooks left, not built).
- Making the **TUI** multi-tenant (it stays single-user/local).
- Org/team accounts (one tenant == one user for now; the schema should not
  *preclude* orgs later, but we do not build them).
- Changing the scoring algorithm or the agent prompts themselves.
- Admin console beyond what Keycloak provides out of the box.

## Phasing

Each sub-phase is independently reviewable and leaves the system working.

### Phase A — `harness-db` becomes backend-agnostic & tenant-aware

- Introduce a DB-backend abstraction so the same models run on SQLite (local)
  and Postgres (cloud). Connection resolved from config, not hard-coded.
- Add the `tenant` dimension (a tenant is the cloud analogue of spec-12's
  `uid`). Locally, there is exactly one tenant; in the cloud, many.
- Split tables into **shared** (postings, companies, embeddings) and **private**
  (`tenant_*` scores/statuses/overlays/config/outputs) per D1.
- Replace `sqlite-vec` reads with a vector abstraction that maps to `pgvector`
  in the cloud and `sqlite-vec` locally.
- Migrations: pick and wire a migration tool (Alembic) for the Postgres path.

**Done when:** the TUI + pipeline still pass against SQLite, and the same
queries run green against a Postgres test DB with two tenants whose private data
does not bleed across.

### Phase B — Identity (Keycloak) stood up

- Terraform a Keycloak deployment (container + its own Postgres schema) and a
  realm: email/magic-link flow, email verification, and Google/GitHub/Facebook
  identity providers (secrets from Vault).
- Wire OCI Email Delivery as Keycloak's SMTP.
- Define the OIDC clients the apps will use (account app, product app, API
  gateway audience).

**Done when:** a user can register + verify + log in against Keycloak in a
staging realm via every method (magic-link and each social IdP), with no app
integration yet.

### Phase C — Web bifurcation + shared design system

- Extract the current look/feel (`web/web/theme.py`, logo, Radix theme,
  `branding.md`) into a **shared design package** importable by both apps.
- Build the **account app**: landing, sign-up, login, post-verify, account/
  profile, sign-out. It is an OIDC relying party (login → Keycloak → callback).
- Make the existing **product app** an OIDC relying party too: it requires a
  valid session, resolves the tenant from the token, and 401→redirects
  unauthenticated users to the account app.

**Done when:** logging in via the account app lands the user in the product app
as the right tenant; both apps are visually one product.

### Phase D — Per-request tenant scoping + tenant-aware agents

- Replace the process-global cached engine/`get_db_path()` in `web/web/data.py`
  with per-request tenant resolution; every query carries the tenant.
- `agent-runner` accepts a tenant context and runs score/prepare against that
  tenant's private data + resume, writing outputs to that tenant's store.
- Decide and implement the agent run model (queue, concurrency caps, platform
  Anthropic credential + per-tenant quota) — see architecture doc §7.

**Done when:** two tenants can browse, score, and prepare concurrently in the
cloud with fully isolated data and outputs.

### Phase E — Cloud deployment on OCI via Terraform

- Containerize all services; push to OCIR.
- Terraform: VCN, API Gateway, Container Instances, managed Postgres, Email
  Delivery, Vault, Object Storage (outputs/resumes), Certificates, Logging.
- Local `docker-compose` adapts to 12-factor config (no host bind mounts of
  credentials; everything via env/secrets) so compose-up still works for dev and
  mirrors the cloud topology.

**Done when:** `terraform apply` from clean state yields a reachable HTTPS
deployment where a new user can register and run the full flow.

## Completion criteria

- [ ] A new user can register via email magic-link **and** via each OAuth
      provider; email is verified before product access.
- [ ] The account surface and the product app are separate apps sharing one
      design system (no forked styling).
- [ ] Postings/company corpus is shared; scores/statuses/config/outputs are
      private per tenant, with no cross-tenant leakage (proven by tests).
- [ ] Cloud runs on managed Postgres + pgvector; the TUI still runs on local
      SQLite + sqlite-vec from the same `harness-db` code.
- [ ] `agent-runner` runs are tenant-scoped (data, resume, outputs).
- [ ] The whole OCI stack is provisioned by Terraform; secrets live in Vault,
      not in images or compose files.
- [ ] `docker-compose` still brings the system up locally for development.

## Constraints

- **Do not regress the TUI / local pipeline.** `harness-db` must remain a single
  library serving both the local single-tenant SQLite world and the cloud
  multi-tenant Postgres world.
- **Simplest thing that works** (per CLAUDE.md): Container Instances over OKE for
  v1; one Keycloak realm; one Postgres; no org/team layer yet.
- **No secrets in the repo or images.** Bootstrap pointers only, as today.
- Worktree discipline still applies to all repo changes; `$JOB_DATA_ROOT` write
  exception is unchanged.
