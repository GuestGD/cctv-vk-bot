#!/bin/bash
set -e

echo "=== ПОЛНОЕ УДАЛЕНИЕ СИСТЕМЫ CCTV VK BOT ==="

# 1. Остановка и удаление службы systemd
echo "[1/6] Остановка и удаление службы vk-watcher..."
sudo systemctl stop vk-watcher.service 2>/dev/null || true
sudo systemctl disable vk-watcher.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/vk-watcher.service
sudo systemctl daemon-reload
sudo systemctl reset-failed 2>/dev/null || true

# 2. Очистка cron
echo "[2/6] Удаление задачи ротации из планировщика cron..."
if crontab -l 2>/dev/null | grep -q "rotate_camera.sh"; then
    crontab -l 2>/dev/null | grep -Fv "rotate_camera.sh" | crontab - || true
fi

# 3. Удаление прав sudoers для бота
echo "[3/6] Удаление системных правил sudoers..."
sudo rm -f /etc/sudoers.d/cctv_bot

# 4. Удаление команды проверки
echo "[4/6] Удаление утилиты cctv-check..."
sudo rm -f /usr/local/bin/cctv-check

# 5. Возврат папки video в стандартный режим
echo "[5/6] Восстановление структуры папок..."
if [ -L "$HOME/Videos/video" ]; then
    rm -f "$HOME/Videos/video"
    mkdir -p "$HOME/Videos/video"
fi

# 6. Удаление скриптов, конфигов и временных файлов
echo "[6/6] Удаление скриптов и файлов конфигурации..."
rm -f "$HOME/scripts/vk_watcher.py"
rm -f "$HOME/scripts/rotate_camera.sh"
rm -f "$HOME/scripts/cctv_config.json"
rm -f "$HOME/scripts/uploaded_history.log"
rm -f "$HOME/scripts/rotation.log"
rm -f "$HOME/scripts/vk_config.py"
rm -f "$HOME/scripts/live_cam.sh"
rm -f "$HOME/Desktop/Camera_Live.desktop" "$HOME/Рабочий стол/Camera_Live.desktop" 2>/dev/null || true
rm -f /tmp/upload_*.mp4 /tmp/thumb_*.jpg /tmp/cat_*.jpg 2>/dev/null || true

# Удаляем папку scripts, если в ней больше ничего нет
rmdir "$HOME/scripts" 2>/dev/null || true

echo ""
echo "=================================================="
echo "    СИСТЕМА CCTV VK BOT ПОЛНОСТЬЮ УДАЛЕНА!        "
echo "=================================================="
echo "• Службы, автозапуск, cron и конфиги зачищены."
echo "• Сами файлы видео в папках Videos/ НЕ удалялись."
echo "=================================================="
