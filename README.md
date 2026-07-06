# Automate Generator

> AI-driven Power Automate Cloud Flow generator — packaged as GitHub Copilot Agent Skills.

Describe what you want in natural language → AI assembles the Flow JSON → deploys to your Power Platform environment. No manual JSON editing, no portal clicking.

## Features

- **Natural language → deployed flow**: Describe your automation need, get a working flow
- **Component library**: 111+ OpenAPI actions, 21 triggers, 17 built-in types — learned from real production flows
- **Multi-tenant support**: Configure multiple environments via profile files
- **Workflow support**: Generate Copilot Studio Workflows with visual graph canvas
- **Battle-tested**: Comprehensive pitfall documentation from real-world deployments

## Quick Start

### 1. Clone this repository

```bash
git clone https://github.com/zaz8848/Power-Automate-Generator.git
cd Power-Automate-Generator
pip install requests
```

### 2. Point your project to the skills **and** instructions

In your project's `.vscode/settings.json`:

```json
{
  "chat.agentSkillsLocations": {
    "/path/to/Power-Automate-Generator/.github/skills": true
  },
  "chat.instructionsFilesLocations": {
    "/path/to/Power-Automate-Generator/.github/instructions": true
  }
}
```

> Use forward slashes `/` even on Windows. Replace `/path/to/` with where you cloned the repo.
>
> **Why both?** Skills (`.github/skills/`) are the slash-command entry points (`/create-flow`, etc.). Instructions (`.github/instructions/`) carry the deep SOP each skill calls into (token management, flow operations API endpoints, component-library rules, 30+ verified pitfalls). Without `chat.instructionsFilesLocations` the skills still load, but the agent loses the deep API knowledge and will hit avoidable bugs.

### 3. Configure your tenant + environment(s)

```bash
cp profiles/profile-template.json profiles/<your-tenant>.json
# Edit profiles/<your-tenant>.json: fill tenantId, clientId, clientSecret
# and add one or more entries to environments[]
```

Then in VS Code Copilot Chat:

```
/configure-profile
```

The skill walks you through:

- Creating an **Azure App Registration** (5 minutes; needs Global Admin or Application Administrator to grant consent) with permissions for Dynamics CRM / Power Automate / PowerApps Service / Microsoft Graph (+ optional SharePoint / Approvals)
- Filling the profile file with tenantId / clientId / clientSecret
- Listing every Power Platform environment under that tenant in `environments[]`
- Running `python scripts/configure_profile.py profiles/<your-tenant>.json` once to do the **Authorization Code Flow** in your browser and persist a `refreshToken`

**Profile schema v2** — one file per Azure AD tenant. Top-level keys carry tenant-wide OAuth credentials; `environments[]` lists all Power Platform environments under that tenant. Switch envs at runtime without re-OAuth:

```bash
# List environments under this profile
python scripts/configure_profile.py profiles/contoso.json --list

# Change the default env (no OAuth)
python scripts/configure_profile.py profiles/contoso.json --set-default "prod"

# Get an access token for a specific env (uses the stored refreshToken)
python scripts/configure_profile.py profiles/contoso.json --env "dev" --get-token

# Sanity-check by calling Dataverse WhoAmI on that env
python scripts/configure_profile.py profiles/contoso.json --env "dev" --whoami
```

For multiple tenants (e.g. Contoso + Fabrikam), create one profile file per tenant. `/create-flow` and `/scan-environment` read the default profile + default env unless you say "use the fabrikam profile, prod env" in chat.

### 4. Create your first flow

```
/create-flow Create a flow that sends a Teams notification when a new item is added to a SharePoint list
```

## Available Skills

| Skill | Trigger Keywords | Description |
|---|---|---|
| `/create-flow` | create flow, deploy flow, 创建 flow, 生成 Power Automate | End-to-end: **prototype → describe → learn → deploy**. Refuses to skip the prototype confirmation step. |
| `/describe-component` | describe component, 查组件 | Print inputSchema / outputSchema / known pitfalls / graphTemplate for a component. **Refuses to invent params from memory.** |
| `/learn-component` | learn component, 学习组件 | Pull Swagger → write `components/actions/openapi/*.json` → update `_catalog.json`. Marks `verified=false` until a real deployment confirms. |
| `/scan-environment` | scan environment, list flows, 扫环境, learn flow | Discover flows / connectors / connection references; optional `learn` mode batches `/learn-component`. |
| `/configure-profile` | configure profile, add tenant, 配置环境 | Set up OAuth2 credentials for a new tenant (Device Code Flow). |
| `/report-issue` | report issue, 反馈, this skill is wrong, 报个 bug | Append a feedback entry to **`feedback/{your-project-name}.md`** in this tool repo (one file per consuming project, append-only). Auto-sanitizes tokens/URLs/emails. Requires a writable local clone of this repo. |

## Feedback Loop

Found a pitfall? Component schema looks off? A skill's SOP is unclear? Run `/report-issue` in chat. The agent will:

1. Collect context (which skill/component/error, expected vs actual, repro steps)
2. Strip secrets (Bearer tokens, client_secret, org URLs, emails)
3. Show you the draft, then **append** it to `feedback/{your-project-name}.md` in this tool repo

One file per consuming project (e.g. `feedback/Echo-Service.md`), append-only — a rolling log you fully control. The maintainer triages all `feedback/*.md` files in the private lab repo and syncs fixes back here, so a future `git pull` brings the fix. (Requires a writable local clone; if you only reference the skills remotely, paste the feedback to the maintainer or open a GitHub Issue at [zaz8848/Power-Automate-Generator](https://github.com/zaz8848/Power-Automate-Generator/issues).)

## Three-layer Design

| Layer | Folder | Loaded by (VS Code setting) | Role |
|---|---|---|---|
| 1️⃣ Skills | `.github/skills/<name>/SKILL.md` | `chat.agentSkillsLocations` | Slash-command entry points; flow skeleton + mandatory steps |
| 2️⃣ Instructions | `.github/instructions/*.instructions.md` | `chat.instructionsFilesLocations` | Always-loaded deep SOP — API endpoints, body shapes, pitfalls |
| 3️⃣ Data | `components/` + `scripts/` + `profiles/` | Skills reference at runtime | Concrete schemas + executable PowerShell/Python helpers |

Skills are intentionally short (the "what"). Instructions carry the heavy detail (the "how"). Both must be wired in `settings.json` for the agent to behave correctly.

## How It Works

```
┌─────────────────────────────────┐
│  Your Project (any VS Code)     │
│  .vscode/settings.json          │
│    └─ chat.agentSkillsLocations │──→ Points to this repo's skills
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  Automate Generator (this repo) │
│                                 │
│  .github/skills/                │ ← 1️⃣ chat.agentSkillsLocations (slash commands)
│    ├─ create-flow/SKILL.md      │    NL → prototype → describe → learn → deploy
│    ├─ describe-component/SKILL.md  Component contract reader
│    ├─ learn-component/SKILL.md     Swagger → component file writer
│    ├─ scan-environment/SKILL.md    Environment / flow / connector scanner
│    └─ configure-profile/SKILL.md   Tenant profile + Device Code Flow
│                                 │
│  .github/instructions/          │ ← 2️⃣ chat.instructionsFilesLocations (deep SOP)
│    ├─ flow-operations.instructions.md       Flow CRUD / API endpoints / 30+ pitfalls
│    ├─ token-management.instructions.md      4-scope OAuth2 refresh template
│    └─ component-library.instructions.md     Component query / learning SOP
│                                 │
│  components/                    │ ← Pre-learned action/trigger templates
│    ├─ _catalog.json             │
│    ├─ actions/openapi/          │
│    ├─ connectors/               │
│    └─ triggers/                 │
│                                 │
│  profiles/                      │ ← Your tenant credentials (gitignored)
│  scripts/                       │ ← Helper scripts (graph conversion, etc.)
└─────────────────────────────────┘

         ↓ AI executes via PowerShell

┌─────────────────────────────────┐
│  Microsoft REST APIs            │
│  ├─ Flow Management API         │ ← Create/update/query flows
│  ├─ Dataverse Web API           │ ← Connection references, workflows
│  ├─ PowerApps API               │ ← Connectors, Swagger schemas
│  └─ SharePoint / Graph          │ ← Supporting data
└─────────────────────────────────┘
```

## Project Structure

```
Power-Automate-Generator/
├── .github/
│   ├── skills/                        ← Agent Skills (`/`-triggered AI entry points)
│   │   ├── create-flow/SKILL.md       ← NL → prototype → describe → learn → deploy
│   │   ├── describe-component/SKILL.md   Component contract reader
│   │   ├── learn-component/SKILL.md      Swagger → component file writer (with canvas-native node guard)
│   │   ├── scan-environment/SKILL.md     3 modes: list / scan-all-workflows / learn-graph-templates
│   │   ├── configure-profile/SKILL.md    Tenant onboarding + multi-env management
│   │   └── report-issue/SKILL.md         Append sanitized feedback to your local rolling log
│   └── instructions/                  ← Deep SOP (always-loaded via `chat.instructionsFilesLocations`)
│       ├── flow-operations.instructions.md       Flow CRUD API + 30+ verified pitfalls
│       ├── token-management.instructions.md      4-scope OAuth2 refresh template + scope table
│       └── component-library.instructions.md     Component query / learning SOP + graphTemplate spec
├── components/                        ← Component library (learned from 87+ real flows across 32 envs)
│   ├── _catalog.json                  ← Full index
│   ├── actions/                       ← 17 built-in + agent-node.json (canvas-native AI node)
│   │   └── openapi/                   ← 113 connector action templates with graphTemplate fields
│   ├── connectors/                    ← 29 connector definitions (with swaggerUrl)
│   ├── triggers/                      ← 21 trigger templates
│   └── patterns/                      ← 2 multi-step composition patterns
├── profiles/                          ← Tenant credentials (gitignored — schema v2: tenant + environments[])
│   └── profile-template.json          ← Copy + fill this; one file per tenant
├── scripts/                           ← Utility scripts (all Python; PowerShell legacy phased out)
│   ├── configure_profile.py           ← OAuth + multi-env CLI (5 subcommands)
│   ├── scan_all_envs.py               ← Pull Workflow JSON from every env in environments.json
│   ├── extract_graph_templates.py     ← Mine graphTemplate from local workflow JSON → component files
│   ├── definition_to_graph.py         ← Convert Flow definition → Copilot Studio graph (Workflow only)
│   └── generate_test_pdf.py           ← Generate test PDF knowledge files
├── docs/
│   └── INTEGRATION_GUIDE.md           ← How to wire skills + instructions into your project
└── README.md
```

## Prerequisites

| Requirement | Purpose |
|---|---|
| **VS Code** with GitHub Copilot Chat | Loads the Agent Skills + Instructions |
| **PowerShell 5.1 / 7** | Built into Windows; used by some helper scripts |
| **Python 3.10+** with `requests` | OAuth flow, env scanning, graph template extraction, definition→graph conversion |
| **Azure App Registration** | OAuth2 tokens for Power Platform APIs (see `/configure-profile` SKILL) |
| **Power Automate license** | Required in the target tenant |
| **Global Admin / Application Administrator** (one-time) | To grant admin consent on the App Registration's API permissions |

## Supported Flow Types

| Type | Description | Graph Canvas |
|---|---|---|
| **Regular PA flow** | Standard Power Automate cloud flow | No |
| **Agent flow** | Uses Copilot Studio agent connector actions | No |
| **Workflow** | Full Copilot Studio Workflow with visual canvas | Yes |

## Component Library

The component library (`components/`) contains templates learned from real production flows:

- **111 OpenAPI actions** across 24 connectors (SharePoint, Outlook, Teams, Dataverse, etc.)
- **21 triggers** (manual, scheduled, email, webhook, virtual agent, etc.)
- **17 built-in types** (Compose, Condition, ForEach, Switch, HTTP, ParseJSON, etc.)
- **2 patterns** (multi-step compositions for common scenarios)

Each component includes:
- `template` — Ready-to-use clientdata fragment
- `inputSchema` / `outputSchema` — From Swagger, for parameter validation
- `parameters` — Parameter definitions with example values
- `graphConvertible` — Whether it can auto-convert to Copilot Studio graph nodes

To add new components, use the `/scan-environment` skill's "learn flow" capability.

## Security Notes

- **Profiles are gitignored**: `profiles/*.json` (except `profile-template.json`) are excluded from version control
- **No hardcoded credentials**: All credentials are read from profile files at runtime
- **OAuth2 Refresh Token flow**: Tokens auto-renew; manual re-auth only needed every ~90 days
- **Read-before-write safety**: The `/create-flow` skill checks for existing flows before creating duplicates

## Known Limitations

- Component learning requires access to the source flow's environment
- Copilot Studio Workflows require the `definition_to_graph.py` script (Python 3.x)
- "Unpublished active row" errors in Copilot Studio are unrecoverable — flow must be recreated
- Agent `contentUrl` attachments require SharePoint sharing links, not direct file paths

## Contributing

1. **Learn new components**: Use `/scan-environment` to learn flows from your environment
2. **Report pitfalls**: Open an issue with the error message, symptom, and fix
3. **Add patterns**: Create multi-step composition templates in `components/patterns/`

## License

MIT
