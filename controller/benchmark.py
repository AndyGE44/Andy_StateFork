import logging
import os
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List


@dataclass
class BenchmarkEntry:
    sequence: int
    operation: str
    target_id: str
    elapsed_time: float


class SizeCalculator:
    _counter = 0

    def __init__(self, root_dir: str):
        self.logger = logging.getLogger("Benchmark.SizeCal")
        self.root_dir = os.path.abspath(root_dir)
        type(self)._counter += 1
        self.instance_id = type(self)._counter
        self.logger.info(f"Attached SizeCalculator instance #{self.instance_id} to root directory: {self.root_dir}")

    def _get_all_items(self) -> List[str]:
        if not os.path.exists(self.root_dir):
            return []
        return [os.path.join(self.root_dir, name) for name in os.listdir(self.root_dir)]

    @staticmethod
    def _get_size(path: str) -> int:
        if os.path.isfile(path):
            return os.path.getsize(path)
        elif os.path.isdir(path):
            try:
                output = subprocess.check_output(["du", "-sb", path], text=True)
                return int(output.split()[0])
            except Exception as e:
                self.logger.error(f"Error getting size for {path}: {e}")
                return 0
        return 0

    @staticmethod
    def _human_readable(size_bytes: int|float) -> str:
        for unit in ['B', 'KB', 'MB']:
            if size_bytes < 1024:
                return f"{size_bytes:.3f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.3f} GB"

    def summary(self) -> str:
        items = self._get_all_items()
        sizes = [self._get_size(p) for p in items]

        if not sizes:
            return "No valid snapshot files or directories found in target directory."

        return (f"[STORAGE #{self.instance_id}] "
               f"mean={self._human_readable(statistics.mean(sizes))} "
               f"median={self._human_readable(statistics.median(sizes))} "
               f"min={self._human_readable(min(sizes))} "
               f"max={self._human_readable(max(sizes))}\n")

    def details(self) -> str:
        items = self._get_all_items()
        if not items:
            return "No snapshot files or directories found."

        lines = [f"[Storage Cost Summary #{self.instance_id}: {self.root_dir}]"]
        for path in items:
            size = self._get_size(path)
            lines.append(f">> {os.path.basename(path)}: {self._human_readable(size)}")
        return "\n".join(lines)


@dataclass
class BenchmarkStats:
    sequence_counter: int = 0
    log: List[BenchmarkEntry] = field(default_factory=list)
    size_calculators: List[SizeCalculator] = field(default_factory=list)

    def add_entry(self, operation: str, target_id: str, elapsed_time: float) -> None:
        self.sequence_counter += 1
        self.log.append(BenchmarkEntry(self.sequence_counter, operation, target_id, elapsed_time))

    def attach_size_calculator(self, root_dir: str) -> None:
        self.size_calculators.append(SizeCalculator(root_dir))

    def print_stats(self) -> str:
        stats = defaultdict(list)
        result = ""
        for entry in self.log:
            stats[entry.operation].append(entry.elapsed_time)
        for op, times in stats.items():
            mean = statistics.mean(times)
            median = statistics.median(times)
            min_time = min(times)
            max_time = max(times)
            result += f"[{op.upper():<10}] mean={mean:.6f}s median={median:.6f}s min={min_time:.6f}s max={max_time:.6f}s\n"
        for sc in self.size_calculators:
            result += sc.summary()
        return result

    def print_history(self) -> None:
        result = ""
        for entry in self.log:
            result += f"#{entry.sequence:<4d} [{entry.operation.upper():<10}] -> {entry.target_id:<8} took {entry.elapsed_time:.4f}s\n"
        return result

    def print_size_details(self) -> str:
        result = ""
        for sc in self.size_calculators:
            result += sc.details() + "\n"
        return result.strip() if result else "No size details available."