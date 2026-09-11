import json
import random
import threading
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.models.schemas import (
    IoTSensorReading,
    WardStatus,
    CitizenSOSRequest,
    CitizenSOSRecord,
    DispatchAlertRequest,
    DispatchAlertRecord
)
from app.models.risk_engine import RiskEngine
from app.services.historical_db import HistoricalDBService
from app.services.weather_service import WeatherService

logger = logging.getLogger("pahad_rakshak_iot_simulator")

# How often (seconds) the background thread refreshes real weather per ward.
# Open-Meteo is free/no-key but this keeps calls reasonable and avoids
# hammering the API on every websocket tick (which fires every ~2.5s).
WEATHER_REFRESH_INTERVAL_SECONDS = 600  # 10 minutes


class IoTSimulatorService:
    def __init__(self):
        # Load baseline wards and sensors
        with open("app/data/village_wards.json", "r", encoding="utf-8") as f:
            self.wards_data = json.load(f)
        with open("app/data/sensor_nodes.json", "r", encoding="utf-8") as f:
            self.sensor_data = json.load(f)

        # Dynamic state storage
        self.simulation_scenario = "NORMAL"  # NORMAL, CLOUDBURST, SATURATION_SPIKE, FLASH_SURGE, GLOF
        self.target_ward_id = "W-UK-CHM-04"  # Default active test ward for crisis scenario

        # Ward dynamic conditions
        self.ward_states: Dict[str, Dict[str, float]] = {}
        for w in self.wards_data:
            wid = w["ward_id"]
            self.ward_states[wid] = {
                "rainfall_1h_mm": 15.0 if wid == "W-UK-CHM-04" else (12.0 if wid == "W-UK-RDR-06" else 5.0),
                "rainfall_24h_mm": 65.0 if wid == "W-UK-CHM-04" else 20.0,
                "volumetric_water_content": 0.38 if wid == "W-UK-CHM-04" else 0.22,
                "river_water_level_m": 1982.5 if wid == "W-UK-CHM-04" else (w["river_danger_level_m"] - 3.0)
            }

        # Real weather cache: ward_id -> {"rainfall_1h_mm", "rainfall_24h_mm", "temperature_c", "fetched_at", "source"}
        self.real_weather_cache: Dict[str, Dict[str, Any]] = {}
        self._weather_lock = threading.Lock()
        self._start_weather_refresh_thread()

        # Citizen SOS records store
        self.sos_records: List[CitizenSOSRecord] = [
            CitizenSOSRecord(
                sos_id="SOS-8821",
                ward_id="W-UK-CHM-04",
                ward_name="Raini Village - Rishi Ganga Basin (Ward 4)",
                citizen_name="Rameshwar Negi",
                phone_number="+91-98765-43210",
                lat=30.4820,
                lng=79.6950,
                people_count=4,
                situation_desc="Water rising rapidly near lower terrace footbridge. Slope debris cracking above cowshed.",
                requires_medical=True,
                timestamp="10 mins ago",
                status="PENDING"
            ),
            CitizenSOSRecord(
                sos_id="SOS-8820",
                ward_id="W-UK-RDR-06",
                ward_name="Kedarnath Mandakini Basin (Ward 6)",
                citizen_name="Sunil Joshi",
                phone_number="+91-94120-11223",
                lat=30.7330,
                lng=79.0660,
                people_count=6,
                situation_desc="Mandakini stream overflowing into path. 6 pilgrims seeking ridge shelter guidance.",
                requires_medical=False,
                timestamp="25 mins ago",
                status="DISPATCHED"
            )
        ]

        # Dispatch history log
        self.dispatch_history: List[DispatchAlertRecord] = [
            DispatchAlertRecord(
                dispatch_id="DSP-1092",
                ward_id="W-UK-CHM-04",
                ward_name="Raini Village (Ward 4)",
                severity="RED",
                message="EMERGENCY EVACUATION: Extreme flash flood & landslide risk. Evacuate via Nanda Devi High Trail immediately.",
                channels=["SMS", "PUBLIC_SIREN", "VHF_RADIO"],
                recipients_count=1240,
                timestamp="05 mins ago",
                status="DELIVERED"
            )
        ]

    # ------------------------------------------------------------------
    # Real weather integration
    # ------------------------------------------------------------------

    def _start_weather_refresh_thread(self):
        """
        Spawns a daemon background thread that periodically pulls real
        rainfall/temperature data from Open-Meteo for every ward with
        resolvable coordinates, and stores it in self.real_weather_cache.
        Runs an initial fetch immediately (non-blocking to the caller since
        it's on its own thread), then repeats every
        WEATHER_REFRESH_INTERVAL_SECONDS.
        """
        thread = threading.Thread(target=self._weather_refresh_loop, daemon=True)
        thread.start()

    def _weather_refresh_loop(self):
        while True:
            self._refresh_all_ward_weather()
            time.sleep(WEATHER_REFRESH_INTERVAL_SECONDS)

    def _refresh_all_ward_weather(self):
        for ward in self.wards_data:
            wid = ward["ward_id"]
            centroid = WeatherService.compute_ward_centroid(ward)
            if centroid is None:
                logger.warning(
                    f"No usable lat/lng found for ward {wid}; skipping real weather fetch, "
                    f"keeping simulated rainfall."
                )
                continue

            lat, lng = centroid
            result = WeatherService.fetch_rainfall_data(lat, lng)
            if result is None:
                # Leave any previously cached value in place; don't clobber
                # good data with a failed fetch.
                continue

            with self._weather_lock:
                result["fetched_at"] = datetime.now(timezone.utc)
                self.real_weather_cache[wid] = result

    def _apply_real_weather_if_available(self, wid: str, state: Dict[str, float]):
        """
        Overwrites the given ward's rainfall fields with real weather data
        when available AND the scenario is NORMAL. Manual demo scenarios
        (CLOUDBURST, SATURATION_SPIKE, FLASH_SURGE, GLOF) intentionally keep
        their synthetic injected values on the target ward so testing alerts
        still works.
        """
        if self.simulation_scenario != "NORMAL":
            return

        with self._weather_lock:
            cached = self.real_weather_cache.get(wid)

        if cached is None:
            return

        state["rainfall_1h_mm"] = cached["rainfall_1h_mm"]
        state["rainfall_24h_mm"] = cached["rainfall_24h_mm"]

    def get_weather_cache_snapshot(self) -> Dict[str, Any]:
        """Exposes the current real-weather cache, useful for a debug/health endpoint."""
        with self._weather_lock:
            return {
                wid: {
                    **v,
                    "fetched_at": v["fetched_at"].isoformat() if isinstance(v.get("fetched_at"), datetime) else v.get("fetched_at")
                }
                for wid, v in self.real_weather_cache.items()
            }

    # ------------------------------------------------------------------
    # Existing simulator logic
    # ------------------------------------------------------------------

    def set_simulation_scenario(self, scenario: str, target_ward_id: str = "W-UK-CHM-04", custom_rainfall: Optional[float] = None):
        """
        Triggers emergency crisis scenarios for testing early warning alerts.
        """
        self.simulation_scenario = scenario
        self.target_ward_id = target_ward_id

        if scenario == "CLOUDBURST":
            rain = custom_rainfall if custom_rainfall is not None else 125.0
            self.ward_states[target_ward_id]["rainfall_1h_mm"] = rain
            self.ward_states[target_ward_id]["rainfall_24h_mm"] = 285.0
            self.ward_states[target_ward_id]["volumetric_water_content"] = 0.44
            self.ward_states[target_ward_id]["river_water_level_m"] += 6.5
        elif scenario == "SATURATION_SPIKE":
            self.ward_states[target_ward_id]["rainfall_1h_mm"] = 55.0
            self.ward_states[target_ward_id]["rainfall_24h_mm"] = 180.0
            self.ward_states[target_ward_id]["volumetric_water_content"] = 0.446  # Near max saturation (0.45)
        elif scenario == "FLASH_SURGE":
            self.ward_states[target_ward_id]["rainfall_1h_mm"] = 70.0
            self.ward_states[target_ward_id]["river_water_level_m"] += 8.2
        elif scenario == "GLOF":
            # Glacial Lake Outburst Flood
            self.ward_states[target_ward_id]["rainfall_1h_mm"] = 45.0
            self.ward_states[target_ward_id]["river_water_level_m"] += 12.0
            self.ward_states[target_ward_id]["volumetric_water_content"] = 0.442
        elif scenario == "NORMAL":
            for wid in self.ward_states:
                self.ward_states[wid]["rainfall_1h_mm"] = random.uniform(2.0, 10.0)
                self.ward_states[wid]["volumetric_water_content"] = random.uniform(0.18, 0.28)
                # Reset river levels near safe baseline
                for w in self.wards_data:
                    if w["ward_id"] == wid:
                        self.ward_states[wid]["river_water_level_m"] = w["river_danger_level_m"] - 3.5
            # Immediately try to overlay real weather on top of the reset baseline
            # rather than waiting up to WEATHER_REFRESH_INTERVAL_SECONDS.
            for wid, state in self.ward_states.items():
                self._apply_real_weather_if_available(wid, state)

    def tick(self):
        """
        Advances telemetry state by one timestamp tick with realistic micro-variations.
        Real weather (when available and scenario is NORMAL) takes priority over
        the synthetic random walk for rainfall fields.
        """
        for wid, state in self.ward_states.items():
            if self.simulation_scenario == "CLOUDBURST" and wid == self.target_ward_id:
                state["rainfall_1h_mm"] = min(160.0, state["rainfall_1h_mm"] + random.uniform(0.2, 1.2))
                state["volumetric_water_content"] = min(0.449, state["volumetric_water_content"] + 0.001)
                state["river_water_level_m"] += random.uniform(0.04, 0.12)
            elif self.simulation_scenario == "NORMAL":
                state["rainfall_1h_mm"] = max(0.0, state["rainfall_1h_mm"] + random.uniform(-0.3, 0.3))
                state["volumetric_water_content"] = min(0.40, max(0.15, state["volumetric_water_content"] + random.uniform(-0.002, 0.002)))
                self._apply_real_weather_if_available(wid, state)

    def get_latest_sensor_readings(self) -> List[IoTSensorReading]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        readings = []
        for node in self.sensor_data:
            wid = node["ward_id"]
            stype = node["sensor_type"]
            val = node["default_value"]

            if wid in self.ward_states:
                state = self.ward_states[wid]
                if stype == "rain_gauge":
                    val = state["rainfall_1h_mm"] + random.uniform(-0.2, 0.2)
                elif stype == "soil_moisture":
                    val = (state["volumetric_water_content"] * 100.0) + random.uniform(-0.1, 0.1)
                elif stype == "river_gauge":
                    val = state["river_water_level_m"] + random.uniform(-0.05, 0.05)

            readings.append(IoTSensorReading(
                sensor_id=node["sensor_id"],
                ward_id=wid,
                sensor_type=stype,
                name=node["name"],
                lat=node["lat"],
                lng=node["lng"],
                value=round(val, 2),
                unit=node["unit"],
                timestamp=now,
                battery_level=round(90.0 + random.uniform(0, 9.9), 1),
                rssi_dbm=random.randint(-72, -58),
                status="ONLINE"
            ))
        return readings

    def get_all_ward_statuses(self) -> List[WardStatus]:
        self.tick()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        ward_statuses = []

        for ward in self.wards_data:
            wid = ward["ward_id"]
            state = self.ward_states.get(wid, {
                "rainfall_1h_mm": 5.0,
                "rainfall_24h_mm": 20.0,
                "volumetric_water_content": 0.20,
                "river_water_level_m": 1000.0
            })

            # Calculate risk using physical risk engine
            risk_eval = RiskEngine.evaluate_ward_risk(
                slope_angle_deg=ward["avg_slope_deg"],
                cohesion_kpa=ward["cohesion_kpa"],
                friction_angle_deg=ward["friction_angle_deg"],
                soil_depth_m=ward["soil_depth_m"],
                volumetric_water_content=state["volumetric_water_content"],
                rainfall_1h_mm=state["rainfall_1h_mm"],
                rainfall_24h_mm=state["rainfall_24h_mm"],
                river_water_level_m=state["river_water_level_m"],
                river_danger_level_m=ward["river_danger_level_m"],
                historical_disasters_count=ward["historical_disasters_count"],
                population=ward["population"]
            )

            ward_statuses.append(WardStatus(
                ward_id=wid,
                ward_name=ward["ward_name"],
                district=ward["district"],
                state=ward["state"],
                population=ward["population"],
                elevation_m=ward["elevation_m"],
                avg_slope_deg=ward["avg_slope_deg"],
                risk_level=risk_eval["risk_level"],
                risk_score=risk_eval["risk_score"],
                factor_of_safety=risk_eval["factor_of_safety"],
                rainfall_1h_mm=round(state["rainfall_1h_mm"], 1),
                rainfall_24h_mm=round(state["rainfall_24h_mm"], 1),
                soil_saturation_pct=round((state["volumetric_water_content"] / 0.45) * 100.0, 1),
                river_water_level_m=round(state["river_water_level_m"], 2),
                river_danger_level_m=ward["river_danger_level_m"],
                estimated_lead_time_min=risk_eval["estimated_lead_time_min"],
                historical_disasters_count=ward["historical_disasters_count"],
                recommended_action=risk_eval["recommended_action"],
                last_updated=now,
                polygon=ward["polygon"],
                evacuation_routes=ward.get("evacuation_routes", ["High-Ground Trail"]),
                shelter_locations=ward.get("shelter_locations", ["Community Relief Camp"])
            ))

        return ward_statuses

    def add_citizen_sos(self, req: CitizenSOSRequest) -> CitizenSOSRecord:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        # Match nearest ward if none given
        ward_name = "Hilly Sector"
        target_wid = req.ward_id or "W-UK-CHM-04"
        for w in self.wards_data:
            if w["ward_id"] == target_wid:
                ward_name = w["ward_name"]
                break

        record = CitizenSOSRecord(
            sos_id=f"SOS-{random.randint(1000, 9999)}",
            ward_id=target_wid,
            ward_name=ward_name,
            citizen_name=req.citizen_name,
            phone_number=req.phone_number,
            lat=req.lat,
            lng=req.lng,
            people_count=req.people_count,
            situation_desc=req.situation_desc,
            requires_medical=req.requires_medical,
            timestamp=now,
            status="PENDING"
        )
        self.sos_records.insert(0, record)
        return record

    def get_citizen_sos_list(self) -> List[CitizenSOSRecord]:
        return self.sos_records

    def update_sos_status(self, sos_id: str, new_status: str) -> bool:
        for r in self.sos_records:
            if r.sos_id == sos_id:
                r.status = new_status
                return True
        return False

    def add_dispatch_alert(self, req: DispatchAlertRequest) -> DispatchAlertRecord:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        ward_name = "Target Ward"
        pop = 1000
        for w in self.wards_data:
            if w["ward_id"] == req.ward_id:
                ward_name = w["ward_name"]
                pop = w["population"]
                break

        msg = req.custom_message or f"ALERT: Immediate flash flood / landslide warning in {ward_name}. Move to high ground!"
        record = DispatchAlertRecord(
            dispatch_id=f"DSP-{random.randint(1000, 9999)}",
            ward_id=req.ward_id,
            ward_name=ward_name,
            severity=req.severity or "RED",
            message=msg,
            channels=req.channels,
            recipients_count=pop,
            timestamp=now,
            status="DELIVERED"
        )
        self.dispatch_history.insert(0, record)
        return record

    def get_dispatch_history(self) -> List[DispatchAlertRecord]:
        return self.dispatch_history

iot_simulator_instance = IoTSimulatorService()
