#!/usr/bin/python3

# SPDX-FileCopyrightText: Copyright 2026 The Secureblue Authors
#
# SPDX-License-Identifier: Apache-2.0

"""Update system (with provenance verification)."""

import enum
import subprocess
import sys
from pathlib import Path
from typing import assert_never

from verify_provenance import (
    ImageRef,
    ProvenanceVerificationError,
    ProvenanceVerificationResult,
    verify_update_image_provenance,
)


def security_update_notification() -> None:
    """Run security update notification (if appropriate) as a detached process."""
    if Path("/usr/libexec/secureblue/security-update-notification").is_file():
        subprocess.Popen(
            ["/usr/libexec/secureblue/security-update-notification"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


class BootcCheckResult(enum.Enum):
    """The result of running `bootc upgrade --check`."""

    NO_CHANGES = enum.auto()
    UPDATE_AVAILABLE = enum.auto()
    LOCAL_MODIFICATIONS = enum.auto()
    FAILED = enum.auto()


def bootc_check() -> BootcCheckResult:
    """Check for updates via bootc."""
    result = subprocess.run(
        ["/usr/bin/bootc", "upgrade", "--check"],
        stderr=sys.stdout,
        check=False,
        capture_output=True,
        text=True,
    )
    if "failed to invoke method OpenImage" in result.stdout:
        return BootcCheckResult.FAILED
    if "local rpm-ostree modifications" in result.stdout:
        return BootcCheckResult.LOCAL_MODIFICATIONS
    if "No changes" in result.stdout:
        return BootcCheckResult.NO_CHANGES
    return BootcCheckResult.UPDATE_AVAILABLE


def bootc_upgrade(verified_ref: ImageRef, *, progress_fd: int | None = None) -> None:
    """Update to the verified ref using bootc."""
    progress_fd_args = [] if progress_fd is None else ["--progress-fd", str(progress_fd)]
    subprocess.run(
        [
            "/usr/bin/bootc",
            "switch",
            "--enforce-container-sigpolicy",
            *progress_fd_args,
            "--",
            str(verified_ref),
        ],
        check=True,
    )


def rpm_ostree_upgrade(verified_ref: ImageRef) -> None:
    """Update to the verified ref using rpm-ostree."""
    if verified_ref.digest is None:
        raise ValueError("Verified image reference must have a digest")
    subprocess.run(
        ["/usr/bin/rpm-ostree", "deploy", "--disallow-downgrade", "--", verified_ref.digest],
        check=True,
    )


def do_upgrade(prov_result: ProvenanceVerificationResult, *, progress_fd: int | None = None) -> int:
    """Do the update with either bootc or rpm-ostree."""
    try:
        match bootc_check():
            case BootcCheckResult.NO_CHANGES:
                print("No update available.")
                return 0
            case BootcCheckResult.FAILED:
                print("Error: Checking for update failed.", file=sys.stderr)
                return 1
            case BootcCheckResult.UPDATE_AVAILABLE:
                bootc_upgrade(prov_result.verified_ref, progress_fd=progress_fd)
            case BootcCheckResult.LOCAL_MODIFICATIONS:
                rpm_ostree_upgrade(prov_result.verified_ref)
            case _ as unreachable:
                assert_never(unreachable)
    except subprocess.CalledProcessError:
        return 1
    return 0


def main() -> int:
    progress_fd = int(sys.argv[2]) if sys.argv[1] == "--progress-fd" else None
    try:
        prov_result = verify_update_image_provenance()
    except ProvenanceVerificationError as err:
        print(err, file=sys.stderr)
        return 1
    exit_status = do_upgrade(prov_result, progress_fd=progress_fd)
    if exit_status == 0:
        security_update_notification()
    return exit_status


if __name__ == "__main__":
    sys.exit(main())
