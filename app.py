"""
NanoStream FastAPI Backend
Web API for video analysis, encoding, and streaming
"""

import os
import time
import logging
from typing import List, Dict, Optional

from dotenv import load_dotenv
load_dotenv()  # loads .env file in dev; no-op in production

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from analyzer import ContentAnalyzer
from encoder import Encoder
from hls_generator import HLSGenerator
from bitrate_ladder import BitrateLadder
from job_queue import JobQueue
from ml_encoder import MLEncoderSelector
from cost_optimizer import CostOptimizer
from observability import instrument_app, metrics, timer
from adaptive_bitrate import AdaptiveBitrateEngine, BandwidthSimulator

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NanoStream API",
    description="Adaptive video delivery platform",
    version="1.0.0"
)

# Enable Prometheus metrics at /metrics
instrument_app(app)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
analyzer = ContentAnalyzer()
job_queue = JobQueue()
ml_selector = MLEncoderSelector()
cost_optimizer = CostOptimizer()

# Storage
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
async def root():
    """Serve the main control panel dashboard."""
    dashboard_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return RedirectResponse(url="/docs")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the NanoStream economics dashboard."""
    dashboard_path = os.path.join(os.path.dirname(__file__), "economics_dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api")
async def api_info():
    """API info."""
    return {
        "name": "NanoStream",
        "version": "1.0.0",
        "description": "Adaptive video delivery platform API",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "health": "/health",
        "metrics": "/metrics",
    }


@app.get("/uploads")
async def list_uploads():
    """List uploaded video files available for encoding."""
    files = []
    if os.path.exists(UPLOAD_DIR):
        for f in os.listdir(UPLOAD_DIR):
            filepath = os.path.join(UPLOAD_DIR, f)
            if os.path.isfile(filepath):
                files.append({
                    'filename': f,
                    'path': filepath,
                    'size_mb': round(os.path.getsize(filepath) / 1024 / 1024, 2),
                })
    return {'uploads': files, 'upload_dir': UPLOAD_DIR}


@app.post("/analyze")
async def analyze_video(file: UploadFile = File(...)):
    """Analyze video content.
    
    Args:
        file: Video file to analyze
        
    Returns:
        Content analysis results
    """
    try:
        # Save uploaded file
        filepath = f"{UPLOAD_DIR}/{file.filename}"
        with open(filepath, "wb") as f:
            f.write(await file.read())
        
        # Analyze
        t0 = time.time()
        analysis = analyzer.analyze(filepath)
        metrics.record_analysis(time.time() - t0)
        
        # Get ML recommendation
        recommendation = ml_selector.get_recommendation(analysis['metrics'])
        
        return {
            'analysis': analysis,
            'recommendation': recommendation,
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/encode")
async def encode_video(
    job_id: Optional[str] = None,
    video_path: str = None,
    codec: str = 'h265',
    max_resolution: str = '1080p',
):
    """Submit video encoding job.
    
    Args:
        job_id: Optional existing job ID
        video_path: Path to video
        codec: Encoding codec
        max_resolution: Maximum resolution
        
    Returns:
        Job information
    """
    try:
        if not video_path:
            raise ValueError("video_path required")
        
        # Resolve path — check if it's in uploads directory
        if not os.path.isabs(video_path):
            video_path = os.path.join(UPLOAD_DIR, video_path)
        if not os.path.exists(video_path):
            raise ValueError(f"Video file not found: {video_path}. Upload a video first via /analyze, then use the filename.")
        
        # Generate bitrate ladder
        import cv2
        cap = cv2.VideoCapture(video_path)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        
        if width == 0 or height == 0:
            raise ValueError(f"Could not read video dimensions from: {video_path}. File may be corrupted or unsupported.")
        
        ladder_gen = BitrateLadder(width, height)
        resolutions = ladder_gen.generate(max_resolution=max_resolution)
        
        # Submit job
        job_id = job_queue.submit(
            video_path,
            resolutions,
            codec=codec,
        )
        metrics.job_submitted(codec)
        
        return {
            'job_id': job_id,
            'status': 'submitted',
            'video_path': video_path,
            'resolutions': len(resolutions),
        }
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status.
    
    Args:
        job_id: Job ID
        
    Returns:
        Job status
    """
    status = job_queue.status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@app.get("/jobs")
async def list_jobs(status: Optional[str] = None):
    """List all jobs.
    
    Args:
        status: Optional status filter
        
    Returns:
        List of jobs
    """
    return job_queue.list_jobs(status=status)


@app.get("/queue/stats")
async def get_queue_stats():
    """Get queue statistics.
    
    Returns:
        Queue stats
    """
    return job_queue.stats()


@app.get("/abr/simulation")
async def simulate_abr(variants: Optional[List[Dict]] = None):
    """Simulate adaptive bitrate behavior.
    
    Args:
        variants: List of variant configs
        
    Returns:
        Simulation results
    """
    try:
        if not variants:
            variants = [
                {'name': '360p', 'bitrate_mbps': 0.8, 'width': 640, 'height': 360},
                {'name': '480p', 'bitrate_mbps': 1.5, 'width': 854, 'height': 480},
                {'name': '720p', 'bitrate_mbps': 3.0, 'width': 1280, 'height': 720},
                {'name': '1080p', 'bitrate_mbps': 5.0, 'width': 1920, 'height': 1080},
            ]
        
        abr = AdaptiveBitrateEngine(variants)
        scenarios = BandwidthSimulator.get_simulation_scenarios()
        results = BandwidthSimulator.simulate_quality_selection(abr, scenarios)
        
        return results
    except Exception as e:
        logger.error(f"ABR simulation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cost/compare")
async def compare_codec_costs(
    video_size_gb: float,
    video_duration_minutes: float,
    monthly_views: int,
    num_resolutions: int = 4,
):
    """Compare costs across codecs.
    
    Args:
        video_size_gb: Video size
        video_duration_minutes: Duration
        monthly_views: Expected views
        num_resolutions: Number of resolutions
        
    Returns:
        Cost comparison
    """
    try:
        costs = cost_optimizer.compare_codec_costs(
            video_size_gb,
            video_duration_minutes,
            monthly_views,
            num_resolutions,
        )
        return {'costs': costs}
    except Exception as e:
        logger.error(f"Cost comparison failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint.
    
    Returns:
        Health status
    """
    queue_stats = job_queue.stats()
    return {
        'status': 'healthy',
        'queue_stats': queue_stats,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

