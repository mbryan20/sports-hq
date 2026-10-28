# Browser rules for every Sports HQ laptop task

Since 2026-10-28 all laptop tasks use **Michael's own Chrome through Claude in Chrome** (tools named
`mcp__claude-in-chrome__*`). His sign-ins there persist (Yahoo, Yahoo pick'em, ESPN, BTO, CFP, Sleeper).
The Claude app's built-in browser (`mcp__Claude_Browser__*`) loses sign-ins when the app restarts:
**never use it** for these tasks.

## Connect (do this first)
1. If Chrome isn't running, start it (PowerShell):
   `if (-not (Get-Process chrome -ErrorAction SilentlyContinue)) { Start-Process chrome; Start-Sleep 30 }`
2. Load the tools in ONE ToolSearch call:
   `select:mcp__claude-in-chrome__list_connected_browsers,mcp__claude-in-chrome__select_browser,mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__tabs_close_mcp`
3. `list_connected_browsers`. If a browser is listed but not "inUse", `select_browser` with its deviceId
   (prefer the local one). If none is listed or a tool says the extension isn't connected, retry up to
   4 times, 30 seconds apart (restart Chrome with step 1 between tries). Still nothing → the task's failure
   push with reason "Chrome extension not connected".
4. `tabs_context_mcp` with `createIfEmpty: true`, and work only in the tab(s) of that group. Open extra
   pages with `navigate` (pass the tabId) or `tabs_create_mcp`. Never touch tabs outside the group.

## Reading
- `navigate` to the URL, then `get_page_text` or `javascript_tool` (`action: "javascript_exec"`, `text`, `tabId`).
- Signed out (a login page, login.yahoo.com, ESPN log-in prompt, `/login` path) → record "<site> signed out in
  Chrome — Michael needs to sign in there" and carry on with what you can.

## Always
- Read-only: never submit, save, bid, add, drop, trade or set lineups. Never type a password or press a sign-in
  button. Never print cookies or tokens.
- Close every tab you opened (`tabs_close_mcp`) before finishing.
