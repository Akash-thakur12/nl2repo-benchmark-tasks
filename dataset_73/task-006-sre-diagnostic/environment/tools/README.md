# tools/

Odds and ends that have accumulated around the incident workflow. Nothing here
is part of the classifier and nothing here is under test.

* `triage_report.py` — an on-call helper from the 2022 rotation that prints a
  root-cause line for a capture file. It predates the v2 runbook and has not
  been touched since. If its output disagrees with a capture's
  `recorded_verdict`, the capture is right.
