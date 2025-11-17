# mcp_rule_config

> Locale sync: keep this README as the single source of truth. If translations are added in the future, they must mirror this file.

Centralized repository to manage and sync MCP configuration, global rules, and Windsurf workflows. Targets:

- Cursor
- Windsurf
- Claude (Claude CLI MCP configuration)

## Project Files

- `global_rules.md`: Global standards and documentation workflow.
- `mcp_config.json`: MCP server configuration (secrets referenced via env vars).
- `workflows/`: Windsurf workflow descriptions (Markdown).
- `sync_mcp.py`: Sync script that expands env vars, generates temp files, and writes data to target locations.

## Sync Targets

- Cursor: `~/.cursor/AGENTS.md`, `~/.cursor/mcp.json`
- Windsurf:
  - `~/.codeium/windsurf/mcp_config.json`
  - `~/.codeium/windsurf/memories/global_rules.md`
  - `~/.codeium/windsurf/workflows/**/*.md` (workflow subfolders preserved; if agent names collide the script removes the old version first)
- Claude: `~/.claude/CLAUDE.md` and MCP registrations via `claude mcp add`

> Paths are resolved via the user home directory, so the script works on macOS, Linux, and Windows.

## Usage

Prefer running with `uv` (plain `python3` also works):

```bash
# Sync Cursor / Windsurf / Claude configs and update Claude CLI MCP servers
uv run sync_mcp.py

# or
python3 sync_mcp.py
```

### What the script does

1. Reloads `.env`, `~/.env`, and fish-login environment variables, then expands `mcp_config.json` placeholders.
2. Generates a temp `mcp_config.json` and writes it to Cursor and Windsurf targets.
3. Registers MCP servers with Claude CLI (user scope) and prunes obsolete entries.
4. Copies `global_rules.md` to all destinations.
5. Copies every `workflows/**/*.md` file to `~/.codeium/windsurf/workflows/`, preserving folder structure and deduplicating agents by name.

## Environment Variables

Set these in your shell or local `.env` (never commit `.env`):

- `NOTION_TOKEN`
- `GOOGLE_MAPS_API_KEY`
- `SSH_PASSWORD`
- Any other `${VAR_NAME}` referenced in `mcp_config.json`

Example:

```bash
export NOTION_TOKEN=your_notion_token
export GOOGLE_MAPS_API_KEY=your_google_maps_api_key
export SSH_PASSWORD=your_ssh_password
```

Copy `.env.example` to `.env` for local use:

```bash
cp .env.example .env
```

## Security Practices

- Keep secrets out of version control; always reference them via env vars.
- Enable `pre-commit` + `gitleaks` in this repo:

```bash
# macOS example
brew install pre-commit gitleaks
# or via uv
uv tool install pre-commit

pre-commit install
pre-commit run --all-files
```

- In GitHub, enable Secret Scanning, Push Protection, and protect the `main` branch.

## Notes

- `${VAR_NAME}` placeholders must resolve to real env vars; the script reloads them before syncing.
- Adding new workflows only requires running `sync_mcp.py`; agent-name clashes automatically replace older files.
- Extend `sync_to_editors` or add helper functions if new editors need support.
