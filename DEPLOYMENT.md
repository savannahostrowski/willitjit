# Deployment

The manual `Deploy to FastAPI Cloud` workflow builds the frontend, copies it
into `api/static`, and runs `fastapi deploy` from the API directory.

Configure these repository secrets before running it:

- `FASTAPI_CLOUD_TOKEN`
- `FASTAPI_CLOUD_APP_ID`

The workflow never runs on push. Publishing fresh compatibility results remains
separate, so a deployment contains the JSON already checked into `frontend/public/data`.
