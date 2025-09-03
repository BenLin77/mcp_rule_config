#!/usr/bin/env python3
"""
Automatically sync MCP config to Claude CLI and global rules to Cursor paths
Default config path resolved relative to this script or $HOME/code/mcp_rule_config/mcp_config.json
"""
import json
import subprocess
import sys
import shutil
from pathlib import Path
import platform
import os
import re


def load_mcp_config():
    """Load MCP configuration file"""
    # Use current script directory to find config file
    script_dir = Path(__file__).parent.resolve()
    config_path = script_dir / "mcp_config.json"
    
    # Ubuntu/Linux support - fallback to traditional path if needed
    if not config_path.exists() and platform.system().lower() == "linux":
        home = Path.home()
        config_path = home / "code/mcp_rule_config/mcp_config.json"
    
    if not config_path.exists():
        print(f"Error: Config file not found {config_path}")
        sys.exit(1)
        
    print(f"Loading config: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _resolve_string_env(s: str, env: dict) -> str:
    """Replace ${VAR} placeholders in a string using provided env.

    - 僅替換 ${VAR} 型式；若變數不存在，保留原字串並印出警告。
    - 也支援 $VAR 透過 os.path.expandvars，但以 ${} 為主。
    """
    # 先找出所有 ${VAR}
    pattern = re.compile(r"\$\{([^}]+)\}")

    def repl(match: re.Match) -> str:
        var = match.group(1)
        if var in env and env[var] is not None:
            return str(env[var])
        else:
            print(f"Warning: Environment variable '{var}' not set; leaving placeholder as-is")
            return match.group(0)

    replaced = pattern.sub(repl, s)
    # 額外處理 $VAR（若存在）
    replaced = os.path.expandvars(replaced)
    return replaced


def resolve_env_placeholders(obj, env: dict = None):
    """Recursively resolve ${VAR} placeholders in a JSON-like object.

    - 支援 dict / list / str；其他型別直接回傳。
    - 預設使用當前 process 的環境變數。
    """
    if env is None:
        env = os.environ

    if isinstance(obj, dict):
        return {k: resolve_env_placeholders(v, env) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [resolve_env_placeholders(v, env) for v in obj]
    elif isinstance(obj, str):
        return _resolve_string_env(obj, env)
    else:
        return obj


def get_resolved_mcp_config():
    """Load and resolve environment placeholders in MCP config.

    回傳一份已將 ${VAR} 替換為實際環境值的配置。
    """
    raw = load_mcp_config()
    return resolve_env_placeholders(raw)


def get_existing_servers():
    """Get existing MCP server list"""
    existing = set()
    try:
        result = subprocess.run(['claude', 'mcp', 'list'], 
                              capture_output=True, text=True, check=False)
        
        # Parse output to find server names
        lines = result.stdout.strip().split('\n')
        for line in lines:
            # Skip empty lines and header lines
            if not line or 'Checking MCP server health' in line or line.startswith(' ') or not ':' in line:
                continue
            
            # Extract server name (format: server_name: command - status)
            if ': ' in line and (' - ' in line):
                server_name = line.split(':')[0].strip()
                existing.add(server_name)
                print(f"Found existing server: {server_name}")
                
    except subprocess.CalledProcessError as e:
        print(f"Warning: Unable to fetch existing settings - {e}")
    
    print(f"Existing server count: {len(existing)}")
    return existing


def add_mcp_server(name, config):
    """Add a single MCP server to the global settings"""
    try:
        cmd = ['claude', 'mcp', 'add', '--scope', 'user', name, config['command']]  # write to user scope
        args = config.get('args', [])
        
        # Filter and process arguments
        for arg in args:
            if arg == '-y':  # skip -y argument
                continue
            cmd.append(arg)
        
        print(f"Adding MCP server to global: {name}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ Successfully added to global: {name}")
        
        # If env vars are required, show a reminder
        if 'env' in config and config['env']:
            print(f"Note: {name} requires environment variables: {list(config['env'].keys())}")
            
        return True
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        
        # If it's an 'already exists' error, treat as success
        if "already exists" in error_msg:
            print(f"✓ {name} already exists in global settings")
            return True
            
        print(f"✗ Failed to add to global {name}: {error_msg}")
        return False


def sync_global_rules():
    """Sync global_rules.md to Cursor, Windsurf, and Claude paths under HOME"""
    # Source file path
    script_dir = Path(__file__).parent.resolve()
    source_file = script_dir / "global_rules.md"
    
    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}")
        return False
    
    # Target paths: Cursor, Windsurf, Claude
    home = Path.home()
    target_paths = [
        home / ".cursor/AGENTS.md",  # Cursor
        home / ".codeium/windsurf/memories/global_rules.md",  # Windsurf
        home / ".claude/CLAUDE.md",  # Claude
    ]
    
    # Create directories if they don't exist and copy the file
    success_count = 0
    for target_path in target_paths:
        try:
            # Create parent directories if they don't exist
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source_file, target_path)
            print(f"✓ Successfully copied to: {target_path}")
            success_count += 1
        except Exception as e:
            print(f"✗ Failed to copy to {target_path}: {e}")
    
    print(f"\nGlobal rules sync complete! Success: {success_count}/{len(target_paths)}")
    return success_count > 0


def sync_cursor_mcp_json():
    """Sync local mcp_config.json to Cursor's mcp.json under HOME"""
    home = Path.home()
    target_path = home / ".cursor/mcp.json"
    try:
        # 讀取並展開環境變數
        config = get_resolved_mcp_config()
        # Ensure parent exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        # Write JSON with UTF-8 and pretty formatting
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✓ Successfully wrote Cursor MCP config: {target_path}")
        return True
    except Exception as e:
        print(f"✗ Failed to write Cursor MCP config to {target_path}: {e}")
        return False


def sync_windsurf_mcp_json():
    """Sync local mcp_config.json to Windsurf's mcp_config.json under HOME"""
    home = Path.home()
    target_path = home / ".codeium/windsurf/mcp_config.json"
    try:
        # 讀取並展開環境變數
        config = get_resolved_mcp_config()
        # Ensure parent exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✓ Successfully wrote Windsurf MCP config: {target_path}")
        return True
    except Exception as e:
        print(f"✗ Failed to write Windsurf MCP config to {target_path}: {e}")
        return False


def sync_mcp_config():
    """Sync MCP configuration"""
    # 使用展開後的配置，確保 args/command 中的變數也被處理
    config = get_resolved_mcp_config()
    
    servers = config.get('mcpServers', {})
    success_count = 0
    total_count = len(servers)
    
    print(f"Starting forced sync of {total_count} MCP servers to Claude CLI global settings...")
    
    for name, server_config in servers.items():
        if server_config.get('disabled', False):
            print(f"Skipping disabled server: {name}")
            continue
            
        if add_mcp_server(name, server_config):
            success_count += 1
    
    print(f"\nSync complete! Success: {success_count}/{total_count}")
    
    print("\nCurrent MCP servers:")
    subprocess.run(['claude', 'mcp', 'list'], check=False)


if __name__ == "__main__":
    try:
        # Sync global rules first
        print("Syncing global rules...")
        sync_global_rules()
        
        # Sync Cursor MCP JSON
        print("\nSyncing Cursor MCP JSON...")
        sync_cursor_mcp_json()

        # Sync Windsurf MCP JSON
        print("\nSyncing Windsurf MCP JSON...")
        sync_windsurf_mcp_json()

        # Then sync MCP config to Claude CLI
        print("\nSyncing MCP configuration to Claude CLI...")
        sync_mcp_config()
    except KeyboardInterrupt:
        print("\nUser interrupted execution")
        sys.exit(1)
    except Exception as e:
        print(f"Execution error: {e}")
        sys.exit(1)