from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.scripts.query_tfidf import get_recommendations

app = FastAPI()

# Essential for React to be allowed to talk to Python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/search")
async def search(recipient: str="", min_price: float=0.0, max_price: float=1000.0, q: str=""):
	#Call query_tfidf logic directly
    data = get_recommendations(
        recipient=recipient, 
        min_price=min_price, 
        max_price=max_price, 
        q=q
    )
    return {"gifts": data}