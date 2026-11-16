"""Create a source-only archive from the current checkout, including uncommitted work."""
from pathlib import Path, PurePosixPath
import os
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'node_modules', '.venv', 'dist', '__pycache__', 'runtime', '.git',
            '.pytest_cache', 'playwright-report', 'test-results', 'artifacts', '.codex', '.agents'}
PRIVATE_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.zip', '.pyc', '.pyo'}


def included(name):
    path = PurePosixPath(name)
    return (not any(part.casefold() in EXCLUDED for part in path.parts)
            and not path.name.casefold().startswith('.env')
            and path.suffix.lower() not in PRIVATE_SUFFIXES
            and not path.name.endswith(('-wal', '-shm')))


def main():
    try:
        git_root = subprocess.check_output(
            ['git', 'rev-parse', '--show-toplevel'], cwd=ROOT,
            stderr=subprocess.DEVNULL).decode().strip()
        if Path(git_root).resolve() != ROOT:
            raise ValueError('This source folder is inside a different Git checkout')
        candidates = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
            cwd=ROOT, stderr=subprocess.DEVNULL).decode().split('\0')
    except (OSError, ValueError, subprocess.CalledProcessError):
        # An extracted submission has no Git metadata, but can still be packaged.
        candidates = []
        for directory, folders, filenames in os.walk(ROOT):
            folders[:] = [name for name in folders if name.casefold() not in EXCLUDED
                          and not (Path(directory) / name).is_symlink()
                          and (Path(directory) / name).resolve().is_relative_to(ROOT)]
            candidates.extend((Path(directory) / name).relative_to(ROOT).as_posix()
                              for name in filenames)
    destination = ROOT / 'artifacts' / 'ESG-Pulse360-source.zip'
    destination.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(set(filter(None, candidates))):
            path = ROOT / name
            if included(name) and path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT):
                archive.write(path, 'ESG-Pulse360/' + name)
                count += 1
    print(f'Created {destination} ({count} source files, {destination.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()
