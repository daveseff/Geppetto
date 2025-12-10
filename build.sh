#!/bin/bash

PAYLOAD=payload
rm -rf "$PAYLOAD"
mkdir -p "$PAYLOAD/usr" "$PAYLOAD/usr/bin" "$PAYLOAD/etc/geppetto"

wheel=$(ls -1t dist/geppetto_automation-*.whl 2>/dev/null | head -n1)
if [[ -z "$wheel" ]]; then
  echo "Unable to locate built geppetto_automation wheel in dist/" >&2
  exit 1
fi

pip install "$wheel" --prefix "$PAYLOAD/usr"

cp scripts/geppetto-auto "$PAYLOAD/usr/bin/"
chmod 755 "$PAYLOAD/usr/bin/geppetto-auto"

cp examples/base_plan.fops "$PAYLOAD/etc/geppetto/"
