import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const environment = join(
  root,
  'backend',
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const python = existsSync(environment)
  ? environment
  : process.platform === 'win32'
    ? 'python'
    : 'python3';
const result = spawnSync(python, [join(root, 'scripts/package.py')], {
  cwd: root,
  stdio: 'inherit',
  windowsHide: true,
});
if (result.error)
  console.error('Python 3 is required to package the source:', result.error.message);
process.exitCode = result.status ?? 1;
