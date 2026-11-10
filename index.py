#!/usr/bin/env python3
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
