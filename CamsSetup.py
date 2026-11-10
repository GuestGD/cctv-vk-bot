#!/usr/bin/env python3
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
