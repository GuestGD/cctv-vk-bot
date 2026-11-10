import os
import time
import requests
import subprocess

from . import vkapi, media
from .config import ADMIN_USER_ID, WATCH_DIR

HELP = (
    "📋 Команды:\n"
    "!статус | !status | !cpu — CPU, память, диск\n"
    "!cmd <команда> — bash\n"
    "!dvr restart — перезапуск Agent DVR\n"
    "!reboot — перезагрузка ПК\n"
    "!кот | !вебка | !cat | !webcam — снимок с веб-камеры\n"
    "!звук | !mic — 5 сек. с микрофона"
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
            vkapi.send_message(
                peer, "⚠️ Не удалось отправить снимок: %s" % err)
    finally:
        try:
            os.remove(img)
        except OSError:
            pass


def _audio(peer):
    vkapi.send_message(peer, "🎤 Записываю 5 сек...")
    ogg, err = media.record_audio(5)
    if not ogg:
        vkapi.send_message(peer, "⚠️ Аудио: %s" % err)
        return
    try:
        attach, err = vkapi.upload_voice_message(ogg, peer)
        if attach:
            vkapi.send_message(peer, "🎙 Голосовое (5 сек):", attach)
        else:
            vkapi.send_message(peer, "⚠️ Ошибка загрузки аудио: %s" % err)
    finally:
        try:
            os.remove(ogg)
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
    if text in ("!кот", "!вебка", "!webcam", "!cat"):
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
