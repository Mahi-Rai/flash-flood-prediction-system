import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.models.schemas import (
    IoTSensorReading,
    WardStatus,
    HistoricalDisasterEvent,
    SlopeParameters,
    AIAdvisoryRequest,
    AIAdvisoryResponse,
    CitizenSOSRequest,
    CitizenSOSRecord,
    DispatchAlertRequest,
    DispatchAlertRecord,
    AIChatRequest,
    AIChatResponse,
    PhysicsSensitivityRequest
)
from app.models.physics import SlopeStabilityPhysics
from app.models.risk_engine import RiskEngine
from app.services.iot_simulator import iot_simulator_instance
from app.services.historical_db import HistoricalDBService
from app.services.gemini_advisor import GeminiAdvisorService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pahad_rakshak_prediction_system")

app = FastAPI(
    title="PahadRakshak Flash Flood & Landslide Prediction System API",
    description="Hyper-local disaster prediction platform for hilly regions integrating multi-source IoT telemetry, geotechnical slope physics, and Gemini AI.",
    version="3.3.0"
)

# Mount static folder for dashboard UI and assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)

@app.get("/manifest.json")
async def serve_manifest():
    manifest_path = os.path.join(static_dir, "manifest.json")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    return {"name": "PahadRakshak Flash Flood Prediction System"}

@app.get("/sw.js")
async def serve_service_worker():
    sw_path = os.path.join(static_dir, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    return PlainTextResponse("// Service Worker stub", media_type="application/javascript")

@app.get("/api/weather/debug")
async def weather_debug_snapshot():
    """
    Exposes the real-time Open-Meteo weather cache per ward for debugging /
    verifying that live weather data is actually being pulled in.
    """
    return iot_simulator_instance.get_weather_cache_snapshot()

@app.get("/api/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "system": "PahadRakshak Flash Flood & Landslide Prediction Platform",
        "telemetry_stream": iot_simulator_instance.simulation_scenario,
        "active_wards_monitored": len(iot_simulator_instance.wards_data),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/wards", response_model=List[WardStatus])
async def get_all_wards():
    return iot_simulator_instance.get_all_ward_statuses()

@app.get("/api/wards/{ward_id}", response_model=WardStatus)
async def get_ward_by_id(ward_id: str):
    wards = iot_simulator_instance.get_all_ward_statuses()
    for w in wards:
        if w.ward_id == ward_id:
            return w
    raise HTTPException(status_code=404, detail=f"Ward {ward_id} not found")

@app.get("/api/sensors", response_model=List[IoTSensorReading])
async def get_sensors():
    return iot_simulator_instance.get_latest_sensor_readings()

@app.get("/api/historical-events", response_model=List[HistoricalDisasterEvent])
async def get_historical_events():
    return HistoricalDBService.get_all_events()

@app.post("/api/predict")
async def predict_slope_stability(params: SlopeParameters):
    physics_res = SlopeStabilityPhysics.calculate_factor_of_safety(
        slope_angle_deg=params.slope_angle_deg,
        cohesion_kpa=params.cohesion_kpa,
        friction_angle_deg=params.friction_angle_deg,
        soil_depth_m=params.soil_depth_m,
        volumetric_water_content=params.volumetric_water_content,
        porosity_sat_vwc=params.saturation_vwc,
        soil_dry_weight_kn_m3=params.soil_unit_weight_kn_m3,
        root_cohesion_kpa=params.root_cohesion_kpa
    )
    return physics_res

@app.post("/api/physics/sensitivity")
async def calculate_physics_sensitivity(req: PhysicsSensitivityRequest):
    return SlopeStabilityPhysics.calculate_sensitivity_curve(
        slope_angle_deg=req.slope_angle_deg,
        cohesion_kpa=req.cohesion_kpa,
        friction_angle_deg=req.friction_angle_deg,
        soil_depth_m=req.soil_depth_m
    )

class ScenarioRequest(BaseModel):
    scenario: str  # 'NORMAL', 'CLOUDBURST', 'SATURATION_SPIKE', 'FLASH_SURGE', 'GLOF'
    ward_id: str = "W-UK-CHM-04"
    custom_rainfall: Optional[float] = None

@app.post("/api/simulator/scenario")
async def set_simulator_scenario(req: ScenarioRequest):
    iot_simulator_instance.set_simulation_scenario(req.scenario, req.ward_id, req.custom_rainfall)
    return {
        "status": "SUCCESS",
        "active_scenario": req.scenario,
        "target_ward_id": req.ward_id,
        "message": f"Scenario {req.scenario} activated for {req.ward_id}"
    }

@app.post("/api/ai-advisory", response_model=AIAdvisoryResponse)
async def get_ai_advisory(req: AIAdvisoryRequest):
    wards = iot_simulator_instance.get_all_ward_statuses()
    target_ward = None
    for w in wards:
        if w.ward_id == req.ward_id:
            target_ward = w
            break
    
    if not target_ward and wards:
        target_ward = wards[0]

    if not target_ward:
        raise HTTPException(status_code=404, detail="No ward data available")

    return GeminiAdvisorService.generate_advisory(target_ward, req)

@app.post("/api/ai-chat", response_model=AIChatResponse)
async def ai_copilot_chat(req: AIChatRequest):
    wards = iot_simulator_instance.get_all_ward_statuses()
    return GeminiAdvisorService.chat_copilot(req, wards)

@app.post("/api/citizen/sos", response_model=CitizenSOSRecord)
async def submit_citizen_sos(req: CitizenSOSRequest):
    return iot_simulator_instance.add_citizen_sos(req)

@app.get("/api/citizen/sos", response_model=List[CitizenSOSRecord])
async def get_citizen_sos_list():
    return iot_simulator_instance.get_citizen_sos_list()

class SOSStatusUpdate(BaseModel):
    status: str  # PENDING, DISPATCHED, RESOLVED

@app.post("/api/citizen/sos/{sos_id}/status")
async def update_sos_status(sos_id: str, body: SOSStatusUpdate):
    ok = iot_simulator_instance.update_sos_status(sos_id, body.status)
    if not ok:
        raise HTTPException(status_code=404, detail=f"SOS record {sos_id} not found")
    return {"status": "SUCCESS", "sos_id": sos_id, "new_status": body.status}

@app.post("/api/alerts/dispatch", response_model=DispatchAlertRecord)
async def dispatch_emergency_alert(req: DispatchAlertRequest):
    return iot_simulator_instance.add_dispatch_alert(req)

@app.get("/api/alerts/history", response_model=List[DispatchAlertRecord])
async def get_dispatch_history():
    return iot_simulator_instance.get_dispatch_history()

@app.get("/api/reports/iap", response_class=PlainTextResponse)
async def generate_incident_action_plan(ward_id: Optional[str] = "W-UK-CHM-04"):
    wards = iot_simulator_instance.get_all_ward_statuses()
    target_ward = next((w for w in wards if w.ward_id == ward_id), wards[0] if wards else None)
    now = datetime.now(timezone.utc).strftime("%d-%b-%Y %H:%M:%S UTC")

    if not target_ward:
        return "NO DATA AVAILABLE"

    lines = [
        "================================================================================",
        "                    PAHADRAKSHAK - INCIDENT ACTION PLAN (IAP)                  ",
        "================================================================================",
        f"OPERATIONAL PERIOD: {now} | OPERATIONAL SECTOR: {target_ward.district.upper()}, {target_ward.state.upper()}",
        f"INCIDENT NAME     : FLASH FLOOD & LANDSLIDE PRE-DISASTER DEPLOYMENT",
        f"TARGET WARD       : {target_ward.ward_name} (ID: {target_ward.ward_id})",
        "--------------------------------------------------------------------------------",
        "1. CURRENT SITUATION & GEOTECHNICAL TELEMETRY",
        f"   - Hazard Alert Level   : {target_ward.risk_level} (Composite Risk Score: {target_ward.risk_score}/100)",
        f"   - Factor of Safety     : FoS = {target_ward.factor_of_safety} (Threshold < 1.0 = Critical)",
        f"   - Rainfall Rate        : 1-Hour: {target_ward.rainfall_1h_mm} mm/h | 24-Hour: {target_ward.rainfall_24h_mm} mm",
        f"   - Soil Moisture (VWC)  : {target_ward.soil_saturation_pct}% Saturation",
        f"   - River Water Level    : {target_ward.river_water_level_m} m (Danger Mark: {target_ward.river_danger_level_m} m)",
        f"   - Lead Time Remaining  : {target_ward.estimated_lead_time_min} MINUTES",
        "",
        "2. STRATEGIC OBJECTIVES",
        f"   a. Safely evacuate {target_ward.population} residents from {target_ward.ward_name} to designated shelters.",
        f"   b. Cordon off debris runout paths and low-lying riverbank sectors.",
        f"   c. Maintain comms via VHF Satellite Repeater Net-14.",
        "",
        "3. DESIGNATED EVACUATION TRACKS & RELIEF CENTERS",
        f"   - Primary Route: {target_ward.evacuation_routes[0] if target_ward.evacuation_routes else 'High Ridge Path'}",
        f"   - Primary Camp : {target_ward.shelter_locations[0] if target_ward.shelter_locations else 'Government Secondary School'}",
        "",
        "4. TEAM ASSIGNMENTS & RESOURCE ALLOCATION",
        "   - Team Alpha : Ridge path traffic management & vulnerable citizen transport",
        "   - Team Bravo : River sector swiftwater rescue & ropeway bridging",
        "   - Heavy Plant: 2x JCB Earthmovers positioned at sector gateway",
        "   - Medical    : 1x Mobile Emergency Treatment Camp with 50-bed triage",
        "================================================================================",
        "APPROVED BY: PAHADRAKSHAK OPERATIONS COMMANDER / DISTRICT DISASTER AUTHORITY",
        "================================================================================"
    ]
    return "\n".join(lines)

# WebSocket endpoint for real-time telemetry streaming
@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket telemetry client connected")
    try:
        while True:
            wards = iot_simulator_instance.get_all_ward_statuses()
            sensors = iot_simulator_instance.get_latest_sensor_readings()
            payload = {
                "scenario": iot_simulator_instance.simulation_scenario,
                "target_ward_id": iot_simulator_instance.target_ward_id,
                "wards": [w.dict() for w in wards],
                "sensors": [s.dict() for s in sensors],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(2.5)
    except WebSocketDisconnect:
        logger.info("WebSocket telemetry client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
