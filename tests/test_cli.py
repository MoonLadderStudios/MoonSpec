from moonspec_cli import main


def test_cli_prints_bundle_path(capsys) -> None:
    assert main(["bundle-path"]) == 0
    assert "bundle" in capsys.readouterr().out
