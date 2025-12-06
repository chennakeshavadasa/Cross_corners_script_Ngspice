import tempfile
from pathlib import Path
import pytest
from unittest.mock import MagicMock

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import classes from cross_corners.py
import cross_corners as cc


SIMPLE_TEMPLATE = """sch_path: /tmp/some_folder/case.sch
* TEMPLATE CONTENT
.model M1 NMOS
case_sim.raw
case_sim.csv
case_sim.txt
.include tt_model.spice
"""

def test_spice_template_processor_replaces_tokens(tmp_path):
    tp = cc.SpiceTemplateProcessor()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = tp.generate_content(SIMPLE_TEMPLATE, "case_sim", "ss_ll_mm", out_dir)

    assert "ss_ll_mm" in result

    raw_path = str(out_dir.joinpath("raw", "case_sim_ss_ll_mm.raw").resolve())
    assert raw_path in result


def test_folder_manager_creates_subfolders(tmp_path):
    fm = cc.FolderManager()
    root = tmp_path / "root"
    fm.create_all(root)
    for sub in fm.REQUIRED_SUBFOLDERS:
        assert (root / sub).exists() and (root / sub).is_dir()


def test_processor_runs_simulator_for_all_corners(tmp_path, monkeypatch):
    # Prepare template file
    template_path = tmp_path / "template.spice"
    template_path.write_text(SIMPLE_TEMPLATE.replace("/tmp/some_folder/case.sch", str((tmp_path / "case").resolve())))
    # Setup fake simulator that records calls
    called = []
    class FakeSim:
        def run(self, spice_file, log_file):
            called.append((str(spice_file), str(log_file)))
    corners = cc.StaticCornerProvider(["c1", "c2", "c3"])
    processor = cc.CrossCornerProcessor(
        corner_provider=corners,
        simulator=FakeSim(),
        template_processor=cc.SpiceTemplateProcessor(),
        folder_manager=cc.FolderManager(),
    )
    processor.run(template_path, output_dir_override=tmp_path / "out")
    # Expect 3 runs
    assert len(called) == 3
    # Check that spice files were created
    for corner in ["c1", "c2", "c3"]:
        spice = tmp_path / "out" / "spice" / f"template_{corner}.spice"
        assert spice.exists()


def test_cli_errors_on_missing_template(tmp_path, monkeypatch):
    # Provide a non-existent file
    rc = cc.cli([str(tmp_path / "nope.spice")])
    assert rc == 2
