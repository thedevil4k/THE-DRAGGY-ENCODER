#!/bin/bash
set -e

APP_NAME="DraggyEncoder"
VERSION="${1:-rolling}"
ICON_PATH="res/pyEncoder.png"
DESKTOP_PATH="DraggyEncoder.desktop"
DIST_DIR="dist/DraggyEncoder"

# Create AppDir structure
mkdir -p AppDir/usr/bin
mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps
mkdir -p AppDir/usr/share/applications

# Copy PyInstaller bundle to AppDir
cp -r "$DIST_DIR"/* AppDir/usr/bin/

# Copy assets
cp "$ICON_PATH" AppDir/pyEncoder.png
cp "$DESKTOP_PATH" AppDir/DraggyEncoder.desktop

# Create AppRun
cat << 'EOF' > AppDir/AppRun
#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/DraggyEncoder" "$@"
EOF
chmod +x AppDir/AppRun

# Download appimagetool if not present
if [ ! -f ./appimagetool ]; then
    wget -q https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage -O appimagetool
    chmod +x appimagetool
fi

# Build AppImage
# Handle environments without FUSE (like many CI runners)
if ! ./appimagetool --version >/dev/null 2>&1; then
    echo "FUSE not available, extracting appimagetool..."
    ./appimagetool --appimage-extract
    ARCH=x86_64 ./squashfs-root/AppRun AppDir "${APP_NAME}-${VERSION}-x86_64.AppImage"
else
    ARCH=x86_64 ./appimagetool AppDir "${APP_NAME}-${VERSION}-x86_64.AppImage"
fi

# Clean up
rm -rf AppDir
