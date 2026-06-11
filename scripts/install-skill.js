#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const SKILL_NAME = "bid-check-similarity";

function main() {
  const args = process.argv.slice(2);
  if (args.includes("--help") || args.includes("-h")) {
    printHelp();
    return;
  }

  const targetRoot = resolveTargetRoot(args);
  const packageRoot = path.resolve(__dirname, "..");
  const sourceSkill = path.join(packageRoot, "skills", SKILL_NAME);
  const destSkill = path.join(targetRoot, SKILL_NAME);

  assertDirectory(sourceSkill, "Skill source");
  assertDirectory(path.join(sourceSkill, "scripts", "vendor", "checksim"), "Skill bundled checksim core");
  fs.mkdirSync(targetRoot, { recursive: true });

  if (fs.existsSync(destSkill)) {
    fs.rmSync(destSkill, { recursive: true, force: true });
  }
  copyRecursive(sourceSkill, destSkill);

  console.log(`Installed ${SKILL_NAME} to: ${destSkill}`);
  console.log("");
  console.log("Python dependencies:");
  console.log(`  python -m pip install -r "${path.join(destSkill, "scripts", "requirements.txt")}"`);
  console.log("");
  console.log("CLI smoke test:");
  console.log(`  python "${path.join(destSkill, "scripts", "run_check.py")}" --help`);
}

function resolveTargetRoot(args) {
  const targetIndex = args.findIndex((arg) => arg === "--target" || arg === "--skills-dir");
  if (targetIndex >= 0) {
    const value = args[targetIndex + 1];
    if (!value) {
      throw new Error("--target requires a directory path");
    }
    return path.resolve(value);
  }
  if (process.env.AGENT_SKILLS_DIR) {
    return path.resolve(process.env.AGENT_SKILLS_DIR);
  }
  return path.resolve("skills");
}

function copyRecursive(source, dest, ignoredNames = new Set()) {
  if (shouldSkip(source, ignoredNames)) {
    return;
  }
  const stat = fs.statSync(source);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(source)) {
      copyRecursive(path.join(source, entry), path.join(dest, entry), ignoredNames);
    }
    return;
  }
  fs.copyFileSync(source, dest);
}

function shouldSkip(source, ignoredNames) {
  const name = path.basename(source);
  return ignoredNames.has(name) || name === "__pycache__" || name.endsWith(".pyc") || name.endsWith(".pyo");
}

function assertDirectory(dir, label) {
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
    throw new Error(`${label} not found: ${dir}`);
  }
}

function printHelp() {
  console.log(`Install the ${SKILL_NAME} agent skill.`);
  console.log("");
  console.log("Usage:");
  console.log("  npx github:cwyalpha/bid-check-similarity --target ./skills");
  console.log("  AGENT_SKILLS_DIR=./skills npx github:cwyalpha/bid-check-similarity");
}

main();
