import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';

const result = await build({
  entryPoints: ['frontend/editor.js'], bundle: true, minify: true,
  format: 'esm', target: 'es2020', outfile: 'app/static/editor.bundle.js',
  legalComments: 'linked', metafile: true,
});
const notices = new Map();
for (const input of Object.keys(result.metafile.inputs)) {
  if (!input.includes('node_modules/')) continue;
  let directory = path.dirname(path.resolve(input));
  while (directory !== path.dirname(directory)) {
    const manifest = path.join(directory, 'package.json');
    if (fs.existsSync(manifest)) {
      const pkg = JSON.parse(fs.readFileSync(manifest, 'utf8'));
      const licenseFile = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license'].find(name => fs.existsSync(path.join(directory, name)));
      notices.set(pkg.name, `${pkg.name} ${pkg.version} (${pkg.license || 'see package'})\n${licenseFile ? fs.readFileSync(path.join(directory, licenseFile), 'utf8') : pkg.repository?.url || ''}`);
      break;
    }
    directory = path.dirname(directory);
  }
}
fs.writeFileSync('app/static/editor-notices.txt', [...notices.values()].join('\n\n---------------------\n\n'));
console.log(`Built editor and ${notices.size} third-party license notices.`);
