import importlib
from typing import Literal, TYPE_CHECKING

# --- Lightweight (stdlib-only) imports -------------------------------------
# Keeping the package import light lets external integrations (e.g. Harbor)
# import the container/base/decider machinery without pulling in optional
# heavy backends and their dependencies (paramiko for Firecracker, psutil for
# CRIU/Firecracker, etc.). The heavy backends are imported lazily inside the
# factory and exposed via module ``__getattr__`` for backwards compatibility.
from .base_env_manager import EnvironmentManager
from .container_env_manager import ContainerAttachManager, ContainerBuildManager
from .benchmark import BenchmarkStats, BenchmarkResult, Statistics
from .dolt_controller import DoltController
from decider.decider import Decider, RandomDecider, AlwaysFalseDecider, AlwaysTrueDecider

if TYPE_CHECKING:  # for type checkers / IDEs only; not imported at runtime
    from .criu_env_manager import CRIUAttachManager, CRIUBuildManager
    from .hybrid_env_manager import HybridAttachManager, HybridBuildManager
    from .waypoint_env_manager import WaypointAttachManager, WaypointBuildManager
    from .gvisor_env_manager import GvisorBuildManager, GvisorAttachManager
    from .firecracker_env_manager import FireBuildManager, FireAttachManager

# Map of lazily-loaded names -> (submodule, attribute). Accessing any of these
# as ``controller.<Name>`` (or ``from controller import <Name>``) imports the
# backing module on demand, so optional dependencies are only required when the
# corresponding backend is actually used.
_LAZY_EXPORTS = {
    "CRIUAttachManager": ".criu_env_manager",
    "CRIUBuildManager": ".criu_env_manager",
    "HybridAttachManager": ".hybrid_env_manager",
    "HybridBuildManager": ".hybrid_env_manager",
    "WaypointAttachManager": ".waypoint_env_manager",
    "WaypointBuildManager": ".waypoint_env_manager",
    "GvisorBuildManager": ".gvisor_env_manager",
    "GvisorAttachManager": ".gvisor_env_manager",
    "FireBuildManager": ".firecracker_env_manager",
    "FireAttachManager": ".firecracker_env_manager",
}


def __getattr__(name: str):
    """PEP 562 lazy attribute access for optional heavy backends."""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(module_name, __name__)
    return getattr(module, name)


EnvType = Literal[
    "criu_build", "criu_attach",
    "docker_build", "docker_attach",
    "podman_build", "podman_attach",
    "hybrid_build", "hybrid_attach",
    "waypoint_build", "waypoint_attach", "ckpt_build", "ckpt_attach",
    "gvisor_build", "gvisor_attach",
    "firecracker_build", "firecracker_attach"
]

"""
Apply the Factory Method pattern to create different environment managers based on the method type.

In addition to the backend-specific arguments, an optional **external Dolt**
database can be controlled in lockstep with the file-system snapshots. Pass
either a ready-made ``dolt=DoltController(...)`` instance, or the convenience
kwargs ``dolt_repo`` (path to the Dolt repo, which also enables the feature),
``dolt_branch_prefix``, ``dolt_working_branch``, and ``dolt_bin``. When enabled,
each ``snapshot()`` commits the Dolt working set onto a per-snapshot branch and
each ``restore()`` resets the database back to it.
"""
def create_env_manager(method: EnvType, **kwargs) -> EnvironmentManager:
    manager = _instantiate_manager(method, **kwargs)
    _attach_dolt(manager, kwargs)
    return manager


def _attach_dolt(manager: EnvironmentManager, kwargs: dict) -> None:
    """
    Attach an external Dolt controller to a freshly created manager when the
    caller asked for it. Doing this here (rather than threading a ``dolt`` arg
    through every backend constructor) keeps the feature in one place.
    """
    dolt = kwargs.get("dolt")
    if dolt is None and (kwargs.get("dolt_repo") or kwargs.get("use_dolt")):
        dolt = DoltController(
            repo_dir=kwargs.get("dolt_repo", "."),
            branch_prefix=kwargs.get("dolt_branch_prefix", "sf_"),
            working_branch=kwargs.get("dolt_working_branch", "main"),
            dolt_bin=kwargs.get("dolt_bin", "dolt"),
        )
    if dolt is not None:
        manager.dolt = dolt


def _instantiate_manager(method: EnvType, **kwargs) -> EnvironmentManager:
    if method == "criu_build":
        from .criu_env_manager import CRIUBuildManager
        return CRIUBuildManager(
            work_dir=kwargs.get("work_dir", "/tmp/statefork_criu"),
            command=kwargs.get("command"),
            decider=kwargs.get("decider")
        )
    elif method == "criu_attach":
        from .criu_env_manager import CRIUAttachManager
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
        from .hybrid_env_manager import HybridBuildManager
        return HybridBuildManager(
            container_name=kwargs.get("container_name", "podman-build"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman"),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "hybrid_attach":
        from .hybrid_env_manager import HybridAttachManager
        return HybridAttachManager(
            container_name=kwargs["container_name"],
            export_dir=kwargs.get("export_dir", "/tmp/statefork_podman"),
            decider=kwargs.get("decider")
        )
    elif method in ("waypoint_build", "ckpt_build"):
        from .waypoint_env_manager import WaypointBuildManager
        return WaypointBuildManager(
            dockerfile_dir=kwargs.get("dockerfile_dir"),
            build=kwargs.get("build", True),
            decider=kwargs.get("decider")
        )
    elif method in ("waypoint_attach", "ckpt_attach"):
        from .waypoint_env_manager import WaypointAttachManager
        return WaypointAttachManager(
            session_id=kwargs["session_id"],
            target_pid=kwargs.get("target_pid", -2),
            decider=kwargs.get("decider")
        )
    elif method == "gvisor_build":
        from .gvisor_env_manager import GvisorBuildManager
        return GvisorBuildManager(
            base_image=kwargs.get("base_image"),
            dockerfile_dir=kwargs.get("dockerfile_dir", "."),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "gvisor_attach":
        from .gvisor_env_manager import GvisorAttachManager
        return GvisorAttachManager(
            container_name=kwargs["container_name"],
            base_image=kwargs.get("base_image", "statefork-app:base"),
            extra_args=kwargs.get("extra_args"),
            decider=kwargs.get("decider")
        )
    elif method == "firecracker_build":
        from .firecracker_env_manager import FireBuildManager
        return FireBuildManager(
            fire_parent_dir=kwargs.get("firecracker_dir", "/tmp"), # create artifact and ckpt directories here
            inject_dir=kwargs.get("inject_dir", "app"), # pass files to be in the vm
            decider=kwargs.get("decider")
        )
    elif method == "firecracker_attach":
        import psutil
        from pathlib import Path
        from .firecracker_env_manager import FireAttachManager
        fire_pid = int(kwargs["pid"])
        return FireAttachManager(
            fire_process = psutil.Process(fire_pid),
            microvm_ip=kwargs.get("microvm_ip", "172.16.0.2"),
            tap_dev=kwargs.get("tap_dev", "tap0"),

            key=Path(kwargs["key"]),
            checkpoint_dir=Path(kwargs.get("checkpoint_dir", "/tmp/fire_ckpts")),
            vm_dir=Path(kwargs.get("vm_dir", "/tmp/fire_vm")),
            fire_binary=Path(kwargs.get("fire_binary", "/tmp/fire_vm/firecracker")),

            api_socket=kwargs.get("api_socket", "/tmp/firecracker.socket"),
            decider=kwargs.get("decider")
        )
    else:
        raise ValueError(f"Unknown method: {method}")
