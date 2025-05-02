#!/bin/bash
# wait-for-it.sh: Wait for services to be available before starting the application
# Adapted from https://github.com/vishnubob/wait-for-it

TIMEOUT=15
QUIET=0

echoerr() {
  if [[ $QUIET -ne 1 ]]; then echo "$@" 1>&2; fi
}

usage() {
  cat << USAGE >&2
Usage:
  $0 host:port [-t timeout] [-- command args]
  -t TIMEOUT  Timeout in seconds, zero for no timeout
  -q          Don't output any status messages
  -- COMMAND ARGS  Execute command with args after the test finishes
USAGE
  exit 1
}

wait_for() {
  for i in `seq $TIMEOUT` ; do
    nc -z "$HOST" "$PORT" > /dev/null 2>&1
    
    result=$?
    if [[ $result -eq 0 ]]; then
      if [[ $# -gt 0 ]]; then
        exec "$@"
      fi
      return 0
    fi
    sleep 1
  done
  echo "Operation timed out" >&2
  return 1
}

while [[ $# -gt 0 ]]
do
  case "$1" in
    *:* )
    HOST=$(printf "%s\n" "$1"| cut -d : -f 1)
    PORT=$(printf "%s\n" "$1"| cut -d : -f 2)
    shift 1
    ;;
    -t)
    TIMEOUT="$2"
    if [[ $TIMEOUT == "" ]]; then usage; fi
    shift 2
    ;;
    -q)
    QUIET=1
    shift 1
    ;;
    --)
    shift
    break
    ;;
    --help)
    usage
    ;;
    *)
    echoerr "Unknown argument: $1"
    usage
    ;;
  esac
done

if [[ $HOST == "" || $PORT == "" ]]; then
  echoerr "Error: you need to provide a host and port to test."
  usage
fi

wait_for "$@"