import os
import subprocess
import time
import uuid
import shutil
import logging
from typing import Optional
from .base_env_manager import EnvironmentManager, SnapshotNode

logger = logging.getLogger("EnvManager.Podman")


class PodmanHybridManager(EnvironmentManager):
    def __init__(self, container_name: str, export_dir: str = "/tmp/statefork_podman"):
        super().__init__(backend_name="Podman+CRIU")
        self.container_name = container_name
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)

        logger.info(f"Initializing PodmanHybridManager with container '{self.container_name}'")

        # Ensure container is running
        self.__ensure_container_running()

        # Take initial snapshot
        sid, _ = self._core_snapshot()
        if sid is None:
            raise RuntimeError("Failed to create initial snapshot.")

        # Init the Tree Graph
        self.snapshot_graph[sid] = SnapshotNode(snapshot_id=sid, parent_id=None)
        self.current_snapshot_id = sid
        self.last_snapshot_id = sid

    def __ensure_container_running(self):
        result = subprocess.run(["podman", "ps", "-q", "-f", f"name={self.container_name}"], capture_output=True, text=True)
        if not result.stdout.strip():
            raise RuntimeError(f"Container '{self.container_name}' is not running. Please start it before using this manager.")
        logger.debug(f"Pass validation: Container '{self.container_name}' is running.")

    def _core_snapshot(self) -> tuple[Optional[str], float]:
        sid = str(uuid.uuid4())[:8]
        export_path = os.path.join(self.export_dir, f"{sid}.tar.zstd")

        start = time.time()
        subprocess.run([
            "podman", "container", "checkpoint", self.container_name,
            "-e", export_path, "--leave-running"
        ], check=True)
        elapsed = time.time() - start

        self.snapshots[sid] = export_path

        return sid, elapsed

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        export_path = self.snapshots.get(snapshot_id)
        if not export_path:
            logger.warning(f"Snapshot ID {snapshot_id} not found.")
            return None, 0.0

        # Stop & remove existing container if running
        subprocess.run(["podman", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        start = time.time()
        subprocess.run([
            "podman", "container", "restore",
            "-i", export_path,
            "-n", self.container_name
        ], check=True)
        elapsed = time.time() - start

        return self.container_name, elapsed

    def _core_cleanup(self):
        logger.info(f"Cleaning up Podman container '{self.container_name}'")
        subprocess.run(["podman", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Cleaning up Podman checkpoint files in {self.export_dir}")
        shutil.rmtree(self.export_dir, ignore_errors=True)


class PodmanBuildManager(PodmanHybridManager):
    def __init__(self, container_name="podman-build", dockerfile_dir: str = ".", export_dir: str = "/tmp/statefork_podman"):
        image_name = "init_image"
        logger.info(f"Building Podman image from directory '{dockerfile_dir}'...")
        subprocess.run(["podman", "build", "-t", image_name, dockerfile_dir], check=True)

        logger.info(f"Launching container '{container_name}' from image '{image_name}'...")
        subprocess.run(["podman", "run", "-d", "--rm", "-p", "8000:8000", "-v", "/tmp:/tmp","--name", container_name, image_name], check=True)

        time.sleep(2)  # wait for app to initialize

        super().__init__(container_name=container_name, export_dir=export_dir)


