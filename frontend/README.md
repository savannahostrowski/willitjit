# Will It JIT? frontend

Static React/Vite frontend served by the FastAPI app in `../api`.

```console
npm install
npm run dev
npm run build
```

The browser reads `results.json` and `history.json` from the public GitHub Pages
data feed. Set `VITE_DATA_URL` to use a different feed while developing.
