# api/main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from api.routes import auth, fixture, history, stats, settlement

app = FastAPI(title="Stoppage Time API")

# Bearer-token auth, not cookies — allow_credentials=False deliberately.
# ALLOWED_ORIGINS defaults to "*", and browsers reject wildcard origins
# combined with allow_credentials=True outright.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(fixture.router)
app.include_router(history.router)
app.include_router(stats.router)
app.include_router(settlement.router)


@app.get("/health")
def health():
    return {"status": "ok"}
