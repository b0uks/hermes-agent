from argparse import Namespace

import pytest

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
    assert "-e HERMES_INSTALL_METHOD=docker" in out
    assert "-e HERMES_TUI_DIR=/opt/hermes/ui-tui" in out
    assert "nousresearch/hermes-agent:latest gateway run" in out


def test_common_flags_add_extra_volumes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--dry-run",
            "-v",
            "/host/penny:/opt/penny",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "-v /host/penny:/opt/penny" in out


def test_gh_auth_mounts_host_gh_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    host_home = tmp_path / "home"
    gh_config = host_home / ".config" / "gh"
    gh_config.mkdir(parents=True)
    (gh_config / "hosts.yml").write_text("github.com:\n  user: test\n")
    monkeypatch.setenv("HOME", str(host_home))
    monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--gh-auth",
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert (
        f"-v {gh_config.resolve()}:{docker_launcher.GH_CONFIG_CONTAINER_DIR}:ro"
        in out
    )
    assert f"-e GH_CONFIG_DIR={docker_launcher.GH_CONFIG_CONTAINER_DIR}" in out


def test_gh_auth_forwards_host_token_without_printing_value(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GH_TOKEN", "ghp_super_secret")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--gh-auth",
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "-e GH_TOKEN" in out
    assert "ghp_super_secret" not in out


def test_gh_auth_errors_without_config_or_token(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GH_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc:
        docker_launcher.main(
            ["chat", "--data-dir", str(tmp_path / ".hermes"), "--gh-auth"]
        )

    err = capsys.readouterr().err
    assert exc.value.code == 1
    assert "--gh-auth requested" in err


def test_skills_dir_mounts_read_only_and_sets_external_dirs_env(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    skills_dir = tmp_path / "claude skills"
    skills_dir.mkdir()
    expected_container = (
        docker_launcher.EXTERNAL_SKILLS_ROOT
        + "/claude-skills-"
        + docker_launcher.hashlib.sha1(str(skills_dir.resolve()).encode("utf-8")).hexdigest()[:8]
    )

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--skills-dir",
            str(skills_dir),
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert f"-v '{skills_dir.resolve()}:{expected_container}:ro'" in out
    assert f"-e HERMES_EXTERNAL_SKILLS_DIRS={expected_container}" in out


def test_skills_dir_combines_with_user_external_dirs_env(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    expected_container = (
        docker_launcher.EXTERNAL_SKILLS_ROOT
        + "/skills-"
        + docker_launcher.hashlib.sha1(str(skills_dir.resolve()).encode("utf-8")).hexdigest()[:8]
    )

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--skills-dir",
            str(skills_dir),
            "-e",
            "HERMES_EXTERNAL_SKILLS_DIRS=/already/in/container",
            "--dry-run",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert (
        f"-e HERMES_EXTERNAL_SKILLS_DIRS={expected_container}:/already/in/container"
        in out
    )
    assert out.count("HERMES_EXTERNAL_SKILLS_DIRS") == 1


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
    assert "-e HERMES_INSTALL_METHOD=docker" in out
    assert "-e HERMES_TUI_DIR=/opt/hermes/ui-tui" in out
    assert "-e HERMES_SKIP_PROFILE_GATEWAY_RECONCILE=1" in out
    assert "--tui --model gpt-test" in out


def test_main_handles_keyboard_interrupt(monkeypatch, capsys):
    def raise_interrupt(args):
        raise KeyboardInterrupt

    parser = docker_launcher.build_parser()
    parsed = parser.parse_args(["status"])
    parsed.func = raise_interrupt
    monkeypatch.setattr(docker_launcher, "build_parser", lambda prog: parser)
    monkeypatch.setattr(parser, "parse_args", lambda argv: parsed)

    code = docker_launcher.main(["status"])

    err = capsys.readouterr().err
    assert code == 130
    assert "Interrupted." in err


def test_command_main_handles_keyboard_interrupt(monkeypatch, capsys):
    def raise_interrupt(args):
        raise KeyboardInterrupt

    parser = docker_launcher.build_parser()
    parsed = parser.parse_args(["status"])
    parsed.func = raise_interrupt
    monkeypatch.setattr(docker_launcher, "build_parser", lambda prog: parser)
    monkeypatch.setattr(parser, "parse_args", lambda argv: parsed)

    code = docker_launcher.command_main(Namespace(docker_args=["status"]))

    err = capsys.readouterr().err
    assert code == 130
    assert "Interrupted." in err


def test_gateway_does_not_skip_profile_gateway_reconcile(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        ["gateway", "--data-dir", str(tmp_path / ".hermes"), "--dry-run"]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "HERMES_SKIP_PROFILE_GATEWAY_RECONCILE" not in out


def test_gateway_existing_container_warns_gh_auth_is_create_only(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")
    monkeypatch.setattr(docker_launcher, "_container_exists", lambda name: True)
    monkeypatch.setattr(docker_launcher, "_container_running", lambda name: True)

    code = docker_launcher.main(
        ["gateway", "--data-dir", str(tmp_path / ".hermes"), "--gh-auth"]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "container running" in out
    assert "--gh-auth only applies when creating a container" in out


def test_user_env_can_override_tui_dir(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--dry-run",
            "-e",
            "HERMES_TUI_DIR=/custom/tui",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "-e HERMES_TUI_DIR=/custom/tui" in out
    assert "-e HERMES_TUI_DIR=/opt/hermes/ui-tui" not in out


def test_user_env_can_override_install_method(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(docker_launcher.shutil, "which", lambda name: "docker")

    code = docker_launcher.main(
        [
            "chat",
            "--data-dir",
            str(tmp_path / ".hermes"),
            "--dry-run",
            "-e",
            "HERMES_INSTALL_METHOD=custom",
        ]
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "-e HERMES_INSTALL_METHOD=custom" in out
    assert "-e HERMES_INSTALL_METHOD=docker" not in out
