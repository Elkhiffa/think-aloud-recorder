"""Explicit portable layout paths; an ordinary source folder named app is not a package."""
import json
from pathlib import Path

COMPACT_LAYOUT = 'compact-v1'


def _compact(path):
    try:
        return json.loads((path / 'portable.json').read_text(encoding='utf-8')).get('layout') == COMPACT_LAYOUT
    except (OSError, ValueError, AttributeError):
        return False


def application_root(path):
    root = Path(path).resolve()
    if _compact(root / 'app'):
        return root / 'app'
    return root


def installation_root(path):
    root = application_root(path)
    return root.parent if root.name == 'app' and _compact(root) else root


def vocabulary_dir(path):
    return installation_root(path) / 'vocabularies'


def manifest_path(path):
    return application_root(path) / 'package-manifest.json'


def metadata_path(path):
    return application_root(path) / 'portable.json'
