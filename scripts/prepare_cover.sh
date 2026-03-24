#!/bin/bash
# prepare_cover.sh — Convert cover image to jpg for xelatex compatibility.
#
# YouTube often gives webp, Bilibili gives jpg. xelatex needs jpg/png.
#
# Usage: ./prepare_cover.sh [directory]
#   Finds cover.* in the directory and converts to cover.jpg

DIR="${1:-.}"

for ext in webp png avif; do
    if [ -f "$DIR/cover.$ext" ]; then
        echo "Converting cover.$ext -> cover.jpg"
        magick "$DIR/cover.$ext" "$DIR/cover.jpg" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo "Done: $DIR/cover.jpg"
            exit 0
        fi
    fi
done

if [ -f "$DIR/cover.jpg" ]; then
    echo "cover.jpg already exists"
    exit 0
fi

echo "No cover image found in $DIR" >&2
exit 1
