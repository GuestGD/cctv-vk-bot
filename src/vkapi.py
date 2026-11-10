import random
import requests

from .config import VK_TOKEN, GROUP_ID, API_VERSION

API = "https://api.vk.com/method/"


def call(method, params=None, files=None, timeout=30):
    data = dict(params or {})
    data["access_token"] = VK_TOKEN
    data["v"] = API_VERSION
    if files is not None:
        return requests.post(API + method, data=data, files=files, timeout=timeout).json()
    return requests.get(API + method, params=data, timeout=timeout).json()


def _save_doc(uploaded, title):
    r = call("docs.save", {"file": uploaded, "title": title})
    if "error" in r:
        return None, r["error"]["error_msg"]
    doc = r["response"]["doc"]
    return "doc%d_%d" % (doc["owner_id"], doc["id"]), doc.get("url", "")


def upload_doc_to_messages(path, name, peer_id):
    params = {"type": "doc", "peer_id": peer_id}
    if GROUP_ID:
        params["group_id"] = GROUP_ID
    r = call("docs.getMessagesUploadServer", params)
    if "error" in r:
        return None, r["error"]["error_msg"]
    with open(path, "rb") as fh:
        up = requests.post(r["response"]["upload_url"],
                           files={"file": (name, fh)}, timeout=180).json()
    if "file" not in up:
        return None, "upload: %s" % str(up)[:200]
    return _save_doc(up["file"], name)


def upload_doc_to_wall(path, name):
    r = call("docs.getWallUploadServer", {"group_id": GROUP_ID})
    if "error" in r:
        return None, r["error"]["error_msg"]
    with open(path, "rb") as fh:
        up = requests.post(r["response"]["upload_url"],
                           files={"file": (name, fh)}, timeout=300).json()
    if "file" not in up:
        return None, "upload: %s" % str(up)[:200]
    return _save_doc(up["file"], name)


def upload_voice_message(path, peer_id):
    """Загрузка голосового сообщения (audio_message)."""
    params = {"type": "audio_message", "peer_id": peer_id}
    if GROUP_ID:
        params["group_id"] = GROUP_ID
    r = call("docs.getMessagesUploadServer", params)
    if "error" in r:
        return None, r["error"]["error_msg"]

    with open(path, "rb") as fh:
        up = requests.post(r["response"]["upload_url"],
                           files={"file": ("voice.ogg", fh)}, timeout=60).json()

    if "file" not in up:
        return None, "upload: %s" % str(up)[:300]

    save = call("docs.save", {"file": up["file"], "title": "voice.ogg"})
    if "error" in save:
        return None, save["error"]["error_msg"]

    resp = save.get("response", {})
    if "audio_message" in resp:
        m = resp["audio_message"]
        return "doc%d_%d" % (m["owner_id"], m["id"]), None

    if "doc" in resp:
        d = resp["doc"]
        return "doc%d_%d" % (d["owner_id"], d["id"]), None

    return None, "неизвестный ответ: %s" % str(resp)[:300]


def send_message(peer_id, text="", attachment=None):
    params = {"peer_id": peer_id, "random_id": random.randint(1, 10**9)}
    if text:
        params["message"] = text[:4000]
    if attachment:
        params["attachment"] = attachment
    try:
        return call("messages.send", params, timeout=15)
    except Exception:
        return {"error": "network"}


def longpoll_server():
    return call("groups.getLongPollServer", {"group_id": GROUP_ID}, timeout=20)


def post_to_wall(message, attachment):
    return call("wall.post", {
        "owner_id": -GROUP_ID,
        "from_group": 1,
        "message": message,
        "attachments": attachment,
    })
