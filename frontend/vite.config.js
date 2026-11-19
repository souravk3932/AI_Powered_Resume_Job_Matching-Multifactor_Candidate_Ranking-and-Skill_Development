import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// Plugins: React support + Tailwind CSS support
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
