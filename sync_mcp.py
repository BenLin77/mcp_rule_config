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
from typing import Set, List, Dict, Tuple


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


def _parse_dotenv_file(path: Path) -> Dict[str, str]:
    """解析簡單 .env 檔 (KEY=VALUE)。忽略註解與空行。
    - 不支援複雜插值，只做最基本的 KEY=VALUE。
    - 去除成對引號。
    """
    env: Dict[str, str] = {}
    if not path.exists() or not path.is_file():
        return env
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # 支援前綴 export KEY=VAL
            if s.startswith("export "):
                s = s[len("export "):].lstrip()
            if "=" not in s:
                continue
            key, val = s.split("=", 1)
            key = key.strip()
            val = val.strip()
            # 去除首尾引號
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            env[key] = val
    except Exception:
        # 靜默忽略解析錯誤，避免影響主要流程
        pass
    return env


def _env_from_fish_login() -> Dict[str, str]:
    """透過 fish login shell 取得環境變數 (會載入 ~/.config/fish/config.fish 等)，
    回傳 KEY=VALUE 字典。若 fish 不存在或失敗，回傳空字典。
    """
    try:
        proc = subprocess.run(
            ["fish", "-lc", "env"], capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            return {}
        env: Dict[str, str] = {}
        for line in (proc.stdout or "").splitlines():
            if not line or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k] = v
        return env
    except FileNotFoundError:
        # 系統沒有 fish，忽略
        return {}
    except Exception:
        return {}


def reload_env_vars() -> None:
    """在每次執行前重新載入環境變數：
    1. 專案根目錄 .env
    2. 使用者家目錄 ~/.env
    3. fish login shell 的 env (若可用)

    載入順序：較前面的優先度較高；後者不覆蓋既有鍵，避免意外覆蓋既有環境。
    """
    project_root = Path(__file__).parent

    # 1) 專案 .env
    proj_env = _parse_dotenv_file(project_root / ".env")
    for k, v in proj_env.items():
        if k not in os.environ:
            os.environ[k] = v

    # 2) 家目錄 .env
    home_env = _parse_dotenv_file(Path.home() / ".env")
    for k, v in home_env.items():
        if k not in os.environ:
            os.environ[k] = v

    # 3) fish login 環境
    fish_env = _env_from_fish_login()
    for k, v in fish_env.items():
        if k not in os.environ:
            os.environ[k] = v


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

        # 在展開之前，重新載入環境變數來源 (.env / ~/.env / fish)
        reload_env_vars()

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


def files_are_identical(file1: Path, file2: Path) -> bool:
    """比對兩個檔案內容是否完全相同"""
    if not file1.exists() or not file2.exists():
        return False
    try:
        content1 = file1.read_text(encoding='utf-8')
        content2 = file2.read_text(encoding='utf-8')
        return content1 == content2
    except Exception:
        return False


def sync_to_editors(config_data: dict, temp_path: Path):
    """同步配置到各編輯器（使用臨時檔案，僅在內容不同時更新）"""
    home = Path.home()

    # 目標路徑配置
    targets = {
        "Windsurf": home / ".codeium/windsurf/mcp_config.json",
        "Cursor": home / ".cursor/mcp.json",
        "Antigravity": home / ".gemini/antigravity/mcp_config.json"
    }

    success_count = 0

    # 複製臨時檔案到各編輯器
    for editor, target_path in targets.items():
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 比對檔案內容
            if files_are_identical(temp_path, target_path):
                print(f"⊜ {editor}: 內容相同，跳過更新")
                success_count += 1
            else:
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

    # 先比較目前 Claude CLI 已註冊的 MCP 名稱與設定檔是否一致
    try:
        existing = list_claude_cli_mcp_names()
    except Exception:
        existing = set()

    desired = desired_mcp_names(config)

    if existing == desired:
        print("Claude CLI MCP 名稱清單與 mcp_config.json 相同，略過 Claude MCP 同步。")
        return

    print(f"正在同步 {len(servers)} 個 MCP 伺服器到 Claude CLI（將只新增缺少的項目）...")

    for name, server_config in servers.items():
        if server_config.get('disabled', False):
            print(f"跳過已停用的伺服器: {name}")
            continue

        try:
            cmd = ['claude', 'mcp', 'add', '--scope', 'user']

            # 1) 支援 HTTP transport：'serverUrl' 或 'url' 皆可
            server_url = server_config.get('serverUrl') or server_config.get('url')
            if server_url:
                cmd.extend(['--transport', 'http', name, server_url])

                # 處理 headers（字典形式），避免在日誌中洩漏敏感值
                headers = server_config.get('headers') or {}
                if isinstance(headers, dict):
                    for k, v in headers.items():
                        cmd.extend(['--header', f"{k}: {v}"])
                elif isinstance(headers, list):
                    for h in headers:
                        cmd.extend(['--header', str(h)])
            else:
                # 2) 若為 command 型，嘗試偵測 mcp-remote + URL 並轉為 HTTP transport
                command = server_config.get('command')
                args = server_config.get('args', []) or []
                # 從 args 中找第一個 http(s) URL
                url_in_args = next((a for a in args if isinstance(a, str) and a.startswith(('http://', 'https://'))), None)
                uses_remote = any(isinstance(a, str) and 'mcp-remote' in a for a in args)
                if command and uses_remote and url_in_args:
                    print(f"偵測到 {name} 使用 mcp-remote，將改用 HTTP transport 以支援瀏覽器授權彈窗。")
                    cmd.extend(['--transport', 'http', name, url_in_args])
                else:
                    if not command:
                        raise ValueError(f"伺服器 {name} 缺少必要欄位：'command' 或 'serverUrl'/'url'")
                    # 使用 '--' 作為參數分隔，避免 Claude CLI 將後續引數（如 '--from'）誤判為自身參數
                    cmd.extend([name, "--", command])
                    for arg in args:
                        if arg != '-y':
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


def extract_agent_names_from_markdown(content: str) -> Set[str]:
    """從 workflow Markdown 內容找出 agent (step) 名稱。"""
    pattern = re.compile(r'^\s*-\s*name:\s*([^\n\r]+)', re.MULTILINE)
    names: Set[str] = set()
    for match in pattern.finditer(content):
        raw = match.group(1).strip().strip('"').strip("'")
        if raw:
            names.add(raw)
    return names


def build_workflow_agent_index(folder: Path) -> Tuple[Dict[str, Set[Path]], Dict[Path, Set[str]]]:
    """建立目標 workflows 目錄的 agent 與檔案對應表。"""
    agent_to_files: Dict[str, Set[Path]] = {}
    file_to_agents: Dict[Path, Set[str]] = {}

    for md_file in folder.rglob("*.md"):
        if not md_file.is_file():
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception:
            continue
        agents = extract_agent_names_from_markdown(text)
        if not agents:
            continue
        file_to_agents[md_file] = agents
        for agent in agents:
            agent_to_files.setdefault(agent, set()).add(md_file)

    return agent_to_files, file_to_agents


def sync_global_rules():
    """同步全域規則檔案（僅在內容不同時更新）"""
    source = Path(__file__).parent / "global_rules.md"
    if not source.exists():
        print("跳過全域規則同步（檔案不存在）")
        return

    targets = {
        "Cursor": Path.home() / ".cursor/AGENTS.md",
        "Windsurf": Path.home() / ".codeium/windsurf/memories/global_rules.md",
        "Claude": Path.home() / ".claude/CLAUDE.md",
        "Antigravity": Path.home() / ".gemini/GEMINI.md"
    }

    for editor, target in targets.items():
        try:
            target.parent.mkdir(parents=True, exist_ok=True)

            # 比對檔案內容
            if files_are_identical(source, target):
                print(f"⊜ {editor} 全域規則: 內容相同，跳過更新")
            else:
                shutil.copy2(source, target)
                print(f"✓ {editor} 全域規則: {target}")
        except Exception as e:
            print(f"✗ {editor} 全域規則失敗: {e}")


def _sync_workflows_impl(source_dir: Path, target_root: Path, system_name: str):
    """實際執行 workflow 同步的內部函式"""
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"跳過 {system_name} workflows 同步（來源資料夾不存在）")
        return

    try:
        target_root.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"✗ 建立 {system_name} workflows 目標目錄失敗: {e}")
        return

    agent_to_files, file_to_agents = build_workflow_agent_index(target_root)

    count = 0
    for src in source_dir.rglob("*.md"):
        if not src.is_file():
            continue
        try:
            rel = src.relative_to(source_dir)
            dst = target_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            content = src.read_text(encoding="utf-8")
            agents = extract_agent_names_from_markdown(content)

            # 若目標已有相同 agent 名稱，先移除舊檔
            files_to_remove: Set[Path] = set()
            for agent in agents:
                files_to_remove.update(agent_to_files.get(agent, set()))

            for old in files_to_remove:
                # 避免刪除正要更新的檔案本身（若路徑相同）
                if old.resolve() == dst.resolve():
                    continue

                try:
                    if old.exists():
                        old.unlink()
                        print(f"↻ [{system_name}] 移除舊版 workflow (agent 重複): {old}")
                except Exception as e:
                    print(f"✗ [{system_name}] 無法移除舊 workflow {old}: {e}")
                    continue
                for agent in file_to_agents.get(old, set()):
                    files = agent_to_files.get(agent)
                    if files:
                        files.discard(old)
                        if not files:
                            agent_to_files.pop(agent, None)
                file_to_agents.pop(old, None)

            # 比對檔案內容
            if files_are_identical(src, dst):
                print(f"⊜ {system_name} workflow: 內容相同，跳過 {dst}")
            else:
                shutil.copy2(src, dst)
                print(f"✓ {system_name} workflow: {dst}")

            # 更新索引（無論是否更新，都要維護索引）
            if agents:
                file_to_agents[dst] = agents
                for agent in agents:
                    agent_to_files.setdefault(agent, set()).add(dst)

            count += 1
        except Exception as e:
            print(f"✗ [{system_name}] 複製失敗 {src} -> {e}")

    if count == 0:
        print(f"注意: {system_name} workflows 來源目錄內未找到任何 .md 檔")


def sync_workflows():
    """同步 workflows 目錄下的所有 .md 到各系統 (Windsurf, Antigravity) 的目標資料夾。
    - 來源: <repo>/workflows/**/*.md
    - 目標 Windsurf: ~/.codeium/windsurf/global_workflows/
    - 目標 Antigravity: ~/.gemini/antigravity/global_workflows/
    """
    source_dir = Path(__file__).parent / "workflows"
    
    targets = {
        "Windsurf": Path.home() / ".codeium/windsurf/global_workflows",
        "Antigravity": Path.home() / ".gemini/antigravity/global_workflows"
    }

    for system_name, target_root in targets.items():
        _sync_workflows_impl(source_dir, target_root, system_name)


def print_banner():
    """印出程式標題"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║              🔄 MCP 配置同步工具 - 互動式選單                     ║
║━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━║
║  同步目標: Windsurf | Cursor | Antigravity | Claude Code         ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def show_menu() -> str:
    """顯示互動式選單並取得使用者選擇"""
    menu = """
┌─────────────────────────────────────────────────────────────┐
│                    請選擇要執行的操作                        │
├─────────────────────────────────────────────────────────────┤
│  [1] 🔄 同步全部 (MCP + 規則 + Workflows)                   │
│  [2] 📦 只同步 MCP 配置                                      │
│  [3] 📋 只同步全域規則 (global_rules.md)                    │
│  [4] 🤖 只同步 Workflows                                     │
│  [5] 🧹 清理所有 Claude CLI MCP                             │
│  [6] 📊 顯示 Claude CLI MCP 狀態                            │
│  [0] ❌ 離開                                                 │
└─────────────────────────────────────────────────────────────┘
"""
    print(menu)
    return input("請輸入選項 [0-6]: ").strip()


def run_sync_mcp(config: dict, temp_path: Path) -> int:
    """執行 MCP 配置同步"""
    print("\n📦 同步 MCP 配置...")
    success_count = sync_to_editors(config, temp_path)
    
    # 清理多餘 MCP
    try:
        removed = prune_claude_cli(config)
        if removed:
            print(f"已清理多餘 MCP: {', '.join(removed)}")
    except Exception as e:
        print(f"清理多餘 MCP 時發生錯誤: {e}")
    
    return success_count


def run_sync_rules():
    """執行全域規則同步"""
    print("\n📋 同步全域規則...")
    sync_global_rules()


def run_sync_workflows():
    """執行 Workflows 同步"""
    print("\n🤖 同步 Workflows...")
    sync_workflows()


def run_show_claude_status():
    """顯示 Claude CLI MCP 狀態"""
    print("\n📊 目前 Claude CLI MCP 伺服器:")
    subprocess.run(['claude', 'mcp', 'list'], check=False)


def run_clean_claude_mcps():
    """清理所有 Claude CLI MCP"""
    print("\n🧹 清理所有 Claude CLI MCP...")
    confirm = input("確定要清理所有 Claude CLI MCP 嗎？(y/N): ").strip().lower()
    if confirm == 'y':
        removed = remove_all_claude_cli_mcps()
        print(f"\n已清理 {len(removed)} 個 MCP")
    else:
        print("已取消清理操作")


def interactive_mode():
    """互動式選單模式"""
    print_banner()
    
    temp_path = None
    config = None
    
    try:
        while True:
            choice = show_menu()
            
            if choice == '0':
                print("\n👋 再見！")
                break
            
            elif choice == '1':
                # 同步全部
                if config is None:
                    config, temp_path = process_config()
                    print("✓ 配置檔案處理完成")
                
                run_sync_mcp(config, temp_path)
                run_sync_rules()
                run_sync_workflows()
                run_show_claude_status()
                print("\n✅ 全部同步完成！")
            
            elif choice == '2':
                # 只同步 MCP
                if config is None:
                    config, temp_path = process_config()
                    print("✓ 配置檔案處理完成")
                
                success = run_sync_mcp(config, temp_path)
                print(f"\n✅ MCP 同步完成！成功: {success}/4 個目標")
            
            elif choice == '3':
                # 只同步規則
                run_sync_rules()
                print("\n✅ 全域規則同步完成！")
            
            elif choice == '4':
                # 只同步 Workflows
                run_sync_workflows()
                print("\n✅ Workflows 同步完成！")
            
            elif choice == '5':
                # 清理 Claude MCP
                run_clean_claude_mcps()
            
            elif choice == '6':
                # 顯示狀態
                run_show_claude_status()
            
            else:
                print("\n⚠ 無效選項，請重新輸入")
            
            input("\n按 Enter 繼續...")
    
    except KeyboardInterrupt:
        print("\n\n使用者中斷執行")
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def batch_mode():
    """批次模式 (原本的 main 流程)"""
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

        # 4.1 同步 Workflows (Windsurf & Antigravity)
        sync_workflows()

        print(f"\n同步完成！成功: {success_count}/4 個目標")

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


def main():
    """主程式入口：支援互動式選單或批次模式"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='🔄 MCP 配置同步工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 互動式選單模式
  python sync_mcp.py
  
  # 批次模式 (一次同步全部)
  python sync_mcp.py --batch
  python sync_mcp.py -b
  
  # 只同步特定項目
  python sync_mcp.py --mcp        # 只同步 MCP 配置
  python sync_mcp.py --rules      # 只同步全域規則
  python sync_mcp.py --workflows  # 只同步 Workflows
        """
    )
    
    parser.add_argument(
        '--batch', '-b',
        action='store_true',
        help='批次模式：一次同步全部 (不顯示選單)'
    )
    
    parser.add_argument(
        '--mcp',
        action='store_true',
        help='只同步 MCP 配置'
    )
    
    parser.add_argument(
        '--rules',
        action='store_true',
        help='只同步全域規則'
    )
    
    parser.add_argument(
        '--workflows',
        action='store_true',
        help='只同步 Workflows'
    )
    
    args = parser.parse_args()
    
    # 判斷執行模式
    if args.batch:
        batch_mode()
    elif args.mcp or args.rules or args.workflows:
        # 部分同步模式
        temp_path = None
        try:
            if args.mcp:
                config, temp_path = process_config()
                print("✓ 配置檔案處理完成")
                run_sync_mcp(config, temp_path)
            
            if args.rules:
                run_sync_rules()
            
            if args.workflows:
                run_sync_workflows()
            
            print("\n✅ 同步完成！")
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
    else:
        # 預設進入互動式選單
        interactive_mode()


if __name__ == "__main__":
    main()
