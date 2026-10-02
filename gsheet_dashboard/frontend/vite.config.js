import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8510' } },
  build: {rollupOptions: {output: {manualChunks(id) {
    if (id.includes('node_modules') && /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return 'react';
    if (id.includes('node_modules') && /recharts|d3-|victory-vendor/.test(id)) return 'charts';
  }}}},
});
