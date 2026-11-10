#!/bin/bash
set -e

echo "=== ПОЛНОЕ УДАЛЕНИЕ СИСТЕМЫ CCTV VK BOT ==="

# 1. Стоп и удаление службы
echo "[1/6] Остановка и удаление vk-watcher..."
sudo systemctl stop vk-watcher.service 2>/dev/null || true
sudo systemctl disable vk-watcher.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/vk-watcher.service
sudo systemctl daemon-reload
sudo systemctl reset-failed 2>/dev/null || true

# 2. Cron
echo "[2/6] Удаление cron-задачи ротации..."
if crontab -l 2>/dev/null | grep -q "rotate_camera.sh"; then
    crontab -l 2>/dev/null | grep -Fv "rotate_camera.sh" | crontab - || true
fi

# 3. Sudoers
echo "[3/6] Удаление sudoers..."
sudo rm -f /etc/sudoers.d/cctv_bot

# 4. Утилита проверки
echo "[4/6] Удаление cctv-check..."
sudo rm -f /usr/local/bin/cctv-check

# 5. Восстановление папки video
echo "[5/6] Восстановление структуры папок..."
if [ -L "$HOME/Videos/video" ]; then
    rm -f "$HOME/Videos/video"
    mkdir -p "$HOME/Videos/video"
fi

# 6. Скрипты, конфиги, временные файлы (НОВАЯ СТРУКТУРА)
echo "[6/6] Удаление index.py, src/, конфигов и tmp..."
rm -f  "$HOME/scripts/index.py"
rm -rf "$HOME/scripts/src"
rm -f  "$HOME/scripts/rotate_camera.sh"
rm -f  "$HOME/scripts/cctv_config.json"
rm -f  "$HOME/scripts/uploaded_history.log"
rm -f  "$HOME/scripts/rotation.log"
rm -f  "$HOME/scripts/vk_watcher.py"        # наследие старой версии
rm -f  "$HOME/scripts/vk_config.py"
rm -f  "$HOME/scripts/live_cam.sh"
rm -f  "$HOME/Desktop/Camera_Live.desktop" "$HOME/Рабочий стол/Camera_Live.desktop" 2>/dev/null || true

# Все виды временных файлов
rm -f /tmp/upload_*.mp4 /tmp/thumb_*.jpg /tmp/cat_*.jpg \
      /tmp/mic_*.mp3 /tmp/mic_rec_*.wav 2>/dev/null || true

rmdir "$HOME/scripts" 2>/dev/null || true

echo ""
echo "=================================================="
echo "    СИСТЕМА CCTV VK BOT ПОЛНОСТЬЮ УДАЛЕНА!        "
echo "=================================================="
echo "• Службы, автозапуск, cron и конфиги зачищены."
echo "• Файлы видео в Videos/ НЕ удалялись."
echo "=================================================="