# Will It JIT? frontend

Static React/Vite frontend served by the FastAPI app in `../api`.

```console
npm install
npm run dev
npm run build
```

The runner merges platform artifacts into `public/data/results.json`; history
lives in `public/data/history.json`. The browser reads both files directly, so
there is no runtime database dependency.
