"""Source-checkout wrapper for `agent_cli.py layout-apply` (the installed app runs that command directly).

  runtime\python.exe -B -X utf8 scripts\apply_layout.py "<资料库>\燕云十六声" --dry-run
  runtime\python.exe -B -X utf8 scripts\apply_layout.py "<资料库>\燕云十六声"
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    sys.exit(subprocess.call([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'layout-apply', *sys.argv[1:]]))
