# Will It JIT? frontend

Static React/Vite frontend served by the FastAPI app in `../api`.

```console
npm install
npm run dev
npm run build
```

The browser reads `index.json`, versioned snapshots below `results/`, and
`history.json` from the public GitHub Pages data feed. It falls back to the
legacy `results.json` feed during deployments. Set `VITE_DATA_URL` to use a
different feed while developing.
