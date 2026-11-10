cat << 'EOF' > ~/CamsSetup.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent DVR to VK Exporter & Remote Control Bot
Production-ready installer for Ubuntu / Xubuntu systems.
Zero hardcoded credentials. Safe for public repositories.
"""

import os
import sys
import json
import shutil
import subprocess
import requests

def print_banner():
    print("=" * 60)
    print("   AGENT DVR -> VK AUTOUPLOADER & REMOTE CONTROL BOT")
    print("=" * 60)

def get_args():
    token = os.environ.get("VK_TOKEN")
    group_id = os.environ.get("VK_GROUP_ID")
    admin_id = os.environ.get("VK_ADMIN_ID")

    if len(sys.argv) >= 4:
        token = sys.argv[1]
        group_id = sys.argv[2]
        admin_id = sys.argv[3]

    if not token:
        token = input("1. Введите токен сообщества VK (vk1.a...): ")
    if not group_id:
        group_id = input("2. Введите цифровой ID группы (только цифры): ")
    if not admin_id:
        admin_id = input("3. Введите ваш личный ID страницы VK для команд: ")

    token = token.strip().replace("'", "").replace('"', "").replace("\n", "").replace(" ", "")
    group_id = group_id.strip().replace("-", "").replace(" ", "")
    admin_id = admin_id.strip().replace("-", "").replace(" ", "")

    if not group_id.isdigit() or not admin_id.isdigit():
        print("\n[ОШИБКА] ID группы и ID администратора должны состоять строго из цифр.")
        sys.exit(1)

    return token, int(group_id), int(admin_id)

def verify_and_configure_vk(token, group_id):
    print("\n[1/6] Проверка токена и настройка прав Long Poll API...")
    try:
        res = requests.get("https://api.vk.com/method/docs.getWallUploadServer", params={
            "access_token": token,
            "group_id": group_id,
            "v": "5.131"
        }, timeout=10).json()

        if "error" in res:
            print(f"[ОШИБКА VK] {res['error']['error_msg']}")
            sys.exit(1)

        requests.get("https://api.vk.com/method/groups.setLongPollSettings", params={
            "access_token": token,
            "group_id": group_id,
            "enabled": 1,
            "api_version": "5.131",
            "message_new": 1,
            "v": "5.131"
        }, timeout=10)

        print("[ OK ] Токен валиден, Long Poll для входящих сообщений активирован.")
    except Exception as e:
        print(f"[ОШИБКА] Сбой подключения к серверам VK: {e}")
        sys.exit(1)

def install_system_dependencies():
    print("\n[2/6] Установка зависимостей (ffmpeg, psmisc, curl, python3-requests)...")
    subprocess.run(["sudo", "apt", "update", "-y"], check=True)
    subprocess.run(["sudo", "apt", "install", "-y", "python3", "python3-requests", "ffmpeg", "curl", "psmisc"], check=True)

def setup_paths_and_permissions(home, videos_dir, scripts_dir):
    print("\n[3/6] Настройка каталогов и суточной ротации...")
    os.makedirs(scripts_dir, exist_ok=True)
    os.makedirs(videos_dir, exist_ok=True)

    rotate_script = os.path.join(scripts_dir, "rotate_camera.sh")
    with open(rotate_script, "w", encoding="utf-8") as f:
        f.write(f'''#!/bin/bash
TODAY=$(date +%d.%m.%Y)
BASE_DIR="{videos_dir}"
TARGET_DIR="${{BASE_DIR}}/videos_${{TODAY}}"
LINK_PATH="${{BASE_DIR}}/video"

mkdir -p "$TARGET_DIR"
chmod -R 777 "$TARGET_DIR" 2>/dev/null || true
ln -sfn "$TARGET_DIR" "$LINK_PATH"
echo "[$(date)] Ротация: $LINK_PATH -> $TARGET_DIR" >> "{scripts_dir}/rotation.log"
''')
    os.chmod(rotate_script, 0o755)

    video_path = os.path.join(videos_dir, "video")
    if os.path.exists(video_path) and not os.path.islink(video_path):
        os.rename(video_path, os.path.join(videos_dir, "videos_old_archive"))
    subprocess.run([rotate_script], check=True)

    existing_cron = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout
    cron_line = f"0 0 * * * {rotate_script}\n"
    if "rotate_camera.sh" not in existing_cron:
        new_cron = existing_cron + cron_line
        subprocess.run(["crontab", "-"], input=new_cron, text=True, check=True)

def setup_sudoers_for_bot(user):
    print("\n[4/6] Настройка прав sudo для команд бота...")
    rule = f"{user} ALL=(ALL) NOPASSWD: /bin/systemctl restart AgentDVR, /bin/systemctl restart agentdvr, /sbin/reboot, /sbin/shutdown\n"
    sudoers_path = "/etc/sudoers.d/cctv_bot"
    subprocess.run(["sudo", "tee", sudoers_path], input=rule, text=True, stdout=subprocess.DEVNULL, check=True)
    subprocess.run(["sudo", "chmod", "0440", sudoers_path], check=True)

def generate_watcher_daemon(home, scripts_dir, videos_dir, token, group_id, admin_id):
    print("\n[5/6] Генерация демона vk_watcher.py...")
    config_file = os.path.join(scripts_dir, "cctv_config.json")
    config_data = {
        "VK_TOKEN": token,
        "GROUP_ID": group_id,
        "ADMIN_USER_ID": admin_id,
        "WATCH_DIR": videos_dir,
        "API_VERSION": "5.131"
    }
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4)
    os.chmod(config_file, 0o600)

    watcher_file = os.path.join(scripts_dir, "vk_watcher.py")
    watcher_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import random
import shutil
import threading
import subprocess
import requests
import datetime

CONFIG_PATH = "{config_file}"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

VK_TOKEN = CONFIG["VK_TOKEN"]
GROUP_ID = CONFIG["GROUP_ID"]
ADMIN_USER_ID = CONFIG["ADMIN_USER_ID"]
WATCH_DIR = CONFIG["WATCH_DIR"]
API_VERSION = CONFIG["API_VERSION"]
HISTORY_FILE = os.path.join(os.path.dirname(CONFIG_PATH), "uploaded_history.log")

def is_file_ready(filepath):
    try:
        if not os.path.exists(filepath): return False
        size = os.path.getsize(filepath)
        if size < 80000: return False
        chk = subprocess.run(["fuser", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if chk.returncode == 0: return False
        mtime = os.path.getmtime(filepath)
        if (time.time() - mtime) < 8: return False
        time.sleep(2)
        return size == os.path.getsize(filepath)
    except Exception:
        return False

def get_video_duration(file_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        secs = int(float(out))
        mins, secs = divmod(secs, 60)
        return f"{{mins:02d}}:{{secs:02d}}"
    except Exception:
        return "неизвестно"

def convert_to_mp4(mkv_path):
    temp_mp4 = f"/tmp/upload_{{int(time.time())}}_{{os.getpid()}}.mp4"
    cmd = ["ffmpeg", "-y", "-i", mkv_path, "-map", "0:v:0", "-map", "0:a?", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", temp_mp4]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode == 0 and os.path.exists(temp_mp4) and os.path.getsize(temp_mp4) > 0:
        return temp_mp4
    return None

def find_thumb_image(video_path):
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    cam_dir = os.path.dirname(video_path)
    large_thumb = os.path.join(cam_dir, "thumbs", f"{{base_name}}_large.jpg")
    if os.path.exists(large_thumb) and os.path.getsize(large_thumb) > 0:
        return large_thumb, False
    std_thumb = os.path.join(cam_dir, "thumbs", f"{{base_name}}.jpg")
    if os.path.exists(std_thumb) and os.path.getsize(std_thumb) > 0:
        return std_thumb, False
    fallback = f"/tmp/thumb_{{int(time.time())}}.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", "00:00:02", "-i", video_path, "-vframes", "1", "-q:v", "2", fallback], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(fallback) and os.path.getsize(fallback) > 0:
        return fallback, True
    return None, False

def upload_doc_file(file_path, display_name):
    try:
        res = requests.get("https://api.vk.com/method/docs.getWallUploadServer", params={{"access_token": VK_TOKEN, "group_id": GROUP_ID, "v": API_VERSION}}, timeout=15).json()
        if "error" in res: return None, None
        upload_url = res["response"]["upload_url"]
        with open(file_path, "rb") as f:
            up_res = requests.post(upload_url, files={{"file": (display_name, f)}}, timeout=120).json()
        if "file" not in up_res: return None, None
        save_res = requests.get("https://api.vk.com/method/docs.save", params={{"access_token": VK_TOKEN, "file": up_res["file"], "title": display_name, "v": API_VERSION}}, timeout=15).json()
        if "error" in save_res: return None, None
        doc_info = save_res["response"]["doc"]
        return f"doc{{doc_info['owner_id']}}_{{doc_info['id']}}", doc_info.get("url", "")
    except Exception:
        return None, None

def load_history():
    if not os.path.exists(HISTORY_FILE): return set()
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f)

def add_to_history(filename):
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(filename + "\\n")

# --- ПОТОК 1: ОТПРАВКА НА СТЕНУ ---
def watcher_thread():
    print(f"[*] Мониторинг видео запущен: {{WATCH_DIR}}")
    history = load_history()
    while True:
        try:
            for root, _, files in os.walk(WATCH_DIR):
                if "videos_old_archive" in root: continue
                for file in files:
                    if file.lower().endswith(".mkv") and file not in history:
                        full_path = os.path.join(root, file)
                        cam_name = os.path.basename(root)
                        if cam_name.startswith("videos_") or cam_name == "video":
                            cam_name = "Камера"

                        if is_file_ready(full_path):
                            temp_video = convert_to_mp4(full_path)
                            send_video = temp_video if temp_video else full_path
                            base_name = os.path.splitext(file)[0]
                            upload_vname = f"{{base_name}}.mp4" if temp_video else file

                            file_size_mb = os.path.getsize(send_video) / (1024 * 1024)
                            duration_str = get_video_duration(send_video)

                            thumb_path, is_temp_thumb = find_thumb_image(full_path)
                            thumb_url = None
                            if thumb_path:
                                _, thumb_url = upload_doc_file(thumb_path, f"{{base_name}}_preview.jpg")
                                if is_temp_thumb and os.path.exists(thumb_path):
                                    try: os.remove(thumb_path)
                                    except: pass

                            video_attach, video_url = upload_doc_file(send_video, upload_vname)
                            if video_attach:
                                now = datetime.datetime.now()
                                date_str = now.strftime("%d.%m.%Y %H:%M:%S")
                                tag_date = now.strftime("%d_%m_%Y")
                                clean_cam = cam_name.replace(" ", "_")

                                post_text = (
                                    f"📹 [{{cam_name}}] Запись: {{date_str}}\\n"
                                    f"⏱ Длительность: {{duration_str}}\\n"
                                    f"💾 Размер: {{file_size_mb:.1f}} МБ"
                                )
                                if thumb_url: post_text += f"\\n🖼 Превью: {{thumb_url}}"
                                if video_url: post_text += f"\\n▶️ Смотреть онлайн: {{video_url}}"
                                post_text += f"\\n\\n#камера_{{clean_cam}} #дата_{{tag_date}}"

                                w_res = requests.get("https://api.vk.com/method/wall.post", params={{
                                    "access_token": VK_TOKEN,
                                    "owner_id": -GROUP_ID,
                                    "from_group": 1,
                                    "message": post_text,
                                    "attachments": video_attach,
                                    "v": API_VERSION
                                }}, timeout=15).json()

                                if "response" in w_res:
                                    print(f"[+] Опубликовано: {{upload_vname}}")
                                    history.add(file)
                                    add_to_history(file)

                            if temp_video and os.path.exists(temp_video):
                                try: os.remove(temp_video)
                                except: pass
            time.sleep(3)
        except Exception as e:
            time.sleep(3)

# --- ПОТОК 2: АДМИН-БОТ (ЛС + ЧАТЫ) ---
def send_msg(target_peer, text):
    try:
        requests.post("https://api.vk.com/method/messages.send", data={{
            "access_token": VK_TOKEN,
            "peer_id": target_peer,
            "random_id": random.randint(1, 1000000000),
            "message": text[:4000],
            "v": API_VERSION
        }}, timeout=10)
    except: pass

def get_system_status():
    try:
        uptime = subprocess.check_output(["uptime", "-p"]).decode("utf-8").strip()
        total, used, free = shutil.disk_usage(WATCH_DIR)
        disk_free_gb = free // (2**30)
        disk_total_gb = total // (2**30)
        load = os.getloadavg()
        
        mem_info = "Н/Д"
        if os.path.exists("/proc/meminfo"):
            m = {{}}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    p = line.split(":")
                    if len(p) == 2:
                        m[p[0].strip()] = int(p[1].split()[0])
            total_mb = m.get("MemTotal", 0) // 1024
            avail_mb = m.get("MemAvailable", 0) // 1024
            used_mb = total_mb - avail_mb
            pct = (used_mb / total_mb * 100) if total_mb else 0
            mem_info = f"{{used_mb}}/{{total_mb}} МБ ({{pct:.1f}}%)"
        
        return (
            f"📊 Состояние сервера:\\n"
            f"• Аптайм: {{uptime}}\\n"
            f"• Нагрузка CPU (1/5/15 мин): {{load[0]:.2f}}, {{load[1]:.2f}}, {{load[2]:.2f}}\\n"
            f"• Оперативная память: {{mem_info}}\\n"
            f"• Место на диске: свободно {{disk_free_gb}} ГБ из {{disk_total_gb}} ГБ"
        )
    except Exception as e:
        return f"Ошибка сбора метрик: {{e}}"

def bot_thread():
    print("[*] Админ-бот запущен. Ожидание команд...")
    while True:
        try:
            lp = requests.get("https://api.vk.com/method/groups.getLongPollServer", params={{"access_token": VK_TOKEN, "group_id": GROUP_ID, "v": API_VERSION}}, timeout=15).json()
            if "error" in lp:
                time.sleep(10)
                continue
            server = lp["response"]["server"]
            key = lp["response"]["key"]
            ts = lp["response"]["ts"]

            while True:
                resp = requests.get(f"{{server}}?act=a_check&key={{key}}&ts={{ts}}&wait=25", timeout=35).json()
                if "failed" in resp: break
                ts = resp.get("ts", ts)
                for update in resp.get("updates", []):
                    if update.get("type") == "message_new":
                        obj = update.get("object", {{}})
                        msg = obj.get("message", obj)
                        from_id = msg.get("from_id")
                        peer_id = msg.get("peer_id", from_id)
                        text = msg.get("text", "").strip()

                        # Строгая проверка: только автор-админ
                        if from_id != ADMIN_USER_ID:
                            continue

                        if text in ["!статус", "!cpu", "!status"]:
                            send_msg(peer_id, get_system_status())

                        elif text.startswith("!cmd "):
                            cmd = text[5:].strip()
                            try:
                                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=12)
                                out = res.stdout if res.stdout else res.stderr
                                if not out: out = "[Команда выполнена, вывод пуст]"
                                send_msg(peer_id, f"💻 $ {{cmd}}\\n\\n{{out}}")
                            except subprocess.TimeoutExpired:
                                send_msg(peer_id, "⚠️ Ошибка: Таймаут команды (более 12 сек)")
                            except Exception as e:
                                send_msg(peer_id, f"⚠️ Ошибка: {{e}}")

                        elif text in ["!dvr restart", "!dvr"]:
                            send_msg(peer_id, "⏳ Перезапускаю службу Agent DVR...")
                            subprocess.run("sudo systemctl restart AgentDVR || sudo systemctl restart agentdvr", shell=True)
                            send_msg(peer_id, "✅ Команда перезапуска Agent DVR выполнена.")

                        elif text in ["!reboot"]:
                            send_msg(peer_id, "⚠️ Перезагрузка системы...")
                            time.sleep(2)
                            subprocess.run("sudo reboot", shell=True)

                        elif text in ["!help", "!помощь"]:
                            send_msg(peer_id, "📋 Доступные команды:\\n!статус — нагрузка CPU, память, диск\\n!cmd <команда> — выполнить в bash\\n!dvr restart — перезапуск Agent DVR\\n!reboot — перезагрузка ПК")
        except Exception:
            time.sleep(5)

if __name__ == "__main__":
    t1 = threading.Thread(target=watcher_thread, daemon=True)
    t2 = threading.Thread(target=bot_thread, daemon=True)
    t1.start()
    t2.start()
    while True:
        time.sleep(1)
'''
    with open(watcher_file, "w", encoding="utf-8") as f:
        f.write(watcher_code)
    os.chmod(watcher_file, 0o755)

def setup_systemd(user, scripts_dir):
    print("\n[6/6] Перезапуск службы vk-watcher...")
    watcher_file = os.path.join(scripts_dir, "vk_watcher.py")
    service_content = f"""[Unit]
Description=CCTV VK Watcher & Admin Bot
After=network.target

[Service]
Type=simple
User={user}
ExecStart=/usr/bin/python3 {watcher_file}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    subprocess.run(["sudo", "tee", "/etc/systemd/system/vk-watcher.service"], input=service_content, text=True, stdout=subprocess.DEVNULL, check=True)
    subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
    subprocess.run(["sudo", "systemctl", "enable", "--now", "vk-watcher.service"], check=True)
    subprocess.run(["sudo", "systemctl", "restart", "vk-watcher.service"], check=True)

def main():
    print_banner()
    token, group_id, admin_id = get_args()
    verify_and_configure_vk(token, group_id)
    install_system_dependencies()
    
    home = os.path.expanduser("~")
    user = os.environ.get("USER", "user")
    scripts_dir = os.path.join(home, "scripts")
    videos_dir = os.path.join(home, "Videos")
    
    setup_paths_and_permissions(home, videos_dir, scripts_dir)
    setup_sudoers_for_bot(user)
    generate_watcher_daemon(home, scripts_dir, videos_dir, token, group_id, admin_id)
    setup_systemd(user, scripts_dir)
    
    print("\n" + "=" * 60)
    print("      УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА!")
    print("=" * 60)

if __name__ == "__main__":
    main()
EOF
