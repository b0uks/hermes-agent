from pathlib import Path


def test_entrypoint_chown_skips_nested_workspace_mounts() -> None:
    entrypoint = Path("docker/entrypoint.sh").read_text()

    assert "chown -R hermes:hermes \"$HERMES_HOME\"" not in entrypoint
    assert "chown_hermes_home" in entrypoint
    assert "chown hermes:hermes \"$HERMES_HOME/workspace\"" in entrypoint
    assert "chown -R hermes:hermes \"$HERMES_HOME/$target\"" in entrypoint
