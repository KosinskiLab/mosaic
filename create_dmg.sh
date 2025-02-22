#!/bin/sh

mkdir -p dist/dmg
rm -r dist/dmg/*

cp -r "dist/mosaic.app" dist/dmg

test -f "dist/mosaic.dmg" && rm "dist/mosaic.dmg"
create-dmg \
  --volname "mosaic" \
  --volicon "src/mosaic/data/mosaic.icns" \
  --window-pos 200 120 \
  --window-size 600 300 \
  --icon-size 100 \
  --icon "mosaic.app" 175 120 \
  --hide-extension "mosaic.app" \
  --app-drop-link 425 120 \
  "dist/mosaic.dmg" \
  "dist/dmg/"