import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev server binds to 127.0.0.1 only (shared NERSC login nodes); reach it via SSH port forwarding.
export default defineConfig({
  plugins: [react()],
  define: {
    'process.env': {},
    global: 'globalThis',
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  build: {
    chunkSizeWarningLimit: 4000,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('ketcher')) return 'ketcher';
          if (id.includes('3dmol')) return 'viewer3d';
          if (id.includes('echarts')) return 'charts';
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('rc-')) return 'antd';
          return undefined;
        },
      },
    },
  },
});
