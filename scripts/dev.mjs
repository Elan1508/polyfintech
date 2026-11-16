import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const frontend = join(root, 'frontend');
const backend = join(root, 'backend');
const python = join(
  backend,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const vite = join(frontend, 'node_modules/vite/bin/vite.js');
const onlyFrontend = process.argv.includes('--frontend');
const onlyBackend = process.argv.includes('--backend');
const targets = [];

if (!onlyFrontend) {
  if (!existsSync(python)) {
    console.error(
      'Backend environment is missing. Create backend/.venv and install backend/requirements.txt first.',
    );
    process.exit(1);
  }
  targets.push({
    name: 'API',
    command: python,
    args: [
      '-m',
      'uvicorn',
      'app.main:app',
      '--reload',
      '--reload-dir',
      'app',
      '--host',
      '127.0.0.1',
      '--port',
      '8000',
    ],
    cwd: backend,
  });
}
if (!onlyBackend) {
  if (!existsSync(vite)) {
    console.error(
      'Frontend dependencies are missing. Run npm install from the project folder first.',
    );
    process.exit(1);
  }
  targets.push({
    name: 'Website',
    command: process.execPath,
    args: [vite, '--host', '127.0.0.1', '--port', '5173', '--strictPort'],
    cwd: frontend,
  });
}

const children = new Set();
let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) {
    if (process.platform === 'win32' && child.pid) {
      // Uvicorn's reloader owns another process; stop the complete owned tree.
      const cleanup = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
      cleanup.on('error', () => child.kill('SIGTERM'));
    } else {
      child.kill('SIGTERM');
    }
  }
}
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));

for (const target of targets) {
  console.log(`Starting ${target.name}…`);
  const child = spawn(target.command, target.args, {
    cwd: target.cwd,
    stdio: 'inherit',
    windowsHide: true,
  });
  children.add(child);
  child.on('error', (error) => {
    console.error(`${target.name} could not start: ${error.message}`);
    children.delete(child);
    stop(1);
  });
  child.on('exit', (code, signal) => {
    children.delete(child);
    if (!stopping) {
      console.error(`${target.name} stopped${code ? ` (exit ${code})` : ''}.`);
      stop(code ?? (signal ? 1 : 0));
    }
  });
}
