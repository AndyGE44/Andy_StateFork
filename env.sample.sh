# StateFork environment configuration — sample.
#
# Usage:
#     cp env.sample.sh env.local.sh
#     # edit env.local.sh
#     source ./env.local.sh        # before running StateFork
#
# env.local.sh is gitignored. Every variable below is OPTIONAL: the Waypoint
# backend resolves its binaries from these env vars first, then from $PATH,
# then from a repo-root fallback (see controller/waypoint_env_manager.py), so
# you only need to set what differs from your layout.

# --- Waypoint backend ---

# Path to the `waypoint` binary. Unset -> looked up on $PATH, then ./waypoint.
# export WAYPOINT_BIN=/abs/path/to/waypoint

# Path to the `bash_init` helper. Unset -> $PATH, then ./bash_init.
# export WAYPOINT_BASH_INIT_SRC=/abs/path/to/bash_init

# Directory where Waypoint stores session state (OverlayFS upper + CRIU images).
# CHECKPOINT_SESSIONS_DIR is honored as an alias and feeds WAYPOINT_SESSIONS_DIR.
# export WAYPOINT_SESSIONS_DIR=/var/lib/statefork/sessions

# Keep session directories after cleanup. Default: true.
# export WAYPOINT_PRESERVE_SESSION_ON_CLEANUP=true
