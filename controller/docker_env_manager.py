import subprocess
import time
import uuid
import logging
from typing import Optional
from .base_env_manager import EnvironmentManager, SnapshotNode

logger = logging.getLogger(__name__)


class DockerAttachManager(EnvironmentManager):
    def __init__(self, container_name: str, base_image: str):
        super().__init__()
        self.container_name = container_name
        self.snapshots["base"] = base_image

        # Init the Tree Graph
        self.snapshot_graph["base"] = SnapshotNode(snapshot_id="base", parent_id=None)
        self.current_snapshot_id = "base"
        self.last_snapshot_id = "base"


    def _core_snapshot(self) -> tuple[Optional[str], float]:
        snapshot_id = str(uuid.uuid4())[:8]
        image_name = f"snapshot_{snapshot_id}"

        start = time.time()
        subprocess.run(["docker", "commit", self.container_name, image_name], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elapsed = time.time() - start

        self.snapshots[snapshot_id] = image_name

        return snapshot_id, elapsed

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        image_name = self.snapshots.get(snapshot_id)
        if not image_name:
            logger.warning(f"Snapshot ID {snapshot_id} not found.")
            return None, 0.0

        # Stop & remove existing container if running
        subprocess.run(["docker", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        start = time.time()
        subprocess.run([
            "docker", "run", "-d", "--rm",
            "--name", self.container_name,
            "-p", "8000:8000",
            "-v", "/tmp:/tmp",
            image_name
        ], check=True)
        elapsed = time.time() - start

        return self.container_name, elapsed

    def _core_restore(self, snapshot_id: str) -> tuple[bool, float]:
        start = time.time()
        result, _ = self._core_create_env(snapshot_id)
        elapsed = time.time() - start

        return result is not None, elapsed

    def _core_cleanup(self):
        subprocess.run(["docker", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for snapshot_id in list(self.snapshots.keys()):
            image_name = self.snapshots[snapshot_id]
            subprocess.run(["docker", "rmi", image_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            del self.snapshots[snapshot_id]


class DockerBuildManager(DockerAttachManager):
    def __init__(self, base_image: str = "statefork-app:latest", dockerfile_dir: str = "."):
        logger.info(f"Building base Docker image '{base_image}' from directory '{dockerfile_dir}'...")
        subprocess.run(["docker", "build", "-t", base_image, dockerfile_dir], check=True)

        super().__init__(container_name="statefork_active", base_image=base_image)

        logger.info("Creating initial environment from base image...")
        res, _ = self._core_create_env("base")
        if res is None:
            raise RuntimeError("Failed to create initial environment from base image.")
