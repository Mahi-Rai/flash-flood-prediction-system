from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class IoTSensorReading(BaseModel):
    sensor_id: str
    ward_id: str
    sensor_type: str  # 'rain_gauge', 'soil_moisture', 'pore_pressure', 'river_gauge', 'inclinometer'
    name: str
    lat: float
    lng: float
    value: float
    unit: str
    timestamp: str
    battery_level: float = 95.0
    rssi_dbm: int = -65
    status: str = "ONLINE"  # ONLINE, DEGRADED, OFFLINE

class SlopeParameters(BaseModel):
    slope_angle_deg: float = Field(..., description="Slope inclination in degrees")
    cohesion_kpa: float = Field(..., description="Effective soil cohesion in kPa")
    friction_angle_deg: float = Field(..., description="Soil internal friction angle in degrees")
    soil_unit_weight_kn_m3: float = Field(16.0, description="Unit weight of unsaturated soil in kN/m3")
    soil_depth_m: float = Field(..., description="Critical potential sliding depth in meters")
    volumetric_water_content: float = Field(..., description="Current soil moisture (0.0 to 1.0 VWC)")
    saturation_vwc: float = Field(0.45, description="Porosity / Saturated VWC")
    root_cohesion_kpa: float = Field(0.0, description="Additional root cohesion from forest cover in kPa")

class WardStatus(BaseModel):
    ward_id: str
    ward_name: str
    district: str
    state: str
    population: int
    elevation_m: float
    avg_slope_deg: float
    risk_level: str  # 'GREEN', 'YELLOW', 'ORANGE', 'RED'
    risk_score: float  # 0.0 to 100.0
    factor_of_safety: float  # Slope stability FoS
    rainfall_1h_mm: float
    rainfall_24h_mm: float
    soil_saturation_pct: float
    river_water_level_m: float
    river_danger_level_m: float
    estimated_lead_time_min: int
    historical_disasters_count: int
    recommended_action: str
    last_updated: str
    polygon: List[List[float]]  # GeoJSON coordinates [[lat, lng], ...]
    evacuation_routes: List[str] = []
    shelter_locations: List[str] = []

class HistoricalDisasterEvent(BaseModel):
    id: str
    location_name: str
    ward_id: str
    district: str
    state: str
    event_type: str  # 'Landslide', 'Flash Flood', 'Debris Flow', 'Cloudburst'
    date: str
    trigger_rainfall_mm: float
    casualties: int
    houses_damaged: int
    severity: str  # High, Critical, Moderate
    coordinates: List[float]  # [lat, lng]
    description: str

class AlertNotification(BaseModel):
    id: str
    ward_id: str
    ward_name: str
    severity: str  # 'GREEN', 'YELLOW', 'ORANGE', 'RED'
    title: str
    message: str
    suggested_lead_time_min: int
    evacuation_routes: List[str]
    shelter_locations: List[str]
    timestamp: str
    is_dispatched: bool = False

class AIAdvisoryRequest(BaseModel):
    ward_id: str
    scenario_notes: Optional[str] = None
    language: str = "English"  # "English", "Hindi", "Garhwali", "Punjabi", "Malayalam", "Bengali"

class AIAdvisoryResponse(BaseModel):
    ward_id: str
    ward_name: str
    district: str
    current_risk_level: str
    situation_summary: str
    tactical_ndrf_instructions: List[str]
    public_evacuation_broadcast: str
    resource_allocation_plan: List[str]
    timestamp: str

class CitizenSOSRequest(BaseModel):
    ward_id: Optional[str] = None
    citizen_name: str
    phone_number: str
    lat: float
    lng: float
    people_count: int = 1
    situation_desc: str
    requires_medical: bool = False

class CitizenSOSRecord(BaseModel):
    sos_id: str
    ward_id: str
    ward_name: str
    citizen_name: str
    phone_number: str
    lat: float
    lng: float
    people_count: int
    situation_desc: str
    requires_medical: bool
    timestamp: str
    status: str = "PENDING"  # PENDING, DISPATCHED, RESOLVED

class DispatchAlertRequest(BaseModel):
    ward_id: str
    channels: List[str] = ["SMS", "VHF_RADIO", "PUBLIC_SIREN", "WHATSAPP"]
    custom_message: Optional[str] = None
    severity: Optional[str] = None

class DispatchAlertRecord(BaseModel):
    dispatch_id: str
    ward_id: str
    ward_name: str
    severity: str
    message: str
    channels: List[str]
    recipients_count: int
    timestamp: str
    status: str = "DELIVERED"

class AIChatRequest(BaseModel):
    message: str
    ward_id: Optional[str] = "W-UK-CHM-04"
    history: Optional[List[Dict[str, str]]] = None

class AIChatResponse(BaseModel):
    reply: str
    suggested_actions: List[str] = []
    timestamp: str

class PhysicsSensitivityRequest(BaseModel):
    slope_angle_deg: float = 40.0
    cohesion_kpa: float = 10.0
    friction_angle_deg: float = 28.0
    soil_depth_m: float = 2.5
