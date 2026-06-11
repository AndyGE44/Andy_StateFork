from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import List, Optional

logger = logging.getLogger("EnvManager.Dolt")


class DoltController:
    """
    Controls an *external* Dolt database alongside StateFork's system-file
    snapshots, using Dolt's own branching to version the database.

    The Dolt repository lives **outside** the StateFork shell: it is a plain
    directory on the host (initialised with ``dolt init``) that the managed
    application reads/writes directly. StateFork never proxies the database
    traffic; it only versions it. The mapping is:

    - On every StateFork ``snapshot(id)`` the current Dolt working set is
      committed and a branch named ``<branch_prefix><id>`` is pointed at that
      commit. Live work continues on ``working_branch``.
    - On every StateFork ``restore(id)`` the ``working_branch`` is reset hard to
      the matching snapshot branch, so the database state follows the
      file-system state back in time.

    All operations shell out to the ``dolt`` CLI with ``cwd`` set to
    ``repo_dir``. Failures are logged but never raised: a problem with the
    external database must not abort a StateFork snapshot/restore that already
    captured the file system. If the ``dolt`` binary is missing, the controller
    quietly disables itself (``enabled`` is False) and every operation no-ops.
    """

    def __init__(self,
                 repo_dir: str,
                 branch_prefix: str = "sf_",
                 working_branch: str = "main",
                 dolt_bin: str = "dolt",
                 author: str = "StateFork <statefork@local>",
                 init_if_missing: bool = True):
        """
        :param repo_dir: Path to the external Dolt repository directory.
        :param branch_prefix: Prefix for the per-snapshot branch names.
        :param working_branch: Branch where live work happens between snapshots.
        :param dolt_bin: Name/path of the dolt executable.
        :param author: Author string used for snapshot commits.
        :param init_if_missing: Run ``dolt init`` when ``repo_dir`` has no
            ``.dolt`` directory yet.
        """
        self.repo_dir = os.path.abspath(repo_dir)
        self.branch_prefix = branch_prefix
        self.working_branch = working_branch
        self.dolt_bin = dolt_bin
        self.author = author
        # snapshot branches created by this controller (for cleanup/inspection)
        self._branches: set[str] = set()

        self._available = shutil.which(dolt_bin) is not None
        if not self._available:
            logger.warning(
                f"`{dolt_bin}` not found on PATH; external Dolt control is disabled."
            )
            return

        os.makedirs(self.repo_dir, exist_ok=True)
        if init_if_missing and not os.path.isdir(os.path.join(self.repo_dir, ".dolt")):
            logger.info(f"Initializing new Dolt repository at {self.repo_dir}")
            self._run(["init"], check=False)

        # Make sure commits have an identity even on a fresh machine.
        self._run(["config", "--local", "--add", "user.name", "StateFork"], check=False)
        self._run(["config", "--local", "--add", "user.email", "statefork@local"], check=False)

        logger.info(
            f"External Dolt control enabled on {self.repo_dir} "
            f"(working branch '{self.working_branch}', branch prefix '{self.branch_prefix}')"
        )

    @property
    def enabled(self) -> bool:
        """True when the dolt binary is available and the controller is active."""
        return self._available

    def branch_name(self, snapshot_id: str) -> str:
        """Return the Dolt branch name used for a StateFork snapshot id."""
        return f"{self.branch_prefix}{snapshot_id}"

    def _run(self, args: List[str], check: bool = True) -> Optional[subprocess.CompletedProcess]:
        """
        Run a dolt subcommand in the repo directory. Returns the
        CompletedProcess, or None if dolt is unavailable / the call raised.
        """
        if not self._available:
            return None
        try:
            proc = subprocess.run(
                [self.dolt_bin, *args],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            if check and proc.returncode != 0:
                logger.error(
                    f"dolt {' '.join(args)} failed (rc={proc.returncode}): "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                )
            return proc
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"dolt {' '.join(args)} raised: {e}")
            return None

    def snapshot(self, snapshot_id: str) -> bool:
        """
        Commit the current Dolt working set and point a snapshot branch at it.

        Mirrors a StateFork ``snapshot()``: live work stays on
        ``working_branch`` while ``<branch_prefix><snapshot_id>`` is created (or
        force-moved) to the freshly committed state.

        :return: True if the snapshot branch was recorded, False if dolt is
            disabled.
        """
        if not self._available:
            return False

        branch = self.branch_name(snapshot_id)

        # Stage and commit everything. --allow-empty guarantees that every
        # StateFork snapshot id maps to a Dolt commit, even with no data change.
        self._run(["add", "-A"], check=False)
        self._run(
            ["commit", "--allow-empty", "--author", self.author,
             "-m", f"StateFork snapshot {snapshot_id}"],
            check=False,
        )

        # Create or force-move the per-snapshot branch pointer at HEAD.
        self._run(["branch", "-f", branch, "HEAD"], check=False)
        self._branches.add(branch)

        logger.info(f"Dolt snapshot recorded on branch '{branch}'")
        return True

    def restore(self, snapshot_id: str) -> bool:
        """
        Reset the working branch back to the snapshot branch for ``snapshot_id``.

        Mirrors a StateFork ``restore()``: the database follows the file system
        back to the captured state.

        :return: True if the restore was attempted, False if dolt is disabled or
            the snapshot branch does not exist.
        """
        if not self._available:
            return False

        branch = self.branch_name(snapshot_id)

        # Verify the snapshot branch exists before touching the working branch.
        proc = self._run(["branch", "--list", branch], check=False)
        if proc is None or branch not in (proc.stdout or ""):
            logger.error(f"Dolt snapshot branch '{branch}' not found; cannot restore.")
            return False

        # Work always happens on the working branch; reset it to the snapshot.
        self._run(["checkout", self.working_branch], check=False)
        self._run(["reset", "--hard", branch], check=False)

        logger.info(f"Dolt restored to snapshot branch '{branch}'")
        return True

    def cleanup(self) -> None:
        """
        Best-effort cleanup of the snapshot branches created in this session.

        The committed data and the working branch are left intact; only the
        ``<branch_prefix>*`` pointers this controller created are removed so the
        repository is not littered with stale snapshot branches.
        """
        if not self._available:
            return
        # Make sure we are not standing on a branch we are about to delete.
        self._run(["checkout", self.working_branch], check=False)
        for branch in sorted(self._branches):
            self._run(["branch", "-D", branch], check=False)
        self._branches.clear()
