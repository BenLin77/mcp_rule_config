# mcp_rule_config

> 語系同步：此檔案需與 `README.en.md` 保持一致，更新任一語系請同步另一份文件。

集中管理 MCP 設定、全域規則與 Windsurf 工作流程的倉庫，支援以下目標環境：

- Cursor
- Windsurf
- Claude（Claude CLI MCP 設定與註冊）

## 專案檔案

- `global_rules.md`：全域規範與開發標準。
- `mcp_config.json`：MCP 伺服器設定（敏感資訊以環境變數引用）。
- `workflows/`：供 Windsurf 使用的 workflow 說明文件（Markdown）。
- `sync_mcp.py`：同步腳本，負責處理環境變數、生成臨時檔案並寫入各目標路徑。

## 同步目標

- Cursor：`~/.cursor/AGENTS.md`、`~/.cursor/mcp.json`
- Windsurf：
  - `~/.codeium/windsurf/mcp_config.json`
  - `~/.codeium/windsurf/memories/global_rules.md`
  - `~/.codeium/windsurf/workflows/**/*.md`（會保留 workflow 子資料夾結構）
- Claude：`~/.claude/CLAUDE.md`，並透過 `claude mcp add` 註冊 `mcp_config.json` 內的伺服器

> 註：上述路徑會自動依 OS 家目錄解析，可在 macOS、Linux、Windows 執行。

## 使用方式

建議使用 `uv` 執行（亦可直接使用 `python3`）：

```bash
# 將設定同步至 Cursor / Windsurf / Claude 並更新 Claude CLI MCP 伺服器
uv run sync_mcp.py

# 或使用系統 Python
python3 sync_mcp.py
```

### 腳本流程摘要

1. 重新載入 `.env` / `~/.env` / fish shell 環境變數並展開 `mcp_config.json` 內容。
2. 生成臨時 `mcp_config.json`，同步至 Cursor 與 Windsurf。
3. 依設定註冊 Claude CLI MCP 伺服器並清理多餘項目。
4. 將 `global_rules.md` 複製到各目標路徑。
5. 將 `workflows/**/*.md` 複製到 `~/.codeium/windsurf/workflows/`（維持原始子資料夾結構）。

## 環境變數

請在 shell 或本地 `.env` 中設定以下變數（勿提交 `.env`）：

- `NOTION_TOKEN`
- `GOOGLE_MAPS_API_KEY`
- `SSH_PASSWORD`
- 其他在 `mcp_config.json` 以 `${VAR_NAME}` 引用的密鑰

示例：

```bash
export NOTION_TOKEN=your_notion_token
export GOOGLE_MAPS_API_KEY=your_google_maps_api_key
export SSH_PASSWORD=your_ssh_password
```

可複製 `.env.example` 為 `.env` 並填入實際值：

```bash
cp .env.example .env
```

## 安全建議

- 所有秘密值僅以環境變數引用，避免寫進版本控制。
- 建議啟用 `pre-commit` + `gitleaks` 於本倉庫：

```bash
# 以 macOS 為例
brew install pre-commit gitleaks
# 或使用 uv
uv tool install pre-commit

pre-commit install
pre-commit run --all-files
```

- 在 GitHub Repository 啟用 Secret Scanning、Push Protection，並保護 `main` 分支。

## 備註

- `mcp_config.json` 內的 `${VAR_NAME}` 佔位符需對應至有效環境變數，腳本會在同步前重新載入。
- 若新增 workflow，執行 `sync_mcp.py` 後即可自動同步至 Windsurf。
- 若需要額外支援其他編輯器，可延伸 `sync_to_editors` 或新增專屬函式。
