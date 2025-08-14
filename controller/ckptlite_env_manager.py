import subprocess
import time
import uuid
import logging
from typing import Optional
from .base_env_manager import EnvironmentManager, SnapshotNode

logger = logging.getLogger("EnvManager.CRIU")


class CheckpointLiteAttachManager(EnvironmentManager):
    """
    CheckpointLiteAttachManager is a specialized Checkpoint-lite EnvironmentManager that attaches to an existing session.
    """
    def __init__(self,
                 target_pid: int,
                 session_id: str
                 ):
        super().__init__(backend_name="CheckpointLite")
        self.session_id = session_id
        self.target_pid = target_pid

        logger.info(f"Attaching to existing Checkpoint-lite session {self.session_id} with target PID {self.target_pid}...")

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
            subprocess.run(
                ["checkpoint-lite", "create", self.session_id, str(self.target_pid), snapshot_id],
                check=True
            )
            elapsed = time.time() - start
            self.snapshots[snapshot_id] = snapshot_id
            return snapshot_id, elapsed
        except subprocess.CalledProcessError as e:
            logger.error(f"CheckpointLite snapshot failed: {e}")
            return None, 0.0

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        snapshot_id = self.snapshots.get(snapshot_id)
        if not snapshot_id:
            logger.warning(f"Snapshot {snapshot_id} not found.")
            return None, 0.0

        start = time.time()
        try:
            subprocess.run(
                ["checkpoint-lite", "restore", self.session_id, snapshot_id],
                check=True
            )
            elapsed = time.time() - start
            return snapshot_id, elapsed
        except subprocess.CalledProcessError as e:
            logger.error(f"CheckpointLite restore failed: {e}")
            return None, 0.0

    def _core_cleanup(self):
        logger.info("Shutting down CheckpointLite environment...")
        try:
            subprocess.run(
                ["checkpoint-lite", "cleanup", self.session_id, "--force"],
                check=True
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"CheckpointLite force cleanup failed: {e}")
            return
