#!/bin/bash
# Build OTA update bundle for Capacitor Updater
# Usage: ./scripts/build-update.sh [version]

set -e

VERSION=${1:-$(node -p "require('./package.json').version")}
BUILD_DIR="dist"
UPDATE_DIR="updates"
ZIP_NAME="bundle-${VERSION}.zip"

echo "=== Building OTA Update Bundle v${VERSION} ==="

# Clean and create dirs
rm -rf "$BUILD_DIR" "$UPDATE_DIR"
mkdir -p "$BUILD_DIR" "$UPDATE_DIR"

# Copy web assets
cp index.html "$BUILD_DIR/"
cp data.json "$BUILD_DIR/" 2>/dev/null || true
cp manifest.json "$BUILD_DIR/" 2>/dev/null || true
cp sw.js "$BUILD_DIR/" 2>/dev/null || true
cp -r icon-*.png "$BUILD_DIR/" 2>/dev/null || true

# Create zip bundle
cd "$BUILD_DIR"
zip -r "../$UPDATE_DIR/$ZIP_NAME" .
cd ..

# Generate checksum
CHECKSUM=$(sha256sum "$UPDATE_DIR/$ZIP_NAME" | awk '{print $1}')

# Create updates.json
cat > "$UPDATE_DIR/updates.json" << EOF
{
  "version": "${VERSION}",
  "url": "https://jivonkiang.github.io/alipay-portfolio-report/updates/${ZIP_NAME}",
  "checksum": "${CHECKSUM}",
  "message": "OTA update v${VERSION}"
}
EOF

echo "=== Build Complete ==="
echo "Bundle: $UPDATE_DIR/$ZIP_NAME"
echo "Checksum: $CHECKSUM"
echo "Update JSON: $UPDATE_DIR/updates.json"
