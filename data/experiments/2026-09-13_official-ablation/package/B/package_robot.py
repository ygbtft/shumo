"""Make a portable source package in B/dist, with no official identity or recordings."""
from pathlib import Path
import zipfile
import hashlib
import json

root=Path(__file__).resolve().parent
dest=root/"dist"
dest.mkdir(exist_ok=True)
files=["run_robot.py","client.py","policies.py","geometry.py","intelligent.py","coverage.py","simulator.py"]
with zipfile.ZipFile(dest/"b-robot-offline-and-practice.zip","w",zipfile.ZIP_DEFLATED) as z:
    for name in files:
        z.write(root/name,"b-robot/"+name)
    z.write(root/"experiments/runs/2026-09-10_independent/routes.json","b-robot/routes.json")
    z.writestr("b-robot/requirements-runtime.txt","numpy>=2.1\n")
    z.writestr("b-robot/README.txt", "Q3/Q4 CPU runtime needs Python 3.10+ and NumPy. Q1 LP checks additionally need SciPy.\n"
               "First run offline: python -B run_robot.py --mode offline --problem 4 --strategy square_cropped_2opt\n"
               "Official GUI and this program must run on the same Windows guest.\n"
               "After a HUMAN starts and confirms a PRACTICE session: python -B run_robot.py --mode practice --problem 3 --strategy active_2opt --confirm-practice --robot-id YOUR_TEAM_ID\n"
               "The flag is an operator declaration, not server mode authentication. Never use enter as a probe.\n"
               "No account registration, GUI automation, formal-test start, or management endpoint is implemented.\n"
               "This strategy has passed offline cross-tests but has not itself run in the official simulator.\n")
path=dest/"b-robot-offline-and-practice.zip"
(dest/"manifest.json").write_text(json.dumps({"zip":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "contains_official_identity":False,"contains_official_logs":False,
                                            "contains_installer_or_vm":False},indent=2))
print(path)
