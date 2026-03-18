from fastapi import FastAPI

api = FastAPI(title="PD General Purpose Agent")


@api.get("/health")
async def health():
    return {"status": "ok"}
