#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Одноразовый генератор: создаёт index.py, src/* и перезаписывает CamsSetup.py."""

import os

FILES = {}

FILES["index.py"] = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Точка входа: два демона — публикатор и бот."""

import time
import threading

from src import publisher, bot


def main():
    threading.Thread(target=publisher.watcher_thread, daemon=True).start()
    threading.Thread(target=bot.bot_thread, daemon=True).start()
    print("[*] Запущено. Ctrl+C для остановки.", flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
'''

FILES["src/__init__.py"] = r'''__version__ = "2.1.0"
'''

FILES["src/config.py"] = r'''import os
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
'''

FILES["src/vkapi.py"] = r'''import random
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
'''

FILES["src/media.py"] = r'''import os
import time
import glob
import shutil
import subprocess

DEVNULL = subprocess.DEVNULL


def wait_until_ready(path, min_bytes=80000, settle=8, stable_check=2):
    try:
        if not os.path.exists(path):
            return False
        if os.path.getsize(path) < min_bytes:
            return False
        if subprocess.run(["fuser", path], stdout=DEVNULL, stderr=DEVNULL).returncode == 0:
            return False
        if (time.time() - os.path.getmtime(path)) < settle:
            return False
        size = os.path.getsize(path)
        time.sleep(stable_check)
        return size == os.path.getsize(path)
    except Exception:
        return False


def probe_duration(path):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ], stderr=DEVNULL).decode().strip()
        mins, secs = divmod(int(float(out)), 60)
        return "%02d:%02d" % (mins, secs)
    except Exception:
        return "неизвестно"


def to_mp4(mkv_path):
    out = "/tmp/upload_%d_%d.mp4" % (int(time.time()), os.getpid())
    cmd = ["ffmpeg", "-y", "-i", mkv_path, "-map", "0:v:0", "-map", "0:a?",
           "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", out]
    if subprocess.run(cmd, stdout=DEVNULL, stderr=DEVNULL).returncode == 0:
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return out
    return None


def find_thumbnail(video_path):
    base = os.path.splitext(os.path.basename(video_path))[0]
    thumbs = os.path.join(os.path.dirname(video_path), "thumbs")
    for name in ("%s_large.jpg" % base, "%s.jpg" % base):
        p = os.path.join(thumbs, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p, False
    fb = "/tmp/thumb_%d.jpg" % int(time.time())
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:02", "-i", video_path,
                    "-vframes", "1", "-q:v", "2", fb],
                   stdout=DEVNULL, stderr=DEVNULL)
    if os.path.exists(fb) and os.path.getsize(fb) > 0:
        return fb, True
    return None, False


def capture_webcam():
    devs = sorted(glob.glob("/dev/video*"))
    if not devs:
        return None, "нет веб-камеры (/dev/video* не найдены)"
    img = "/tmp/cat_%d.jpg" % int(time.time())
    cmd = ["ffmpeg", "-y", "-f", "v4l2", "-i", devs[0],
           "-vframes", "1", "-q:v", "2", img]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, timeout=10)
        if not os.path.exists(img) or os.path.getsize(img) == 0:
            lines = proc.stderr.strip().splitlines()
            return None, lines[-1] if lines else "нет кадра"
        return img, None
    except Exception as exc:
        return None, str(exc)


def record_audio(seconds=5):
    wav = "/tmp/mic_rec_%d.wav" % int(time.time())
    mp3 = "/tmp/mic_%d.mp3" % int(time.time())
    try:
        subprocess.run(["arecord", "-d", str(seconds), "-f", "cd", wav],
                       stdout=DEVNULL, stderr=DEVNULL, timeout=seconds + 8)
        if not os.path.exists(wav) or os.path.getsize(wav) == 0:
            return None, "микрофон не отвечает"
        subprocess.run(["ffmpeg", "-y", "-i", wav, "-b:a", "128k", mp3],
                       stdout=DEVNULL, stderr=DEVNULL, timeout=15)
    except Exception as exc:
        return None, str(exc)
    finally:
        try:
            os.remove(wav)
        except OSError:
            pass
    if not os.path.exists(mp3) or os.path.getsize(mp3) == 0:
        return None, "не удалось сконвертировать в mp3"
    return mp3, None


def system_status(watch_dir):
    try:
        uptime = subprocess.check_output(["uptime", "-p"]).decode().strip()
        total, _used, free = shutil.disk_usage(watch_dir)
        load = os.getloadavg()

        mem_info = "Н/Д"
        if os.path.exists("/proc/meminfo"):
            mem = {}
            with open("/proc/meminfo", "r") as fh:
                for line in fh:
                    p = line.split(":")
                    if len(p) == 2:
                        mem[p[0].strip()] = int(p[1].split()[0])
            total_mb = mem.get("MemTotal", 0) // 1024
            avail_mb = mem.get("MemAvailable", 0) // 1024
            used_mb = total_mb - avail_mb
            pct = (used_mb / total_mb * 100) if total_mb else 0
            mem_info = "%d/%d МБ (%.1f%%)" % (used_mb, total_mb, pct)

        return (
            "📊 Состояние сервера:\n"
            "• Аптайм: %s\n"
            "• CPU (1/5/15): %.2f, %.2f, %.2f\n"
            "• RAM: %s\n"
            "• Диск: свободно %d ГБ из %d ГБ"
            % (uptime, load[0], load[1], load[2], mem_info,
               free // (2 ** 30), total // (2 ** 30))
        )
    except Exception as exc:
        return "Ошибка сбора метрик: %s" % exc
'''

FILES["src/publisher.py"] = r'''import os
import time
import datetime

from . import vkapi, media
from .config import WATCH_DIR, GROUP_ID, HISTORY_FILE


def _load_history():
    if not os.path.exists(HISTORY_FILE):
        return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as fh:
        return set(line.strip() for line in fh)


def _remember(filename):
    with open(HISTORY_FILE, "a", encoding="utf-8") as fh:
        fh.write(filename + "\n")


def _build_post(cam_name, duration, size_mb, thumb_url, video_url):
    now = datetime.datetime.now()
    text = (
        "📹 [%s] Запись: %s\n"
        "⏱ Длительность: %s\n"
        "💾 Размер: %.1f МБ"
        % (cam_name, now.strftime("%d.%m.%Y %H:%M:%S"), duration, size_mb)
    )
    if thumb_url:
        text += "\n🖼 Превью: %s" % thumb_url
    if video_url:
        text += "\n▶️ Смотреть онлайн: %s" % video_url
    text += ("\n\n#камера_%s@club%d #дата_%s@club%d"
             % (cam_name.replace(" ", "_"), GROUP_ID,
                now.strftime("%d_%m_%Y"), GROUP_ID))
    return text


def _process(full_path, file_name, cam_name):
    tmp_mp4 = media.to_mp4(full_path)
    send_path = tmp_mp4 or full_path
    base = os.path.splitext(file_name)[0]
    upload_name = "%s.mp4" % base if tmp_mp4 else file_name
    size_mb = os.path.getsize(send_path) / (1024 * 1024)
    duration = media.probe_duration(send_path)

    thumb_path, is_temp = media.find_thumbnail(full_path)
    thumb_url = None
    if thumb_path:
        _, thumb_url = vkapi.upload_doc_to_wall(thumb_path, "%s_preview.jpg" % base)
        if is_temp:
            try:
                os.remove(thumb_path)
            except OSError:
                pass

    try:
        attach, video_url = vkapi.upload_doc_to_wall(send_path, upload_name)
        if not attach:
            return False
        text = _build_post(cam_name, duration, size_mb, thumb_url, video_url)
        res = vkapi.post_to_wall(text, attach)
        return "response" in res
    finally:
        if tmp_mp4 and os.path.exists(tmp_mp4):
            try:
                os.remove(tmp_mp4)
            except OSError:
                pass


def watcher_thread():
    print("[*] Мониторинг: %s" % WATCH_DIR, flush=True)
    history = _load_history()
    while True:
        try:
            for root, _dirs, files in os.walk(WATCH_DIR):
                if "videos_old_archive" in root:
                    continue
                for name in files:
                    if not name.lower().endswith(".mkv") or name in history:
                        continue
                    full = os.path.join(root, name)
                    cam = os.path.basename(root)
                    if cam.startswith("videos_") or cam == "video":
                        cam = "Камера"
                    if not media.wait_until_ready(full):
                        continue
                    ok = _process(full, name, cam)
                    print("[%s] %s" % ("+" if ok else "!", name), flush=True)
                    history.add(name)
                    _remember(name)
            time.sleep(3)
        except Exception as exc:
            print("[!] publisher: %s" % exc, flush=True)
            time.sleep(3)
'''

FILES["src/bot.py"] = r'''import os
import time
import requests
import subprocess

from . import vkapi, media
from .config import ADMIN_USER_ID, WATCH_DIR

HELP = (
    "📋 Команды:\n"
    "!статус — CPU, память, диск\n"
    "!cmd <команда> — bash\n"
    "!dvr restart — перезапуск Agent DVR\n"
    "!reboot — перезагрузка ПК\n"
    "!кот — снимок с веб-камеры\n"
    "!звук — 5 сек. с микрофона"
)


def _webcam(peer):
    img, err = media.capture_webcam()
    if not img:
        vkapi.send_message(peer, "⚠️ Камера: %s" % err)
        return
    try:
        attach, err = vkapi.upload_doc_to_messages(img, "webcam.jpg", peer)
        if attach:
            vkapi.send_message(peer, "🐱 Кот на связи:", attach)
        else:
            vkapi.send_message(peer, "⚠️ Не удалось отправить снимок: %s" % err)
    finally:
        try:
            os.remove(img)
        except OSError:
            pass


def _audio(peer):
    vkapi.send_message(peer, "🎤 Записываю 5 сек...")
    mp3, err = media.record_audio(5)
    if not mp3:
        vkapi.send_message(peer, "⚠️ Аудио: %s" % err)
        return
    try:
        attach, err = vkapi.upload_doc_to_messages(mp3, "audio_record.mp3", peer)
        if not attach:
            attach, err = vkapi.upload_doc_to_wall(mp3, "audio_record.mp3")
        if attach:
            vkapi.send_message(peer, "🎙 Аудиозапись (5 сек):", attach)
        else:
            vkapi.send_message(peer, "⚠️ Ошибка загрузки аудио: %s" % err)
    finally:
        try:
            os.remove(mp3)
        except OSError:
            pass


def _cmd(peer, text):
    cmd = text[5:].strip()
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True,
                             text=True, timeout=20)
        out = res.stdout or res.stderr or "[вывод пуст]"
        vkapi.send_message(peer, "💻 $ %s\n\n%s" % (cmd, out))
    except subprocess.TimeoutExpired:
        vkapi.send_message(peer, "⚠️ Таймаут команды (20 сек)")
    except Exception as exc:
        vkapi.send_message(peer, "⚠️ %s" % exc)


def handle_command(text, peer_id):
    if text in ("!кот", "!вебка", "!cat"):
        _webcam(peer_id)
    elif text in ("!звук", "!аудио", "!mic"):
        _audio(peer_id)
    elif text in ("!статус", "!cpu", "!status"):
        vkapi.send_message(peer_id, media.system_status(WATCH_DIR))
    elif text.startswith("!cmd "):
        _cmd(peer_id, text)
    elif text in ("!dvr restart", "!dvr"):
        vkapi.send_message(peer_id, "⏳ Перезапускаю Agent DVR...")
        subprocess.run("sudo systemctl restart AgentDVR || sudo systemctl restart agentdvr",
                       shell=True)
        vkapi.send_message(peer_id, "✅ Готово.")
    elif text == "!reboot":
        vkapi.send_message(peer_id, "⚠️ Перезагрузка...")
        time.sleep(2)
        subprocess.run("sudo reboot", shell=True)
    elif text in ("!help", "!помощь"):
        vkapi.send_message(peer_id, HELP)


def bot_thread():
    print("[*] Бот запущен, ожидание команд...", flush=True)
    while True:
        try:
            lp = vkapi.longpoll_server()
            if "error" in lp:
                time.sleep(10)
                continue
            server = lp["response"]["server"]
            key = lp["response"]["key"]
            ts = lp["response"]["ts"]

            while True:
                resp = requests.get(
                    "%s?act=a_check&key=%s&ts=%s&wait=25" % (server, key, ts),
                    timeout=40).json()
                if "failed" in resp:
                    break
                ts = resp.get("ts", ts)
                for upd in resp.get("updates", []):
                    if upd.get("type") != "message_new":
                        continue
                    obj = upd.get("object", {})
                    msg = obj.get("message", obj)
                    from_id = msg.get("from_id")
                    peer_id = msg.get("peer_id", from_id)
                    text = (msg.get("text") or "").strip()
                    if from_id != ADMIN_USER_ID or not text.startswith("!"):
                        continue
                    handle_command(text, peer_id)
        except Exception as exc:
            print("[!] bot: %s" % exc, flush=True)
            time.sleep(5)
'''

FILES["CamsSetup.py"] = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Установщик: копирует index.py + src/ в ~/scripts, настраивает systemd."""

import os
import sys
import json
import shutil
import subprocess

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def banner():
    print("=" * 60)
    print("   CCTV VK BOT — УСТАНОВКА")
    print("=" * 60)


def get_args():
    token = os.environ.get("VK_TOKEN")
    group_id = os.environ.get("VK_GROUP_ID")
    admin_id = os.environ.get("VK_ADMIN_ID")
    if len(sys.argv) >= 4:
        token, group_id, admin_id = sys.argv[1:4]
    token = token or input("1. Токен сообщества VK: ").strip()
    group_id = (group_id or input("2. ID группы (цифры): ")).strip().replace("-", "")
    admin_id = (admin_id or input("3. Ваш ID VK (цифры): ")).strip().replace("-", "")
    token = token.replace(" ", "").replace("'", "").replace('"', "")
    if not group_id.isdigit() or not admin_id.isdigit():
        sys.exit("[!] ID группы и админа — только цифры.")
    return token, int(group_id), int(admin_id)


def check_token(token, group_id):
    print("\n[1/5] Проверка токена...")
    r = requests.get("https://api.vk.com/method/docs.getWallUploadServer",
                     params={"access_token": token, "group_id": group_id,
                             "v": "5.131"}, timeout=15).json()
    if "error" in r:
        sys.exit("[!] VK: %s" % r["error"]["error_msg"])
    requests.get("https://api.vk.com/method/groups.setLongPollSettings",
                 params={"access_token": token, "group_id": group_id,
                         "enabled": 1, "api_version": "5.131",
                         "message_new": 1, "v": "5.131"}, timeout=15)
    print("[ OK ] Long Poll активирован.")


def deps():
    print("\n[2/5] apt: python3-requests, ffmpeg, alsa-utils, psmisc...")
    subprocess.run(["sudo", "apt", "update", "-y"], check=True)
    subprocess.run(["sudo", "apt", "install", "-y", "python3", "python3-requests",
                    "ffmpeg", "alsa-utils", "psmisc"], check=True)


def rotation(videos_dir, scripts_dir):
    print("\n[3/5] Ротация и cron...")
    os.makedirs(videos_dir, exist_ok=True)
    os.makedirs(scripts_dir, exist_ok=True)
    script = os.path.join(scripts_dir, "rotate_camera.sh")
    with open(script, "w", encoding="utf-8") as fh:
        fh.write('#!/bin/bash\n'
                 'TODAY=$(date +%%d.%%m.%%Y)\n'
                 'BASE="%s"\n'
                 'T="$BASE/videos_${TODAY}"\n'
                 'L="$BASE/video"\n'
                 'mkdir -p "$T"\n'
                 'chmod -R 777 "$T" 2>/dev/null || true\n'
                 'ln -sfn "$T" "$L"\n'
                 'echo "[$(date)] $L -> $T" >> "%s/rotation.log"\n'
                 % (videos_dir, scripts_dir))
    os.chmod(script, 0o755)

    vp = os.path.join(videos_dir, "video")
    if os.path.exists(vp) and not os.path.islink(vp):
        os.rename(vp, os.path.join(videos_dir, "videos_old_archive"))
    subprocess.run([script], check=True)

    cron = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True).stdout
    if "rotate_camera.sh" not in cron:
        subprocess.run(["crontab", "-"],
                       input=cron + "0 0 * * * %s\n" % script,
                       text=True, check=True)


def install_package(scripts_dir, token, group_id, admin_id, videos_dir):
    print("\n[4/5] Копирование index.py и src/...")
    src_dir = os.path.join(HERE, "src")
    index_src = os.path.join(HERE, "index.py")
    if not os.path.isdir(src_dir):
        sys.exit("[!] Не найден каталог src/ рядом с CamsSetup.py")
    if not os.path.isfile(index_src):
        sys.exit("[!] Не найден index.py рядом с CamsSetup.py")

    src_dst = os.path.join(scripts_dir, "src")
    index_dst = os.path.join(scripts_dir, "index.py")
    if os.path.exists(src_dst):
        shutil.rmtree(src_dst)
    shutil.copytree(src_dir, src_dst,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(index_src, index_dst)

    config = os.path.join(scripts_dir, "cctv_config.json")
    with open(config, "w", encoding="utf-8") as fh:
        json.dump({
            "VK_TOKEN": token,
            "GROUP_ID": group_id,
            "ADMIN_USER_ID": admin_id,
            "WATCH_DIR": videos_dir,
            "API_VERSION": "5.131",
        }, fh, indent=4, ensure_ascii=False)
    os.chmod(config, 0o600)

    files = [index_dst] + [os.path.join(src_dst, f) for f in os.listdir(src_dst)
                            if f.endswith(".py")]
    subprocess.run([sys.executable, "-m", "py_compile"] + files, check=True)
    print("[ OK ] Синтаксис проверен.")


def sudoers(user):
    rule = ("%s ALL=(ALL) NOPASSWD: /bin/systemctl restart vk-watcher.service, "
            "/bin/systemctl restart AgentDVR, /bin/systemctl restart agentdvr, "
            "/sbin/reboot, /sbin/shutdown\n" % user)
    path = "/etc/sudoers.d/cctv_bot"
    subprocess.run(["sudo", "tee", path], input=rule, text=True,
                   stdout=subprocess.DEVNULL, check=True)
    subprocess.run(["sudo", "chmod", "0440", path], check=True)


def systemd(user, scripts_dir):
    print("\n[5/5] Служба vk-watcher.service...")
    unit = ("[Unit]\n"
            "Description=CCTV VK Bot\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            "User=%s\n"
            "WorkingDirectory=%s\n"
            "ExecStart=/usr/bin/python3 %s/index.py\n"
            "Restart=always\n"
            "RestartSec=10\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
            % (user, scripts_dir, scripts_dir))
    subprocess.run(["sudo", "tee", "/etc/systemd/system/vk-watcher.service"],
                   input=unit, text=True, stdout=subprocess.DEVNULL, check=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    subprocess.run(["sudo", "systemctl", "enable", "--now", "vk-watcher.service"],
                   check=True)
    subprocess.run(["sudo", "systemctl", "restart", "vk-watcher.service"],
                   check=True)


def main():
    banner()
    token, group_id, admin_id = get_args()
    check_token(token, group_id)
    deps()
    home = os.path.expanduser("~")
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "user"
    scripts_dir = os.path.join(home, "scripts")
    videos_dir = os.path.join(home, "Videos")
    rotation(videos_dir, scripts_dir)
    install_package(scripts_dir, token, group_id, admin_id, videos_dir)
    sudoers(user)
    systemd(user, scripts_dir)
    print("\n✅ Готово. Проверь в ВК: !help, !статус, !звук, !кот")


if __name__ == "__main__":
    main()
'''

for path, content in FILES.items():
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK:", path)

print("\nВсе файлы созданы. Дальше: git add -A && git commit && git push")
