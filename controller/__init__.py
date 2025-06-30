from .base_env_manager import EnvironmentManager
from .docker_env_manager import DockerAttachManager, DockerBuildManager
from .criu_env_manager import CRIUAttachManager, CRIULaunchManager
from .podman_env_manager import PodmanHybridManager, PodmanBuildManager
from .benchmark import BenchmarkStats

from typing import Literal

EnvType = Literal["criu_launch", "criu_attach", "docker_build", "docker_attach", "podman_build", "podman_attach"]

"""
Apply the Factory Method pattern to create different environment managers based on the method type.
"""
def create_env_manager(method: EnvType, **kwargs) -> EnvironmentManager:
    if method == "criu_launch":
        return CRIULaunchManager(
            work_dir=kwargs.get("work_dir", "/tmp/statefork_criu"),
            command=kwargs.get("command")
        )
    elif method == "criu_attach":
        return CRIUAttachManager(
            target_pid=kwargs["target_pid"],
            work_dir=kwargs.get("work_dir", "/tmp/statefork_criu")
        )
    elif method == "docker_build":
        return DockerBuildManager(
            base_image=kwargs.get("base_image", "statefork-app:latest"),
            dockerfile_dir=kwargs.get("dockerfile_dir", ".")
        )
    elif method == "docker_attach":
        return DockerAttachManager(
            container_name=kwargs["container_name"],
            base_image=kwargs.get("base_image", "statefork-app:latest")
        )
    elif method == "podman_build":
        return PodmanBuildManager(
            container_name=kwargs.get("container_name", "podman-build"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman")
        )
    elif method == "podman_attach":
        return PodmanHybridManager(
            container_name=kwargs["container_name"],
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman")
        )
    else:
        raise ValueError(f"Unknown method: {method}")
