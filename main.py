import os
# import subprocess

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
    print("Hello from cross-corners-script-ngspice!")

    # extract template filename without extension
    filename = os.path.splitext(os.path.basename(TEMPLATE_SPICE_FILE))[0]

    # create folders raw, csv, txt, logs, spice
    if not os.path.exists("raw"):
        os.makedirs("raw")
    if not os.path.exists("csv"):
        os.makedirs("csv")
    if not os.path.exists("txt"):
        os.makedirs("txt")
    if not os.path.exists("logs"):
        os.makedirs("logs")
    if not os.path.exists("spice"):
        os.makedirs("spice")

    # read the template
    with open(TEMPLATE_SPICE_FILE, "r") as f:
        template_file_data = f.read()

    # create spice files for all corners using template
    for corner in CORNERS_DATA:
        new_filename = f"{filename}_{corner}"
        spice_file_name = f"spice/{new_filename}.spice"
        with open(spice_file_name, "w") as f:
            new_data = template_file_data.replace(filename, new_filename)
            new_data = new_data.replace(
                f"{new_filename}.raw", f"raw/{new_filename}.raw"
            )
            new_data = new_data.replace(
                f"{new_filename}.csv", f"csv/{new_filename}.csv"
            )
            new_data = new_data.replace(
                f"{new_filename}.txt", f"txt/{new_filename}.txt"
            )
            f.write(new_data)

        # run ngspice
        # subprocess.run(["ngspice", "-b", spice_file_name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        # exit ngspice
        # subprocess.run(["exit"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


if __name__ == "__main__":
    main()
