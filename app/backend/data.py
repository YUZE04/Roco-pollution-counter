"""污染计数持久化。包含节流写盘（避免频繁同步磁盘 I/O 卡 UI）。"""

from __future__ import annotations

import csv
import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import QObject, QTimer

from .paths import (
    RECORD_CSV,
    RECORD_DIR,
    RECORD_JSONL,
    SAVE_EXAMPLE_NAME,
    SAVE_FILE,
    seed_runtime_file,
)
from .utils import aggregate_species_totals, clean_pet_name, today_str


def _empty_payload() -> Dict[str, Any]:
    return {
        "count": 0,
        "species_counts": {},
        "daily_totals": {},
        "daily_species": {},
        "species_total_counts": {},
        "last_species": "无",
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

    @staticmethod
    def _normalize_payload(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("文件内容不是有效的统计 JSON 对象")

        d: Dict[str, Any] = dict(payload)

        try:
            d["count"] = max(0, int(d.get("count", 0)))
        except Exception:
            d["count"] = 0

        for key in ("species_counts", "daily_totals", "daily_species", "species_total_counts"):
            if not isinstance(d.get(key), dict):
                d[key] = {}

        daily_sum = 0
        for day, value in list(d["daily_totals"].items()):
            try:
                clean_value = max(0, int(value))
            except Exception:
                clean_value = 0
            d["daily_totals"][day] = clean_value
            daily_sum += clean_value
        d["count"] = max(int(d.get("count", 0)), daily_sum)

        d["last_species"] = str(d.get("last_species", "无") or "无")

        if not d["species_total_counts"]:
            d["species_total_counts"] = aggregate_species_totals(
                d.get("daily_species", {}), d.get("species_counts", {})
            )

        return d

    def _load(self) -> Dict[str, Any]:
        seed_runtime_file(
            SAVE_FILE,
            SAVE_EXAMPLE_NAME,
            json.dumps(_empty_payload(), ensure_ascii=False, indent=2),
        )
        if SAVE_FILE.exists():
            try:
                d = json.loads(SAVE_FILE.read_text(encoding="utf-8"))
                return self._normalize_payload(d)
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

    @staticmethod
    def _collapse_imported_payload_to_cumulative(payload: Dict[str, Any]) -> Dict[str, Any]:
        """旧版 count 导入时统一折叠成“累计模式”，不保留按天拆分。"""
        merged_totals: Dict[str, int] = {}
        for source in (
            payload.get("species_total_counts", {}),
            payload.get("species_counts", {}),
            aggregate_species_totals(payload.get("daily_species", {}), payload.get("species_counts", {})),
        ):
            if not isinstance(source, dict):
                continue
            for name, count in source.items():
                clean_name = clean_pet_name(name)
                try:
                    value = max(0, int(count))
                except Exception:
                    value = 0
                if not clean_name or clean_name == "未识别" or value <= 0:
                    continue
                merged_totals[clean_name] = max(int(merged_totals.get(clean_name, 0)), value)

        collapsed_count = max(
            int(payload.get("count", 0)),
            sum(int(v) for v in merged_totals.values()),
        )
        last_species = str(payload.get("last_species", "无") or "无")
        if not merged_totals:
            last_species = "无"
        elif clean_pet_name(last_species) not in merged_totals:
            last_species = max(merged_totals.items(), key=lambda kv: (kv[1], kv[0]))[0]

        return {
            "count": collapsed_count,
            "species_counts": {},
            "daily_totals": {},
            "daily_species": {},
            "species_total_counts": merged_totals,
            "last_species": last_species,
        }

    def replace_from_file(self, source_path: str | Path) -> Dict[str, Any]:
        source = Path(source_path).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"文件不存在：{source}")
        if not source.is_file():
            raise ValueError(f"不是文件：{source}")

        try:
            raw = json.loads(source.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            raw = json.loads(source.read_text(encoding="utf-8-sig"))

        new_data = self._normalize_payload(raw)
        new_data = self._collapse_imported_payload_to_cumulative(new_data)

        backup_path: Path | None = None
        if SAVE_FILE.exists():
            try:
                if source.resolve() != SAVE_FILE.resolve():
                    backup_path = SAVE_FILE.with_name(
                        f"{SAVE_FILE.stem}.backup_{time.strftime('%Y%m%d_%H%M%S')}{SAVE_FILE.suffix}"
                    )
                    shutil.copy2(SAVE_FILE, backup_path)
            except Exception:
                backup_path = None

        self._save_timer.stop()
        self._data = new_data
        self._refresh_last_species()
        self._dirty = True
        self._flush()

        return {
            "source_path": str(source),
            "backup_path": str(backup_path) if backup_path else "",
            "count": int(new_data.get("count", 0)),
            "species_total": len(new_data.get("species_total_counts", {})),
            "day_total": 0,
            "import_mode": "cumulative_only",
        }

    # ---------- 属性 ----------

    @property
    def total_count(self) -> int:
        """当前累计污染数。不会因为日期变化自动清零。"""
        return int(self._data.get("count", 0))

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
        self._data["daily_totals"].setdefault(day, 0)
        self._data["daily_species"].setdefault(day, {})

    def _sync_today_species_cache(self) -> None:
        day = today_str()
        today_map = self._data.get("daily_species", {}).get(day, {})
        if isinstance(today_map, dict):
            self._data["species_counts"] = dict(today_map)
        else:
            self._data["species_counts"] = {}

    def _refresh_last_species(self) -> None:
        last = clean_pet_name(self._data.get("last_species", ""))
        today_map = self.species_counts
        total_map = self.species_total_counts
        if last and last not in ("未识别", "无"):
            if int(today_map.get(last, 0)) > 0 or int(total_map.get(last, 0)) > 0:
                return
        for source in (today_map, total_map):
            positive = {k: int(v) for k, v in source.items() if int(v) > 0}
            if positive:
                self._data["last_species"] = max(
                    positive.items(), key=lambda kv: (kv[1], kv[0])
                )[0]
                return
        self._data["last_species"] = "无"

    def _append_species_archive_record(self, record: Dict[str, Any]) -> None:
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        with RECORD_JSONL.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        csv_exists = RECORD_CSV.exists()
        with RECORD_CSV.open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if not csv_exists:
                writer.writerow(
                    [
                        "archived_at",
                        "species",
                        "species_total_count",
                        "today_species_count",
                        "removed_from_current_total",
                        "last_species",
                        "daily_breakdown_json",
                    ]
                )
            writer.writerow(
                [
                    record["archived_at"],
                    record["species"],
                    record["species_total_count"],
                    record["today_species_count"],
                    record["removed_from_current_total"],
                    record["last_species"],
                    json.dumps(record["daily_breakdown"], ensure_ascii=False),
                ]
            )

    def increment(self, species: str) -> None:
        """命中一次污染。unknown 不计入总数，但精灵历史累计里也不记。"""
        self._ensure_today()
        day = today_str()
        name = clean_pet_name(species)
        if name == "未识别":
            # 保留上一只精灵；不增加计数；仅更新状态
            return
        self._data["last_species"] = name
        self._data["count"] = int(self._data.get("count", 0)) + 1
        self._data["daily_totals"][day] = int(self._data["daily_totals"].get(day, 0)) + 1
        today_map = self._data["daily_species"].setdefault(day, {})
        today_map[name] = int(today_map.get(name, 0)) + 1
        # 总累计
        stc = self._data.setdefault("species_total_counts", {})
        stc[name] = int(stc.get(name, 0)) + 1
        # 兼容旧字段
        self._sync_today_species_cache()
        self.save()

    def preferred_species(self) -> str:
        """挑一个"当前精灵"的回退：last_species → 今日榜首 → 累计榜首。找不到返回空串。"""
        last = clean_pet_name(self.last_species)
        if last and last not in ("未识别", "无"):
            return last
        today_map = self.species_counts
        if today_map:
            # 选今日出现次数最多的
            return max(today_map.items(), key=lambda kv: (kv[1], kv[0]))[0]
        stc = self.species_total_counts
        if stc:
            return max(stc.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return ""

    def manual_add(self, species: str | None = None) -> bool:
        """手动 +1。若未指定 species，使用 `preferred_species()` 回退。"""
        name = clean_pet_name(species) if species else self.preferred_species()
        if not name or name == "未识别":
            return False
        self.increment(name)
        return True

    def manual_sub(self, species: str | None = None) -> bool:
        """手动 -1。若未指定 species，使用 `preferred_species()` 回退。"""
        self._ensure_today()
        day = today_str()
        name = clean_pet_name(species) if species else self.preferred_species()
        if not name or name == "未识别":
            return False
        today_map = self._data["daily_species"].get(day, {})
        if today_map.get(name, 0) <= 0:
            return False
        today_map[name] = max(0, int(today_map.get(name, 0)) - 1)
        if today_map[name] == 0:
            today_map.pop(name, None)
        self._data["daily_totals"][day] = max(0, int(self._data["daily_totals"].get(day, 0)) - 1)
        self._data["count"] = max(0, int(self._data.get("count", 0)) - 1)
        stc = self._data.setdefault("species_total_counts", {})
        if stc.get(name, 0) > 0:
            stc[name] = max(0, int(stc.get(name, 0)) - 1)
            if stc[name] == 0:
                stc.pop(name, None)
        self._sync_today_species_cache()
        # 把它记为"当前精灵"，连续手动±更顺手
        self._data["last_species"] = name
        self._refresh_last_species()
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
        self._data["count"] = max(0, int(self._data.get("count", 0)) + delta)
        # species_total_counts 按差值同步
        stc = self._data.setdefault("species_total_counts", {})
        stc[name] = max(0, int(stc.get(name, 0)) + delta)
        if stc[name] == 0:
            stc.pop(name, None)
        # 兼容字段
        self._sync_today_species_cache()
        self._refresh_last_species()
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
        daily_totals = self._data.setdefault("daily_totals", {})
        old = max(0, int(daily_totals.get(day, 0)))
        daily_totals[day] = value
        self._data["count"] = max(0, int(self._data.get("count", 0)) + (value - old))
        self.save()

    def reset_today(self) -> None:
        day = today_str()
        today_total = int(self._data.get("daily_totals", {}).get(day, 0))
        today_map = dict(self._data.get("daily_species", {}).get(day, {}))
        if today_total <= 0 and not today_map:
            return

        stc = self._data.setdefault("species_total_counts", {})
        for name, value in today_map.items():
            try:
                delta = max(0, int(value))
            except Exception:
                delta = 0
            if delta <= 0:
                continue
            if name in stc:
                stc[name] = max(0, int(stc.get(name, 0)) - delta)
                if stc[name] == 0:
                    stc.pop(name, None)

        self._data["count"] = max(0, int(self._data.get("count", 0)) - today_total)
        self._data.get("daily_totals", {}).pop(day, None)
        self._data.get("daily_species", {}).pop(day, None)
        self._sync_today_species_cache()
        self._refresh_last_species()
        self.save(force=True)

    def archive_and_clear_species(self, species: str) -> Dict[str, Any]:
        name = clean_pet_name(species)
        if not name or name == "未识别":
            raise ValueError("精灵名字无效")

        stc = self._data.setdefault("species_total_counts", {})
        current_total = max(0, int(stc.get(name, 0)))
        daily_species = self._data.setdefault("daily_species", {})
        daily_totals = self._data.setdefault("daily_totals", {})
        today = today_str()
        today_count = 0
        daily_breakdown: Dict[str, int] = {}
        removed_from_current_total = 0

        for day, species_map in list(daily_species.items()):
            if not isinstance(species_map, dict):
                continue
            try:
                removed = max(0, int(species_map.get(name, 0)))
            except Exception:
                removed = 0
            if removed <= 0:
                continue
            daily_breakdown[day] = removed
            removed_from_current_total += removed
            if day == today:
                today_count = removed
            species_map.pop(name, None)
            if not species_map:
                daily_species.pop(day, None)
            if day in daily_totals:
                daily_totals[day] = max(0, int(daily_totals.get(day, 0)) - removed)
                if daily_totals[day] == 0 and day not in daily_species:
                    daily_totals.pop(day, None)

        if current_total <= 0 and removed_from_current_total <= 0:
            raise ValueError(f"「{name}」当前没有可存档的计数")

        removed_from_current_total = removed_from_current_total or current_total
        record = {
            "archived_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "species": name,
            "species_total_count": current_total or removed_from_current_total,
            "today_species_count": today_count,
            "removed_from_current_total": removed_from_current_total,
            "last_species": self._data.get("last_species", "无"),
            "daily_breakdown": daily_breakdown,
        }

        stc.pop(name, None)
        self._data["count"] = max(
            0, int(self._data.get("count", 0)) - removed_from_current_total
        )
        self._append_species_archive_record(record)
        self._sync_today_species_cache()
        self._refresh_last_species()
        self.save(force=True)
        return record
