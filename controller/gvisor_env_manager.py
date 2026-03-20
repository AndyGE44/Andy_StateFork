from __future__ import annotations

import logging
import subprocess
import time
import uuid
from typing import Optional, List
from .base_env_manager import EnvironmentManager, SnapshotNode
from decider import Decider

logger = logging.getLogger("EnvManager.GVisor")
#TODO: STILL NEED TO DO CALCULATOR!
#TODO: also need to check messages for step etc, since not in a new container

class GvisorAttachManager(EnvironmentManager):
    def __init__(self,
                 container_name: str,
                 base_image: str,
                 extra_args: Optional[List[str]] = None,
                 decider: Optional[Decider] = None,
                 ):
        """
        Initialize a gVisor-based environment.

        :param container_name: Name of the running container to attach to.
        :param base_image: Base image to use for the environment.
            Example: "ubuntu:latest" or "statefork:base".
        :param extra_args: Additional command-line args passed during container startup.
            Example: ["-v", "/tmp:/tmp"]
        """
        super().__init__(backend_name="gVisor", decider=decider)
        self.container_name = container_name
        self.extra_args = extra_args or []

        sid, _ = self._core_snapshot()
        if sid is None:
            raise RuntimeError("Failed to create initial snapshot.")

        # Init the Tree Graph
        self.snapshot_graph[sid] = SnapshotNode(snapshot_id=sid, parent_id=None)
        self.current_snapshot_id = sid
        self.last_snapshot_id = sid

        # TODO: Attach image calculator?


    def _core_snapshot(self) -> tuple[Optional[str], float]:
        snapshot_id = str(uuid.uuid4())[:8]

        start = time.time()
        # ask: wrap in try/except? not sure why ckptlite has but not container
        subprocess.run(
            ["docker", "checkpoint", "create", "--leave-running", self.container_name, snapshot_id],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        elapsed = time.time() - start
        self.snapshots[snapshot_id] = snapshot_id
        return snapshot_id, elapsed

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        snapshot_id = self.snapshots.get(snapshot_id)
        if not snapshot_id:
            logger.warning(f"Snapshot {snapshot_id} not found.")
            return None, 0.0

        # Stop container if running
        subprocess.run(["docker", "stop", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # TODO: Run `docker start --checkpoint image_name self.container_name`
        # Start from checkpoint
        cmd = ["docker", "start", "--checkpoint", snapshot_id, self.container_name]
        logger.debug(f"Starting container with command: {' '.join(cmd)}")

        start = time.time()
        subprocess.run(cmd, stdout=subprocess.DEVNULL, check=True)
        elapsed = time.time() - start

        return self.container_name, elapsed

    def _core_cleanup(self):
        logger.info(f"Cleaning up gVisor docker container '{self.container_name}'")
        subprocess.run(["docker", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # if don't using custom --checkpoint-dir on checkpoint, images are in container dir and removed during rm.
   
    def _core_exec(self, command, timeout=None):
        if isinstance(command, list):
            cmd = ["docker", "exec", self.container_name] + command
        else:
            cmd = ["docker", "exec", self.container_name, "bash", "-c", command]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result.returncode, result.stdout, result.stderr


class GvisorBuildManager(GvisorAttachManager):
    def __init__(self,
                 dockerfile_dir: str = ".",
                 base_image: str = None,
                 extra_args: Optional[List[str]] = None,
                 decider: Optional[Decider] = None,
                 ):
        """
        Initialize a gVisor-based environment by building from a Dockerfile.

        :param dockerfile_dir: Path to the directory containing the Dockerfile.
            Example: "/home/user/projects/myapp/"
        :param base_image: Base image to use for building the container.
            Example: "python:3.10-slim"
        :param extra_args: Additional command-line args passed during container startup.
            Example: ["-v", "/tmp:/tmp"]
        """
        if base_image is None:
            base_image = f"statefork_{str(uuid.uuid4())[:4]}:base"

        if extra_args is None:
            extra_args = ["-v", "/tmp:/tmp"]

        container_name = "statefork_active"

        logger.info(f"Building base gVisor image '{base_image}' from directory '{dockerfile_dir}'...")
        subprocess.run(["docker", "build", "-t", base_image, dockerfile_dir], stdout=subprocess.DEVNULL, check=True)

        logger.info("Creating initial environment from base image...")
        cmd = ["docker", "run", "-d", "--runtime", "runsc", "--network", "host", "--name", container_name] + extra_args + [base_image]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to create initial environment from base image.")

        super().__init__(container_name=container_name, base_image=base_image, extra_args=extra_args, decider=decider)