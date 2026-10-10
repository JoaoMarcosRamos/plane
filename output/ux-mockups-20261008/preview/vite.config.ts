import path from "node:path";
const root = path.resolve(import.meta.dirname, "../../..");
const web = path.join(root, "apps/web");
/** Standalone preview of apps/web/components/radar/mockups: no API, no auth, mock data only. */
export default {
  root: import.meta.dirname,
  define: { "process.env": "{}" },
  resolve: {
    alias: {
      // main.tsx lives outside apps/web, so its two provider imports are pointed at apps/web's copies.
      "@plane/i18n": path.join(web, "node_modules/@plane/i18n/dist/index.js"),
      "@plane/blocks/toast": path.join(web, "node_modules/@plane/blocks/dist/toast/index.js"),
      "next/link": path.join(web, "app/compat/next/link.tsx"),
      "next/navigation": path.join(web, "app/compat/next/navigation.ts"),
      "react-router": path.join(web, "node_modules/react-router"),
      "mobx-react": path.join(web, "node_modules/mobx-react"),
      mobx: path.join(web, "node_modules/mobx"),
      "@": web,
      react: path.join(web, "node_modules/react"),
      "react-dom": path.join(web, "node_modules/react-dom"),
    },
    dedupe: ["react", "react-dom"],
  },
  css: { postcss: web },
  esbuild: { jsx: "automatic" },
  server: { host: "127.0.0.1", port: 3058, fs: { allow: [root] } },
};
