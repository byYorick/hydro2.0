/**
 * Копирует swagger-ui-dist в public/vendor/swagger-ui для офлайн-режима (без unpkg).
 */
import { copyFileSync, existsSync, mkdirSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const srcDir = join(root, 'node_modules/swagger-ui-dist');
const outDir = join(root, 'public/vendor/swagger-ui');

const files = ['swagger-ui.css', 'swagger-ui-bundle.js'];

if (!existsSync(srcDir)) {
    console.warn('[vendor-swagger-ui] swagger-ui-dist не установлен, пропуск.');
    process.exit(0);
}

mkdirSync(outDir, { recursive: true });
for (const name of files) {
    copyFileSync(join(srcDir, name), join(outDir, name));
}
console.log('[vendor-swagger-ui] скопировано в public/vendor/swagger-ui');
