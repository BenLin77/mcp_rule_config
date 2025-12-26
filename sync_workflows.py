#!/usr/bin/env python3
"""
🚀 Workflow Agent 部署工具

將 workflows 目錄下的 agent 部署到各種 AI IDE:
- Antigravity (Google Gemini)
- Cursor
- Windsurf
- Claude Code

支援平台: macOS, Ubuntu/Linux
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime


# ============================================================================
# AI IDE 配置路徑
# ============================================================================

def get_ide_paths() -> Dict[str, Dict[str, Path]]:
    """取得各 AI IDE 的 workflow 配置路徑
    
    Returns:
        Dict[IDE名稱, Dict[類型, Path]]
        - 類型: 'global_workflows' (全域 workflow), 'project_workflows' (專案 workflow),
                'global_rules' (全域規則), 'agents' (代理設定)
    """
    home = Path.home()
    system = platform.system()  # 'Darwin' for macOS, 'Linux' for Ubuntu
    
    paths = {
        # ================================================================
        # Antigravity (Google Gemini Code)
        # - 全域 workflows: ~/.gemini/antigravity/global_workflows/
        # - 專案 workflows: .agent/workflows/ (in project root)
        # - 全域規則: ~/.gemini/GEMINI.md
        # ================================================================
        "Antigravity": {
            "global_workflows": home / ".gemini" / "antigravity" / "global_workflows",
            "global_rules": home / ".gemini" / "GEMINI.md",
            "agents": home / ".gemini" / "agents",
            "project_workflows_template": ".agent/workflows",  # 相對於專案根目錄
        },
        
        # ================================================================
        # Cursor
        # - 全域規則: ~/.cursor/AGENTS.md (或專案 .cursorrules)
        # - 專案規則: <project>/.cursor/rules/*.mdc
        # - 舊格式: <project>/.cursorrules
        # ================================================================
        "Cursor": {
            "global_workflows": home / ".cursor" / "rules",  # 全域規則目錄
            "global_rules": home / ".cursor" / "AGENTS.md",
            "agents": home / ".cursor" / "agents",
            "project_workflows_template": ".cursor/rules",  # 相對於專案根目錄
        },
        
        # ================================================================
        # Windsurf (Codeium)
        # - 全域 workflows: ~/.codeium/windsurf/global_workflows/
        # - 全域規則: ~/.codeium/windsurf/memories/global_rules.md
        # - 專案規則: <project>/.windsurf/rules/rules.md
        # ================================================================
        "Windsurf": {
            "global_workflows": home / ".codeium" / "windsurf" / "global_workflows",
            "global_rules": home / ".codeium" / "windsurf" / "memories" / "global_rules.md",
            "agents": home / ".codeium" / "windsurf" / "agents",
            "project_workflows_template": ".windsurf/rules",  # 相對於專案根目錄
        },
        
        # ================================================================
        # Claude Code
        # - 使用者代理: ~/.claude/agents/*.md
        # - 全域規則: ~/.claude/CLAUDE.md
        # - 專案代理: <project>/.claude/agents/*.md
        # - 專案規則: <project>/CLAUDE.md 或 <project>/.claude/CLAUDE.md
        # ================================================================
        "Claude Code": {
            "global_workflows": home / ".claude" / "agents",  # Claude 用 agents 目錄
            "global_rules": home / ".claude" / "CLAUDE.md",
            "agents": home / ".claude" / "agents",
            "project_workflows_template": ".claude/agents",  # 相對於專案根目錄
        },
    }
    
    return paths


# ============================================================================
# 工具函數
# ============================================================================

def print_banner():
    """印出程式標題"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║         🤖 Workflow Agent 部署工具 - 支援多 AI IDE               ║
║━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━║
║  支援: Antigravity | Cursor | Windsurf | Claude Code             ║
║  平台: macOS | Ubuntu/Linux                                       ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def get_system_info() -> Dict[str, str]:
    """取得系統資訊"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "home": str(Path.home()),
    }


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


def ensure_dir(path: Path) -> bool:
    """確保目錄存在，若不存在則建立"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"  ✗ 無法建立目錄 {path}: {e}")
        return False


def copy_file_if_different(src: Path, dst: Path, dry_run: bool = False) -> Tuple[bool, str]:
    """複製檔案（若內容不同）
    
    Returns:
        Tuple[成功與否, 狀態訊息]
    """
    if not src.exists():
        return False, f"來源檔案不存在: {src}"
    
    if files_are_identical(src, dst):
        return True, "⊜ 內容相同，跳過"
    
    if dry_run:
        return True, "🔍 (dry-run) 將會複製"
    
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True, "✓ 已複製"
    except Exception as e:
        return False, f"✗ 複製失敗: {e}"


# ============================================================================
# Workflow 解析與處理
# ============================================================================

def parse_workflow_frontmatter(content: str) -> Dict[str, str]:
    """解析 Workflow 的 YAML frontmatter
    
    格式:
    ---
    description: 短描述
    ---
    """
    metadata: Dict[str, str] = {}
    lines = content.split('\n')
    
    if not lines or lines[0].strip() != '---':
        return metadata
    
    in_frontmatter = True
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            break
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip()
    
    return metadata


def get_workflow_command_name(filepath: Path) -> str:
    """從檔名取得 workflow 命令名稱 (e.g., code-review-agent.md -> /code-review-agent)"""
    name = filepath.stem  # 移除 .md 副檔名
    return f"/{name}"


def discover_workflows(source_dir: Path) -> List[Dict]:
    """探索來源目錄下的所有 workflow
    
    Returns:
        List[Dict] 每個 workflow 包含:
        - path: 完整路徑
        - name: 檔名
        - command: 命令名稱 (e.g., /code-review-agent)
        - description: 描述
    """
    workflows = []
    
    if not source_dir.exists() or not source_dir.is_dir():
        return workflows
    
    for md_file in source_dir.rglob("*.md"):
        if not md_file.is_file() or md_file.name.startswith('_'):
            continue
        
        try:
            content = md_file.read_text(encoding='utf-8')
            metadata = parse_workflow_frontmatter(content)
            
            workflows.append({
                "path": md_file,
                "name": md_file.name,
                "command": get_workflow_command_name(md_file),
                "description": metadata.get("description", ""),
                "relative_path": md_file.relative_to(source_dir),
            })
        except Exception as e:
            print(f"  ⚠ 無法解析 {md_file}: {e}")
    
    return sorted(workflows, key=lambda x: x["name"])


# ============================================================================
# IDE 專用轉換器
# ============================================================================

def convert_for_cursor(content: str, filename: str) -> str:
    """轉換 workflow 為 Cursor 格式
    
    Cursor 使用 .mdc 格式或 AGENTS.md
    """
    # 基本上直接使用 markdown，但可以加入 Cursor 特定語法
    return content


def convert_for_claude(content: str, filename: str) -> str:
    """轉換 workflow 為 Claude Code 格式
    
    Claude Code 接受標準 markdown，放在 ~/.claude/agents/ 目錄
    """
    # Claude 也接受標準 markdown
    return content


def convert_for_windsurf(content: str, filename: str) -> str:
    """轉換 workflow 為 Windsurf 格式"""
    # Windsurf 也接受標準 markdown
    return content


def convert_for_antigravity(content: str, filename: str) -> str:
    """轉換 workflow 為 Antigravity 格式"""
    # Antigravity 也接受標準 markdown
    return content


# ============================================================================
# 部署邏輯
# ============================================================================

def deploy_to_ide(
    ide_name: str,
    ide_paths: Dict[str, Path],
    workflows: List[Dict],
    dry_run: bool = False,
    verbose: bool = False
) -> Tuple[int, int, int]:
    """部署 workflows 到特定 IDE
    
    Returns:
        Tuple[成功數, 跳過數, 失敗數]
    """
    print(f"\n📦 部署到 {ide_name}...")
    
    target_dir = ide_paths.get("global_workflows")
    if not target_dir:
        print(f"  ⚠ 找不到 {ide_name} 的 workflow 目錄配置")
        return 0, 0, len(workflows)
    
    if not dry_run and not ensure_dir(target_dir):
        return 0, 0, len(workflows)
    
    success, skipped, failed = 0, 0, 0
    
    # 取得對應的轉換器
    converters = {
        "Antigravity": convert_for_antigravity,
        "Cursor": convert_for_cursor,
        "Windsurf": convert_for_windsurf,
        "Claude Code": convert_for_claude,
    }
    converter = converters.get(ide_name, lambda c, f: c)
    
    for wf in workflows:
        src_path = wf["path"]
        relative = wf.get("relative_path", Path(wf["name"]))
        dst_path = target_dir / relative
        
        # 讀取並轉換內容
        try:
            content = src_path.read_text(encoding='utf-8')
            converted = converter(content, wf["name"])
            
            # 檢查是否需要更新
            if dst_path.exists():
                existing = dst_path.read_text(encoding='utf-8')
                if existing == converted:
                    if verbose:
                        print(f"  ⊜ {wf['name']}: 內容相同，跳過")
                    skipped += 1
                    continue
            
            if dry_run:
                print(f"  🔍 {wf['name']}: 將會部署到 {dst_path}")
                success += 1
                continue
            
            # 實際寫入
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            dst_path.write_text(converted, encoding='utf-8')
            print(f"  ✓ {wf['name']} → {dst_path}")
            success += 1
            
        except Exception as e:
            print(f"  ✗ {wf['name']}: {e}")
            failed += 1
    
    return success, skipped, failed


def deploy_global_rules(
    source_file: Path,
    ide_paths: Dict[str, Dict[str, Path]],
    dry_run: bool = False
) -> None:
    """部署全域規則到所有 IDE"""
    if not source_file.exists():
        print(f"⚠ 找不到全域規則檔案: {source_file}")
        return
    
    print("\n📋 部署全域規則...")
    
    for ide_name, paths in ide_paths.items():
        rules_path = paths.get("global_rules")
        if not rules_path:
            continue
        
        ok, msg = copy_file_if_different(source_file, rules_path, dry_run)
        print(f"  {ide_name}: {msg}")


# ============================================================================
# 狀態檢查
# ============================================================================

def check_ide_status(ide_paths: Dict[str, Dict[str, Path]]) -> None:
    """檢查各 IDE 的配置狀態"""
    print("\n🔍 AI IDE 配置狀態檢查...")
    print("─" * 60)
    
    for ide_name, paths in ide_paths.items():
        print(f"\n🖥️  {ide_name}")
        
        for path_type, path in paths.items():
            if isinstance(path, str):  # 這是模板路徑，跳過
                continue
                
            if path.exists():
                if path.is_dir():
                    count = len(list(path.glob("*.md")))
                    print(f"   ✓ {path_type}: {path} ({count} 個 .md 檔)")
                else:
                    size = path.stat().st_size
                    print(f"   ✓ {path_type}: {path} ({size} bytes)")
            else:
                print(f"   ○ {path_type}: {path} (尚未建立)")


def list_deployed_workflows(ide_paths: Dict[str, Dict[str, Path]]) -> None:
    """列出各 IDE 已部署的 workflows"""
    print("\n📋 已部署的 Workflows...")
    print("═" * 60)
    
    for ide_name, paths in ide_paths.items():
        wf_dir = paths.get("global_workflows")
        if not wf_dir or not wf_dir.exists():
            print(f"\n🖥️  {ide_name}: (無 workflows)")
            continue
        
        workflows = list(wf_dir.rglob("*.md"))
        print(f"\n🖥️  {ide_name}: ({len(workflows)} 個 workflows)")
        
        for wf in sorted(workflows):
            cmd = get_workflow_command_name(wf)
            rel = wf.relative_to(wf_dir) if wf_dir in wf.parents or wf.parent == wf_dir else wf.name
            print(f"   • {cmd} ({rel})")


# ============================================================================
# 清理功能
# ============================================================================

def clean_ide_workflows(
    ide_name: str,
    ide_paths: Dict[str, Path],
    dry_run: bool = False
) -> int:
    """清理特定 IDE 的所有 workflows
    
    Returns:
        已刪除的檔案數
    """
    wf_dir = ide_paths.get("global_workflows")
    if not wf_dir or not wf_dir.exists():
        return 0
    
    workflows = list(wf_dir.rglob("*.md"))
    deleted = 0
    
    for wf in workflows:
        if dry_run:
            print(f"  🔍 將刪除: {wf}")
            deleted += 1
        else:
            try:
                wf.unlink()
                print(f"  ✓ 已刪除: {wf}")
                deleted += 1
            except Exception as e:
                print(f"  ✗ 無法刪除 {wf}: {e}")
    
    return deleted


# ============================================================================
# 主程式
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='🤖 Workflow Agent 部署工具 - 支援多 AI IDE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 列出可用的 workflows
  python sync_workflows.py --list

  # 部署到所有 IDE
  python sync_workflows.py --deploy

  # 只部署到特定 IDE
  python sync_workflows.py --deploy --ide Cursor

  # 乾跑模式（不實際變更）
  python sync_workflows.py --deploy --dry-run

  # 檢查各 IDE 狀態
  python sync_workflows.py --status

  # 清理特定 IDE 的 workflows
  python sync_workflows.py --clean --ide "Claude Code"
        """
    )
    
    parser.add_argument(
        '--source', '-s',
        type=Path,
        default=Path(__file__).parent / 'workflows',
        help='Workflow 來源目錄 (預設: ./workflows)'
    )
    
    parser.add_argument(
        '--deploy', '-d',
        action='store_true',
        help='部署 workflows 到 AI IDE'
    )
    
    parser.add_argument(
        '--ide', '-i',
        type=str,
        choices=['Antigravity', 'Cursor', 'Windsurf', 'Claude Code', 'all'],
        default='all',
        help='目標 IDE (預設: all)'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='列出可用的 workflows'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='檢查各 IDE 配置狀態'
    )
    
    parser.add_argument(
        '--clean',
        action='store_true',
        help='清理指定 IDE 的 workflows'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='乾跑模式，不實際變更檔案'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='顯示詳細輸出'
    )
    
    parser.add_argument(
        '--with-rules',
        action='store_true',
        help='同時部署全域規則 (global_rules.md)'
    )
    
    args = parser.parse_args()
    
    # 印出標題
    print_banner()
    
    # 取得系統資訊
    sys_info = get_system_info()
    print(f"📍 系統: {sys_info['system']} {sys_info['release']} ({sys_info['machine']})")
    print(f"🐍 Python: {sys_info['python']}")
    print(f"🏠 Home: {sys_info['home']}")
    
    # 取得 IDE 路徑配置
    ide_paths = get_ide_paths()
    
    # 狀態檢查
    if args.status:
        check_ide_status(ide_paths)
        list_deployed_workflows(ide_paths)
        return
    
    # 探索來源 workflows
    print(f"\n📂 來源目錄: {args.source}")
    workflows = discover_workflows(args.source)
    
    if not workflows:
        print("⚠ 未找到任何 workflow 檔案")
        return
    
    # 列出 workflows
    if args.list or args.verbose:
        print(f"\n📋 找到 {len(workflows)} 個 Workflows:")
        print("─" * 60)
        for wf in workflows:
            desc = wf['description'] or '(無描述)'
            print(f"  {wf['command']:<35} {desc}")
        print("─" * 60)
    
    if args.list and not args.deploy:
        return
    
    # 清理模式
    if args.clean:
        print("\n🧹 清理模式" + (" (dry-run)" if args.dry_run else ""))
        
        targets = [args.ide] if args.ide != 'all' else list(ide_paths.keys())
        total_deleted = 0
        
        for ide_name in targets:
            if ide_name in ide_paths:
                print(f"\n清理 {ide_name}...")
                deleted = clean_ide_workflows(ide_name, ide_paths[ide_name], args.dry_run)
                total_deleted += deleted
        
        print(f"\n✓ 共清理 {total_deleted} 個 workflow 檔案")
        return
    
    # 部署模式
    if args.deploy:
        print("\n🚀 部署模式" + (" (dry-run)" if args.dry_run else ""))
        
        targets = [args.ide] if args.ide != 'all' else list(ide_paths.keys())
        
        total_success, total_skipped, total_failed = 0, 0, 0
        
        for ide_name in targets:
            if ide_name in ide_paths:
                s, sk, f = deploy_to_ide(
                    ide_name,
                    ide_paths[ide_name],
                    workflows,
                    dry_run=args.dry_run,
                    verbose=args.verbose
                )
                total_success += s
                total_skipped += sk
                total_failed += f
        
        # 部署全域規則
        if args.with_rules:
            global_rules = args.source.parent / 'global_rules.md'
            deploy_global_rules(global_rules, ide_paths, args.dry_run)
        
        # 總結
        print("\n" + "═" * 60)
        print(f"📊 部署摘要:")
        print(f"   ✓ 成功: {total_success}")
        print(f"   ⊜ 跳過: {total_skipped}")
        print(f"   ✗ 失敗: {total_failed}")
        print("═" * 60)
        
        if not args.dry_run:
            print("\n💡 提示: 請重新啟動 AI IDE 以載入新的 workflows")
        
        return
    
    # 若沒有指定動作，顯示說明
    parser.print_help()


if __name__ == "__main__":
    main()
