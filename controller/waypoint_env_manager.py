from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
import logging
from typing import Optional, List
from .base_env_manager import EnvironmentManager, SnapshotNode
from .benchmark import Calculator
from decider import Decider

logger = logging.getLogger("EnvManager.Waypoint")

STATEFORK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WAYPOINT_BIN = os.path.join(STATEFORK_ROOT, "waypoint")
BASH_INIT_BIN = os.path.join(STATEFORK_ROOT, "bash_init")

def _waypoint_bin() -> str:
    """Path to the ``waypoint`` binary.

    Defaults to ``<STATEFORK_ROOT>/waypoint`` (the symlink to the built Go
    binary). Override with ``WAYPOINT_BIN`` so an external orchestrator (e.g.
    Harbor) can point at a binary outside this checkout.
    """
    return os.environ.get("WAYPOINT_BIN", WAYPOINT_BIN)

def _waypoint_prefix() -> list[str]:
    """Optional argv prefix prepended to every waypoint invocation.

    Waypoint needs root (CRIU/OverlayFS/chroot). When StateFork is driven from
    a non-root process, set ``WAYPOINT_CMD_PREFIX`` (e.g. ``"sudo -n -E"``) so
    the binary runs with privilege. Empty by default — fully backward
    compatible with callers that already run as root.
    """
    return shlex.split(os.environ.get("WAYPOINT_CMD_PREFIX", ""))

def _waypoint_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("WAYPOINT_BASH_INIT_SRC", BASH_INIT_BIN)
    env.setdefault("WAYPOINT_PRESERVE_SESSION_ON_CLEANUP", "true")
    if "CHECKPOINT_SESSIONS_DIR" in env:
        env.setdefault("WAYPOINT_SESSIONS_DIR", env["CHECKPOINT_SESSIONS_DIR"])
    return env

def _run_waypoint(args: list[str], **kwargs):
    return subprocess.run(
        [*_waypoint_prefix(), _waypoint_bin(), *args],
        cwd=STATEFORK_ROOT,
        env=_waypoint_env(),
        **kwargs,
    )

class WaypointCalculator(Calculator):
    """
    WaypointCalculator is a specialized FileSizeCalculator for Waypoint that
    collects the sizes of filesystem and memory checkpoint files in a session directory.

    We have to override but not extend the FileSizeCalculator because we need to
    target a specific subdirectory structure created by Waypoint v0.4.0 and do some filtering.
    """
    def __init__(self, root_dir: str, sub_dir: str, name: str = "WaypointFsCalculator"):
        super().__init__(name=name)
        self.root_dir = os.path.abspath(root_dir)
        self.sub_dir = sub_dir  # either "upper" or "criu"
        self.logger.debug(f"Attached WaypointCalculator #{self.instance_id} to {self.root_dir}/*/{self.sub_dir}")

    def __get_all_items(self) -> List[str]:
        if not os.path.exists(self.root_dir):
            return []
        items = []
        for name in os.listdir(self.root_dir):
            if name in ["metadata", "work", "temp"]:
                continue
            sub_path = os.path.join(self.root_dir, name, self.sub_dir)
            if os.path.exists(sub_path):
                items.append(sub_path)
        return items

    def __get_size(self, path: str) -> int:
        try:
            output = subprocess.check_output(["du", "-sb", path], text=True)
            return int(output.split()[0])
        except Exception as e:
            self.logger.error(f"Error getting size for {path}: {e}")
            return 0

    def _collect(self) -> List[tuple[str, int]]:
        items = self.__get_all_items()
        if not items:
            return []

        data = []
        for item in items:
            size = self.__get_size(item)
            if size >= 0:
                parts = os.path.normpath(item).split(os.sep)
                name = os.path.join(parts[-2], parts[-1])
                data.append((name, size))
        return data

class WaypointAttachManager(EnvironmentManager):
    """
    WaypointAttachManager is a specialized Waypoint EnvironmentManager that attaches to an existing session.
    """
    PID_NOT_PROVIDED = -2

    def __init__(self,
                 session_id: str,
                 target_pid: int = PID_NOT_PROVIDED,
                 decider: Optional[Decider] = None,
                 ):
        super().__init__(backend_name="Waypoint", decider=decider)
        self.session_id = session_id
        self.target_pid = target_pid

        logger.info(f"Attaching to existing Waypoint session {self.session_id} with target PID {self.target_pid}...")

        sid, _ = self._core_snapshot()
        if sid is None:
            raise RuntimeError("Failed to create initial snapshot.")

        # Init the Tree Graph
        self.snapshot_graph[sid] = SnapshotNode(snapshot_id=sid, parent_id=None)
        self.current_snapshot_id = sid
        self.last_snapshot_id = sid


    def _core_snapshot(self) -> tuple[Optional[str], float]:
        snapshot_id = str(uuid.uuid4())[:8]

        start = time.time()
        try:
            _run_waypoint(
                ["create", self.session_id, snapshot_id, str(self.target_pid)],
                check=True,
            )
            elapsed = time.time() - start
            self.snapshots[snapshot_id] = snapshot_id
            return snapshot_id, elapsed
        except subprocess.CalledProcessError as e:
            logger.error(f"Waypoint snapshot failed: {e}")
            return None, 0.0

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        snapshot_id = self.snapshots.get(snapshot_id)
        if not snapshot_id:
            logger.warning(f"Snapshot {snapshot_id} not found.")
            return None, 0.0

        start = time.time()
        try:
            _run_waypoint(
                ["restore", self.session_id, snapshot_id],
                check=True,
            )
            elapsed = time.time() - start
            return snapshot_id, elapsed
        except subprocess.CalledProcessError as e:
            logger.error(f"Waypoint restore failed: {e}")
            return None, 0.0

    def _core_cleanup(self):
        logger.info("Shutting down Waypoint environment...")
        try:
            _run_waypoint(
                ["cleanup", self.session_id],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Waypoint cleanup failed: {e}")
            logger.info("Attempting force cleanup...")
            try:
                _run_waypoint(
                    ["cleanup", self.session_id, "--force"],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                logger.error(f"Waypoint force cleanup failed: {e}")
                return

    def _core_exec(self, command: List[str] | str, timeout: Optional[float]) -> tuple[int, str, str]:
        if not self.session_id:
            return -1, "", "No session_id available"

        # Convert command into a sequence of arguments (waypoint expects args list)
        if isinstance(command, str):
            cmd_str = command
        else:
            cmd_str = shlex.join(command)

        # Execute `command` via `waypoint exec <session_id> <args...>`.
        try:
            proc = _run_waypoint(
                ["exec", self.session_id, cmd_str],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Command output may contain non-UTF-8 bytes (binary files,
                # hexdumps, etc.); decode leniently instead of raising.
                errors="replace",
                timeout=timeout,
                check=False,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            out = e.stdout or ""
            err = (e.stderr or "") + f"\n[timeout after {timeout}s]"
            logger.error(f"Waypoint exec timeout: {e}")
            return -1, out, err
        except Exception as e:
            logger.error(f"Waypoint exec failed: {e}")
            return -1, "", str(e)

class WaypointBuildManager(WaypointAttachManager):
    """
    WaypointBuildManager is a specialized Waypoint EnvironmentManager that builds a new session.
    """
    def __init__(self,
                 dockerfile_dir: str = ".",
                 build: bool = True,
                 decider: Optional[Decider] = None,
                 ):
        if dockerfile_dir is None:
            target_dir = os.getcwd()
        else:
            target_dir = os.path.abspath(dockerfile_dir)

        logger.info("Creating a new Waypoint session...")
        if not build:
            init_process = _run_waypoint(
                ["init", target_dir, "--quiet"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            output = init_process.stdout.strip()
            try:
                sid, self._work_dir = output.split(",", 1)
            except ValueError:
                raise RuntimeError(f"Unexpected output format: {output}")
        else:
            init_process = _run_waypoint(
                ["build", target_dir, "--quiet"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            output = init_process.stdout.strip()
            try:
                sid, self._work_dir, _ = output.split(",", 2)
            except ValueError:
                raise RuntimeError(f"Unexpected output format: {output}")

        logger.info(f"New session {sid} with work directory '{self._work_dir}' created.")

        super().__init__(session_id=sid, decider=decider)

        # Attach the new WaypointCalculator to this session
        base_dir = os.path.join(self._work_dir, "../")
        self._stats.attach_size_calculator(WaypointCalculator(base_dir, "upper", name="FILESYSTEM"))
        self._stats.attach_size_calculator(WaypointCalculator(base_dir, "criu", name="MEMORY"))

    @property
    def work_dir(self) -> str:
        return self._work_dir
