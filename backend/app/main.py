"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="JAPDP API",
    description="Jablonsky Data Platform — structural engineering data services",
    version="0.1.0",
)

# CORS — allow frontend dev server and any localhost origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Basic health check endpoint."""
    return {"status": "ok"}


# Router includes
from app.routers import projects, load_tables, tributary, elements, identity, rundown, chains
app.include_router(projects.router, prefix="/api")
app.include_router(load_tables.router, prefix="/api")
app.include_router(tributary.router, prefix="/api")
app.include_router(elements.router, prefix="/api")
app.include_router(identity.router, prefix="/api")
app.include_router(rundown.router, prefix="/api")
app.include_router(chains.router, prefix="/api")

# ---------------------------------------------------------------
# User router
from app.routers import users
app.include_router(users.router, prefix="/api")
# ---------------------------------------------------------------