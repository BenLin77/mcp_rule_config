#!/usr/bin/env python3
"""
Automatically sync MCP config to Claude CLI and global rules to specified paths
Default config path: /Users/ben/code/mcp_sync/mcp_config.json

執行方式：
- 建議使用 uv run sync_mcp.py
- 或使用 python3 sync_mcp.py
"""
import json
import subprocess
import sys
import shutil
from pathlib import Path
import platform
import os


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
    """Sync global_rules.md to specified paths for Mac and Ubuntu"""
    # Source file path
    script_dir = Path(__file__).parent.resolve()
    source_file = script_dir / "global_rules.md"
    
    if not source_file.exists():
        print(f"Error: Source file not found: {source_file}")
        return False
    
    # Target paths based on OS
    home = Path.home()
    target_paths = []
    
    if platform.system().lower() == "darwin":  # Mac
        target_paths = [
            home / ".codeium/windsurf/memories/global_rules.md",
            home / ".claude/CLAUDE.md"
        ]
    elif platform.system().lower() == "linux":  # Ubuntu
        target_paths = [
            home / ".codeium/windsurf/memories/global_rules.md",
            home / ".claude/CLAUDE.md"
        ]
    else:
        print(f"Unsupported OS: {platform.system()}")
        return False
    
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


def sync_mcp_config():
    """Sync MCP configuration"""
    config = load_mcp_config()
    
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
        
        # Then sync MCP config
        print("\nSyncing MCP configuration...")
        sync_mcp_config()
    except KeyboardInterrupt:
        print("\nUser interrupted execution")
        sys.exit(1)
    except Exception as e:
        print(f"Execution error: {e}")
        sys.exit(1)