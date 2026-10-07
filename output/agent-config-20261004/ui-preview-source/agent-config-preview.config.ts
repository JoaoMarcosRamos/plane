import path from "node:path";
import { defineConfig } from "vite";
export default defineConfig({root:path.resolve(import.meta.dirname,".agent-config-preview"),resolve:{alias:{"@":path.resolve(import.meta.dirname)},dedupe:["react","react-dom"]},esbuild:{jsx:"automatic"},server:{host:"127.0.0.1",port:3014,fs:{allow:[path.resolve(import.meta.dirname,"../..")]}}});
