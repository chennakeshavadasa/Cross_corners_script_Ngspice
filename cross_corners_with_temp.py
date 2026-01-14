#!/usr/bin/env python3
"""
cross_corners.py

Object-oriented, dependency-injected NGSpice cross-corner + temperature runner with:
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
from itertools import product

# Optional dependencies with graceful fallback
try:
    from tqdm import tqdm
except Exception:
    def tqdm(iterable=None, total=None, desc=None):
        if iterable is None:
            return []
        return iterable

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    _COLORAMA_AVAILABLE = True
except Exception:
    Fore = type("F", (), {"GREEN": "", "YELLOW": "", "RED": "", "BLUE": "", "MAGENTA": ""})()
    Style = type("S", (), {"BRIGHT": "", "RESET_ALL": ""})()
    _COLORAMA_AVAILABLE = False


# ----------------------
# Interfaces (Protocols)
# ----------------------
class CornerProvider(Protocol):
    def get_corners(self) -> List[str]: ...


class TemperatureProvider(Protocol):
    def get_temperatures(self) -> List[float]: ...


class Simulator(Protocol):
    def run(self, spice_file: Path, log_file: Path) -> None: ...


class TemplateProcessor(Protocol):
    def generate_content(
        self,
        template: str,
        filename: str,
        corner: str,
        temp: float,
        output_dir: Path,
    ) -> str: ...


# ----------------------
# Implementations
# ----------------------
@dataclass
class StaticCornerProvider:
    corners: List[str]

    def get_corners(self) -> List[str]:
        return self.corners


@dataclass
class StaticTemperatureProvider:
    temperatures: List[float]

    def get_temperatures(self) -> List[float]:
        return self.temperatures


class NgSpiceSimulator:
    """Runs NGSpice in batch mode (subprocess)."""

    def __init__(self, ngspice_cmd: List[str] | None = None):
        self.ngspice_cmd = ngspice_cmd or ["ngspice", "-b"]

    def run(self, spice_file: Path, log_file: Path) -> None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as f:
            logging.debug(f"Running simulator: {self.ngspice_cmd + [str(spice_file)]}")
            subprocess.run(
                self.ngspice_cmd + [str(spice_file)],
                stdout=f,
                stderr=f,
            )


class SpiceTemplateProcessor:
    """Processes SPICE templates with CORNER and TEMP tokens."""

    @staticmethod
    def _temp_tag(temp: float) -> str:
        t = int(temp)
        return f"m{abs(t)}C" if t < 0 else f"{t}C"

    def generate_content(
        self,
        template: str,
        filename: str,
        corner: str,
        temp: float,
        output_dir: Path,
    ) -> str:
        temp_tag = self._temp_tag(temp)
        new_filename = f"{filename}_{corner}_{temp_tag}"

        data = template
        data = data.replace("{CORNER}", corner)
        data = data.replace("{TEMP}", str(int(temp)))
        data = data.replace(filename, new_filename)

        replacements = {
            f"{new_filename}.raw": output_dir / "raw" / f"{new_filename}.raw",
            f"{new_filename}.csv": output_dir / "csv" / f"{new_filename}.csv",
            f"{new_filename}.txt": output_dir / "txt" / f"{new_filename}.txt",
        }

        for old, new in replacements.items():
            data = data.replace(old, new.resolve().as_posix())

        return data


class FolderManager:
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
        original = super().format(record)
        return f"{prefix}{original}{reset}"


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    fmt = "%(asctime)s %(levelname)-7s: %(message)s"
    handler.setFormatter(ColoredFormatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
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
        temperature_provider: TemperatureProvider,
        simulator: Simulator,
        template_processor: TemplateProcessor,
        folder_manager: FolderManager,
    ):
        self.corner_provider = corner_provider
        self.temperature_provider = temperature_provider
        self.simulator = simulator
        self.template_processor = template_processor
        self.folder_manager = folder_manager

    def _load_template(self, template_file: Path) -> Tuple[str, str, Path]:
        content = template_file.read_text()
        filename = template_file.stem
        lines = content.splitlines()

        if not lines:
            raise ValueError("Template file is empty")

        first = lines[0].strip()

        # Strip SPICE comment markers (* or **)
        while first.startswith("*"):
            first = first[1:].strip()

        if first.startswith("sch_path:"):
            sch_path = first.split("sch_path:", 1)[1].strip()
            output_dir = Path(sch_path).parent
            logging.debug(f"Using sch_path from template: {output_dir}")
        else:
            output_dir = template_file.parent / "SCH_Results"
            logging.warning(
                "No 'sch_path:' found in template header. "
                f"Defaulting output directory to {output_dir}"
            )

        return content, filename, output_dir

    def run(self, template_file: Path, output_dir_override: Optional[Path] = None) -> None:
        logging.info("Starting cross-corner × temperature processing")

        template_text, filename, derived_output_dir = self._load_template(template_file)
        output_dir = output_dir_override or derived_output_dir
        self.folder_manager.create_all(output_dir)

        corners = self.corner_provider.get_corners()
        temps = self.temperature_provider.get_temperatures()

        total = len(corners) * len(temps)
        logging.info(
            f"Running {total} simulations "
            f"({len(corners)} corners × {len(temps)} temperatures)"
        )

        runs = list(product(corners, temps))
        iterator = tqdm(runs, desc="Corner × Temp", total=total) if "tqdm" in globals() else runs

        for corner, temp in iterator:
            temp_tag = SpiceTemplateProcessor._temp_tag(temp)
            run_tag = f"{corner}_{temp_tag}"

            spice_path = output_dir / "spice" / f"{filename}_{run_tag}.spice"
            log_path = output_dir / "logs" / f"{filename}_{run_tag}.log"

            logging.info(f"Running {run_tag}")

            content = self.template_processor.generate_content(
                template_text,
                filename,
                corner,
                temp,
                output_dir,
            )
            spice_path.write_text(content)
            self.simulator.run(spice_path, log_path)

        logging.info("All corner × temperature simulations complete")


# ----------------------
# CLI
# ----------------------
def build_default_processor(temps: List[float]) -> CrossCornerProcessor:
    corners = StaticCornerProvider(
        [
            "ss_ll_mm", "ss_hl_mm", "ss_lh_mm", "ss_hh_mm",
            "sf_ll_mm", "sf_hl_mm", "sf_lh_mm", "sf_hh_mm",
            "fs_ll_mm", "fs_hl_mm", "fs_lh_mm", "fs_hh_mm",
            "ff_ll_mm", "ff_hl_mm", "ff_lh_mm", "ff_hh_mm",
        ]
    )

    temperature_provider = StaticTemperatureProvider(temps)

    return CrossCornerProcessor(
        corner_provider=corners,
        temperature_provider=temperature_provider,
        simulator=NgSpiceSimulator(),
        template_processor=SpiceTemplateProcessor(),
        folder_manager=FolderManager(),
    )


def cli(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run NGSpice cross-corner × temperature batch simulations."
    )
    parser.add_argument("template_file", help="Input SPICE template file")
    parser.add_argument(
        "--temps",
        type=float,
        nargs="+",
        default=[27.0],
        help="Temperatures in °C (e.g. --temps -40 27 85 125)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Optional output directory (overrides sch_path)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args(argv)
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    template_path = Path(args.template_file)
    if not template_path.exists():
        logging.error(f"Template file not found: {template_path}")
        return 2

    output_override = Path(args.output_dir) if args.output_dir else None
    processor = build_default_processor(args.temps)
    processor.run(template_path, output_override)
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
