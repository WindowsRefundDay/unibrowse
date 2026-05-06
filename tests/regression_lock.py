import sys
import os
from pathlib import Path

# Add paths for imports
ROOT = Path("/Users/joelmanuel/browser-harness-folder")
sys.path.insert(0, str(ROOT / "unibrowse"))
sys.path.insert(0, str(ROOT / "browser-harness" / "agent-workspace"))

import app
import migrate
from agent_helpers import fetch_memory, get_credentials, store_learning, cleanup_tabs

def test_tab_cleanup_tool():
    print("Testing tab cleanup tool...")
    # Should at least run without crashing, even if it returns 'No clutter found.'
    res = cleanup_tabs()
    assert isinstance(res, str)
    print("  ✓ Tab cleanup tool ok")

def test_user_card():
    print("Testing User Card...")
    card = app.load_user_card()
    assert "Joel Manuel" in card
    print("  ✓ User Card ok")

def test_learning_tool():
    print("Testing learning tool...")
    # This should trigger the fallback signal if worker is not running
    res = store_learning("site_fix", "test fix for regression")
    assert "successfully" in res or "Learning storage failed" in res
    print("  ✓ Learning tool ok")

def test_layered_prompt():
    print("Testing layered prompt...")
    # Qt requirement
    from PySide6.QtWidgets import QApplication
    qt_app = QApplication.instance() or QApplication([])
    
    # Mock some tabs
    app_instance = app.UnibrowseApp()
    app_instance.current_tabs = [{"title": "Test Site", "url": "https://test.com", "targetId": "123"}]
    app_instance.active_tab_id = "123"
    
    prompt = app_instance.build_task_prompt("my secret task")
    assert "# Browser Agent Prompt" in prompt
    assert "Joel Manuel" in prompt
    assert "Test Site · test.com" in prompt
    assert "my secret task" in prompt
    print("  ✓ Layered prompt ok")

def test_auth_helper():
    print("Testing auth helper...")
    # This should trigger the AGENT_SIGNAL (even if keyring is installed) 
    # if the test domain doesn't exist in user's keychain.
    res = get_credentials("test-domain-not-exists-12345.com")
    assert res == "CREDENTIALS_REQUIRED_VIA_GUI"
    print("  ✓ Auth helper ok")

def test_prompt_loading():
    print("Testing prompt loading...")
    prompt = app.load_agent_prompt()
    assert "# Browser Agent Prompt" in prompt
    print("  ✓ Prompt loaded correctly")

def test_tab_summarization():
    print("Testing tab summarization...")
    tab = {"title": "Google", "url": "https://google.com/search?q=test"}
    summary = app.summarize_tab(tab)
    assert "Google" in summary
    assert "google.com" in summary
    
    internal = {"title": "Settings", "url": "chrome://settings"}
    assert app.is_internal_tab(internal)
    
    error_tab = {"title": "Error", "url": "chrome-error://chromewebdata/"}
    assert app.is_internal_tab(error_tab)
    print("  ✓ Tab helpers ok")

def test_constants():
    print("Testing constants...")
    assert isinstance(app.PERSONAL_PROFILE_ROOT, str)
    assert isinstance(app.AGENT_PROFILE_ROOT, str)
    assert app.BROWSER_PORT == "9223"
    print("  ✓ Constants ok")

def test_profile_logic():
    print("Testing profile bootstrap...")
    path = migrate.ensure_agent_profile()
    assert ".profiles" in path
    print("  ✓ Profile logic ok")

def test_command_builders():
    print("Testing command builders...")
    cmd = app.run_unibrowse_backend("hello", "model-x", "high")
    # Verify that it correctly resolves to 'opencode'
    assert cmd[0].endswith("opencode")
    assert "--model" in cmd
    assert "model-x" in cmd
    assert "high" in cmd
    assert cmd[-1] == "hello"
    print("  ✓ Command builders ok")
    print("  ✓ Command builders ok")

def test_memory_fallback():
    print("Testing memory helper...")
    res = fetch_memory("missing-query-12345")
    assert isinstance(res, str)
    print("  ✓ Memory helper ok")

if __name__ == "__main__":
    try:
        test_constants()
        test_tab_cleanup_tool()
        test_user_card()
        test_auth_helper()
        test_learning_tool()
        test_layered_prompt()
        test_prompt_loading()
        test_tab_summarization()
        test_profile_logic()
        test_command_builders()
        test_memory_fallback()
        print("\nREGRESSION LOCK: ALL PASS")
    except Exception as e:
        print(f"\nREGRESSION LOCK FAILED: {e}")
        sys.exit(1)
