import os
import shutil
import subprocess
from pathlib import Path


# Project-Local Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PERSONAL_PROFILE_ROOT = Path.home() / "Library/Application Support/Google/Chrome"
PERSONAL_PROFILE = PERSONAL_PROFILE_ROOT / "Default"

# Local data storage within project folder
AGENT_PROFILE_ROOT = PROJECT_ROOT / ".profiles"
AGENT_PROFILE = AGENT_PROFILE_ROOT / "Default"
MEMORIES_DIR = PROJECT_ROOT / ".memories"
SYNC_EXCLUDES = [
    "Singleton*",
    "*Lock*",
    "Cache*",
    "Code Cache*",
    "GPUCache*",
    "GrShaderCache*",
    "ShaderCache*",
    "Crashpad*",
    "BrowserMetrics*",
    "Session Storage*",
    "Sessions*",
]


def _rsync_update(src, dest):
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-a", "--update"]
    for pattern in SYNC_EXCLUDES:
        cmd.extend(["--exclude", pattern])
    cmd.extend([str(src) + "/", str(dest) + "/"])
    subprocess.run(cmd, check=True)

def ensure_agent_profile():
    src = PERSONAL_PROFILE
    dest = AGENT_PROFILE
    
    if dest.exists():
        print(f"Profile already exists at {dest}. Skipping sync; use on-demand sync when needed.")
        return str(dest.parent)
    
    print(f"Migrating Chrome profile from {src} to {dest}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # We use rsync via subprocess for efficiency and to handle macOS permissions better
    try:
        _rsync_update(src, dest)
        print("Migration successful.")
    except Exception as e:
        print(f"Migration failed: {e}")
        # Fallback to simple copy if rsync fails
        try:
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns('Singleton*', '*Lock*', 'Cache*'))
        except Exception as e2:
            print(f"Fallback migration failed: {e2}")
            
    return str(dest.parent)


def sync_profiles():
    src = PERSONAL_PROFILE
    dest = AGENT_PROFILE
    if not dest.exists():
        ensure_agent_profile()

    print("Syncing personal Chrome profile and agent profile...")
    _rsync_update(src, dest)
    _rsync_update(dest, src)
    print("Profile sync complete.")
    return str(dest.parent)


def sync_to_remote(server_ip, remote_user="root", remote_path="/opt/unibrowse"):
    """
    Syncs the local agent profile and memories to the remote Linux server.
    Note: Requires SSH access to the server.
    """
    print(f"Mirroring workspace to remote server {server_ip}...")
    
    # We sync three folders: .profiles, .memories, and agent-workspace
    sync_targets = [
        (".profiles/", f"{remote_path}/.profiles/"),
        (".memories/", f"{remote_path}/.memories/"),
        ("browser-harness/agent-workspace/", f"{remote_path}/browser-harness/agent-workspace/")
    ]
    
    success = True
    for local_sub, remote_sub in sync_targets:
        local_src = str(PROJECT_ROOT / local_sub)
        if not os.path.exists(local_src):
            continue
            
        remote_dest = f"{remote_user}@{server_ip}:{remote_sub}"
        
        # We use rsync over SSH
        cmd = ["rsync", "-avz", "--delete", "--update"]
        for pattern in SYNC_EXCLUDES:
            cmd.extend(["--exclude", pattern])
        cmd.extend([local_src, remote_dest])
        
        try:
            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"Remote sync failed for {local_sub}: {e}")
            success = False
            
    if success:
        print("Mirroring successful.")
    return success


if __name__ == "__main__":
    sync_profiles()
