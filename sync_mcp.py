#!/usr/bin/env python3
"""
自動同步MCP設定檔到Claude CLI
固定讀取 /Users/ben/code/mcp_sync/mcp_config.json
"""
import json
import subprocess
import sys
from pathlib import Path
import platform


def load_mcp_config():
    """載入MCP設定檔"""
    # 固定設定檔路徑
    config_path = Path("/Users/ben/code/mcp_sync/mcp_config.json")
    
    # Ubuntu 支援
    if platform.system().lower() == "linux":
        home = Path.home()
        config_path = home / "code/mcp_sync/mcp_config.json"
    
    if not config_path.exists():
        print(f"錯誤：找不到設定檔 {config_path}")
        sys.exit(1)
        
    print(f"載入設定檔: {config_path}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_existing_servers():
    """取得現有的MCP伺服器列表"""
    existing = set()
    try:
        result = subprocess.run(['claude', 'mcp', 'list'], 
                              capture_output=True, text=True, check=False)
        
        # 解析輸出找到伺服器名稱
        lines = result.stdout.strip().split('\n')
        for line in lines:
            # 跳過空行和標題行
            if not line or 'Checking MCP server health' in line or line.startswith(' ') or not ':' in line:
                continue
            
            # 找到伺服器名稱（格式：server_name: command - status）
            if ': ' in line and (' - ' in line):
                server_name = line.split(':')[0].strip()
                existing.add(server_name)
                print(f"找到現有伺服器: {server_name}")
                
    except subprocess.CalledProcessError as e:
        print(f"警告：無法取得現有設定 - {e}")
    
    print(f"現有伺服器數量: {len(existing)}")
    return existing


def add_mcp_server(name, config):
    """添加單個MCP伺服器到全域設定"""
    try:
        cmd = ['claude', 'mcp', 'add', '--scope', 'user', name, config['command']]  # 寫入user範圍
        args = config.get('args', [])
        
        # 過濾並處理參數
        for arg in args:
            if arg == '-y':  # 跳過 -y 參數
                continue
            cmd.append(arg)
        
        print(f"添加 MCP 伺服器到全域: {name}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✓ 成功添加到全域: {name}")
        
        # 如果有環境變數，顯示提醒
        if 'env' in config and config['env']:
            print(f"注意：{name} 需要環境變數：{list(config['env'].keys())}")
            
        return True
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        
        # 如果是已存在錯誤，視為成功
        if "already exists" in error_msg:
            print(f"✓ {name} 已存在於全域設定")
            return True
            
        print(f"✗ 無法添加到全域 {name}: {error_msg}")
        return False


def sync_mcp_config():
    """同步MCP設定檔"""
    config = load_mcp_config()
    
    servers = config.get('mcpServers', {})
    success_count = 0
    total_count = len(servers)
    
    print(f"開始強制同步 {total_count} 個MCP伺服器到Claude CLI全域設定...")
    
    for name, server_config in servers.items():
        if server_config.get('disabled', False):
            print(f"跳過已停用的伺服器: {name}")
            continue
            
        if add_mcp_server(name, server_config):
            success_count += 1
    
    print(f"\n同步完成！成功: {success_count}/{total_count}")
    
    print("\n當前MCP伺服器:")
    subprocess.run(['claude', 'mcp', 'list'], check=False)


if __name__ == "__main__":
    try:
        sync_mcp_config()
    except KeyboardInterrupt:
        print("\n用戶中斷執行")
        sys.exit(1)
    except Exception as e:
        print(f"執行錯誤: {e}")
        sys.exit(1)