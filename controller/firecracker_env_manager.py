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
import paramiko # need to pip install
import ipaddress

logger = logging.getLogger("EnvManager.Firecracker")

class FireAttachManager(EnvironmentManager):
    def __init__(self,
                microvm_ip,
                fire_process,
                fire_binary,
                key,
                api_socket: Optional[str] = "/tmp/firecracker.socket",
                checkpoint_dir: Optional[str] = "fire_ckpts",
                decider: Optional[Decider] = None,
                ):
        """
        Initialize a Firecracker microVM.
        """
        super().__init__(backend_name="Firecracker", decider=decider)

        self.api_socket = api_socket
        self.microvm_ip = microvm_ip
        self.key = key
        self.fire_binary = fire_binary
        self.fire_process = fire_process

        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        

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
        if result.stdout.strip() == ("204"):
            return True
        logger.error(f"Failed to pause VM")
        return False

    def __resume_vm(self) -> bool:
        cmd = [
            "sudo", "curl", "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--unix-socket", str(self.api_socket),
            "-X", "PATCH", "http://localhost/vm",
            "-H", "Accept: application/json",
            "-H", "Content-Type: application/json",
            "-d", '{"state": "Resumed"}'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip() == ("204"):
            return True
        logger.error(f"Failed to resume VM")
        return False

    def _core_snapshot(self) -> tuple[Optional[str], float]:
        snapshot_id = str(uuid.uuid4())[:8]

        snapshot_dir = self.checkpoint_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / "snap" 
        mem_file_path = snapshot_dir / "mem"

        start = time.time()
        ok = self.__pause_vm()
        if not ok:
            logger.error("Failed to pause VM before snapshot")
            return None, None

        # Do full for now -- allow user to pass in choice for diff?
        cmd = [
            "sudo", "curl", "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--unix-socket", str(self.api_socket),
            "-X", "PUT", "http://localhost/snapshot/create",
            "-H", "Accept: application/json",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "snapshot_type": "Full", # add option to switch to "Diff"?
                "snapshot_path": str(snapshot_path),
                "mem_file_path": str(mem_file_path)
            })
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip() == ("400"):
            logger.error(f"Failed to snapshot VM")
            return None, None

        ok = self.__resume_vm()
        if not ok:
            logger.error("Failed to resume VM after snapshot")
            return None, None

        elapsed = time.time() - start

        self.snapshots[snapshot_id] = snapshot_id
        return snapshot_id, elapsed

    def _core_create_env(self, snapshot_id: str) -> tuple[Optional[str], float]:
        snapshot_name = self.snapshots.get(snapshot_id)
        if not snapshot_name:
            logger.warning(f"Snapshot ID {snapshot_id} not found.")
            return None, 0.0

        start = time.time()
        # issue ssh reboot
        key = paramiko.RSAKey.from_private_key_file(self.key)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=self.microvm_ip, username="root", pkey=key)
        stdin, stdout, stderr = ssh.exec_command("reboot")
        ssh.close()
        # close firecracker process
        self.fire_process.terminate()
        self.fire_process.wait()

        # remove old socket and start up non-config'd microvm
        try:
            subprocess.run(["sudo", "rm", "-f", self.api_socket], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            firecracker_process = subprocess.Popen(
                ["sudo", str(self.fire_binary), "--api-sock", self.api_socket],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL
            )
        except Exception:
            raise RuntimeError(f"Failed to start firecracker process on socket {self.api_socket}")

        # restore
        snapshot_path = self.checkpoint_dir / snapshot_id / "snap"
        mem_path = self.checkpoint_dir / snapshot_id / "mem"

        cmd = [
            "sudo", "curl", "-s",
            "-o", "/dev/null",
            "-w", "%{http_code}",
            "--unix-socket", str(self.api_socket),
            "-X", "PUT", "http://localhost/snapshot/load",
            "-H", "Accept: application/json",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({
                "snapshot_path": str(snapshot_path),
                "mem_file_path": str(mem_path),
                "resume_vm": True
            })
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip() == ("400"):
            logger.error(f"Failed to load snapshot")
            return None, None

        elapsed = time.time() - start

        return snapshot_name, elapsed

    def _core_cleanup(self):
        logger.info(f"Cleaning up Firecracker microVM...")
        # TODO: How to terminate and cleanup VMs?


    def _core_exec(self, command, timeout=None):
        # TODO: Not sure how to do exec in the VM?
        #   `ssh` with the command?
        #   If it is hard to do so, just make sure the VM can run the default FastAPi workload is enough for MicroBenchmark

        key = paramiko.RSAKey.from_private_key_file(self.key)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(hostname=self.microvm_ip, username="root", pkey=key)
            stdin, stdout, stderr = ssh.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()

            stdout_str = stdout.read().decode()
            stderr_str = stderr.read().decode()

        finally:
            ssh.close()

        return exit_status, stdout_str, stderr_str

    @staticmethod
    def _start_full_microvm(firecracker_dir, ARCH, TAP_DEV, TAP_IP, MASK, FC_MAC, API_SOCKET):
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
                subprocess.check_call(f"ssh-keygen -t rsa -b 4096 -m PEM -f {id_rsa} -N ''", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if id_rsa.exists():
                    logger.info(f"SSH Key set up: {id_rsa}")
                else:
                    raise RuntimeError(f"Unable to set up SSH Key {id_rsa}")
            else:
                logger.info(f"Using SSH Key: {id_rsa}")

            if not rootfs.exists(): # buggy if created new id_rsa but rootfs alr. exists
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

        return id_rsa, firecracker_process, firecracker_binary

class FireBuildManager(FireAttachManager):
    def __init__(self,
                 firecracker_dir: str = ".",
                 ckpt_dir: Optional[str] = "./fire_ckpts",
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
        ssh_key, firecracker_process, firecracker_binary = FireAttachManager._start_full_microvm(firecracker_dir, ARCH=ARCH, TAP_DEV=TAP_DEV, TAP_IP=TAP_IP, MASK=MASK, FC_MAC=FC_MAC, API_SOCKET=API_SOCKET)

        network = ipaddress.ip_network(f"{TAP_IP}{MASK}", strict=False)
        hosts = list(network.hosts())
        microvm_ip = str(hosts[1])  

        # ping to verify that it is running
        result = subprocess.run(
            ["sudo", "curl", "-s", "--unix-socket", API_SOCKET, "http://localhost/"],
            capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError("Firecracker API socket is not responsive")
        logger.info("Firecracker VM is running")

        super().__init__(microvm_ip= microvm_ip, fire_process=firecracker_process, fire_binary=firecracker_binary, key=ssh_key, checkpoint_dir=ckpt_dir, api_socket=API_SOCKET, decider=decider)