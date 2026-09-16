# PowerBIReportServerSmith

*An AlaForge product*

**An MCP server for the full Power BI semantic model lifecycle** — quality
audit, naming, a Staging → Dim/Fact workflow, relationships, AI-readiness for
Copilot, and deployment to an on-premises Power BI Report Server.

[![Tests](https://github.com/Alaeddin-Ebrahimi/powerbi-report-server-smith/actions/workflows/tests.yml/badge.svg)](https://github.com/Alaeddin-Ebrahimi/powerbi-report-server-smith/actions/workflows/tests.yml)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)

Built by **Ala** — BI Solutions & Data Engineering, Power Platform / Microsoft
Fabric / Snowflake / AI Agents.
YouTube: **[Data With Ala](https://www.youtube.com/@DataWithAla)** ·
Contact: ebrahimy.alaeddin@ebrahimy *(verify this domain before relying on it — see note at bottom)*

> This is an independent, community-built project. It is not affiliated with,
> endorsed by, or connected to Microsoft Corporation. "Power BI" and "Power BI
> Report Server" are Microsoft trademarks, referenced here only to describe
> compatibility.

---

## Why this exists

Most Power BI + AI tooling stops at "let an LLM query my model." PowerBIReportServerSmith
is aimed one level earlier: **is the model itself actually good** — is every
table classified fact or dimension, is naming consistent, is it documented
well enough for Copilot to use, and can it get from a developer's Desktop
file onto an intranet report server without a manual deployment process.
It's a full pipeline, not a single trick.

## How it works

Three layers, each doing a distinct job:

1. **TMDL parsing (`tmdl/`)** — reads a Power BI Project's (`.pbip`) text-based
   semantic model definition directly off disk: tables, columns, measures,
   relationships, descriptions. No live Desktop connection required for this
   layer, which is what makes the audit tools fast and safe to run constantly.
2. **Audits (`audit/`)** — run against the parsed model and return structured
   findings, never silent fixes:
   - `star_schema_audit` — classifies every table fact/dimension/bridge/date/
     disconnected by relationship topology, cross-checked against column shape
   - `naming_audit` — flags convention violations and the same concept spelled
     two different ways across tables
   - `relationship_gap_report` — missing/inactive relationships, many-to-many
     pairs that need a bridge table, a missing date dimension
   - `ai_readiness_score` — description coverage and Copilot-readiness signals
3. **Workflow + writes (`workflow.py`, `modeling.py`)** — the staging→Dim/Fact
   pipeline: tag a new table as `Staging`, and `promote_staging_to_group`
   refuses to move it into `Dim`/`Fact` until the audits above are clean for
   it (or you explicitly override with `force=True`). Relationship creation
   and description writes are targeted, line-level TMDL edits — never a full
   file rewrite — so nothing else in the file changes.

Once the model itself is in good shape, the **deployment layer (`pbirs.py`)**
pushes it to an on-premises **Power BI Report Server** over its REST API
(NTLM auth) — the piece general-purpose Power BI MCP servers skip, since
they're all built for cloud/Fabric auth instead.

## Status — what's tested vs. what isn't

| Layer | Status |
|---|---|
| TMDL parsing, all four audits, staging/Dim/Fact workflow, relationship & description writes | **Built and tested** — 18 unit tests, run automatically on every push via GitHub Actions (see badge above) |
| Power BI Report Server deployment (`pbirs_*` tools) | Built to the documented REST API v2.0 spec — **not yet verified against a live server**. Test against a non-production PBIRS instance before trusting it with anything real. |
| Live Power BI Desktop connection (TOM/ADOMD) | Not in this version — everything here works against `.pbip`/TMDL files on disk |

## Known limitation: Power Query "query group" folders

Power Query Editor's own query-group folders (what you'd see in the Queries
pane) live in a part of the PBIP format this project doesn't have verified
write access to. Rather than guess and risk a file Desktop can't open,
Staging/Dim/Fact membership is tracked in a sidecar file
(`.pbirs_smith/state.json`) and mirrored onto the standard `displayFolder` TOM
property — safe, documented, and tested. Set the literal Editor folder by
hand in Desktop for now if that specific view matters to you.

## Install

```bash
git clone https://github.com/Alaeddin-Ebrahimi/powerbi-report-server-smith.git
cd powerbi-report-server-smith
pip install -e .
# or: pip install -r requirements.txt

# Only if you're using the Power BI Report Server deployment tools:
pip install requests_ntlm2
```

Confirm your install works:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Set up in VS Code

VS Code (GitHub Copilot Chat, Agent mode) reads MCP servers from
`.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "powerbi-report-server-smith": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "powerbi_report_server_smith.server"],
      "env": { "PYTHONPATH": "${workspaceFolder}/src" },
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

Command Palette → **MCP: List Servers** to confirm it's picked up. VS Code
will ask you to trust the server the first time you start it — expected.

Copy `.env.example` to `.env` and fill in `PBIRS_*` values only if you're
using the deployment tools. `.env` is git-ignored.

## Try it against the bundled sample project

`examples/SampleProject.SemanticModel/` is a small, deliberately-imperfect
star schema (Sales fact, Customer/Product dimensions, a Calendar date table,
a disconnected Notes table, and one badly-named column) — a safe first test
before pointing this at a real model. In VS Code chat, once the server's
running:

> "Run a star schema audit on examples/SampleProject.SemanticModel"

Expected: Sales=fact, Customer/Product=dimension, Calendar=date,
Notes=disconnected, plus a naming flag on `prod_nm`.

## Tool reference

**Audit (read-only)**
`star_schema_audit` · `naming_audit` · `relationship_gap_report_tool` · `ai_readiness_score`

**Staging → Dim/Fact workflow**
`label_new_query_stage` · `list_staging_queries` · `create_query_group` ·
`list_query_groups` · `promote_staging_to_group` *(gated on the audits above unless `force=True`)*

**Relationships & metadata**
`create_relationship` · `revise_many_to_many` *(recommends, doesn't silently rewrite)* ·
`set_table_description` · `set_column_description` · `bulk_apply_descriptions`

**Power BI Report Server** *(unverified — see status table)*
`pbirs_list_folders` · `pbirs_create_folder` · `pbirs_list_catalog_items` ·
`pbirs_upload_report` · `pbirs_list_subscriptions` · `pbirs_trigger_refresh_plan`

`project_path` accepts a `.pbip` root, a `*.SemanticModel` folder, or a
`definition/` folder directly.

## Safety

- `PBIRS_SMITH_READONLY=true` (env var or `config/policies.yaml`) blocks every
  write tool; audits keep working.
- `promote_staging_to_group` refuses to promote until the star-schema and
  naming audits are clean for that table, unless `force=True`.
- No credentials are hardcoded anywhere — PBIRS auth reads from environment
  variables only, and `.env` is git-ignored.

## Project layout

```
src/powerbi_report_server_smith/
  tmdl/        parser, loader, writer — the foundation everything else uses
  audit/       star_schema, naming, relationships, ai_readiness
  workflow.py  staging / groups / gated promotion
  modeling.py  relationship + description writes
  pbirs.py     Power BI Report Server REST client (unverified — see status)
  server.py    MCP tool registration
config/policies.yaml   naming rules, group names, safety defaults
examples/               sample project used by the test suite
tests/                  18 unit tests, run on every push via CI
```

## Roadmap

- [ ] Verify the PBIRS deployment layer against a real report server
- [ ] Live Power BI Desktop connection (TOM/ADOMD) for interactive sessions
- [ ] Report/visual-layer (PBIR) authoring

Contributions and issue reports welcome.

## License

MIT — see [LICENSE](LICENSE).

---
*Contact email above may be missing its domain suffix — worth double-checking before anyone relies on it.*
# powerbi-report-server-smith
