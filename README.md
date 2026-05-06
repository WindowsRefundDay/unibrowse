# <img src="assets/logo.svg" width="48" height="48" valign="middle"> unibrowse

Frontend for `browser-harness` with 'opencode' and 'claude-mem' integration.

## Browser Modes

- `Agent profile` uses `~/.unibrowse-agent-profile` for isolated automation.
- `Personal Chrome` uses your normal Chrome user-data directory for personal browsing context, such as YouTube playback.
- `Remote CDP` sends commands to a manually supplied CDP URL.
- On startup, the app syncs newer profile files both ways between your personal `Default` profile and the agent profile, excluding Chrome locks, caches, sessions, and other volatile files.
- Launches the selected local Chrome profile on `http://127.0.0.1:9223`.
- Sets `BH_NO_ACTIVATE=1` so `browser-harness` avoids `Target.activateTarget` focus stealing.

Launch app:

```bash
open "$HOME/Applications/unibrowse.app"
```

## Remote Mode

Enable `Remote backend` in the GUI and enter a CDP URL such as:

```text
http://server.example.com:9223
```

The GUI will send browser-harness/unibrowse commands to that CDP endpoint instead of launching local Chrome.

## Command Shortcuts

- `bh: print(page_info())` runs raw browser-harness Python.
- `url: https://example.com` opens a URL through browser-harness.
- Any other text is sent to `unibrowse run` with browser-harness stealth environment variables.
- The model field defaults to `google/antigravity-gemini-3-flash`. Edit it if your unibrowse provider uses a different exact model ID.
- The progress panel shows concise task/reasoning summaries, not private chain-of-thought.

## Credits & Acknowledgements

- **[browser-harness](https://github.com/browser-harness):** The core engine for stealth browser automation.
- **[OpenCode](https://github.com/opencode):** The foundational agent runtime and execution environment.
- **[Claude-Mem](https://github.com/claude-mem):** Advanced memory and context management for persistent agent learning.
- **Antigravity:** Authored by the Antigravity agentic coding assistant.

