import { defineConfig } from 'astro/config';

const siteUrl = process.env.PUBLIC_SITE_URL;

export default defineConfig({
  output: 'static',
  site: siteUrl,
  build: {
    format: 'directory',
  },
});
