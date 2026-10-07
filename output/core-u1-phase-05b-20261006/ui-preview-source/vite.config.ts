import path from "node:path";
const root = path.resolve(import.meta.dirname, "../../..");
const web = path.join(root, "apps/web");
export default {
  root: import.meta.dirname,
  define: { "process.env": "{}" },
  plugins: [
    {
      name: "isolated-notes",
      enforce: "pre",
      resolveId(source: string, importer?: string) {
        if (source.includes("notes-editor") && importer?.includes("/radar/object-page.tsx"))
          return path.join(import.meta.dirname, "notes.tsx");
      },
    },
  ],
  resolve: {
    alias: {
      "@/components/dropdowns/member/member-select": path.join(import.meta.dirname, "members.tsx"),
      "@/hooks/store/user": path.join(import.meta.dirname, "permissions.ts"),
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
  server: {
    host: "127.0.0.1",
    port: 3056,
    fs: { allow: [root] },
    proxy: { "/api": "http://127.0.0.1:8956", "/fixture": "http://127.0.0.1:8956" },
  },
};
