#!/bin/sh
# Regenerate SAMPLE.json, DDL.jsonl, DLICALL.json and MQCALL.json with the fork's jar. Absolute paths are replaced by /FIXTURE so the
# fixture does not depend on where the repository is checked out.
# Usage: MFMAP_JAR=/path/to/server.jar sh regenerate.sh
set -eu
cd "$(dirname "$0")"
dir=$(pwd)
java -jar "${MFMAP_JAR:?set MFMAP_JAR to server.jar}" analysis -s "$dir/SAMPLE.cbl" -cf "$dir/cpy" --graph \
  | sed "s|$dir|/FIXTURE|g" > SAMPLE.json
# Tables, keys, indexes and views from the DDL files, as mfmap parse reads them.
java -jar "$MFMAP_JAR" ddl "$dir/ddl/PROCS.sql" "$dir/jcl/SAMPDDL.jcl" | sed "s|$dir|/FIXTURE|g" > DDL.jsonl
# DL/I calls through CALL 'CBLTDLI'.
java -jar "$MFMAP_JAR" analysis -s "$dir/DLICALL.cbl" --graph | sed "s|$dir|/FIXTURE|g" > DLICALL.json
# MQGET, MQPUT and MQPUT1 calls.
java -jar "$MFMAP_JAR" analysis -s "$dir/MQCALL.cbl" --graph | sed "s|$dir|/FIXTURE|g" > MQCALL.json
