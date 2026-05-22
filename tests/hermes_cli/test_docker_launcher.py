from argparse import Namespace
from hermes_cli import docker_launcher


def test_generate_container_name_is_stable_and_path_scoped(tmp_path):
    data_dir = tmp_path / "personal profile"
    first = docker_launcher.generate_container_name(data_dir)
    second = docker_launcher.generate_container_name(data_dir)
    other = docker_launcher.generate_container_name(tmp_path / "work")

    assert first == second
    assert first.startswith("hermes-personal-profile-")
    assert other != first


def test_gateway_dry_run_generates_name_and_dashboard_flags(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    data_dir = tmp_path / "hermes-data"
    expected_name = docker_launcher.generate_container_name(data_dir)

    code = docker_launcher.main(
        [
            "gateway",
            "--data-dir",
            str(data_dir),
            "--dry-run",
            "--dashboard",
            "--dashboard-tui",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert f"--name {expected_name}" in out
    assert f"{data_dir.resolve()}:/opt/data" in out
    assert "-p 8642:8642" in out
    assert "-p 9119:9119" in out
    assert "-e HERMES_DASHBOARD=1" in out
    assert "-e HERMES_DASHBOARD_TUI=1" in out
    assert "nousresearch/hermes-agent:latest gateway run" in out


def test_continue_dry_run_wraps_latest_session_resume(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        ["continue", "--data-dir", str(tmp_path / ".hermes"), "--dry-run"]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "--tui --continue" in out


def test_resume_dry_run_wraps_named_session(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        [
            "resume",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--dry-run",
            "Research Session",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "--tui --resume 'Research Session'" in out


def test_command_main_supports_hermes_docker_subcommand(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.command_main(
        Namespace(
            docker_args=[
                "chat",
                "--data-dir",
                str(tmp_path / ".hermes"),
                "--dry-run",
                "--",
                "--model",
                "gpt-test",
            ]
        )
    )

    out = capsys.readouterr().out
    assert code == 0
    assert " -- --model" not in out
    assert "--tui --model gpt-test" in out
