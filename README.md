# Cross_corners_script_Ngspice

This is an attempt to make a single go Cross corner simulation script for NGSpice and open source tools

Basic usage (standard behavior)
```sh
python3 cross_corners.py test_case_sim.spice
```
Output directory auto-derived from `sch_path`.

Custom output directory
```sh
python3 cross_corners.py test_case_sim.spice --output-dir ./my_outputs
```