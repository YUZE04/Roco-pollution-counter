"""污染计数持久化。包含节流写盘（避免频繁同步磁盘 I/O 卡 UI）。"""

from __future__ import annotations

import json
import time
from typing import Any, Dict

from PyQt6.QtCore import QObject, QTimer

from .paths import SAVE_FILE
from .utils import aggregate_species_totals, clean_pet_name, today_str


def _empty_payload() -> Dict[str, Any]:
    return {
        "count": 0,
        "species_counts": {},
        "daily_totals": {},
        "daily_species": {},
        "species_total_counts": {},
    }


class PollutionData(QObject):
    """今日/历史污染数据。所有修改都走这里，统一节流保存。

    线程约束：只在 UI 线程修改。detector/hotkeys 通过 Qt signal 派发到 UI 线程。
    """

    SAVE_THROTTLE_MS = 2000

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._data: Dict[str, Any] = self._load()
        self._dirty = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush)

    # ---------- 磁盘 ----------

    def _load(self) -> Dict[str, Any]:
        if SAVE_FILE.exists():
            try:
                d = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
                if not isinstance(d, dict):
                    return _empty_payload()
                d.setdefault("count", 0)
                d.setdefault("species_counts", {})
                d.setdefault("daily_totals", {})
                d.setdefault("daily_species", {})
                d.setdefault("species_total_counts", {})
                if not d["species_total_counts"]:
                    d["species_total_counts"] = aggregate_species_totals(
                        d.get("daily_species", {}), d.get("species_counts", {})
                    )
                return d
            except Exception:
                pass
        return _empty_payload()

    def _flush(self) -> None:
        if not self._dirty:
            return
        try:
            SAVE_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._dirty = False
        except Exception:
            pass

    def save(self, force: bool = False) -> None:
        self._dirty = True
        if force:
            self._save_timer.stop()
            self._flush()
            return
        if not self._save_timer.isActive():
            self._save_timer.start(self.SAVE_THROTTLE_MS)

    # ---------- 属性 ----------

    @property
    def total_count(self) -> int:
        """今日总污染数（跟随日期）。"""
        day = today_str()
        return int(self._data["daily_totals"].get(day, self._data.get("count", 0)))

    @property
    def species_counts(self) -> Dict[str, int]:
        """今日每种精灵的污染次数。"""
        day = today_str()
        today_map = self._data["daily_species"].get(day)
        if isinstance(today_map, dict):
            return dict(today_map)
        return dict(self._data.get("species_counts", {}))

    @property
    def species_total_counts(self) -> Dict[str, int]:
        return dict(self._data.get("species_total_counts", {}))

    @property
    def last_species(self) -> str:
        return str(self._data.get("last_species", "无"))

    # ---------- 修改 ----------

    def _ensure_today(self) -> None:
        day = today_str()
        self._data["daily_totals"].setdefault(day, int(self._data.get("count", 0)))
        self._data["daily_species"].setdefault(day, {})

    def increment(self, species: str) -> None:
        """命中一次污染。unknown 不计入总数，但精灵历史累计里也不记。"""
        self._ensure_today()
        day = today_str()
        name = clean_pet_name(species)
        if name == "未识别":
            # 保留上一只精灵；不增加计数；仅更新状态
            return
        self._data["last_species"] = name
        self._data["daily_totals"][day] = int(self._data["daily_totals"].get(day, 0)) + 1
        today_map = self._data["daily_species"].setdefault(day, {})
        today_map[name] = int(today_map.get(name, 0)) + 1
        # 总累计
        stc = self._data.setdefault("species_total_counts", {})
        stc[name] = int(stc.get(name, 0)) + 1
        # 兼容旧字段
        self._data["count"] = int(self._data["daily_totals"][day])
        sc = self._data.setdefault("species_counts", {})
        sc[name] = int(today_map[name])
        self.save()

    def manual_add(self) -> bool:
        last = clean_pet_name(self.last_species)
        if not last or last == "未识别":
            return False
        self.increment(last)
        return True

    def manual_sub(self) -> bool:
        self._ensure_today()
        day = today_str()
        last = clean_pet_name(self.last_species)
        if not last or last == "未识别":
            return False
        today_map = self._data["daily_species"].get(day, {})
        if today_map.get(last, 0) <= 0:
            return False
        today_map[last] = max(0, int(today_map.get(last, 0)) - 1)
        self._data["daily_totals"][day] = max(0, int(self._data["daily_totals"].get(day, 0)) - 1)
        stc = self._data.setdefault("species_total_counts", {})
        if stc.get(last, 0) > 0:
            stc[last] = max(0, int(stc.get(last, 0)) - 1)
        self._data["count"] = int(self._data["daily_totals"][day])
        self._data.setdefault("species_counts", {})[last] = int(today_map[last])
        self.save()
        return True

    def set_today_species_count(self, species: str, value: int) -> None:
        self._ensure_today()
        day = today_str()
        name = clean_pet_name(species)
        if not name or name == "未识别":
            return
        value = max(0, int(value))
        today_map = self._data["daily_species"].setdefault(day, {})
        old = int(today_map.get(name, 0))
        delta = value - old
        today_map[name] = value
        if value == 0:
            today_map.pop(name, None)
        # daily_totals 按差值同步
        self._data["daily_totals"][day] = max(0, int(self._data["daily_totals"].get(day, 0)) + delta)
        # species_total_counts 按差值同步
        stc = self._data.setdefault("species_total_counts", {})
        stc[name] = max(0, int(stc.get(name, 0)) + delta)
        if stc[name] == 0:
            stc.pop(name, None)
        # 兼容字段
        self._data["count"] = int(self._data["daily_totals"][day])
        sc = self._data.setdefault("species_counts", {})
        if value > 0:
            sc[name] = value
        else:
            sc.pop(name, None)
        self.save()

    def set_species_total_count(self, species: str, value: int) -> None:
        name = clean_pet_name(species)
        if not name or name == "未识别":
            return
        value = max(0, int(value))
        stc = self._data.setdefault("species_total_counts", {})
        if value == 0:
            stc.pop(name, None)
        else:
            stc[name] = value
        self.save()

    def set_daily_total(self, day: str, value: int) -> None:
        if not day:
            return
        value = max(0, int(value))
        self._data.setdefault("daily_totals", {})[day] = value
        if day == today_str():
            self._data["count"] = value
        self.save()

    def reset_today(self) -> None:
        day = today_str()
        self._data["daily_totals"][day] = 0
        self._data["daily_species"][day] = {}
        self._data["count"] = 0
        self._data["species_counts"] = {}
        self.save(force=True)
