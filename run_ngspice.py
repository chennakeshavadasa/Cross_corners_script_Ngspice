import os
import subprocess

SPICE_FILE = "spice/test_case_sim.spice"

def run_ngspice():
    filename = os.path.splitext(os.path.basename(SPICE_FILE))[0]

    os.makedirs("logs", exist_ok=True)
    # run ngspice and store logs into a file
    with open(f"logs/{filename}.log", "w") as f:
        subprocess.run(["ngspice", "-b", SPICE_FILE], stdout=f)


if __name__ == "__main__":
    run_ngspice()
