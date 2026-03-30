from __future__ import annotations

import logging
import subprocess
import time
import uuid
from typing import Optional, List
from .base_env_manager import EnvironmentManager, SnapshotNode
from decider import Decider
from pathlib import Path
import json

logger = logging.getLogger("EnvManager.Firecracker")
# note: could use diff snapshots and walk snapshot tree on each resume? 
# this will add extra steps to merge, but shouldn't increase actual restore time from final snapshot
# however merge probably would decrease the storage used
# so maybe try to switch to diff/merge later?

class FireAttachManager(EnvironmentManager):
    def __init__(self,
                api_socket: Optional[str] = "/tmp/firecracker.socket",
                arch,
                tap_dev,
                tap_ip,
                mask,
                fc_mac,
                checkpoint_dir: Optional[str] = "fire_ckpts"
                decider: Optional[Decider] = None,
                ):
        """
        Initialize a Firecracker microVM.
        """
        super().__init__(backend_name="Firecracker", decider=decider)

        self.api_socket = api_socket
        self.arch = arch
        self.tap_dev = tap_dev
        self.tap_ip = tap_ip
        self.mask = mask
        self.fs_mac = fc_mac
        self.checkpoint_dir = Path(checkpoint_dir)
        self.snap_dir = self.checkpoint_dir / "snap"
        self.mem_dir = self.checkpoint_dir / "mem"

        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.mem_dir.mkdir(parents=True, exist_ok=True)

        # base snapshot
        sid, _ = self._core_snapshot()
        if sid is None:
            raise RuntimeError("Failed to create initial snapshot.")

        # Init the Tree Graph
        self.snapshot_graph[sid] = SnapshotNode(snapshot_id=sid, parent_id=None)
        self.current_snapshot_id = sid
        self.last_snapshot_id = sid

    def __pause_vm(self) -> bool:
        cmd = [
            "sudo", "curl", "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--unix-socket", str(self.api_socket),
            "-X", "PATCH", "http://localhost/vm",
            "-H", "Accept: application/json",
            "-H", "Content-Type: application/json",
            "-d", '{"state": "Paused"}'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip().startswith("2"):
            return True
        logger.error(f"Failed to pause VM, HTTP status: {result.stdout.strip()}")
        return False

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

        snapshot_path = self.snap_dir / snapshot_id
        mem_file_path = self.mem_dir / snapshot_id

        # Ask: should start include pause and resume?
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

        # ask: should resume time be included in the snapshot elapsed?
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

        # Pause VM first
        ok = self.__pause_vm()
        if not ok:
            return None, None

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

    @staticmethod
    def __start_microvm(firecracker_dir, ARCH, TAP_DEV, TAP_IP, MASK, FC_MAC, API_SOCKET):
        """
        Heavily based off of the "Getting Started" guide: https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md
        """
        logger.info("Setting up files...")
        firecracker_dir = Path(firecracker_dir)
        try:
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

            # 3) get firecracker binary
            firecracker_binary = firecracker_dir / "firecracker"
            if not firecracker_binary.exists():
                subprocess.check_call(
                    f'curl -sL {release_url}/download/{latest_version}/firecracker-{latest_version}-{ARCH}.tgz | tar -xz',
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    cwd=firecracker_dir
                )
                src = firecracker_dir / f'release-{latest_version}-{ARCH}/firecracker-{latest_version}-{ARCH}'
                src.rename(firecracker_binary)
                if firecracker_binary.exists():
                    logger.info(f"Firecracker binary set up: {firecracker_binary}")
                else:
                    raise RuntimeError(f"Unable to set up firecracker binary")
            else:
                logger.info(f"Using firecracker binary {firecracker_binary}")


            # 4) make TAP device for networking
            subprocess.run(["sudo", "ip", "link", "del", TAP_DEV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["sudo", "ip", "tuntap", "add", "dev", TAP_DEV, "mode", "tap"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["sudo", "ip", "addr", "add", f"{TAP_IP}{MASK}", "dev", TAP_DEV], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.check_call(["sudo", "ip", "link", "set", "dev", TAP_DEV, "up"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info(f"TAP device {TAP_DEV} on {TAP_IP}{MASK} set up")

        except subprocess.CalledProcessError:
            raise RuntimeError("Failed to set up necessary files for firecracker")

        # Write config file
        config_path = firecracker_dir / "firecracker-config.json"
        if not config_path.exists():
            boot_args = "console=ttyS0 reboot=k panic=1"
            if ARCH == "aarch64":
                boot_args = f"keep_bootcon {boot_args}"

            config = {
                "boot-source": {
                    "kernel_image_path": str(kernel),
                    "boot_args": boot_args,
                },
                "drives": [
                    {
                        "drive_id": "rootfs",
                        "is_root_device": True,
                        "is_read_only": False,
                        "path_on_host": str(rootfs),
                    }
                ],
                "machine-config": {
                    "vcpu_count": 2,
                    "mem_size_mib": 1024,
                },
                "network-interfaces": [
                    {
                        "iface_id": "net1",
                        "guest_mac": FC_MAC,
                        "host_dev_name": TAP_DEV
                    }
                ],
            }

            try:
                with open(config_path, "w") as f:
                    json.dump(config, f, indent=2)
                logger.info(f"Firecracker config written to {config_path}")
            except Exception:
                raise RuntimeError("Failed to write firecracker config")
        else:
            logger.info(f"Using firecaracker config {config_path}") # careful: need FC_MAC, etc to match

        # Run firecracker
        try:
            subprocess.run(["sudo", "rm", "-f", API_SOCKET], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            firecracker_process = subprocess.Popen(
                ["sudo", str(firecracker_binary), "--api-sock", API_SOCKET, "--config-file", str(config_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
            logger.info(f"Started firecracker process and microVM")
        except Exception:
            raise RuntimeError(f"Failed to start firecracker process on socket {API_SOCKET}")

        return id_rsa, "firecracker_process"

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
        ARCH = subprocess.check_output("uname -m", shell=True, text=True, stderr=subprocess.DEVNULL).strip()
        TAP_DEV = "tap0"
        TAP_IP = "172.16.0.1"
        MASK = "/30"
        FC_MAC = "06:00:AC:10:00:02" # corresponds to TAP_IP and MASK
        API_SOCKET = "/tmp/firecracker.socket"
        logger.info("Creating Firecracker microVM...")
        ssh_key, firecracker_process = FireAttachManager.__start_microvm(firecracker_dir, ARCH=ARCH, TAP_DEV=TAP_DEV, TAP_IP=TAP_IP, MASK=MASK, FC_MAC=FC_MAC, API_SOCKET=API_SOCKET)

        # ping to verify that it is running
        result = subprocess.run(
            ["sudo", "curl", "-s", "--unix-socket", API_SOCKET, "http://localhost/"],
            capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError("Firecracker API socket is not responsive")
        logger.info("Firecracker VM is running")

        # on exit: issue reboot into ssh

        # seems that we can't restore into same vm?
        # so snapshot pauses and then resumes
        # step should pause, resume to kill, kill tap, and reboot into a new loaded one?
        # restore means kill current, kill tap, and then reboot into a newly loaded one?

        super().__init__(api_socket=API_SOCKET, arch=ARCH, tap_dev=TAP_DEV, tap_ip= TAP_IP, mask=MASK, fc_mac=FC_MAC, decider=decider)