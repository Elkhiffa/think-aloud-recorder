"""Source-checkout wrapper for `agent_cli.py context-rebuild` (the installed app runs that command directly).

  runtime\python.exe -B -X utf8 scripts\rebuild_context_tracks.py "<资料库>\燕云十六声" [--workers 2]

Progress goes to the console; one log per session in state\logs\context-rebuild\.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == '__main__':
    sys.exit(subprocess.call([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'context-rebuild', *sys.argv[1:]]))
