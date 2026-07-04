#!/usr/bin/env bash
#
# Build a self-contained x86_64 AppImage of this ScummVM fork.
#
# Intended for the gamepad/touch friendly Stark (The Longest Journey) build, to
# be run on handheld Linux systems such as the ROG Ally / Steam Deck under
# Bazzite. Runs on any x86_64 glibc Linux with the ScummVM build dependencies
# installed (see .github/workflows/appimage.yml for the exact package list).
#
# Usage:
#   dists/bazzite/build-appimage.sh
#
# Environment variables:
#   JOBS             parallel build jobs (default: nproc)
#   OUTPUT_DIR       where to drop the .AppImage (default: repo root)
#   APPIMAGE_TAG     label baked into the file name (default: git describe)
#   CONFIGURE_EXTRA  extra flags passed to ./configure
#   RECONFIGURE=1    force ./configure even if config.mk exists
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ARCH="x86_64"
JOBS="${JOBS:-$(nproc)}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}}"
APPIMAGE_TAG="${APPIMAGE_TAG:-$(git -C "${ROOT_DIR}" describe --tags --always --dirty 2>/dev/null || echo dev)}"

WORK="${ROOT_DIR}/appimage-work"
APPDIR="${WORK}/AppDir"
TOOLS="${WORK}/tools"

echo ">> Cleaning work directory ${WORK}"
rm -rf "${WORK}"
mkdir -p "${APPDIR}" "${TOOLS}"

# ---------------------------------------------------------------------------
# 1. Prebuilt AppImage tooling (no need to compile it on x86_64)
# ---------------------------------------------------------------------------
echo ">> Fetching AppImage tooling"
fetch() { wget -q -O "$2" "$1"; chmod +x "$2"; }
fetch "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-${ARCH}.AppImage" \
      "${TOOLS}/linuxdeploy"
fetch "https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-${ARCH}.AppImage" \
      "${TOOLS}/linuxdeploy-plugin-appimage"
export PATH="${TOOLS}:${PATH}"

# Let the AppImage tools run on CI runners / containers without FUSE
export APPIMAGE_EXTRACT_AND_RUN=1

# ---------------------------------------------------------------------------
# 2. Configure and build ScummVM
# ---------------------------------------------------------------------------
cd "${ROOT_DIR}"
if [ ! -f config.mk ] || [ "${RECONFIGURE:-0}" = "1" ]; then
	echo ">> Configuring"
	./configure \
		--enable-release \
		--disable-debug \
		--prefix=/usr \
		${CONFIGURE_EXTRA:-}
fi

echo ">> Building with ${JOBS} jobs"
make -j"${JOBS}"
strip scummvm || true

# ---------------------------------------------------------------------------
# 3. Install into the AppDir (usr/bin/scummvm, usr/share/scummvm/...)
# ---------------------------------------------------------------------------
echo ">> Installing into AppDir"
make install DESTDIR="${APPDIR}"

# Desktop entry and icon, named to match each other for linuxdeploy
install -Dm644 "${ROOT_DIR}/dists/org.scummvm.scummvm.desktop" \
	"${APPDIR}/usr/share/applications/org.scummvm.scummvm.desktop"
install -Dm644 "${ROOT_DIR}/dists/android/store/scummvm_icon_512.png" \
	"${APPDIR}/usr/share/icons/hicolor/512x512/apps/org.scummvm.scummvm.png"

# Custom AppRun: switch to the data dir before launching (see AppRun.sh)
install -Dm755 "${SCRIPT_DIR}/AppRun.sh" "${APPDIR}/AppRun"

# ---------------------------------------------------------------------------
# 4. Bundle dependencies and produce the AppImage
# ---------------------------------------------------------------------------
OUTPUT="ScummVM-TLJ-Gamepad-${APPIMAGE_TAG}-${ARCH}.AppImage"
export OUTPUT

echo ">> Building AppImage ${OUTPUT}"
linuxdeploy \
	--appdir "${APPDIR}" \
	--executable "${APPDIR}/usr/bin/scummvm" \
	--custom-apprun "${APPDIR}/AppRun" \
	--desktop-file "${APPDIR}/usr/share/applications/org.scummvm.scummvm.desktop" \
	--icon-file "${APPDIR}/usr/share/icons/hicolor/512x512/apps/org.scummvm.scummvm.png" \
	--output appimage

mkdir -p "${OUTPUT_DIR}"
mv "${WORK}/${OUTPUT}" "${OUTPUT_DIR}/" 2>/dev/null || mv "${ROOT_DIR}/${OUTPUT}" "${OUTPUT_DIR}/"

echo ">> Done: ${OUTPUT_DIR}/${OUTPUT}"
