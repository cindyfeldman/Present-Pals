from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx

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

@app.get("/proxy-image")
async def proxy_image(url: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
    
    async def stream_image():
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }
            
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                        if (response.status_code != 200):
                            raise HTTPException(status_code=response.status_code, detail="Failed to fetch image")
                        
                        # Stream the image data in chunks
                        async for chunk in response.aiter_bytes():
                            yield chunk
                except Exception as e:
                    printf(f"Proxy image fetch error: {e}")
                    raise HTTPException(status_code=500, detail="Error fetching image")
                
    return StreamingResponse(stream_image(), media_type="image/jpeg")