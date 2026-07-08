#!/usr/bin/python3

# SPDX-FileCopyrightText: Copyright 2026 The Secureblue Authors
#
# SPDX-License-Identifier: Apache-2.0

"""Verify build provenance of latest available update for current image."""

import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Final

SOURCE_URI: Final[str] = "github.com/secureblue/secureblue"
IMAGE_REGISTRY: Final[str] = "ghcr.io"
IMAGE_REPOSITORY: Final[str] = "secureblue"


@dataclass(kw_only=True)
class ImageRef:
    """A remote container image reference."""

    registry: str
    repository: str | None
    image_name: str
    tag: str | None = None
    digest: str | None = None

    def __str__(self) -> str:
        ref_str = f"{self.registry}/{self.repository}/{self.image_name}"
        if self.tag:
            ref_str += f":{self.tag}"
        if self.digest:
            ref_str += f"@{self.digest}"
        return ref_str

    @classmethod
    def from_str(cls, ref_str: str) -> "ImageRef":
        """Parse image reference from string"""
        if "/" in ref_str:
            registry, _, remainder = ref_str.partition("/")
        else:
            registry = "localhost"
            remainder = ref_str

        if "/" in remainder:
            repository, _, image_component = remainder.rpartition("/")
        else:
            repository = None
            image_component = remainder

        if "@" in image_component:
            image_name_with_tag, _, digest = image_component.rpartition("@")
        else:
            image_name_with_tag = image_component
            digest = None

        if ":" in image_name_with_tag:
            image_name, _, tag = image_name_with_tag.rpartition(":")
        else:
            image_name = image_name_with_tag
            tag = None

        return cls(
            registry=registry,
            repository=repository,
            image_name=image_name,
            tag=tag,
            digest=digest,
        )


class ProvenanceVerificationError(RuntimeError):
    """Runtime error while attempting to verify update provenance."""


def booted_image_ref() -> ImageRef:
    """Get image reference for currently booted image."""
    image_ref_json = subprocess.run(
        [
            "/usr/bin/rpm-ostree",
            "status",
            "--booted",
            "--jsonpath",
            ".deployments[0].container-image-reference",
        ],
        capture_output=True,
        check=True,
    ).stdout
    ref_str = json.loads(image_ref_json)[0].split(":", maxsplit=1)[1].removeprefix("docker://")
    return ImageRef.from_str(ref_str)


def get_branch_name(image_ref: ImageRef) -> str:
    """Get the branch name associated with the given image reference."""
    tag = image_ref.tag
    if tag is None:
        raise ProvenanceVerificationError("WARNING: Missing image tag; unable to check provenance.")
    if tag == "latest":
        return "live"
    if tag.startswith("br-"):
        return tag.removeprefix("br-").rsplit("-", maxsplit=1)[0]
    raise ProvenanceVerificationError(
        f"WARNING: Unknown image tag '{tag}'; unable to check provenance."
    )


def get_latest_digest_for_ref(image_ref: ImageRef) -> str:
    """Use crane to get the digest of the latest image associated with the reference."""
    # If image_ref is pinned to a digest, remove that digest
    image_ref.digest = None
    try:
        result = subprocess.run(
            ["/usr/bin/crane", "digest", "--full-ref", str(image_ref)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as err:
        raise ProvenanceVerificationError("Failed to get image digest") from err

    return result.stdout.strip()


def verify_provenance(*, full_ref: str, source_uri: str, source_branch: str) -> tuple[bool, str]:
    """Run slsa-verifier, returning a tuple of whether verification succeeded and the output."""
    result = subprocess.run(
        [
            "/usr/bin/slsa-verifier",
            "verify-image",
            "--source-uri",
            source_uri,
            "--source-branch",
            source_branch,
            "--",
            full_ref,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return (result.returncode == 0, result.stdout)


@dataclass(kw_only=True)
class ProvenanceVerificationResult:
    """Result of SLSA provenance verification."""

    booted_ref: ImageRef
    verified_ref: ImageRef
    source_uri: str
    source_branch: str


def verify_update_image_provenance() -> ProvenanceVerificationResult:
    """
    Verify provenance for the image that an update would pull.
    Raises `ProvenanceVerificationError` if provenance verification fails.
    """
    booted_ref = booted_image_ref()
    if booted_ref.registry != IMAGE_REGISTRY or booted_ref.repository != IMAGE_REPOSITORY:
        raise ProvenanceVerificationError(
            f"WARNING: Unknown image reference '{booted_ref}'; unable to check provenance."
        )
    print(f"Verifying build provenance for {booted_ref}...")
    branch = get_branch_name(booted_ref)
    print(f"Source: {SOURCE_URI}:{branch}")
    update_ref = get_latest_digest_for_ref(booted_ref)
    print(f"Image reference: {update_ref}")
    success, output = verify_provenance(
        full_ref=update_ref, source_uri=SOURCE_URI, source_branch=branch
    )
    print(output)
    if not success:
        raise ProvenanceVerificationError(
            f"Provenance verification failed for image reference '{update_ref}'"
        )
    verified_ref = ImageRef.from_str(update_ref)
    verified_ref.tag = booted_ref.tag
    return ProvenanceVerificationResult(
        booted_ref=booted_ref,
        verified_ref=verified_ref,
        source_uri=SOURCE_URI,
        source_branch=branch,
    )


def main() -> int:
    """Main entry point when executed as a script."""
    try:
        verify_update_image_provenance()
    except ProvenanceVerificationError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
