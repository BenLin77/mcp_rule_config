#!/usr/bin/env python3
"""
簡潔的 MCP 配置同步工具
1. 複製 mcp_config.json 為臨時檔案
2. 替換環境變數
3. 同步到 Windsurf, Cursor, Claude Code
4. 刪除臨時檔案（避免 token 被推送到 github）
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
import re
import tempfile


def expand_variables(content: str) -> str:
    """替換字串中的 ${VAR} 環境變數"""
    pattern = re.compile(r'\$\{([^}]+)\}')
    
    def replace_var(match):
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            print(f"警告: 環境變數 '{var_name}' 未設置")
            return match.group(0)
        return value
    
    return pattern.sub(replace_var, content)


def process_config():
    """處理配置檔案：複製 → 替換變數 → 返回處理後的配置和臨時檔案路徑"""
    config_path = Path(__file__).parent / "mcp_config.json"
    
    if not config_path.exists():
        print(f"錯誤: 找不到配置檔案 {config_path}")
        sys.exit(1)
    
    # 創建臨時檔案
    temp_file = tempfile.NamedTemporaryFile(mode='w+', suffix='_mcp_config.json', 
                                          delete=False, encoding='utf-8')
    temp_path = Path(temp_file.name)
    
    try:
        # 讀取原始配置
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_content = f.read()
        
        # 替換環境變數
        processed_content = expand_variables(raw_content)
        
        # 寫入臨時檔案
        temp_file.write(processed_content)
        temp_file.close()
        
        # 解析為 JSON 物件
        config = json.loads(processed_content)
        
        print(f"已創建臨時配置檔案: {temp_path}")
        return config, temp_path
        
    except json.JSONDecodeError as e:
        temp_file.close()
        temp_path.unlink(missing_ok=True)
        print(f"錯誤: JSON 解析失敗 - {e}")
        sys.exit(1)
    except Exception as e:
        temp_file.close()
        temp_path.unlink(missing_ok=True)
        print(f"錯誤: 處理配置檔案失敗 - {e}")
        sys.exit(1)


def sync_to_editors(config_data: dict, temp_path: Path):
    """同步配置到各編輯器（使用臨時檔案）"""
    home = Path.home()
    
    # 目標路徑配置
    targets = {
        "Windsurf": home / ".codeium/windsurf/mcp_config.json",
        "Cursor": home / ".cursor/mcp.json"
    }
    
    success_count = 0
    
    # 複製臨時檔案到各編輯器
    for editor, target_path in targets.items():
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(temp_path, target_path)
            print(f"✓ {editor}: {target_path}")
            success_count += 1
        except Exception as e:
            print(f"✗ {editor}: {e}")
    
    # 同步到 Claude CLI
    try:
        sync_to_claude_cli(config_data)
        success_count += 1
    except Exception as e:
        print(f"✗ Claude CLI: {e}")
    
    return success_count


def sync_to_claude_cli(config: dict):
    """同步到 Claude CLI"""
    servers = config.get('mcpServers', {})
    
    print(f"正在同步 {len(servers)} 個 MCP 伺服器到 Claude CLI...")
    
    for name, server_config in servers.items():
        if server_config.get('disabled', False):
            print(f"跳過已停用的伺服器: {name}")
            continue
        
        try:
            cmd = ['claude', 'mcp', 'add', '--scope', 'user', name, server_config['command']]
            
            # 添加參數
            args = server_config.get('args', [])
            for arg in args:
                if arg != '-y':  # 跳過 -y 參數
                    cmd.append(arg)
            
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            print(f"✓ Claude CLI 已添加: {name}")
            
        except subprocess.CalledProcessError as e:
            if "already exists" in str(e.stderr):
                print(f"✓ Claude CLI 已存在: {name}")
            else:
                print(f"✗ Claude CLI 失敗: {name} - {e.stderr}")


def sync_global_rules():
    """同步全域規則檔案"""
    source = Path(__file__).parent / "global_rules.md"
    if not source.exists():
        print("跳過全域規則同步（檔案不存在）")
        return
    
    targets = {
        "Cursor": Path.home() / ".cursor/AGENTS.md",
        "Windsurf": Path.home() / ".codeium/windsurf/memories/global_rules.md",
        "Claude": Path.home() / ".claude/CLAUDE.md"
    }
    
    for editor, target in targets.items():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            print(f"✓ {editor} 全域規則: {target}")
        except Exception as e:
            print(f"✗ {editor} 全域規則失敗: {e}")


def main():
    """主要執行流程"""
    temp_path = None
    try:
        print("開始同步 MCP 配置...")
        
        # 1. 處理配置檔案（創建臨時檔案）
        config, temp_path = process_config()
        print("✓ 配置檔案處理完成")
        
        # 2. 同步到編輯器
        success_count = sync_to_editors(config, temp_path)
        
        # 3. 同步全域規則
        sync_global_rules()
        
        print(f"\n同步完成！成功: {success_count}/3 個目標")
        
        # 4. 顯示 Claude CLI 狀態
        print("\n目前 Claude CLI MCP 伺服器:")
        subprocess.run(['claude', 'mcp', 'list'], check=False)
        
    except KeyboardInterrupt:
        print("\n使用者中斷執行")
        sys.exit(1)
    except Exception as e:
        print(f"執行錯誤: {e}")
        sys.exit(1)
    finally:
        # 清理臨時檔案
        if temp_path and temp_path.exists():
            temp_path.unlink()
            print(f"已刪除臨時檔案: {temp_path}")


if __name__ == "__main__":
    main()