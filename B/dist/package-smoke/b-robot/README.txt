Q3/Q4 CPU runtime needs Python 3.10+ and NumPy. Q1 LP checks additionally need SciPy.
First run offline: python -B run_robot.py --mode offline --problem 4 --strategy square_cropped_2opt
Official GUI and this program must run on the same Windows guest.
After a HUMAN starts and confirms a PRACTICE session: python -B run_robot.py --mode practice --problem 3 --strategy active_2opt --confirm-practice --robot-id YOUR_TEAM_ID
The flag is an operator declaration, not server mode authentication. Never use enter as a probe.
No account registration, GUI automation, formal-test start, or management endpoint is implemented.
This strategy has passed offline cross-tests but has not itself run in the official simulator.
