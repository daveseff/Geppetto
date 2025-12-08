#!/bin/bash

PAYLOAD=payload
rm -rf "$PAYLOAD"
mkdir -p "$PAYLOAD/usr"
mkdir -p "$PAYLOAD/etc/forgeops"
pip install dist/forgeops_automation-0.1.0-py3-none-any.whl --prefix "$PAYLOAD/usr"

cp scripts/forgeops-auto "$PAYLOAD/usr/bin/"
chmod 755 "$PAYLOAD/usr/bin/forgeops-auto"

cp examples/base_plan.fops "$PAYLOAD/etc/forgeops/"