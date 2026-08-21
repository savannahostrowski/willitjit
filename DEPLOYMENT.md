# Deployment status

Will It JIT? is not deployed. The repository has no FastAPI Cloud app ID,
deployment secrets, or deployment workflow.

`./build_app.sh` assembles the production-shaped app locally by building the
Vite frontend and copying it into `api/static` for FastAPI to serve.

Publishing compatibility results and deploying the assembled app require a
separate design and explicit approval. CI currently uploads artifacts only.
