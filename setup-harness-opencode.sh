#!/usr/bin/env bash
# Bootstrap or refresh the harness-local OpenCode installation.
# Run this once after cloning, and re-run after global auth changes.
# Generated dir (.opencode-harness/) is git-ignored.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_OC="$SCRIPT_DIR/.opencode-harness"
HARNESS_CONFIG="$HARNESS_OC/config/opencode"
HARNESS_DATA="$HARNESS_OC/data"
HARNESS_BIN="$HARNESS_OC/bin"
GLOBAL_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
REAL_OPENCODE="${OPENCODE_REAL_BIN:-$(command -v opencode || true)}"

if [[ -z "$REAL_OPENCODE" ]]; then
  echo "ERROR: opencode binary not found on PATH" >&2
  exit 1
fi

case "${1:-}" in
  -h|--help)
    cat <<HELP
Usage: bash setup-harness-opencode.sh [--refresh|--no-npm]

Creates/refreshes a git-ignored harness-local OpenCode home at .opencode-harness/:
  - isolated XDG config/data dirs
  - Antigravity auth copied from your global OpenCode account files
  - Gemini 3 Flash auto-balanced model kept as the default
  - OMO/oh-my-openagent intentionally excluded
  - local wrappers at .opencode-harness/bin/opencode and browser-harness

Re-run after global Antigravity auth/account changes.
HELP
    exit 0
    ;;
esac

SKIP_NPM=0
if [[ "${1:-}" == "--no-npm" ]]; then
  SKIP_NPM=1
fi

echo "Setting up harness-local OpenCode at $HARNESS_OC ..."

mkdir -p "$HARNESS_CONFIG/plugins" "$HARNESS_DATA" "$HARNESS_BIN"

# Write opencode.json with a dynamic absolute path to the harness-local copied plugin.
HARNESS_CONFIG="$HARNESS_CONFIG" python3 - <<'PY'
import json
import os
from pathlib import Path

config_dir = Path(os.environ["HARNESS_CONFIG"]).resolve()
plugin_path = str(config_dir / "plugins" / "claude-mem.js")
config = {
    "$schema": "https://opencode.ai/config.json",
    "model": "google/gemini-3-flash",
    "small_model": "google/gemini-3-flash",
    "compaction": {"auto": True},
    "agent": {"compaction": {"model": "opencode/big-pickle"}},
    "permission": {"*": "allow"},
    "plugin": ["opencode-antigravity-auth@latest", plugin_path],
    "provider": {
        "google": {
            "name": "Google",
            "npm": "@ai-sdk/google",
            "models": {
                "antigravity-gemini-3-pro": {
                    "name": "Gemini 3 Pro (Antigravity)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65535},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {"low": {"thinkingLevel": "low"}, "high": {"thinkingLevel": "high"}},
                },
                "antigravity-gemini-3.1-pro": {
                    "name": "Gemini 3.1 Pro (Antigravity)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65535},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {"low": {"thinkingLevel": "low"}, "high": {"thinkingLevel": "high"}},
                },
                "antigravity-gemini-3-flash": {
                    "name": "Gemini 3 Flash (Antigravity)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65536},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {
                        "minimal": {"thinkingLevel": "minimal"},
                        "low": {"thinkingLevel": "low"},
                        "medium": {"thinkingLevel": "medium"},
                        "high": {"thinkingLevel": "high"},
                    },
                },
                "antigravity-claude-sonnet-4-6": {
                    "name": "Claude Sonnet 4.6 (Antigravity)",
                    "limit": {"context": 200000, "output": 64000},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                },
                "antigravity-claude-opus-4-6-thinking": {
                    "name": "Claude Opus 4.6 Thinking (Antigravity)",
                    "thinking": True,
                    "limit": {"context": 200000, "output": 64000},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {
                        "low": {"thinkingConfig": {"thinkingBudget": 8192}},
                        "max": {"thinkingConfig": {"thinkingBudget": 32768}},
                    },
                },
                "gemini-3-flash": {
                    "name": "Gemini 3 Flash (Auto-Balanced)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65536},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {
                        "minimal": {"thinkingLevel": "minimal"},
                        "low": {"thinkingLevel": "low"},
                        "medium": {"thinkingLevel": "medium"},
                        "high": {"thinkingLevel": "high"},
                    },
                },
                "gemini-3-flash-preview": {
                    "name": "Gemini 3 Flash Preview (Gemini CLI)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65536},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {
                        "minimal": {"thinkingLevel": "minimal"},
                        "low": {"thinkingLevel": "low"},
                        "medium": {"thinkingLevel": "medium"},
                        "high": {"thinkingLevel": "high"},
                    },
                },
                "gemini-3-pro-preview": {
                    "name": "Gemini 3 Pro Preview (Gemini CLI)",
                    "thinking": True,
                    "limit": {"context": 1048576, "output": 65535},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {"low": {"thinkingLevel": "low"}, "high": {"thinkingLevel": "high"}},
                },
            },
        },
        "opencode": {
            "name": "OpenCode Zen",
            "models": {
                "big-pickle": {
                    "name": "Big Pickle (Zen Stealth)",
                    "thinking": True,
                    "attachment": True,
                    "limit": {"context": 2000000, "output": 128000},
                    "modalities": {"input": ["text", "image", "pdf"], "output": ["text"]},
                    "variants": {"thinking": {"thinkingLevel": "high"}},
                }
            },
        },
    },
}
(config_dir / "opencode.json").write_text(json.dumps(config, indent=2) + "\n")
PY

echo "  opencode.json written (OMO excluded)"

for f in antigravity.json antigravity-accounts.json; do
  if [[ -f "$GLOBAL_CONFIG/$f" ]]; then
    cp "$GLOBAL_CONFIG/$f" "$HARNESS_CONFIG/$f"
    chmod go-rwx "$HARNESS_CONFIG/$f" 2>/dev/null || true
    echo "  Copied $f from global config"
  else
    echo "  WARNING: $f not found in $GLOBAL_CONFIG — run opencode auth first"
  fi
done

if [[ -f "$GLOBAL_CONFIG/plugins/claude-mem.js" ]]; then
  cp "$GLOBAL_CONFIG/plugins/claude-mem.js" "$HARNESS_CONFIG/plugins/claude-mem.js"
  echo "  Copied claude-mem.js plugin"
else
  echo "  WARNING: claude-mem.js not found — memory features unavailable"
fi

cat > "$HARNESS_CONFIG/package.json" << 'PKGJSON'
{
  "dependencies": {
    "@opencode-ai/plugin": "1.14.30"
  }
}
PKGJSON

echo "  package.json written"

cat > "$HARNESS_CONFIG/.gitignore" << 'GITIGNORE'
# This directory is generated under the unibrowse-level .opencode-harness/ ignore.
# Keep local auth, runtime DBs, and package installs out of source control.
*
GITIGNORE

cat > "$HARNESS_BIN/opencode" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail
export XDG_CONFIG_HOME="$HARNESS_OC/config"
export XDG_DATA_HOME="$HARNESS_OC/data"
exec "$REAL_OPENCODE" "\$@"
WRAPPER
chmod +x "$HARNESS_BIN/opencode"
echo "  Wrapper written: $HARNESS_BIN/opencode -> $REAL_OPENCODE"

cat > "$HARNESS_BIN/browser-harness" <<'BROWSER_WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIBROWSE_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
export PYTHONPATH="$UNIBROWSE_DIR/browser-harness/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m browser_harness.run "$@"
BROWSER_WRAPPER
chmod +x "$HARNESS_BIN/browser-harness"
echo "  Wrapper written: $HARNESS_BIN/browser-harness -> embedded browser-harness"

if [[ "$SKIP_NPM" == "0" ]]; then
  if command -v npm >/dev/null 2>&1; then
    npm install --prefix "$HARNESS_CONFIG" --silent
    echo "  npm dependencies installed/refreshed"
  else
    echo "  WARNING: npm not found — skipping plugin dependency install"
  fi
fi

echo ""
echo "Done. Harness OpenCode isolated at:"
echo "  config: $HARNESS_CONFIG"
echo "  data:   $HARNESS_DATA"
echo "  bin:    $HARNESS_BIN/opencode"
echo "          $HARNESS_BIN/browser-harness"
echo ""
echo "To re-sync auth after logging in globally:"
echo "  bash $SCRIPT_DIR/setup-harness-opencode.sh"
