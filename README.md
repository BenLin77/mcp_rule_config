# mcp_rule_config

Centralized repository to manage and sync your MCP configuration and global rules. It supports:

- Cursor
- Windsurf
- Claude (Claude CLI MCP configuration)

## Files

- `global_rules.md`: Your global rules and development standards.
- `mcp_config.json`: MCP servers configuration (secrets are referenced via environment variables).
- `sync_mcp.py`: Sync script that writes files to the appropriate locations under your Home directory.

## Sync Targets

- Cursor: `~/.cursor/AGENTS.md`, `~/.cursor/mcp.json`
- Windsurf: `~/.codeium/windsurf/memories/global_rules.md`, `~/.codeium/windsurf/mcp_config.json`
- Claude: `~/.claude/CLAUDE.md` (and registers MCP servers to Claude CLI from `mcp_config.json`)

## Usage

Recommended to run with uv (Python is also fine):

```bash
# Sync files to Cursor/Windsurf/Claude and update Claude CLI MCP servers
uv run sync_mcp.py

# or
python3 sync_mcp.py
```

What the script does:

1. Copies `global_rules.md` to all targets (Cursor/Windsurf/Claude).
2. Generates Cursor's `~/.cursor/mcp.json` from your local `mcp_config.json`.
3. Generates Windsurf's `~/.codeium/windsurf/mcp_config.json` from your local `mcp_config.json`.
4. Registers MCP servers to Claude CLI (user scope) via `claude mcp add` using `mcp_config.json`.

## Environment Variables

Set these in your shell or a local `.env` (do not commit `.env`):

- `NOTION_TOKEN`: Notion API token.
- `GOOGLE_MAPS_API_KEY`: Google Maps API key (for `google-maps` MCP server).
- `SSH_PASSWORD`: Used by `ssh-mcp-server` arguments.

Example:

```bash
export NOTION_TOKEN=your_notion_token
export GOOGLE_MAPS_API_KEY=your_google_maps_api_key
export SSH_PASSWORD=your_ssh_password
```

You can copy `.env.example` to `.env` and fill in your real values locally (remember: never commit `.env`).

```bash
cp .env.example .env
```

## Security

- Always keep secrets out of version control. In `mcp_config.json` secrets are referenced as `${VAR_NAME}` placeholders.
- Use pre-commit hooks with gitleaks to block accidental secret commits.

Setup:

```bash
# Install dependencies (macOS examples)
brew install pre-commit gitleaks  # or: uv tool install pre-commit; brew install gitleaks

# Install hooks for this repo
pre-commit install

# Run against the whole repo to verify
pre-commit run --all-files
```

GitHub settings:

- Enable Secret Scanning and Push Protection in the repository settings.
- Protect the `main` branch and require PRs if possible.

## Notes

- Secrets are not stored in this repo; they are referenced as `${VAR_NAME}` placeholders in `mcp_config.json`.
- If more secrets are added later, switch them to environment variables before committing.
