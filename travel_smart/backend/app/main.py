from fastapi import FastAPI

from app.api.place_routes import router as place_router

app = FastAPI(title="Travel Smart Backend", version="0.1.0")
app.include_router(place_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Travel Smart backend is running"}
