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
    ``repo_dir``. **Failures are logged but never raised**: a problem with the
    external database must not abort a StateFork snapshot/restore that already
    captured the file system. ``snapshot()`` / ``restore()`` return ``False`` on
    failure so the caller can log a notice, but the file-system operation is
    still reported as successful. If the ``dolt`` binary is missing, the
    controller quietly disables itself (``enabled`` is False) and every
    operation no-ops.
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
        self._identity_name, self._identity_email = self._parse_author(author)
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
            # `dolt init` builds the first commit, so it needs an identity up
            # front (it would otherwise read the global config, which may be
            # unset). Pass one explicitly via --name/--email.
            self._run([
                "init",
                "--name", self._identity_name,
                "--email", self._identity_email,
                "--initial-branch", self.working_branch,
            ])

        # Persist a local commit identity so subsequent commits don't depend on
        # global config. Only reachable once the repo exists.
        self._ensure_identity()

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

    @staticmethod
    def _failed(proc: Optional[subprocess.CompletedProcess]) -> bool:
        """True when a dolt command did not run or exited non-zero."""
        return proc is None or proc.returncode != 0

    @staticmethod
    def _parse_author(author: str) -> tuple[str, str]:
        """Split a ``"Name <email>"`` author string into (name, email)."""
        name, _, rest = author.partition("<")
        name = name.strip() or "StateFork"
        email = rest.rstrip(">").strip() or "statefork@local"
        return name, email

    def _run(self,
             args: List[str],
             log_fail: bool = True) -> Optional[subprocess.CompletedProcess]:
        """
        Run a dolt subcommand in the repo directory. Never raises. Logs an error
        on a non-zero exit unless ``log_fail`` is False (used for probes whose
        failure is expected, e.g. ``branch --list`` / ``config --get``).

        :return: the CompletedProcess, or None if dolt is unavailable / the call
            raised before producing a result.
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
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"dolt {' '.join(args)} raised: {e}")
            return None

        if log_fail and proc.returncode != 0:
            logger.error(
                f"dolt {' '.join(args)} failed (rc={proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc

    def _ensure_identity(self) -> None:
        """Set a local commit identity if the repo doesn't already have one."""
        for key, value in (("user.name", self._identity_name),
                           ("user.email", self._identity_email)):
            got = self._run(["config", "--get", key], log_fail=False)
            if got is None or not (got.stdout or "").strip():
                self._run(["config", "--local", "--add", key, value])

    def snapshot(self, snapshot_id: str) -> bool:
        """
        Commit the current Dolt working set and point a snapshot branch at it.

        Mirrors a StateFork ``snapshot()``: live work stays on
        ``working_branch`` while ``<branch_prefix><snapshot_id>`` is created (or
        force-moved) to the freshly committed state.

        :return: True on success. False if dolt is disabled or a step failed
            (already logged); the caller still treats the file-system snapshot as
            successful.
        """
        if not self._available:
            return False

        branch = self.branch_name(snapshot_id)

        # Stage and commit everything. --allow-empty guarantees that every
        # StateFork snapshot id maps to a Dolt commit, even with no data change.
        self._run(["add", "-A"])
        commit = self._run(
            ["commit", "--allow-empty", "--author", self.author,
             "-m", f"StateFork snapshot {snapshot_id}"]
        )

        # Create or force-move the per-snapshot branch pointer at HEAD.
        branched = self._run(["branch", "-f", branch, "HEAD"])

        if self._failed(commit) or self._failed(branched):
            logger.error(
                f"Dolt snapshot for '{snapshot_id}' did not complete; "
                f"database left unversioned for this id."
            )
            return False

        self._branches.add(branch)
        logger.info(f"Dolt snapshot recorded on branch '{branch}'")
        return True

    def restore(self, snapshot_id: str) -> bool:
        """
        Reset the working branch back to the snapshot branch for ``snapshot_id``.

        Mirrors a StateFork ``restore()``: the database follows the file system
        back to the captured state.

        :return: True on success. False if dolt is disabled, the snapshot branch
            does not exist, or a step failed (already logged); the caller still
            treats the file-system restore as successful.
        """
        if not self._available:
            return False

        branch = self.branch_name(snapshot_id)

        # Verify the snapshot branch exists before touching the working branch.
        listing = self._run(["branch", "--list", branch], log_fail=False)
        if self._failed(listing) or branch not in (listing.stdout or ""):
            logger.error(f"Dolt snapshot branch '{branch}' not found; cannot restore.")
            return False

        # Work always happens on the working branch; reset it to the snapshot.
        checked_out = self._run(["checkout", self.working_branch])
        reset = self._run(["reset", "--hard", branch])

        if self._failed(checked_out) or self._failed(reset):
            logger.error(f"Dolt restore to '{branch}' did not complete.")
            return False

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
        self._run(["checkout", self.working_branch], log_fail=False)
        for branch in sorted(self._branches):
            self._run(["branch", "-D", branch], log_fail=False)
        self._branches.clear()
