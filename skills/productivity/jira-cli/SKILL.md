---
name: jira-cli
description: "Jira CLI workflows using ankitpokhrel/jira-cli; no MCP server required."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
prerequisites:
  commands: [jira]
metadata:
  hermes:
    tags: [Jira, CLI, Issues, Project-Management, Atlassian]
    category: productivity
---

# Jira CLI

Use `jira` for Jira work instead of a Jira MCP server. Prefer non-interactive commands (`--plain`, `--raw`, `--no-input`, explicit issue keys) so tool output stays compact and reproducible.

## Auth And Config

Check availability first:

```bash
jira version
jira me 2>/dev/null || jira init
```

In the Hermes Docker image, the entrypoint sets:

```bash
JIRA_CONFIG_FILE=$HOME/.config/.jira/.config.yml
```

With `HOME=/opt/data/home`, this persists under the mounted Hermes data volume.

For Jira Cloud, set `JIRA_API_TOKEN` before `jira init`. For Jira Server/Data Center with PAT auth, also set `JIRA_AUTH_TYPE=bearer`.

## Read Work

```bash
jira me
jira project list --plain
jira board list --plain
jira issue list --plain
jira issue list --raw
jira issue list -a$(jira me) --plain
jira issue list -q 'status != Done ORDER BY updated DESC' --plain
jira issue view TIP-123
```

Use `--raw` when you need structured data and pipe to `jq` for narrow output:

```bash
jira issue list --raw | jq '.issues[] | {key, summary, status: .status.name}'
```

## Create And Update Issues

Use explicit flags plus `--no-input` when creating or editing from an agent turn:

```bash
jira issue create \
  -tTask \
  -s"Short imperative title" \
  -b"Detailed description" \
  --no-input

jira issue edit TIP-123 -s"Updated title" --no-input
jira issue assign TIP-123 $(jira me)
jira issue move TIP-123 "In Progress"
jira issue comment add TIP-123 "Concise progress update"
```

If the user says "team X" in project `TIP`, remember the repo-level Jira mapping: set Team field `customfield_10991` when using Jira API flows. If the CLI cannot set the needed custom field ergonomically, say so and use the smallest REST call instead of opening an MCP server.

## Sprints And Releases

```bash
jira sprint list --table --plain
jira sprint list --current --plain
jira sprint add SPRINT_ID TIP-123
jira release list --plain
```

## Agent Rules

- Do not launch the interactive browser/UI flow unless the user asks for it.
- Use `--plain`, `--raw`, or `--no-input` by default.
- Quote JQL strings.
- Prefer `jira issue view KEY` before editing so you do not overwrite context blindly.
- Keep outputs narrow; Jira issue lists can be noisy.
