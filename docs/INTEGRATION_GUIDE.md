# How to Use Automate Generator Skills in Your Project

## Quick Setup (2 minutes)

### 1. Add skill location to your project

Create or edit `.vscode/settings.json` in your project:

```json
{
  "chat.agentSkillsLocations": {
    "D:/A_Code/Automate Generator-public/.github/skills": true
  }
}
```

> **Note**: Replace the path with wherever you cloned this repo. Use forward slashes `/`.

### 2. Configure your environment (first time only)

In VS Code Copilot Chat, type:

```
/configure-profile
```

Follow the prompts to:
- Provide your Azure App Registration credentials
- Complete Device Code authentication in your browser
- Save the profile to `profiles/{name}.json`

### 3. Start creating flows

```
/create-flow Create a flow that sends a Teams notification when a new SharePoint list item is created
```

Or:

```
/scan-environment List all flows in my environment
```

## Profile Linking

If your project frequently uses a specific profile, add a hint in your project's `.github/copilot-instructions.md`:

```markdown
## Power Automate

Default Automate Generator profile: `contoso-prod`
Environment: Production
```

The AI will pick up this hint and auto-load the correct profile.

## Available Skills

| Command | What it does |
|---|---|
| `/create-flow` | Generate and deploy a Power Automate flow from a natural language description |
| `/configure-profile` | Set up credentials for a new Power Platform environment |
| `/scan-environment` | Discover flows, connectors, connections in an environment; learn new components |

## Troubleshooting

| Issue | Solution |
|---|---|
| Skills don't appear in Copilot Chat | Check the path in `settings.json` uses forward slashes and is absolute |
| "No valid refreshToken" error | Run `/configure-profile` to re-authenticate |
| "AADSTS65001" permission error | Grant admin consent for the App Registration in Azure Portal |
| Flow created but not visible | Wait 30 seconds, then check in Power Automate portal. POST may return error but flow was created |
