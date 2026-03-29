#!/bin/bash
# Master build script for Linux (.deb, .rpm, .AppImage)
# Requirements: PyInstaller, dpkg-deb, rpmbuild, wget

set -e

APP_NAME="DraggyEncoder"
VERSION="1"
DIST_DIR="dist/DraggyEncoder"
ICON_PATH="res/pyEncoder.png"
DESKTOP_FILE="DraggyEncoder.desktop"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTERNAL_OUTPUT="$REPO_ROOT/DRAGGY_RELEASES"

echo "--- Starting Linux Build (v$VERSION) ---"
echo "Output Directory: $EXTERNAL_OUTPUT"

mkdir -p "$EXTERNAL_OUTPUT"
cd "$REPO_ROOT"

# 1. Skip pip install in script (handled by CI/shell)
echo "1. Checking environment (PyInstaller)..."
if ! python3 -m PyInstaller --version >/dev/null 2>&1; then
    echo "Error: PyInstaller not found. Please run 'pip install pyinstaller' first."
    exit 1
fi

# 2. Run PyInstaller
echo "2. Running PyInstaller via python3 -m..."
rm -rf dist build
python3 -m PyInstaller --clean draggy_encoder.spec

if [ ! -d "$DIST_DIR" ]; then
    echo "Error: PyInstaller failed."
    exit 1
fi

# 3. Build AppImage (using existing script)
echo "3. Building AppImage..."
if [ -f "./build_appimage.sh" ]; then
    chmod +x ./build_appimage.sh
    ./build_appimage.sh "$VERSION"
else
    echo "Warning: build_appimage.sh not found."
fi

# 4. Build .DEB (Debian/Ubuntu)
echo "4. Building .DEB package..."
if command -v dpkg-deb >/dev/null 2>&1; then
    DEB_DIR="deb_root"
    rm -rf "$DEB_DIR"
    mkdir -p "$DEB_DIR/usr/bin"
    mkdir -p "$DEB_DIR/usr/share/applications"
    mkdir -p "$DEB_DIR/usr/share/icons/hicolor/256x256/apps"
    mkdir -p "$DEB_DIR/DEBIAN"

    # Copy files
    cp -r "$DIST_DIR"/* "$DEB_DIR/usr/bin/"
    cp "$DESKTOP_FILE" "$DEB_DIR/usr/share/applications/"
    cp "$ICON_PATH" "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/DraggyEncoder.png"

    # Create control file
    cat << 'EOF' > "$DEB_DIR/DEBIAN/control"
Package: draggy-encoder
Version: 1.0.0
Section: video
Priority: optional
Architecture: amd64
Maintainer: thedevil4k <https://github.com/thedevil4k>
Description: Powerful and sleek video compressor (FFmpeg frontend).
 Multi-format support with hardware acceleration.
EOF
    
    dpkg-deb --build "$DEB_DIR" "${APP_NAME}-${VERSION}-x86_64.deb"
    rm -rf "$DEB_DIR"
    echo "Done: .deb package created."
else
    echo "Skipping .deb build: dpkg-deb not found."
fi

# 5. Build .RPM (Fedora/RHEL)
echo "5. Building .RPM package..."
if command -v rpmbuild >/dev/null 2>&1; then
    RPM_ROOT="$HOME/rpmbuild"
    mkdir -p "$RPM_ROOT"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    
    # Create SPEC file
    cat << EOF > "$APP_NAME.spec"
Name:           draggy-encoder
Version:        1.0.0
Release:        1%{?dist}
Summary:        Powerful and sleek video compressor
License:        MIT
URL:            https://github.com/thedevil4k/THE-DRAGGY-ENCODER
Requires:       ffmpeg

%description
Sleek and high-performance video compressor designed for enthusiasts.

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/256x256/apps
cp -r $(pwd)/$DIST_DIR/* %{buildroot}/usr/bin/
cp $(pwd)/$DESKTOP_FILE %{buildroot}/usr/share/applications/
cp $(pwd)/$ICON_PATH %{buildroot}/usr/share/icons/hicolor/256x256/apps/DraggyEncoder.png

%files
/usr/bin/*
/usr/share/applications/DraggyEncoder.desktop
/usr/share/icons/hicolor/256x256/apps/DraggyEncoder.png

%changelog
* Sun Mar 29 2026 thedevil4k - 1.0.0-1
- Initial release
EOF

    rpmbuild -bb "$APP_NAME.spec" --define "_topdir $RPM_ROOT"
    cp "$RPM_ROOT"/RPMS/x86_64/*.rpm .
    echo "Done: .rpm package created."
else
    echo "Skipping .rpm build: rpmbuild not found."
fi

echo "--- All Build processes complete! ---"

# Move all generated packages to external output
mv *.AppImage *.deb *.rpm "$EXTERNAL_OUTPUT/" 2>/dev/null || true

echo "Final files in $EXTERNAL_OUTPUT:"
ls -lh "$EXTERNAL_OUTPUT"
