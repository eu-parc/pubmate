import yaml
from click.testing import CliRunner

from pubmate.cli.yamlconcat import cli


def _run(args):
    return CliRunner().invoke(cli, args)


def test_yamlconcat_combines_targets(tmp_path) -> None:
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text("terms:\n  - name: Alpha\n", encoding="utf-8")
    b.write_text("terms:\n  - name: Beta\n", encoding="utf-8")
    out = tmp_path / "combined.yaml"

    result = _run([str(out), str(a), str(b), "--target", "terms"])

    assert result.exit_code == 0, result.output
    combined = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert [e["name"] for e in combined["terms"]] == ["Alpha", "Beta"]


def test_inherit_applies_file_default_to_entries_without_it(tmp_path) -> None:
    data = tmp_path / "file.yaml"
    data.write_text(
        (
            "suggester: https://orcid.org/0000-0002-1825-0097\n"
            "terms:\n"
            "  - name: Alpha\n"
            "  - name: Beta\n"
            "    suggester: https://orcid.org/0000-0001-5109-3700\n"
        ),
        encoding="utf-8",
    )
    out = tmp_path / "combined.yaml"

    result = _run([str(out), str(data), "--target", "terms", "--inherit", "suggester"])

    assert result.exit_code == 0, result.output
    combined = yaml.safe_load(out.read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in combined["terms"]}
    # Alpha inherits the file-level default; Beta keeps its own override.
    assert by_name["Alpha"]["suggester"] == "https://orcid.org/0000-0002-1825-0097"
    assert by_name["Beta"]["suggester"] == "https://orcid.org/0000-0001-5109-3700"
    # The file-level default is not leaked into the combined container.
    assert "suggester" not in combined


def test_inherit_default_does_not_cross_files(tmp_path) -> None:
    with_default = tmp_path / "a.yaml"
    without_default = tmp_path / "b.yaml"
    with_default.write_text(
        "suggester: https://orcid.org/0000-0002-1825-0097\nterms:\n  - name: Alpha\n",
        encoding="utf-8",
    )
    without_default.write_text("terms:\n  - name: Beta\n", encoding="utf-8")
    out = tmp_path / "combined.yaml"

    result = _run(
        [str(out), str(with_default), str(without_default), "--target", "terms", "--inherit", "suggester"]
    )

    assert result.exit_code == 0, result.output
    combined = yaml.safe_load(out.read_text(encoding="utf-8"))
    by_name = {e["name"]: e for e in combined["terms"]}
    assert by_name["Alpha"]["suggester"] == "https://orcid.org/0000-0002-1825-0097"
    # Beta's file had no default, so it must not pick up a.yaml's suggester.
    assert "suggester" not in by_name["Beta"]
