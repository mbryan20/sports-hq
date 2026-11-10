# Browser rules for every Sports HQ laptop task

Since 2026-10-28 all laptop tasks use **Michael's own Chrome through Claude in Chrome** (tools named
`mcp__claude-in-chrome__*`). His sign-ins there persist (Yahoo, Yahoo pick'em, ESPN, BTO, CFP, Sleeper).
The Claude app's built-in browser (`mcp__Claude_Browser__*`) loses sign-ins when the app restarts:
**never use it** for these tasks.

## Connect (do this first)
1. Make sure Michael's OWN Chrome is running (another Windows user's Chrome can be open in a second
   session; it does not count). PowerShell:
   `$me=(Get-Process -Id $PID).SessionId; if (Get-Process chrome -ErrorAction SilentlyContinue | Where-Object SessionId -eq $me) { 'running' } else { Start-Process chrome; 'started' }`
2. Load the tools in ONE ToolSearch call:
   `select:mcp__claude-in-chrome__list_connected_browsers,mcp__claude-in-chrome__select_browser,mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__find,mcp__claude-in-chrome__tabs_close_mcp`
3. TRY: `tabs_context_mcp` with `createIfEmpty: true`. If it returns tabs, you are connected: go to step 4.
   Judge by tabs_context_mcp only (list_connected_browsers can return [] even when Chrome works).
   If it says Claude in Chrome is not connected: call `list_connected_browsers`; if it lists a browser,
   `select_browser` with its deviceId (prefer the local one) and TRY again at once.
   Otherwise WAIT 60 SECONDS: in Bash run `sleep 60` with run_in_background: true, then make no other
   tool call until its completion notice arrives (a foreground Start-Sleep is blocked; checking early
   wastes a try). Then TRY again. 5 tries in all (about 5 minutes). Never close, kill or restart Chrome.
   Still not connected: the task's failure push with reason "Chrome extension not connected after
   5 tries over 5 minutes. Fix: close and reopen Chrome on the laptop", and end the report with one
   line: FAILED: Chrome extension not connected after 5 tries.
   (Nov 10: the Nov 6 and Nov 9 4:33pm syncs synced nothing after Claude app updates: the extension
   reconnected minutes to hours later, the old check counted another user's Chrome, and its waits were
   not real. Evidence: claude-audit overhaul/staged/BROWSER-retry.md.)
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
