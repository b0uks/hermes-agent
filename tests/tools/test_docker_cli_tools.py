from pathlib import Path


def test_dockerfile_bundles_operator_cli_tools() -> None:
    dockerfile = Path("Dockerfile").read_text()

    for expected in (
        "gh google-cloud-cli",
        "awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip",
        "ankitpokhrel/jira-cli/releases/download",
        "/usr/local/bin/jira",
    ):
        assert expected in dockerfile


def test_entrypoint_persists_cli_config_in_hermes_home() -> None:
    entrypoint = Path("docker/entrypoint.sh").read_text()

    for expected in (
        'export HOME="$HERMES_HOME/home"',
        'export AWS_CONFIG_FILE="${AWS_CONFIG_FILE:-$XDG_CONFIG_HOME/aws/config}"',
        'export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$XDG_CONFIG_HOME/aws/credentials}"',
        'export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-$XDG_CONFIG_HOME/gcloud}"',
        'export JIRA_CONFIG_FILE="${JIRA_CONFIG_FILE:-$XDG_CONFIG_HOME/.jira/.config.yml}"',
    ):
        assert expected in entrypoint
