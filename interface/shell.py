import argparse
import logging

from controller import create_env_manager
from decider import RandomDecider, AlwaysTrueDecider, AlwaysFalseDecider, ThresholdDecider


AVAILABLE_COMMANDS = [
    "snapshot",
    "restore <id>",
    "step",
    "cmd <command>",
    "tree",
    "stats",
    "history",
    "storage",
    "exit",
    "set",
]


# -------- Backend Mapping --------
BACKEND_MAP = {
    "docker": "docker_build",
    "podman": "podman_build",
    "criu": "criu_build",
    "hybrid": "hybrid_build",
    "waypoint": "waypoint_build",
    "ckpt": "waypoint_build",  # legacy alias
    "gvisor": "gvisor_build",
    "firecracker": "firecracker_build"
}


# -------- Decider Mapping --------
DECIDER_MAP = {
    "random": RandomDecider,
    "always_true": AlwaysTrueDecider,
    "always_false": AlwaysFalseDecider,
    "threshold": ThresholdDecider,
}


def build_manager(method: str,
                  decider_name: str,
                  threshold: float,
                  dolt_repo: str = None,
                  dolt_branch_prefix: str = "sf_",
                  dolt_working_branch: str = "main"):
    method_key = BACKEND_MAP[method]

    if decider_name == "threshold":
        decider_instance = ThresholdDecider(threshold)
    else:
        decider_cls = DECIDER_MAP[decider_name]
        decider_instance = decider_cls()

    kwargs = dict(decider=decider_instance)

    # Enable external Dolt control only when a repo path is provided.
    if dolt_repo:
        kwargs.update(
            dolt_repo=dolt_repo,
            dolt_branch_prefix=dolt_branch_prefix,
            dolt_working_branch=dolt_working_branch,
        )

    return create_env_manager(method_key, **kwargs)

def print_welcome_message(manager):
    print("==========================================")
    print("StateFork Container Manager - Interactive Shell")
    print(f"Using {manager.__class__.__name__} with {manager.backend} backend")
    dolt = getattr(manager, "dolt", None)
    if dolt is not None and dolt.enabled:
        print(f"External Dolt control: ON  (repo: {dolt.repo_dir})")
    elif dolt is not None:
        print("External Dolt control: requested but `dolt` binary not found")
    print("")
    print(f"Available commands: {', '.join(AVAILABLE_COMMANDS)}")

def execute_command(manager, command_text):
    rc, out, err = manager.exec_command(command_text)

    if out.strip():
        print("--- stdout ---")
        print(out.strip())
    if err.strip():
        print("--- stderr ---")
        print(err.strip())

def interactive_shell(manager):
    print_welcome_message(manager)

    need_cmd_heading = True

    while True:
        cmd = input("\nStateFork > ").strip()

        if cmd == "snapshot":
            sid = manager.snapshot()
            print(f"Snapshot created: {sid}")

        elif cmd.startswith("restore"):
            _, _, sid = cmd.partition(" ")
            if not sid:
                print("Usage: restore <snapshot_id>")
                continue

            ok = manager.restore(sid)
            print(f"Restored to snapshot {sid}" if ok else f"Snapshot {sid} not found.")

        elif cmd == "step":
            sid = manager.snapshot()
            container = manager.create_env_from_snapshot(sid)
            print(
                f"Stepped to new container with snapshot {sid}"
                if container else
                "Failed to create new container from snapshot."
            )

        elif cmd.startswith("cmd"):
            _, _, command_text = cmd.partition(" ")
            if not command_text:
                print("Usage: cmd <command>")
                continue
            execute_command(manager, command_text)

        elif cmd == "tree":
            print(manager.print_snapshot_tree())

        elif cmd == "stats":
            print(manager.stats.print_stats())

        elif cmd == "history":
            print(manager.stats.print_history())

        elif cmd == "storage":
            print(manager.stats.print_size_details())

        elif cmd == "exit":
            print(manager.stats.print_stats())
            print("Cleaning up resources...")
            manager.cleanup()
            break

        elif cmd.startswith("set"):
            _, _, config_string = cmd.partition(" ")
            if not config_string:
                print("Usage: set <config>")
                continue
            elif config_string == "cmd off":
                need_cmd_heading = False
                print("Command input heading turned OFF.")
            elif config_string == "cmd on":
                need_cmd_heading = True
                print("Command input heading turned ON.")
            else:
                print(f"Unknown config: {config_string}")

        else:
            if need_cmd_heading:
                print(f"Unknown command: {cmd}")
                print(f"Available commands: {', '.join(AVAILABLE_COMMANDS)}")
                continue
            # If heading is turned off, treat unknown commands as direct commands to execute
            execute_command(manager, cmd)


def main():
    parser = argparse.ArgumentParser(description="Environment Manager Launcher")

    parser.add_argument(
        "--method",
        choices=BACKEND_MAP.keys(),
        default="docker",
        help="Choose the environment manager backend"
    )

    parser.add_argument(
        "--decider",
        choices=DECIDER_MAP.keys(),
        default="always_true",
        help="Choose snapshot decision strategy"
    )

    parser.add_argument(
        "--threshold",
        type=float,
        default=5,
        help="Threshold (seconds) for threshold decider"
    )

    parser.add_argument(
        "--dolt-repo",
        default=None,
        help="Path to an external Dolt repository to version alongside file-system "
             "snapshots. Providing this enables external Dolt control."
    )

    parser.add_argument(
        "--dolt-branch-prefix",
        default="sf_",
        help="Prefix for the per-snapshot Dolt branch names (default: sf_)"
    )

    parser.add_argument(
        "--dolt-working-branch",
        default="main",
        help="Dolt branch used for live work between snapshots (default: main)"
    )

    args = parser.parse_args()

    manager = build_manager(
        args.method,
        args.decider,
        args.threshold,
        dolt_repo=args.dolt_repo,
        dolt_branch_prefix=args.dolt_branch_prefix,
        dolt_working_branch=args.dolt_working_branch,
    )
    interactive_shell(manager)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
