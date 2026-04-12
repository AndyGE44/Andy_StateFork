from .base_env_manager import EnvironmentManager
from .container_env_manager import ContainerAttachManager, ContainerBuildManager
from .criu_env_manager import CRIUAttachManager, CRIUBuildManager
from .hybrid_env_manager import HybridAttachManager, HybridBuildManager
from .ckptlite_env_manager import CheckpointLiteAttachManager, CheckpointLiteBuildManager
from .gvisor_env_manager import GvisorBuildManager
from .firecracker_env_manager import FireBuildManager
from .benchmark import BenchmarkStats, BenchmarkResult, Statistics
from decider.decider import Decider, RandomDecider, AlwaysFalseDecider, AlwaysTrueDecider

from typing import Literal

EnvType = Literal[
    "criu_build", "criu_attach",
    "docker_build", "docker_attach",
    "podman_build", "podman_attach",
    "hybrid_build", "hybrid_attach",
    "ckpt_build", "ckpt_attach",
    "gvisor_build",
    "firecracker_build"
]

"""
Apply the Factory Method pattern to create different environment managers based on the method type.
"""
def create_env_manager(method: EnvType, **kwargs) -> EnvironmentManager:
    if method == "criu_build":
        return CRIUBuildManager(
            work_dir=kwargs.get("work_dir", "/tmp/statefork_criu"),
            command=kwargs.get("command"),
            decider=kwargs.get("decider")
        )
    elif method == "criu_attach":
        return CRIUAttachManager(
            target_pid=kwargs["target_pid"],
            work_dir=kwargs.get("work_dir", "/tmp/statefork_criu"),
            decider=kwargs.get("decider")
        )
    elif method == "docker_build":
        return ContainerBuildManager(
            backend="Docker",
            base_image=kwargs.get("base_image"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "docker_attach":
        return ContainerAttachManager(
            backend="Docker",
            container_name=kwargs["container_name"],
            base_image=kwargs.get("base_image", "statefork-app:base"),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "podman_build":
        return ContainerBuildManager(
            backend="Podman",
            base_image=kwargs.get("base_image"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "podman_attach":
        return ContainerAttachManager(
            backend="Podman",
            container_name=kwargs["container_name"],
            base_image=kwargs.get("base_image", "statefork-app:base"),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "hybrid_build":
        return HybridBuildManager(
            container_name=kwargs.get("container_name", "podman-build"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman"),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "hybrid_attach":
        return HybridAttachManager(
            container_name=kwargs["container_name"],
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman"),
            decider=kwargs.get("decider")
        )
    elif method == "ckpt_build":
        return CheckpointLiteBuildManager(
            dockerfile_dir=kwargs.get("dockerfile_dir"),
            build=kwargs.get("build", True),
            decider=kwargs.get("decider")
        )
    elif method == "ckpt_attach":
        return CheckpointLiteAttachManager(
            session_id=kwargs["session_id"],
            target_pid=kwargs.get("target_pid", -2),
            decider=kwargs.get("decider")
        )
    elif method == "gvisor_build":
        return GvisorBuildManager(
            base_image=kwargs.get("base_image"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "firecracker_build":
        return FireBuildManager(
            fire_parent_dir=kwargs.get("firecracker_dir", "/mydata"), # create artifact and ckpt directories here
            inject_dir=kwargs.get("inject_dir", "app"), # pass files to be in the vm
            decider=kwargs.get("decider")
        )
    else:
        raise ValueError(f"Unknown method: {method}")
