import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, '../dist');

if (!fs.existsSync(distDir)) {
  console.error(`Dist directory not found: ${distDir}`);
  process.exit(1);
}

const indexHtmlPath = path.join(distDir, 'index.html');
if (!fs.existsSync(indexHtmlPath)) {
  console.error(`dist/index.html not found: ${indexHtmlPath}`);
  process.exit(1);
}

const indexContent = fs.readFileSync(indexHtmlPath, 'utf8');

// 1. Create .nojekyll to prevent GitHub Pages Jekyll processing
fs.writeFileSync(path.join(distDir, '.nojekyll'), '');
console.log('  ✓ Created dist/.nojekyll');

// 2. Create 404.html fallback
fs.writeFileSync(path.join(distDir, '404.html'), indexContent);
console.log('  ✓ Created dist/404.html (SPA fallback)');

// 3. Create route folders with index.html for direct 200 OK navigation
const routes = [
  'explorer',
  'comparison',
  'explainable-ai',
  'science',
  'new-analysis',
];

for (const route of routes) {
  const routeDir = path.join(distDir, route);
  fs.mkdirSync(routeDir, { recursive: true });
  fs.writeFileSync(path.join(routeDir, 'index.html'), indexContent);
  console.log(`  ✓ Created dist/${route}/index.html`);
}

console.log('GitHub Pages dist preparation complete.');
