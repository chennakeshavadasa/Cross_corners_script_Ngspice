#!/usr/bin/env python3
"""
cross_corners.py

NGSpice cross-corner × temperature automation with:
 - tqdm progress bar
 - colored logging
 - safe .temp rewriting
 - correct write / wrdata / print redirection
 - xschem-compatible sch_path parsing
"""

from __future__ import annotations
import argparse
import logging
import subprocess
import time
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol, Tuple, Optional
from itertools import product

# -------------------------------------------------
# Optional dependencies (graceful fallback)
# -------------------------------------------------
try:
    from tqdm import tqdm
except Exception:
    def tqdm(iterable=None, **kwargs):
        return iterable or []

try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    COLOR = True
except Exception:
    COLOR = False
    class Fore:
        GREEN = YELLOW = RED = MAGENTA = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# -------------------------------------------------
# Interfaces
# -------------------------------------------------
class CornerProvider(Protocol):
    def get_corners(self) -> List[str]: ...

class TemperatureProvider(Protocol):
    def get_temperatures(self) -> List[float]: ...

class Simulator(Protocol):
    def run(self, spice_file: Path, log_file: Path) -> None: ...

class TemplateProcessor(Protocol):
    def generate(
        self,
        template: str,
        base_name: str,
        corner: str,
        temp: float,
        outdir: Path,
    ) -> str: ...

# -------------------------------------------------
# Providers
# -------------------------------------------------
@dataclass
class StaticCornerProvider:
    corners: List[str]
    def get_corners(self) -> List[str]:
        return self.corners

@dataclass
class StaticTemperatureProvider:
    temps: List[float]
    def get_temperatures(self) -> List[float]:
        return self.temps

# -------------------------------------------------
# Simulator
# -------------------------------------------------
class NgSpiceSimulator:
    def __init__(self, cmd: List[str] | None = None):
        self.cmd = cmd or ["ngspice", "-b"]

    def run(self, spice_file: Path, log_file: Path) -> None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "w") as f:
            subprocess.run(self.cmd + [str(spice_file)], stdout=f, stderr=f)

# -------------------------------------------------
# Template processor (CRITICAL PART)
# -------------------------------------------------
class SpiceTemplateProcessor:

    @staticmethod
    def temp_tag(temp: float) -> str:
        t = int(temp)
        return f"m{abs(t)}C" if t < 0 else f"{t}C"

    @staticmethod
    def set_temp(netlist: str, temp: float) -> str:
        """Replace or insert .temp safely"""
        line = f".temp {int(temp)}"
        if re.search(r"(?im)^\s*\.temp\s+", netlist):
            return re.sub(r"(?im)^\s*\.temp\s+[-+]?\d+", line, netlist)
        return re.sub(r"(?im)(\.control)", f"{line}\n\\1", netlist, count=1)

    @staticmethod
    def fix_outputs(netlist: str, name: str, outdir: Path) -> str:
        # RAW
        netlist = re.sub(
            r"(?im)^\s*write\s+\S+",
            f"write {outdir/'raw'/f'{name}.raw'}",
            netlist,
        )

        # CSV — KEEP SIGNAL LIST INTACT
        netlist = re.sub(
            r"(?im)^\s*wrdata\s+(\S+)",
            rf"wrdata {outdir/'csv'/f'{name}.csv'}",
            netlist,
        )

        # TXT — KEEP SIGNAL LIST INTACT
        netlist = re.sub(
            r"(?im)^\s*print\s+(.+?)\s*>\s*\S+",
            rf"print \1 > {outdir/'txt'/f'{name}.txt'}",
            netlist,
        )

        return netlist

    def generate(
        self,
        template: str,
        base_name: str,
        corner: str,
        temp: float,
        outdir: Path,
    ) -> str:
        tag = f"{corner}_{self.temp_tag(temp)}"
        run_name = f"{base_name}_{tag}"

        data = template
        data = self.set_temp(data, temp)
        data = self.fix_outputs(data, run_name, outdir)

        return data

# -------------------------------------------------
# Folder manager
# -------------------------------------------------
class FolderManager:
    SUBDIRS = ["raw", "csv", "txt", "logs", "spice"]

    def create(self, root: Path):
        for d in self.SUBDIRS:
            (root / d).mkdir(parents=True, exist_ok=True)

# -------------------------------------------------
# Logging
# -------------------------------------------------
class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.DEBUG: Fore.MAGENTA,
    }

    def format(self, record):
        msg = super().format(record)
        if COLOR:
            return f"{self.COLORS.get(record.levelno,'')}{Style.BRIGHT}{msg}{Style.RESET_ALL}"
        return msg

def setup_logging(debug: bool):
    h = logging.StreamHandler()
    h.setFormatter(ColorFormatter("%(asctime)s %(levelname)-7s: %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(h)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

# -------------------------------------------------
# Core processor
# -------------------------------------------------
class CrossCornerProcessor:
    def __init__(
        self,
        corners: CornerProvider,
        temps: TemperatureProvider,
        simulator: Simulator,
        processor: TemplateProcessor,
    ):
        self.corners = corners
        self.temps = temps
        self.simulator = simulator
        self.processor = processor

    def load_template(self, f: Path) -> Tuple[str, str, Path]:
        txt = f.read_text()
        first = txt.splitlines()[0].lstrip("* ").strip()
        sch_path = first.split("sch_path:", 1)[1].strip()
        return txt, f.stem, Path(sch_path).parent

    def run(self, template_file: Path, out_override: Optional[Path]):
        tpl, base, outdir = self.load_template(template_file)
        outdir = out_override or outdir
        FolderManager().create(outdir)

        runs = list(product(self.corners.get_corners(), self.temps.get_temperatures()))
        total = len(runs)

        bar = tqdm(
            enumerate(runs, 1),
            total=total,
            desc="Running sims",
            unit="run",
            ascii=True,
            dynamic_ncols=True,
        )

        for idx, (corner, temp) in bar:
            tag = f"{corner}_{SpiceTemplateProcessor.temp_tag(temp)}"
            spice = outdir / "spice" / f"{base}_{tag}.spice"
            log = outdir / "logs" / f"{base}_{tag}.log"

            logging.info(f"[{idx}/{total}] Corner={corner} Temp={temp}C")

            content = self.processor.generate(tpl, base, corner, temp, outdir)
            spice.write_text(content)

            t0 = time.time()
            self.simulator.run(spice, log)
            dt = (time.time() - t0) / 60.0

            logging.info(f"Completed {tag} in {dt:.2f} min")

# -------------------------------------------------
# CLI
# -------------------------------------------------
def build_processor(temps: List[float]) -> CrossCornerProcessor:
    corners = StaticCornerProvider([
        "ss_ll_mm","ss_hl_mm","ss_lh_mm","ss_hh_mm",
        "sf_ll_mm","sf_hl_mm","sf_lh_mm","sf_hh_mm",
        "fs_ll_mm","fs_hl_mm","fs_lh_mm","fs_hh_mm",
        "ff_ll_mm","ff_hl_mm","ff_lh_mm","ff_hh_mm",
    ])
    return CrossCornerProcessor(
        corners,
        StaticTemperatureProvider(temps),
        NgSpiceSimulator(),
        SpiceTemplateProcessor(),
    )

def cli():
    p = argparse.ArgumentParser()
    p.add_argument("template_file")
    p.add_argument("--temps", type=float, nargs="+", default=[27])
    p.add_argument("--output-dir")
    p.add_argument("--debug", action="store_true")
    a = p.parse_args()

    setup_logging(a.debug)

    build_processor(a.temps).run(
        Path(a.template_file),
        Path(a.output_dir) if a.output_dir else None,
    )

if __name__ == "__main__":
    cli()
