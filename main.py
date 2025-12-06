import os
from pathlib import Path
import subprocess

TEMPLATE_SPICE_FILE = "test_case_sim.spice"
CORNERS_DATA = [
    "ss_ll_mm",
    "ss_hl_mm",
    "ss_lh_mm",
    "ss_hh_mm",
    "sf_ll_mm",
    "sf_hl_mm",
    "sf_lh_mm",
    "sf_hh_mm",
    "fs_ll_mm",
    "fs_hl_mm",
    "fs_lh_mm",
    "fs_hh_mm",
    "ff_ll_mm",
    "ff_hl_mm",
    "ff_lh_mm",
    "ff_hh_mm",
]


def main():
    print("Hello from cross-corners-script-ngspice! Please run this script once your tt simulation works properly")

    # extract template filename without extension
    filename = os.path.splitext(os.path.basename(TEMPLATE_SPICE_FILE))[0]

    # read the template
    with open(TEMPLATE_SPICE_FILE, "r") as f:
        template_file_data_lines = f.readlines()

    # extract output directory
    sch_path = template_file_data_lines[0].split("sch_path: ")[1]
    output_dir = Path(sch_path).parent

    # join lines
    template_file_data = "".join(template_file_data_lines)

    # create folders raw, csv, txt, logs, spice
    if not os.path.exists(Path(output_dir, "raw")):
        os.makedirs(Path(output_dir, "raw"))
    if not os.path.exists(Path(output_dir, "csv")):
        os.makedirs(Path(output_dir, "csv"))
    if not os.path.exists(Path(output_dir, "txt")):
        os.makedirs(Path(output_dir, "txt"))
    if not os.path.exists(Path(output_dir, "logs")):
        os.makedirs(Path(output_dir, "logs"))
    if not os.path.exists(Path(output_dir, "spice")):
        os.makedirs(Path(output_dir, "spice"))

    # create spice files for all corners using template
    for corner in CORNERS_DATA:
        new_filename = f"{filename}_{corner}"
        spice_file_path = Path(output_dir, "spice", f"{new_filename}.spice")
        with open(spice_file_path, "w") as f:
            # replace corner
            new_data = template_file_data.replace("tt", corner)

            # replace filename
            new_data = new_data.replace(filename, new_filename)
            # replace paths
            new_data = new_data.replace(
                f"{new_filename}.raw", Path(output_dir, "raw", f"{new_filename}.raw").resolve().as_posix()
            )
            new_data = new_data.replace(
                f"{new_filename}.csv", Path(output_dir, "csv", f"{new_filename}.csv").resolve().as_posix()
            )
            new_data = new_data.replace(
                f"{new_filename}.txt", Path(output_dir, "txt", f"{new_filename}.txt").resolve().as_posix()
            )
            f.write(new_data)

        # run ngspice
        with open(Path(output_dir, "logs", f"{new_filename}.log"), "w") as f:
            subprocess.run(["ngspice", "-b", spice_file_path], stdout=f, stderr=f)


if __name__ == "__main__":
    main()
