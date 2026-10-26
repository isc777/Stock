"""背景排程：每隔 COLLECT_INTERVAL_MIN 分鐘自動執行一次收集。"""
import logging
import threading
from datetime import datetime, timedelta, timezone

from . import collector, config

log = logging.getLogger(__name__)


class CollectorScheduler:
    def __init__(self, interval_min=None):
        self.interval_min = config.COLLECT_INTERVAL_MIN if interval_min is None else interval_min
        self.next_run = None
        self.running = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self.interval_min <= 0 or self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="collector", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def run_now(self, symbols=None):
        """立即收集；若已有收集在進行中則回傳 None。"""
        if not self._lock.acquire(blocking=False):
            return None
        self.running = True
        try:
            return collector.collect_all(symbols)
        finally:
            self.running = False
            self._lock.release()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.run_now()
            except Exception:  # 排程不能因單次錯誤而停止
                log.exception("scheduled collection failed")
            self.next_run = datetime.now(timezone.utc) + timedelta(minutes=self.interval_min)
            self._stop.wait(self.interval_min * 60)
