#!/bin/bash
#
# AppRun entry point for the ScummVM AppImage.
#
# ScummVM looks for its bundled data files (themes, scummvm.dat, per engine
# data) in the current working directory, so we switch into the data directory
# before launching. Libraries bundled by linuxdeploy live in usr/lib.
#
HERE="$(dirname "$(readlink -f "${0}")")"

export LD_LIBRARY_PATH="${HERE}/usr/lib:${HERE}/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH}"

cd "${HERE}/usr/share/scummvm" 2>/dev/null || cd "${HERE}"

exec "${HERE}/usr/bin/scummvm" "$@"
