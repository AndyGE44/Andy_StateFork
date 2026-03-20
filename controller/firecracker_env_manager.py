from __future__ import annotations

import logging
import subprocess
import time
import uuid
from typing import Optional, List
from .base_env_manager import EnvironmentManager, SnapshotNode
from decider import Decider

logger = logging.getLogger("EnvManager.Firecracker")


class FireAttachManager(EnvironmentManager):
    def __init__(self,
                 api_socket: Optional[str] = "/tmp/firecracker.socket",
                 snapshot_base: Optional[str] = "./snapshot_base",
                 memfile_base: Optional[str] = "./memfile_base",
                 decider: Optional[Decider] = None,
                 ):
        """
        Initialize a Firecracker microVM.
        """
        super().__init__(backend_name="Firecracker", decider=decider)
        self.api_socket = api_socket
        self.snapshot_base = snapshot_base
        self.memfile_base = memfile_base

        logger.info(f"Recognized base image prefix: {self.image_prefix}")
        self.snapshots["base"] = base_image

        # Init the Tree Graph
        self.snapshot_graph["base"] = SnapshotNode(snapshot_id="base", parent_id=None)
        self.current_snapshot_id = "base"
        self.last_snapshot_id = "base"

    def __pause_vm(self) -> bool:
        # TODO: Pause the microVM
        #   curl --unix-socket self.api_socket -i \
        #     -X PATCH 'http://localhost/vm' \
        #     -H 'Accept: application/json' \
        #     -H 'Content-Type: application/json' \
        #     -d '{
        #             "state": "Paused"
        #     }'
        # validate the result
        return True

    def __resume_vm(self) -> bool:
        # TODO: Resume the microVM
        #   curl --unix-socket self.api_socket -i \
        #     -X PATCH 'http://localhost/vm' \
        #     -H 'Accept: application/json' \
        #     -H 'Content-Type: application/json' \
        #     -d '{
        #             "state": "Resumed"
        #     }'
        # validate the result
        return True

    def _core_snapshot(self) -> tuple[Optional[str], float]:
        snapshot_id = str(uuid.uuid4())[:8]
        # TODO: Create snapshot paths
        #   snapshot_path = self.snapshot_base / snapshot_id
        #   mem_file_path = self.memfile_base / snapshot_id
        #   May need to `mkdir` those directories?

        start = time.time()
        # TODO: Seems we have to pause the VM before taking a snapshot
        ok = self.__pause_vm()

        # TODO: Create microVm snapshot
        #   curl --unix-socket self.api_socket -i \
        #     -X PUT 'http://localhost/snapshot/create' \
        #     -H  'Accept: application/json' \
        #     -H  'Content-Type: application/json' \
        #     -d '{
        #             "snapshot_type": "Full",
        #             "snapshot_path": "snapshot_path",
        #             "mem_file_path": "mem_file_path"
        #     }'

        # TODO: Restore it so it is in the same semantics of other backends
        ok = self.__resume_vm()

        elapsed = time.time() - start

        self.snapshots[snapshot_id] = snapshot_id

        return snapshot_id, elapsed

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        snapshot_name = self.snapshots.get(snapshot_id)
        if not snapshot_name:
            logger.warning(f"Snapshot ID {snapshot_id} not found.")
            return None, 0.0

        # TODO: Construct image paths
        #   snapshot_path = self.snapshot_base / snapshot_name
        #   mem_file_path = self.memfile_base / snapshot_name

        # TODO: Not sure do we need to pause & remove existing VM if running?
        ok = self.__pause_vm()

        start = time.time()
        # TODO: Load VM states
        #   curl --unix-socket self.api_socket -i \
        #     -X PUT 'http://localhost/snapshot/load' \
        #     -H  'Accept: application/json' \
        #     -H  'Content-Type: application/json' \
        #     -d '{
        #             "snapshot_path": "snapshot_path",
        #             "mem_backend": {
        #                 "backend_path": "mem_file_path",
        #                 "backend_type": "File"
        #             },
        #             "track_dirty_pages": true,
        #             "resume_vm": false
        #     }'

        elapsed = time.time() - start

        # TODO: Restore
        ok = self.__resume_vm()

        return snapshot_name, elapsed

    def _core_cleanup(self):
        logger.info(f"Cleaning up Firecracker microVM...")
        # TODO: How to terminate and cleanup VMs?


    def _core_exec(self, command, timeout=None):
        # TODO: Not sure how to do exec in the VM?
        #   `ssh` with the command?
        #   If it is hard to do so, just make sure the VM can run the default FastAPi workload is enough for MicroBenchmark

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return result.returncode, result.stdout, result.stderr


class FireBuildManager(FireAttachManager):
    def __init__(self,
                 snapshot_base: Optional[str] = "./snapshot_base",
                 memfile_base: Optional[str] = "./memfile_base",
                 decider: Optional[Decider] = None,
                 ):
        """
        Initialize a Firecracker microVM.
        """
        logger.info("Creating Firecracker microVM...")
        # TODO: Seems a lot of steps to start a VM and let it runs the test workload
        api_socket = "..."
        super().__init__(api_socket=api_socket, snapshot_base=snapshot_base, memfile_base=memfile_base, decider=decider)


