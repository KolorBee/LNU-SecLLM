from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from twin_core.mine_twin import get_mining_insights

app = FastAPI()

# This allows your React dashboard to talk to this Python code
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/data")
def read_data():
    return get_mining_insights()