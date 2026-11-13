import { readdirSync, mkdirSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendDir = join(__dirname, '..');
const testDir = join(frontendDir, 'src/__tests__');
const tempOutDir = join(frontendDir, '.test_build');

try {
  mkdirSync(tempOutDir, { recursive: true });

  const testFiles = readdirSync(testDir).filter((f) => f.endsWith('.test.ts'));
  console.log(`[EarthPulse Test Suite] Discovered ${testFiles.length} test files:`, testFiles);

  for (const file of testFiles) {
    const inPath = join(testDir, file);
    const outPath = join(tempOutDir, file.replace('.ts', '.js'));
    execSync(
      `./node_modules/.bin/esbuild "${inPath}" --bundle --platform=node --format=esm --packages=external --outfile="${outPath}"`,
      {
        cwd: frontendDir,
        stdio: 'inherit',
      }
    );
  }

  console.log('[EarthPulse Test Suite] Executing Node.js native test runner...');
  execSync(`node --test "${tempOutDir}"/*.test.js`, {
    cwd: frontendDir,
    stdio: 'inherit',
  });

  console.log('[EarthPulse Test Suite] All frontend tests passed cleanly!');
} finally {
  try {
    rmSync(tempOutDir, { recursive: true, force: true });
  } catch {}
}
