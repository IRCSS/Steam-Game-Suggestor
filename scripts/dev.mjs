// Start the FastAPI backend and the Vite UI together; Ctrl+C stops both.
import { spawn } from "node:child_process";

const procs = [
  ["api", "npm run dev-api"],
  ["ui ", "npm run dev-ui"],
].map(([name, cmd]) => {
  const child = spawn(cmd, { shell: true, stdio: ["ignore", "pipe", "pipe"] });
  const prefix = (chunk) =>
    chunk
      .toString()
      .split(/\r?\n/)
      .filter(Boolean)
      .map((line) => `[${name}] ${line}`)
      .join("\n") + "\n";
  child.stdout.on("data", (c) => process.stdout.write(prefix(c)));
  child.stderr.on("data", (c) => process.stderr.write(prefix(c)));
  child.on("exit", (code) => {
    console.log(`[${name}] exited with code ${code}`);
    shutdown(code ?? 0);
  });
  return child;
});

console.log("\n  API: http://127.0.0.1:8765/docs\n  UI:  http://127.0.0.1:5173\n");

let stopping = false;
function shutdown(code) {
  if (stopping) return;
  stopping = true;
  for (const child of procs) {
    if (child.exitCode === null) {
      if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"]);
      else child.kill("SIGTERM");
    }
  }
  setTimeout(() => process.exit(code), 500);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
