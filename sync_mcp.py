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
from typing import Set, List


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

    # 在新增任何 MCP 之前，先清除 Claude CLI 中所有已註冊的 MCP
    try:
        removed = remove_all_claude_cli_mcps()
        if removed:
            print(f"已先行清除 Claude CLI 內既有 MCP: {', '.join(removed)}")
    except Exception as e:
        print(f"清除 Claude CLI 既有 MCP 時發生錯誤（將繼續嘗試新增）: {e}")

    print(f"正在同步 {len(servers)} 個 MCP 伺服器到 Claude CLI...")

    for name, server_config in servers.items():
        if server_config.get('disabled', False):
            print(f"跳過已停用的伺服器: {name}")
            continue

        try:
            cmd = ['claude', 'mcp', 'add', '--scope', 'user']

            # 支援 HTTP transport（如 Context7）
            if 'serverUrl' in server_config:
                server_url = server_config['serverUrl']
                cmd.extend(['--transport', 'http', name, server_url])

                # 處理 headers（字典形式），避免在日誌中洩漏敏感值
                headers = server_config.get('headers') or {}
                if isinstance(headers, dict):
                    for k, v in headers.items():
                        # 依官方格式 KEY: VALUE
                        cmd.extend(['--header', f"{k}: {v}"])
                elif isinstance(headers, list):
                    # 若已是字串清單，直接附加
                    for h in headers:
                        cmd.extend(['--header', str(h)])
            else:
                # 預設為 command 型
                command = server_config.get('command')
                if not command:
                    raise ValueError(f"伺服器 {name} 缺少必要欄位：'command' 或 'serverUrl'")
                cmd.extend([name, command])

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
        except Exception as e:
            # 捕捉一般錯誤（例如 KeyError）
            print(f"✗ Claude CLI 失敗: {name} - {e}")


def _parse_claude_mcp_list_text(output: str) -> Set[str]:
    """從 `claude mcp list` 的文字輸出解析 MCP 名稱清單。

    常見格式如下（名稱為冒號前的 token）:
    playwright: npx @playwright/mcp@latest - ✓ Connected
    """
    names: Set[str] = set()
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("checking mcp server health"):
            continue
        # 只取第一個冒號前片段作為名稱
        if ":" in line:
            candidate = line.split(":", 1)[0].strip()
            # 合理的名稱限制
            if re.match(r"^[A-Za-z0-9._-]+$", candidate):
                names.add(candidate)
    return names


def list_claude_cli_mcp_names() -> Set[str]:
    """取得目前 Claude CLI 中註冊的 MCP 名稱集合。

    優先嘗試 `--json`，失敗時回退解析純文字。
    """
    # 先嘗試 JSON 介面
    try:
        proc = subprocess.run(
            ['claude', 'mcp', 'list', '--json'],
            capture_output=True, text=True, check=True
        )
        data = json.loads(proc.stdout or '[]')
        names: Set[str] = set()
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and 'name' in item:
                    names.add(str(item['name']))
        elif isinstance(data, dict) and 'servers' in data:
            for item in data.get('servers', []) or []:
                if isinstance(item, dict) and 'name' in item:
                    names.add(str(item['name']))
        if names:
            return names
        # 若為空，改走文字解析
    except subprocess.CalledProcessError:
        pass
    except json.JSONDecodeError:
        pass

    # 文字模式
    try:
        proc = subprocess.run(
            ['claude', 'mcp', 'list'],
            capture_output=True, text=True, check=False
        )
        return _parse_claude_mcp_list_text(proc.stdout or '')
    except Exception:
        return set()


def desired_mcp_names(config: dict) -> Set[str]:
    """從設定檔取出欲啟用的 MCP 名稱（排除 disabled=True）。"""
    names: Set[str] = set()
    for name, server in (config.get('mcpServers') or {}).items():
        if isinstance(server, dict) and server.get('disabled', False):
            continue
        names.add(name)
    return names


def remove_all_claude_cli_mcps() -> List[str]:
    """移除 Claude Code（Claude CLI）中所有已註冊的 MCP。回傳被刪除的名稱清單。"""
    existing = sorted(list_claude_cli_mcp_names())
    if not existing:
        print("Claude CLI 目前沒有已註冊的 MCP。")
        return []

    print(f"將清除 Claude CLI 內所有 MCP，共 {len(existing)} 個: {', '.join(existing)}")
    removed: List[str] = []
    for name in existing:
        tried_cmds = [
            ['claude', 'mcp', 'remove', '--scope', 'user', name],
            ['claude', 'mcp', 'remove', name],
        ]
        ok = False
        last_err = ''
        for cmd in tried_cmds:
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True)
                ok = True
                break
            except subprocess.CalledProcessError as e:
                last_err = e.stderr or e.stdout or str(e)
        if ok:
            print(f"✓ 已移除: {name}")
            removed.append(name)
        else:
            print(f"✗ 無法移除 {name}: {last_err}")
    return removed


def prune_claude_cli(config: dict) -> List[str]:
    """刪除不在設定檔中的 MCP。回傳被刪除的名稱清單。"""
    existing = list_claude_cli_mcp_names()
    desired = desired_mcp_names(config)
    obsolete = sorted(existing - desired)

    if not obsolete:
        print("沒有需要移除的多餘 MCP。")
        return []

    print(f"開始清理多餘 MCP，共 {len(obsolete)} 個: {', '.join(obsolete)}")
    removed: List[str] = []
    for name in obsolete:
        # 優先嘗試帶 scope
        tried_cmds = [
            ['claude', 'mcp', 'remove', '--scope', 'user', name],
            ['claude', 'mcp', 'remove', name],
        ]
        ok = False
        last_err = ''
        for cmd in tried_cmds:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
                ok = True
                break
            except subprocess.CalledProcessError as e:
                last_err = e.stderr or e.stdout or str(e)
        if ok:
            print(f"✓ 已移除: {name}")
            removed.append(name)
        else:
            print(f"✗ 無法移除 {name}: {last_err}")
    return removed


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

        # 3. 刪除未列於設定檔中的 Claude CLI MCP
        try:
            removed = prune_claude_cli(config)
            if removed:
                print(f"已清理多餘 MCP: {', '.join(removed)}")
        except Exception as e:
            print(f"清理多餘 MCP 時發生錯誤: {e}")

        # 4. 同步全域規則
        sync_global_rules()

        print(f"\n同步完成！成功: {success_count}/3 個目標")

        # 5. 顯示 Claude CLI 狀態
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
