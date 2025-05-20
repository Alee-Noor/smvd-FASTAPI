# main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from yt_dlp import YoutubeDL
from typing import Optional
import os
import uuid
import asyncio
from pydantic import BaseModel

app = FastAPI()

origins = [
    "http://localhost:3000",  # Your frontend URL
    "https://your-production-frontend.com"  # Add production URL if needed
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Temporary storage for download progress
download_status = {}

class VideoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_id: str

@app.post("/api/video-info")
async def get_video_info(request: VideoRequest):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'format': 'best',
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            formats = []
            for f in info['formats']:
                if f.get('vcodec') != 'none' or f.get('acodec') != 'none':
                    formats.append({
                        'format_id': f['format_id'],
                        'quality': f.get('format_note', f['ext']),
                        'type': 'Video' if f.get('vcodec') != 'none' else 'Audio',
                        'size': f.get('filesize', 0)
                    })

            return JSONResponse({
                'title': info['title'],
                'thumbnail': info['thumbnail'],
                'duration': info['duration_string'],
                'formats': formats
            })
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    download_id = str(uuid.uuid4())
    temp_filename = f"temp_{download_id}.mp4"
    
    async def download_task():
        try:
            ydl_opts = {
                'format': request.format_id,
                'outtmpl': temp_filename,
                'progress_hooks': [progress_hook],
            }

            with YoutubeDL(ydl_opts) as ydl:
                download_status[download_id] = {'progress': 0, 'status': 'downloading'}
                ydl.download([request.url])
                
                download_status[download_id]['status'] = 'completed'
                
                # Wait for client to pick up the file
                await asyncio.sleep(60)
                
                # Cleanup
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                del download_status[download_id]

        except Exception as e:
            download_status[download_id]['status'] = 'error'
            download_status[download_id]['error'] = str(e)

    def progress_hook(d):
        if d['status'] == 'downloading':
            download_status[download_id]['progress'] = d['_percent_str']

    asyncio.create_task(download_task())
    
    return {'download_id': download_id}

@app.get("/api/progress/{download_id}")
async def get_download_progress(download_id: str):
    status = download_status.get(download_id)
    if not status:
        raise HTTPException(status_code=404, detail="Download ID not found")
    
    return status

@app.get("/api/download-file/{download_id}")
async def get_download_file(download_id: str):
    temp_filename = f"temp_{download_id}.mp4"
    if not os.path.exists(temp_filename):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        temp_filename,
        headers={'Content-Disposition': f'attachment; filename="download_{download_id}.mp4"'}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
