#!/bin/bash

VER="${1}"

if [ -z "${VER}" ]; then
  echo "Usage: ./build.sh <version> "
  exit 1
fi

rsync -avP dist/geppetto_automation-${VER}.tar.gz ~/rpmbuild/SOURCES
rsync -avP geppetto-automation.spec ~/rpmbuild/SPECS/
rpmbuild -bb ~/rpmbuild/SPECS/geppetto-automation.spec && rpm -Uvh --force ~/rpmbuild/RPMS/noarch/geppetto_automation-${VER}-1.amzn2023.noarch.rpm

