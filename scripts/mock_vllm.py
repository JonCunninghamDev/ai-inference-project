from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI()

class ChatRequest(BaseModel):
    model: str
    messages: list

@app.get("/v1/models")
async def get_models():
    return {"data": [{"id": "meta-llama/Llama-3.1-8B-Instruct"}]}

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": f"MOCK RESPONSE: Air-gap verified. I received your prompt: '{request.messages[-1]['content']}'"
            }
        }]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)