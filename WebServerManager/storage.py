import json
import os

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "WebServerManager")
SERVERS_FILE = os.path.join(APP_DIR, "servers.json")
BACKENDS_DIR = os.path.join(APP_DIR, "backends")
INSTANCES_DIR = os.path.join(APP_DIR, "instances")


def ensure_dirs():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(BACKENDS_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)


def load_servers():
    ensure_dirs()
    if not os.path.exists(SERVERS_FILE):
        return []
    try:
        with open(SERVERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_servers(servers):
    ensure_dirs()
    with open(SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump(servers, f, indent=2, ensure_ascii=False)
