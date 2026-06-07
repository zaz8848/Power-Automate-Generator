# How to Use Automate Generator Skills in Your Project

## Quick Setup (2 minutes)

### 1. Add skill **and** instruction locations to your project

Create or edit `.vscode/settings.json` in your project:

```json
{
  "chat.agentSkillsLocations": {
    "D:/A_Code/_DevTool/Power-Automate-Generator/.github/skills": true
  },
  "chat.instructionsFilesLocations": {
    "D:/A_Code/_DevTool/Power-Automate-Generator/.github/instructions": true
  }
}
```

> Replace the path with wherever you cloned this repo. Use forward slashes `/` even on Windows.

> **Why both settings?**
> - `chat.agentSkillsLocations` loads the `/create-flow` / `/describe-component` / ... slash commands (entry points).
> - `chat.instructionsFilesLocations` loads the always-on deep SOP files (API endpoints, body shape, 30+ verified pitfalls) that those skills call into.
>
> Wiring only the skills will still "work" but the agent loses the deep API knowledge and will hit avoidable bugs (wrong token scope, missing connectionReference fields, Copilot Studio plan switch forgotten, etc.).

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
| `/describe-component` | Print inputSchema / outputSchema / known pitfalls / graphTemplate for a component |
| `/learn-component` | Pull Swagger and write a new component file when nothing matches |
| `/scan-environment` | Discover flows, connectors, connections in an environment; learn new components |
| `/configure-profile` | Set up credentials for a new Power Platform environment |
| `/report-issue` | Append a feedback entry to a single rolling file in your workspace (see below) |

## Troubleshooting & Feedback

If a skill misbehaves or a component schema is wrong, use `/report-issue`. The agent appends a sanitized entry to the **single** file:

```
{your-workspace}/.copilot-feedback/power-automate-generator.md
```

Every `/report-issue` invocation appends to the **same** file — no clutter, no scattered notes. The file is yours; the agent never modifies anything outside your workspace, never uploads to the internet, and strips tokens/secrets/org URLs before writing.

When ready, share the file with the maintainer:

- Open a GitHub Issue at [zaz8848/Power-Automate-Generator](https://github.com/zaz8848/Power-Automate-Generator/issues) and paste the file contents
- Or attach the file to an email / chat to the maintainer

The maintainer triages in their private lab repo and pushes sanitized fixes back to this public repo, so the next `git pull` brings the improvements.

| Issue | Solution |
|---|---|
| Skills don't appear in Copilot Chat | Check the path in `settings.json` uses forward slashes and is absolute |
| "No valid refreshToken" error | Run `/configure-profile` to re-authenticate |
| "AADSTS65001" permission error | Grant admin consent for the App Registration in Azure Portal |
| Flow created but not visible | Wait 30 seconds, then check in Power Automate portal. POST may return error but flow was created |
| Something else / skill SOP unclear | Use `/report-issue` and share the file — see above |
