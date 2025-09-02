# mcp_rule_config

This repository stores a backup of your Windsurf MCP configuration files.

> **⚠️ IMPORTANT: Currently only supports Claude code and Windsurf** ⚠️

## Files

- `global_rules.md`: Your global customization rules and development standards.
- `mcp_config.json`: MCP servers configuration. Sensitive values are referenced via environment variables to avoid committing secrets.

## Usage

For convenient access to `global_rules.md`, create a symbolic link (soft link) in your project:

```bash
# Execute in your project root directory
ln -s /path/to/this/repo/global_rules.md ./global_rules.md
```

This allows you to reference the global rules directly in your project without copying the file.

## Environment Variables

Set these variables in your shell or a local `.env` (do not commit `.env`):

- `NOTION_TOKEN`: Notion API token (used in `OPENAPI_MCP_HEADERS`).
- `GOOGLE_MAPS_API_KEY`: Google Maps API key for the `google-maps` MCP server.
- `SSH_PASSWORD`: Password for the `ssh-mcp-server` command argument.

Example (shell):

```bash
export NOTION_TOKEN=your_notion_token
export GOOGLE_MAPS_API_KEY=your_google_maps_api_key
export SSH_PASSWORD=your_ssh_password
```

## Notes

- Secrets are not stored in this repo. They are referenced as `${VAR_NAME}` placeholders inside `mcp_config.json`.
- If additional secrets appear in your configs later, convert them to environment variables before committing.
