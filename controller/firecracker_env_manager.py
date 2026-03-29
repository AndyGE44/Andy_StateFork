from __future__ import annotations

import logging
import subprocess
import time
import uuid
from typing import Optional, List
from .base_env_manager import EnvironmentManager, SnapshotNode
from decider import Decider
from pathlib import Path

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

        """
        self.api_socket = api_socket
        self.snapshot_base = snapshot_base
        self.memfile_base = memfile_base

        logger.info(f"Recognized base image prefix: {self.image_prefix}")
        self.snapshots["base"] = base_image

        # Init the Tree Graph
        self.snapshot_graph["base"] = SnapshotNode(snapshot_id="base", parent_id=None)
        self.current_snapshot_id = "base"
        self.last_snapshot_id = "base"
        """

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
                 firecracker_dir: str = ".",
                 snapshot_base: Optional[str] = "./snapshot_base",
                 memfile_base: Optional[str] = "./memfile_base",
                 decider: Optional[Decider] = None,
                 ):
        """
        Initialize a Firecracker microVM.
        """
        logger.info("Creating Firecracker microVM...")
        # TODO: Seems a lot of steps to start a VM and let it runs the test workload

        # Artifacts
        logger.info("Setting up files...")
        firecracker_dir = Path(firecracker_dir)
        try:
            ARCH = subprocess.check_output("uname -m", shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            release_url = "https://github.com/firecracker-microvm/firecracker/releases"
            latest_version = subprocess.check_output(
                f"basename $(curl -fsSLI -o /dev/null -w %{{url_effective}} {release_url}/latest)",
                shell=True, text=True, stderr=subprocess.DEVNULL
            ).strip()
            CI_VERSION = ".".join(latest_version.split(".")[:2])

            # 1) get linux kernel binary
            latest_kernel_key = subprocess.check_output(
                f'curl -s "http://spec.ccfc.min.s3.amazonaws.com/?prefix=firecracker-ci/{CI_VERSION}/{ARCH}/vmlinux-&list-type=2" '
                f'| grep -oP "(?<=<Key>)(firecracker-ci/{CI_VERSION}/{ARCH}/vmlinux-[0-9]+\\.[0-9]+\\.[0-9]{{1,3}})(?=</Key>)" '
                f'| sort -V | tail -1',
                shell=True, text=True, stderr=subprocess.DEVNULL
            ).strip()

            kernel = firecracker_dir / latest_kernel_key.split("/")[-1]
            if not kernel.exists():
                firecracker_dir.mkdir(parents=True, exist_ok=True)
                subprocess.check_call(f'wget -q "https://s3.amazonaws.com/spec.ccfc.min/{latest_kernel_key}" -O {kernel}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if kernel.exists():
                    logger.info(f"Kernel file set up: {kernel}")
                else:
                    raise RuntimeError(f"Unable to set up kernel {kernel}")
            else:
                logger.info(f"Using kernel file: {kernel}")

            # 2) get rootfs
            latest_ubuntu_key = subprocess.check_output(
                f'curl -s "http://spec.ccfc.min.s3.amazonaws.com/?prefix=firecracker-ci/{CI_VERSION}/{ARCH}/ubuntu-&list-type=2" '
                f'| grep -oP "(?<=<Key>)(firecracker-ci/{CI_VERSION}/{ARCH}/ubuntu-[0-9]+\\.[0-9]+\\.squashfs)(?=</Key>)" '
                f'| sort -V | tail -1',
                shell=True, text=True, stderr=subprocess.DEVNULL
            ).strip()

            ubuntu_version = subprocess.check_output(
                f"basename {latest_ubuntu_key} .squashfs | grep -oE '[0-9]+\\.[0-9]+'",
                shell=True, text=True, stderr=subprocess.DEVNULL
            ).strip()

            rootfs = firecracker_dir / f"ubuntu-{ubuntu_version}.ext4"
            id_rsa = firecracker_dir / f"ubuntu-{ubuntu_version}.id_rsa"

            if not id_rsa.exists():
                subprocess.check_call(f"ssh-keygen -f {id_rsa} -N ''", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if id_rsa.exists():
                    logger.info(f"SSH Key set up: {id_rsa}")
                else:
                    raise RuntimeError(f"Unable to set up SSH Key {id_rsa}")
            else:
                logger.info(f"Using SSH Key: {id_rsa}")

            if not rootfs.exists():
                squashfs = firecracker_dir / f"ubuntu-{ubuntu_version}.squashfs.upstream"
                squashfs_root = firecracker_dir / "squashfs-root"
                subprocess.check_call(f'wget -q -O {squashfs} "https://s3.amazonaws.com/spec.ccfc.min/{latest_ubuntu_key}"', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(f"unsquashfs -d {squashfs_root} {squashfs}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(f"cp {id_rsa}.pub {squashfs_root}/root/.ssh/authorized_keys", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(f"sudo chown -R root:root {squashfs_root}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(f"truncate -s 1G {rootfs}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.check_call(f"sudo mkfs.ext4 -d {squashfs_root} -F {rootfs}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                logger.info(f"Rootfs set up: {rootfs}")

            e2fsck = subprocess.run(f"e2fsck -fn {rootfs}", shell=True, capture_output=True)
            if e2fsck.returncode == 0:
                logger.info(f"Using rootfs {rootfs}")
            else:
                raise RuntimeError(f"{rootfs} is not a valid ext4 fs")

        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to set up necessary files for firecracker")

        # 3) (or maybe make prereq) get firecracker binary
        # 4) make TAP device for networking -- have user pass in the ip? (also used for mac addr) 

        # Start VM
        # 1) Run firecracker using config file long running process -- user pass in socket path?
        # config file specifies:
            #  Configure logging
            #  Set kernel
            #  Set rootfs
            #  Set network interface

        # on exit: issue reboot into ssh

        # seems that we can't restore into same vm?
        # so snapshot pauses and then resumes
        # step should pause, resume to kill, kill tap, and reboot into a new loaded one?
        # restore means kill current, kill tap, and then reboot into a newly loaded one?

        # potentially checkpoint diffs instead, in which case need to merge before loading?

        api_socket = "..."
        super().__init__(api_socket=api_socket, snapshot_base=snapshot_base, memfile_base=memfile_base, decider=decider)


