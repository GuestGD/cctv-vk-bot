import os
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
