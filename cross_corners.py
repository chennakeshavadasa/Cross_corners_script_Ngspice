#!/usr/bin/env python3
"""
cross_corners.py

Object-oriented, dependency-injected NGSpice cross-corner runner with:
 - progress bar (tqdm)
 - colored logging (colorama)
 - typed interfaces
 - CLI via argparse
"""

from __future__ import annotations
import argparse
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol, Tuple, Optional
import sys

# Optional dependencies with graceful fallback
try:
    from tqdm import tqdm
except Exception:
    # simple fallback replacement for tqdm
    def tqdm(iterable=None, total=None, desc=None):
        if iterable is None:
            return []
        return iterable

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    _COLORAMA_AVAILABLE = True
except Exception:
    # fallback constants
    Fore = type("F", (), {"GREEN": "", "YELLOW": "", "RED": "", "BLUE": "", "MAGENTA": ""})()
    Style = type("S", (), {"BRIGHT": "", "RESET_ALL": ""})()
    _COLORAMA_AVAILABLE = False


# ----------------------
# Interfaces (Protocols)
# ----------------------
class CornerProvider(Protocol):
    def get_corners(self) -> List[str]: ...


class Simulator(Protocol):
    def run(self, spice_file: Path, log_file: Path) -> None: ...


class TemplateProcessor(Protocol):
    def generate_content(self, template: str, filename: str, corner: str, output_dir: Path) -> str: ...


# ----------------------
# Implementations
# ----------------------
@dataclass
class StaticCornerProvider:
    corners: List[str]

    def get_corners(self) -> List[str]:
        return self.corners


class NgSpiceSimulator:
    """Runs NGSpice in batch mode (subprocess)."""

    def __init__(self, ngspice_cmd: List[str] | None = None):
        self.ngspice_cmd = ngspice_cmd or ["ngspice", "-b"]

    def run(self, spice_file: Path, log_file: Path) -> None:
        # Ensure parent exists for log
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as f:
            logging.debug(f"Running simulator: {self.ngspice_cmd + [str(spice_file)]}")
            subprocess.run(self.ngspice_cmd + [str(spice_file)], stdout=f, stderr=f)


class SpiceTemplateProcessor:
    """Processes templates by replacing tokens/paths."""

    def generate_content(self, template: str, filename: str, corner: str, output_dir: Path) -> str:
        new_filename = f"{filename}_{corner}"
        data = template.replace("tt", corner)
        data = data.replace(filename, new_filename)

        replacements = {
            f"{new_filename}.raw": output_dir.joinpath("raw", f"{new_filename}.raw").resolve().as_posix(),
            f"{new_filename}.csv": output_dir.joinpath("csv", f"{new_filename}.csv").resolve().as_posix(),
            f"{new_filename}.txt": output_dir.joinpath("txt", f"{new_filename}.txt").resolve().as_posix(),
        }

        for old, new in replacements.items():
            data = data.replace(old, new)

        return data


class FolderManager:
    """Creates required subfolders in output directory."""
    REQUIRED_SUBFOLDERS = ["raw", "csv", "txt", "logs", "spice"]

    def create_all(self, root: Path) -> None:
        for folder in self.REQUIRED_SUBFOLDERS:
            p = root / folder
            p.mkdir(parents=True, exist_ok=True)
            logging.debug(f"Ensured directory exists: {p}")


# ----------------------
# Logging (colored)
# ----------------------
class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.MAGENTA if _COLORAMA_AVAILABLE else "",
        logging.INFO: Fore.GREEN if _COLORAMA_AVAILABLE else "",
        logging.WARNING: Fore.YELLOW if _COLORAMA_AVAILABLE else "",
        logging.ERROR: Fore.RED if _COLORAMA_AVAILABLE else "",
        logging.CRITICAL: Fore.RED if _COLORAMA_AVAILABLE else "",
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, "")
        reset = Style.RESET_ALL if _COLORAMA_AVAILABLE else ""
        prefix = f"{color}{Style.BRIGHT}" if color else ""
        suffix = reset
        original = super().format(record)
        return f"{prefix}{original}{suffix}"


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    fmt = "%(asctime)s %(levelname)-7s: %(message)s"
    handler.setFormatter(ColoredFormatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    # Remove other handlers to avoid duplication when called multiple times
    if root.handlers:
        root.handlers = []
    root.addHandler(handler)


# ----------------------
# Core Processor
# ----------------------
class CrossCornerProcessor:
    def __init__(
        self,
        corner_provider: CornerProvider,
        simulator: Simulator,
        template_processor: TemplateProcessor,
        folder_manager: FolderManager,
    ):
        self.corner_provider = corner_provider
        self.simulator = simulator
        self.template_processor = template_processor
        self.folder_manager = folder_manager

    def _load_template(self, template_file: Path) -> Tuple[str, str, Path]:
        content = template_file.read_text()
        filename = template_file.stem
        lines = content.splitlines()
        if not lines:
            raise ValueError("Template file is empty")
        # Extract sch_path from first line
        if "sch_path:" not in lines[0]:
            raise ValueError("First line must contain 'sch_path: <path>'")
        sch_path = lines[0].split("sch_path: ", 1)[1].strip()
        derived_output_dir = Path(sch_path).parent
        logging.debug(f"Extracted sch_path '{sch_path}', derived_output_dir: {derived_output_dir}")
        return content, filename, derived_output_dir

    def run(self, template_file: Path, output_dir_override: Optional[Path] = None) -> None:
        logging.info("Starting cross-corner processing")
        template_text, filename, derived_output_dir = self._load_template(template_file)
        output_dir = output_dir_override or derived_output_dir

        self.folder_manager.create_all(output_dir)

        corners = self.corner_provider.get_corners()
        logging.info(f"Processing {len(corners)} corners into '{output_dir}'")

        # Use tqdm for progress if available
        iterator = tqdm(corners, desc="Corners", total=len(corners)) if "tqdm" in globals() and callable(globals()["tqdm"]) else corners

        for corner in iterator:
            new_filename = f"{filename}_{corner}"
            spice_path = output_dir / "spice" / f"{new_filename}.spice"
            log_path = output_dir / "logs" / f"{new_filename}.log"

            logging.debug(f"Generating SPICE for corner '{corner}' at '{spice_path}'")
            content = self.template_processor.generate_content(template_text, filename, corner, output_dir)
            spice_path.write_text(content)

            logging.info(f"Running simulator for '{new_filename}' -> log: {log_path.name}")
            self.simulator.run(spice_path, log_path)

        logging.info("All corners complete")


# ----------------------
# CLI
# ----------------------
def build_default_processor() -> CrossCornerProcessor:
    corners = StaticCornerProvider(
        [
            "ss_ll_mm", "ss_hl_mm", "ss_lh_mm", "ss_hh_mm",
            "sf_ll_mm", "sf_hl_mm", "sf_lh_mm", "sf_hh_mm",
            "fs_ll_mm", "fs_hl_mm", "fs_lh_mm", "fs_hh_mm",
            "ff_ll_mm", "ff_hl_mm", "ff_lh_mm", "ff_hh_mm",
        ]
    )

    return CrossCornerProcessor(
        corner_provider=corners,
        simulator=NgSpiceSimulator(),
        template_processor=SpiceTemplateProcessor(),
        folder_manager=FolderManager(),
    )


def cli(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run NGSpice cross-corner batch simulations.")
    parser.add_argument("template_file", type=str, help="Input SPICE template file (e.g., test_case_sim.spice).")
    parser.add_argument("--output-dir", type=str, default=None, help="Optional output directory. If omitted, uses sch_path from template.")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    template_path = Path(args.template_file)
    if not template_path.exists():
        logging.error(f"Template file not found: {template_path}")
        return 2

    output_override = Path(args.output_dir) if args.output_dir else None

    processor = build_default_processor()
    processor.run(template_path, output_override)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
