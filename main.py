from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


@app.get("/")
async def read_root():
    return {"message": "Hello World"}


class GPT5Request(BaseModel):
    prompt: str
    reasoning_effort: str = "medium"  # minimal, low, medium, high
    verbosity: str = "medium"  # low, medium, high


@app.post("/gpt5")
async def gpt5_response(request: GPT5Request):
    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=request.prompt,
        )
        return {
            "response": response.output_text,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))