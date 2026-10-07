import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  test: {
    include: ["store/radar/**/*.test.ts", "services/radar/**/*.test.ts", "components/radar/**/*.test.ts"],
    environment: "node",
  },
});
