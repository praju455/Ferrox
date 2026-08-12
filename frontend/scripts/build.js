const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..");
const required = ["index.html", "styles.css", "app.js"];

for (const file of required) {
  if (!fs.existsSync(path.join(root, file))) {
    console.error(`Missing ${file}`);
    process.exit(1);
  }
}

const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
for (const file of ["styles.css", "app.js"]) {
  if (!html.includes(file)) {
    console.error(`index.html must reference ${file}`);
    process.exit(1);
  }
}

console.log("Build check passed.");
