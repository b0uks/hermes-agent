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


def test_dockerfile_uses_prebuilt_tui_bundle_at_runtime() -> None:
    dockerfile = Path("Dockerfile").read_text()

    assert "ENV HERMES_TUI_DIR=/opt/hermes/ui-tui" in dockerfile


def test_dockerfile_marks_install_method() -> None:
    dockerfile = Path("Dockerfile").read_text()

    assert "ENV HERMES_INSTALL_METHOD=docker" in dockerfile


def test_runtime_persists_cli_config_in_hermes_home() -> None:
    main_wrapper = Path("docker/main-wrapper.sh").read_text()
    dashboard_run = Path("docker/s6-rc.d/dashboard/run").read_text()

    for expected in (
        'export HOME="${HERMES_HOME:-/opt/data}/home"',
        'export AWS_CONFIG_FILE="${AWS_CONFIG_FILE:-$XDG_CONFIG_HOME/aws/config}"',
        'export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$XDG_CONFIG_HOME/aws/credentials}"',
        'export CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-$XDG_CONFIG_HOME/gcloud}"',
        'export JIRA_CONFIG_FILE="${JIRA_CONFIG_FILE:-$XDG_CONFIG_HOME/.jira/.config.yml}"',
    ):
        assert expected in main_wrapper
        assert expected in dashboard_run
