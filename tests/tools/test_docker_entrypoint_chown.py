from pathlib import Path


def test_stage2_chown_skips_nested_workspace_mounts() -> None:
    stage2 = Path("docker/stage2-hook.sh").read_text()

    assert "chown -R hermes:hermes \"$HERMES_HOME\"" not in stage2
    assert "chown_hermes_home" in stage2
    assert "chown hermes:hermes \"$HERMES_HOME/workspace\"" in stage2
    assert "chown -R hermes:hermes \"$HERMES_HOME/$target\"" in stage2
