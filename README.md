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
git clone https://github.com/your-username/automate-generator.git
```

### 2. Point your project to the skills

In your project's `.vscode/settings.json`:

```json
{
  "chat.agentSkillsLocations": {
    "/path/to/automate-generator/.github/skills": true
  }
}
```

### 3. Configure your environment

In VS Code Copilot Chat:

```
/configure-profile
```

You'll need:
- An **Azure App Registration** with API permissions for Dynamics CRM, SharePoint, Flow Service, and Microsoft Graph
- Your **Power Platform Environment ID** and **Dataverse org URL**
- A browser to complete the one-time Device Code authentication

### 4. Create your first flow

```
/create-flow Create a flow that sends a Teams notification when a new item is added to a SharePoint list
```

## Available Skills

| Skill | Trigger Keywords | Description |
|---|---|---|
| `/create-flow` | create flow, deploy flow, 创建 flow, 生成 Power Automate | End-to-end: requirements → JSON → deploy |
| `/configure-profile` | configure profile, add tenant, 配置环境 | Set up OAuth2 credentials for a new tenant |
| `/scan-environment` | scan environment, list flows, 扫描环境, learn flow | Discover flows/connectors/connections, learn components |

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
│  .github/skills/                │ ← AI reads SKILL.md for instructions
│    ├─ create-flow/SKILL.md      │
│    ├─ configure-profile/SKILL.md│
│    └─ scan-environment/SKILL.md │
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
automate-generator/
├── .github/
│   ├── skills/                        ← Agent Skills (AI entry points)
│   │   ├── create-flow/
│   │   │   ├── SKILL.md               ← 17-step SOP: requirements → deploy
│   │   │   ├── get-token.ps1          ← OAuth2 token refresh script
│   │   │   └── flow-template.json     ← Base Flow JSON template
│   │   ├── configure-profile/
│   │   │   └── SKILL.md               ← 6-step profile setup + Device Code Flow
│   │   └── scan-environment/
│   │       └── SKILL.md               ← Environment discovery + component learning
│   └── instructions/                  ← Detailed SOP references
│       ├── flow-operations.instructions.md
│       ├── token-management.instructions.md
│       └── component-library.instructions.md
├── components/                        ← Component library (learned from real flows)
│   ├── _catalog.json                  ← Full index of all components
│   ├── actions/openapi/               ← 111+ connector action templates
│   ├── connectors/                    ← 24 connector definitions
│   ├── triggers/                      ← 21 trigger templates
│   └── patterns/                      ← Multi-step composition patterns
├── profiles/                          ← Tenant credentials (gitignored)
│   └── profile-template.json          ← Template for new profiles
├── scripts/                           ← Utility scripts
│   ├── definition_to_graph.py         ← Convert Flow definition → Copilot Studio graph
│   ├── extract-components.ps1         ← Extract components from Dataverse
│   └── generate-components.ps1        ← Generate component template files
├── flow-templates/                    ← Complete flow JSON examples
│   ├── manual-hello-world.json        ← Simplest flow (button + Compose)
│   ├── email-auto-reply.json          ← Email trigger + connector pattern
│   └── scheduled-sharepoint-to-teams.json  ← Recurrence + multi-connector
├── docs/
│   └── INTEGRATION_GUIDE.md           ← How to add skills to your project
├── environments-example.json          ← Example environment scan output
└── README.md
```

## Prerequisites

| Requirement | Purpose |
|---|---|
| **VS Code** with GitHub Copilot | Runs the Agent Skills |
| **Windows PowerShell** | Executes API calls (built into Windows) |
| **Azure App Registration** | OAuth2 tokens for Power Platform APIs |
| **Power Automate license** | Required in the target tenant |
| **Python 3.x** (optional) | Only for Workflow graph generation |

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
