#!/usr/bin/env bash

# SPDX-FileCopyrightText: Copyright 2026 The Secureblue Authors
#
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

umask 022
cd "${0%/*}"
cd "$(git rev-parse --show-toplevel)"
mkdir -p sysext-tmp
find sysext-tmp -mindepth 1 -delete

if [[ "$(awk -F= '$1 == "ID" { print $2; exit }' /usr/lib/os-release)" != 'secureblue' ]]; then
    echo 'This script must be run on a secureblue system.' >&2
    exit 1
fi

image_name="$(awk -F= '$1 == "VARIANT_ID" { print $2; exit }' /usr/lib/os-release)"

echo 'Copying files to sysext-tmp...'

cp -a files/system/usr files/system/etc sysext-tmp

case "${image_name}" in
    cosmic-*) cp -a files/system/{cosmic,desktop}/* sysext-tmp ;;
    kinoite-*) cp -a files/system/{kinoite,desktop}/* sysext-tmp ;;
    sericea-*) cp -a files/system/{sericea,desktop}/* sysext-tmp ;;
    silverblue-*) cp -a files/system/{silverblue,desktop}/* sysext-tmp ;;
    iot-*|securecore-*) cp -a files/system/server/* sysext-tmp ;;
    *) echo "Unknown image name '${image_name}'" >&2; exit 1 ;;
esac

if [[ "${image_name}" == *-nvidia-* ]]; then
    cp -a files/system/nvidia/* sysext-tmp
fi

if [[ "${image_name}" == *-zfs-* ]]; then
    cp -a files/system/zfs/* sysext-tmp
fi

chmod -R u=rwX,go=rX sysext-tmp

echo 'Building sysext...'
tools/sysextbuddy --name secureblue-dev --output sysext-tmp/secureblue-dev.raw sysext-tmp
