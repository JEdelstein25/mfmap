#!/bin/sh
# Regenerate SAMPLE.json with the fork's jar. Absolute paths are replaced by /FIXTURE so the
# fixture does not depend on where the repository is checked out.
# Usage: MFMAP_JAR=/path/to/server.jar sh regenerate.sh
set -eu
cd "$(dirname "$0")"
dir=$(pwd)
java -jar "${MFMAP_JAR:?set MFMAP_JAR to server.jar}" analysis -s "$dir/SAMPLE.cbl" -cf "$dir/cpy" --graph \
  | sed "s|$dir|/FIXTURE|g" > SAMPLE.json
