#!/usr/bin/env bash
# Install haiku-diff: symlink into /usr/local/bin

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="/usr/local/bin/haiku-diff"

if [ -L "$TARGET" ]; then
    echo "Updating symlink: $TARGET"
    sudo ln -sf "$SCRIPT_DIR/haiku-diff.py" "$TARGET"
else
    echo "Installing: $TARGET"
    sudo ln -s "$SCRIPT_DIR/haiku-diff.py" "$TARGET"
fi

sudo chmod +x "$SCRIPT_DIR/haiku-diff.py"
echo "Done. Try: haiku-diff --last"
