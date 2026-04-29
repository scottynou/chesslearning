import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(scriptDir, "..");
const command = process.platform === "win32" ? "cmd.exe" : "npm";
const args = process.platform === "win32" ? ["/d", "/s", "/c", "npm run build"] : ["run", "build"];

const result = spawnSync(command, args, {
  cwd: frontendDir,
  env: {
    ...process.env,
    NEXT_PUBLIC_API_BASE_URL: "same-origin",
    NEXT_PUBLIC_IMAGE_IMPORT_API_BASE_URL: "https://chess-elo-coach-api-gmhvz5pfcq-ew.a.run.app"
  },
  stdio: "inherit"
});

process.exit(result.status ?? 1);
