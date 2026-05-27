#!/bin/sh
# /opt/hermes/docker/main-wrapper.sh — wraps the container's CMD with
# the same argument-routing logic the pre-s6 entrypoint.sh used. Runs
# as /init's "main program" (Docker CMD) so it inherits stdin/stdout/
# stderr from the container.
#
# Routing:
#   no args                       → exec `hermes` (the default)
#   first arg is an executable    → exec it directly (sleep, bash, sh, …)
#   first arg is anything else    → exec `hermes <args>` (subcommand passthrough)
#
# We drop to the hermes user via `s6-setuidgid` so the supervised
# workload runs unprivileged (UID 10000 by default).
set -e

if [ -d /command ]; then
    export PATH="/command:$PATH"
fi

# s6-overlay runs the Docker CMD as the "main program" through rc.init, which
# does not reliably preserve Docker's container env for this wrapper. Rehydrate
# it here so gateway/CLI processes see HERMES_HOME, mounted skills, and other
# launcher-provided settings before we drop privileges.
if [ -d /run/s6/container_environment ]; then
    for env_file in /run/s6/container_environment/*; do
        [ -f "$env_file" ] || continue
        env_name="${env_file##*/}"
        case "$env_name" in
            ""|[0-9]*|*[!A-Za-z0-9_]*)
                continue
                ;;
        esac
        env_value="$(cat "$env_file")"
        export "$env_name=$env_value"
    done
fi

export HERMES_HOME="${HERMES_HOME:-/opt/data}"

cd /opt/data
# shellcheck disable=SC1091
. /opt/hermes/.venv/bin/activate

# Keep third-party CLI auth/config inside the persistent Hermes volume instead
# of the image user's ephemeral home. This makes gh, gcloud, aws, and jira
# usable across container restarts without mounting extra dot-directories.
export HOME="${HERMES_HOME:-/opt/data}/home"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export AWS_CONFIG_FILE="${AWS_CONFIG_FILE:-$XDG_CONFIG_HOME/aws/config}"
export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$XDG_CONFIG_HOME/aws/credentials}"
export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-$XDG_CONFIG_HOME/gcloud}"
export JIRA_CONFIG_FILE="${JIRA_CONFIG_FILE:-$XDG_CONFIG_HOME/.jira/.config.yml}"

if [ $# -eq 0 ]; then
    exec s6-setuidgid hermes hermes
fi

if command -v "$1" >/dev/null 2>&1; then
    # Bare executable — pass through directly.
    exec s6-setuidgid hermes "$@"
fi

# Hermes subcommand pass-through.
exec s6-setuidgid hermes hermes "$@"
