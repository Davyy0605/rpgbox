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

// O leitor de PDF só é carregado na página do visualizador, fora do pacote principal.
await build({
  entryPoints: { pdf: "src/pdf.js", "pdf.worker": "node_modules/pdfjs-dist/build/pdf.worker.min.mjs" },
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2022"],
  legalComments: "none",
  outdir: "../static/js",
});
