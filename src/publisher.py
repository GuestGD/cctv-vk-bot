import os
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
