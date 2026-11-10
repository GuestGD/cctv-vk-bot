import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "cctv_config.json")
HISTORY_FILE = os.path.join(BASE_DIR, "uploaded_history.log")

with open(CONFIG_PATH, "r", encoding="utf-8") as _f:
    _cfg = json.load(_f)

VK_TOKEN = _cfg["VK_TOKEN"]
GROUP_ID = _cfg["GROUP_ID"]
ADMIN_USER_ID = _cfg["ADMIN_USER_ID"]
WATCH_DIR = _cfg["WATCH_DIR"]
API_VERSION = _cfg.get("API_VERSION", "5.131")
