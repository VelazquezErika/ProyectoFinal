from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
import boto3
from pydantic import BaseModel
import pathlib
from uuid import uuid4
import asyncio
import redis.asyncio as aioredis
import json


FOLDER = 'imagenes'

WORKERS = ['resize', 'thumbnail', 'filter', 'convert']

class File(BaseModel):
    file_name: str
    file_type: str

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/api/presigned-post")
def upload_start(file: File):
    file_name = file_generate_name(file.file_name)
    file_path = f'{FOLDER}/{file_name}'
    presigned_data = s3_generate_presigned_post(file_path=file_path, file_type=file.file_type)
    return {"file_name": file_name, "presigned": presigned_data}

def s3_generate_presigned_post(*, file_path: str, file_type: str):
    s3_client = boto3.client(service_name="s3")
    return s3_client.generate_presigned_post(
        'velazquez-objects',
        file_path,
        Fields={"Content-Type": file_type},
        Conditions=[{"Content-Type": file_type}],
        ExpiresIn=1000,
    )

def file_generate_name(original_file_name):
    name = pathlib.Path(original_file_name)
    return f"{name.stem}-{uuid4().hex}{name.suffix}"

async def event_generator(filename: str):
    redis = aioredis.from_url("redis://redis:6379", encoding="utf-8", decode_responses=True)
    completed = set()

    while True:
        results = {}
        async with redis.client() as conn:
            for worker in WORKERS:
                val = await conn.get(f"{filename}:{worker}")
                results[worker] = val

        any_done = False
        all_done = True
        any_error = False

        for worker, val in results.items():
            if val is None:
                all_done = False
            elif val == "error":
                any_error = True
                completed.add(worker)
            elif val.startswith("completada"):
                completed.add(worker)
            elif val == "en proceso":
                all_done = False

        data = json.dumps({
            'results': results,
            'completed': list(completed),
            'all_done': len(completed) == len(WORKERS)
        })
        yield f"data: {data}\n\n"

        if len(completed) == len(WORKERS):
            await asyncio.sleep(1)
            break

        await asyncio.sleep(1)

@app.get("/events/{filename}")
async def events(request: Request, filename: str):
    return StreamingResponse(event_generator(filename), media_type="text/event-stream")
