import { build } from "esbuild";

await build({
  entryPoints: ["src/main.js"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  legalComments: "none",
  outfile: "../static/js/app.js",
});
