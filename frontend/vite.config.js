import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  preview: {
    port: 3000,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  // Pre-bundle heavy deps pulled in by lazy-loaded routes (PDF viewer, diagrams,
  // charts, markdown/katex). Otherwise Vite discovers them mid-session on first
  // interaction and forces a full page reload — which wipes an in-flight
  // "Teach me" lesson or chat answer, making those features look broken in dev.
  optimizeDeps: {
    include: [
      'react-pdf', 'pdfjs-dist',
      'mermaid', 'recharts',
      'react-markdown', 'remark-gfm', 'remark-math', 'rehype-katex',
      'axios', 'lucide-react',
    ],
  },
});
