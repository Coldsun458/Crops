import math
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

MSP_BENCHMARKS = {
    "Wheat": 2425.0,
    "Rice": 2320.0,
    "Mustard": 5650.0,
    "Maize": 2225.0,
    "Gram": 5440.0
}

# Statutory APMC Cess Rates by Origin State
APMC_CESS_RATES = {
    "Punjab": {"mandi_fee_pct": 2.0, "rdf_pct": 2.0},
    "Haryana": {"mandi_fee_pct": 2.0, "rdf_pct": 2.0},
    "Madhya Pradesh": {"mandi_fee_pct": 1.5, "rdf_pct": 0.0},
    "Rajasthan": {"mandi_fee_pct": 1.6, "rdf_pct": 0.0},
    "Uttar Pradesh": {"mandi_fee_pct": 2.0, "rdf_pct": 0.5},
    "Gujarat": {"mandi_fee_pct": 1.0, "rdf_pct": 0.5},
    "Default": {"mandi_fee_pct": 1.5, "rdf_pct": 0.5}
}

BAGGING_PREMIUMS = {
    "50KG_JUTE_GUNNY": {"name": "50 kg New Jute Bags (B-Twill)", "charge_per_qtl": 65.0},
    "50KG_PP_BAG": {"name": "50 kg HDPE Woven PP Bags", "charge_per_qtl": 28.0},
    "BULK_LOOSE_TIPPER": {"name": "Loose Bulk Tipper Loading", "charge_per_qtl": 0.0}
}

CORRIDOR_WAYPOINTS = {
    "NH44_NORTH": {"name": "Ambala-Panipat Corridor (NH-44)", "lat": 30.0, "lon": 76.9},
    "NH48_WEST": {"name": "Jaipur-Kotputli Bypass (NH-48)", "lat": 27.5, "lon": 76.1},
    "NH46_CENTRAL": {"name": "Gwalior-Jhansi Segment (NH-46)", "lat": 25.8, "lon": 78.3}
}

MANDI_REGISTRY = {
    "Khanna": {"lat": 30.7071, "lon": 76.2197, "state": "Punjab", "fpo": "Doaba Farmer Producer Company Ltd."},
    "Karnal": {"lat": 29.6857, "lon": 76.9905, "state": "Haryana", "fpo": "Taraori Basmati Growers Farmer Producer Co. Ltd."},
    "Indore": {"lat": 22.7196, "lon": 75.8577, "state": "Madhya Pradesh", "fpo": "Malwa Kisan Samriddhi Producer Co. Ltd."},
    "Kota": {"lat": 25.2138, "lon": 75.8648, "state": "Rajasthan", "fpo": "Hadoti Kisan Vikas Agro Producer Co. Ltd."},
    "Bareilly": {"lat": 28.3670, "lon": 79.4304, "state": "Uttar Pradesh", "fpo": "Rohilkhand Krishak Utpadan Producer Co. Ltd."},
    "Rajkot": {"lat": 22.3039, "lon": 70.8022, "state": "Gujarat", "fpo": "Saurashtra Kisan Samriddhi Agro Cluster Ltd."},
    "Bathinda": {"lat": 30.2110, "lon": 74.9455, "state": "Punjab", "fpo": "Bathinda Progressive Farmers Producer Co. Ltd."},
    "Bhatinda": {"lat": 30.2110, "lon": 74.9455, "state": "Punjab", "fpo": "Bathinda Progressive Farmers Producer Co. Ltd."}
}

CITY_COORDINATES = {
    "Jalandhar": {"lat": 31.3260, "lon": 75.5762},
    "Delhi": {"lat": 28.7041, "lon": 77.1025},
    "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Jaipur": {"lat": 26.9124, "lon": 75.7873},
    "Chandigarh": {"lat": 30.7333, "lon": 76.7794}
}

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c * 1.22, 1)

async def fetch_road_matrix(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> dict:
    """
    Fetches real highway network driving distance and duration via OpenStreetMap/OSRM.
    Falls back gracefully to calibrated Haversine distance on timeout or failure.
    """
    url = f"https://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}?overview=false"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                if data.get("routes"):
                    route = data["routes"][0]
                    distance_km = round(route["distance"] / 1000.0, 1)
                    # Commercial heavy truck pace adjustment (car duration * 1.32 factor)
                    transit_hours = round((route["duration"] / 3600.0) * 1.32, 1)
                    return {
                        "distance_km": distance_km,
                        "transit_hours": max(0.5, transit_hours),
                        "routing_source": "OSRM_ROAD_NETWORK"
                    }
    except Exception:
        pass

    # Mathematical fallback
    fallback_km = haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    return {
        "distance_km": fallback_km,
        "transit_hours": round(fallback_km / 45.0, 1),
        "routing_source": "HAVERSINE_ESTIMATION"
    }

async def fetch_live_weather(lat: float, lon: float) -> dict:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation&hourly=precipitation_probability&forecast_days=1"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                current = data.get("current", {})
                hourly = data.get("hourly", {})
                rain_prob = max(hourly.get("precipitation_probability", [5])[:6]) / 100.0
                precip = current.get("precipitation", 0.0)

                condition = "Clear"
                if precip > 2.0 or rain_prob > 0.65:
                    condition = "Storm Alert"
                elif rain_prob > 0.3:
                    condition = "Scattered Rain"

                return {
                    "temp_c": current.get("temperature_2m", 28),
                    "condition": condition,
                    "rain_prob": round(rain_prob, 2)
                }
    except Exception:
        pass
    return {"temp_c": 29, "condition": "Clear", "rain_prob": 0.05}

def calculate_commercial_invoice(
    base_price_per_qtl: float,
    quantity_qtl: float,
    freight_per_qtl: float,
    state_origin: str,
    bagging_type: str = "50KG_JUTE_GUNNY",
    insurance_opted: bool = True
) -> dict:
    crop_base_total = base_price_per_qtl * quantity_qtl
    bagging_rate = BAGGING_PREMIUMS.get(bagging_type, BAGGING_PREMIUMS["50KG_JUTE_GUNNY"])["charge_per_qtl"]
    total_bagging_cost = bagging_rate * quantity_qtl
    freight_total = freight_per_qtl * quantity_qtl
    
    cess_rule = APMC_CESS_RATES.get(state_origin, APMC_CESS_RATES["Default"])
    apmc_mandi_fee = crop_base_total * (cess_rule["mandi_fee_pct"] / 100.0)
    apmc_rdf_fee = crop_base_total * (cess_rule["rdf_pct"] / 100.0)
    total_cess = round(apmc_mandi_fee + apmc_rdf_fee, 2)
    
    # 0.1% TCS on B2B agricultural commodity transactions exceeding statutory limits
    tcs_tax = round((crop_base_total + total_cess) * 0.001, 2)
    
    # 0.08% Transit Marine Insurance
    insurance_cost = round((crop_base_total + freight_total) * 0.0008, 2) if insurance_opted else 0.0
    
    total_invoice = round(crop_base_total + total_bagging_cost + freight_total + total_cess + tcs_tax + insurance_cost, 2)
    net_landed_cost_per_qtl = round(total_invoice / quantity_qtl, 2)

    base_per_qtl = round(base_price_per_qtl, 2)
    bagging_per_qtl = round(bagging_rate, 2)
    freight_qtl = round(freight_per_qtl, 2)
    apmc_cess_per_qtl = round(total_cess / quantity_qtl, 2)
    tcs_per_qtl = round(tcs_tax / quantity_qtl, 2)
    transit_risk_per_qtl = round(insurance_cost / quantity_qtl, 2)

    return {
        "crop_base_total": round(crop_base_total, 2),
        "total_bagging_cost": round(total_bagging_cost, 2),
        "freight_total": round(freight_total, 2),
        "apmc_cess_breakdown": {
            "mandi_fee": round(apmc_mandi_fee, 2),
            "rdf_fee": round(apmc_rdf_fee, 2),
            "total_cess": total_cess,
            "mandi_fee_pct": cess_rule["mandi_fee_pct"],
            "rdf_pct": cess_rule["rdf_pct"]
        },
        "tcs_tax": tcs_tax,
        "insurance_cost": insurance_cost,
        "total_invoice": total_invoice,
        "net_landed_cost_per_qtl": net_landed_cost_per_qtl,
        "formula_per_qtl": {
            "mandi_base_price": base_per_qtl,
            "packaging": bagging_per_qtl,
            "highway_freight": freight_qtl,
            "apmc_state_cess": apmc_cess_per_qtl,
            "tcs": tcs_per_qtl,
            "transit_risk": transit_risk_per_qtl,
            "net_landed_cost": net_landed_cost_per_qtl
        }
    }

async def calculate_best_buy(
    commodity: str,
    buyer_city: str,
    required_qty_qtl: float,
    current_listings: List[Dict]
) -> List[Dict]:
    buyer_coords = CITY_COORDINATES.get(buyer_city, CITY_COORDINATES["Jalandhar"])
    analyzed_options = []
    benchmark_msp = MSP_BENCHMARKS.get(commodity, 2425.0)

    for item in current_listings:
        if item["commodity"].lower() != commodity.lower():
            continue

        mandi_key = item["mandi"].split(",")[0].strip()
        hub = MANDI_REGISTRY.get(mandi_key, {
            "lat": buyer_coords["lat"] + 1.2,
            "lon": buyer_coords["lon"] + 1.2,
            "state": "Punjab",
            "fpo": item.get("fpo_name", "Regional FPO")
        })

        origin_state = hub.get("state", "Punjab")
        if origin_state in ["Madhya Pradesh", "Maharashtra"] or buyer_city == "Mumbai":
            waypoint_key = "NH46_CENTRAL"
        elif origin_state in ["Rajasthan", "Gujarat"] or buyer_city == "Jaipur":
            waypoint_key = "NH48_WEST"
        else:
            waypoint_key = "NH44_NORTH"

        waypoint_info = CORRIDOR_WAYPOINTS.get(waypoint_key, CORRIDOR_WAYPOINTS["NH44_NORTH"])

        # Fetch route geometry and concurrent origin/waypoint weather in parallel
        route_task = fetch_road_matrix(hub["lat"], hub["lon"], buyer_coords["lat"], buyer_coords["lon"])
        origin_weather_task = fetch_live_weather(hub["lat"], hub["lon"])
        waypoint_weather_task = fetch_live_weather(waypoint_info["lat"], waypoint_info["lon"])

        route_res, origin_weather, waypoint_weather = await asyncio.gather(
            route_task, origin_weather_task, waypoint_weather_task
        )

        distance_km = route_res["distance_km"]
        transit_hours = route_res["transit_hours"]
        routing_source = route_res["routing_source"]

        effective_rain_risk = max(origin_weather["rain_prob"], waypoint_weather["rain_prob"])

        # Granular freight breakdown
        toll_estimate_total = round(distance_km * 0.85, 2)
        toll_per_qtl = round(toll_estimate_total / 100.0, 2)
        fuel_distance_per_qtl = round(distance_km * 0.038, 2)
        base_handling_per_qtl = 25.0
        freight_per_qtl = round(fuel_distance_per_qtl + base_handling_per_qtl + toll_per_qtl, 2)

        bagging_type = item.get("bagging_type", "50KG_JUTE_GUNNY")

        # Spoilage risk calculation
        base_spoilage = 0.3
        rain_hazard = effective_rain_risk * (10.0 if bagging_type == "BULK_LOOSE_TIPPER" else 2.5)
        duration_hazard = (transit_hours / 24.0) * 1.0
        spoilage_risk_pct = round(min(25.0, base_spoilage + rain_hazard + duration_hazard), 1)

        if spoilage_risk_pct > 8.0:
            spoilage_alert = "CRITICAL: Rain corridor risk detected. Moisture-tight liners recommended."
        elif spoilage_risk_pct > 4.0:
            spoilage_alert = "MODERATE: Monitor weather conditions along highway checkpoints."
        else:
            spoilage_alert = "SAFE: Clear weather transit corridor window."

        comm_breakdown = calculate_commercial_invoice(
            base_price_per_qtl=item["base_price_per_qtl"],
            quantity_qtl=required_qty_qtl,
            freight_per_qtl=freight_per_qtl,
            state_origin=hub.get("state", "Punjab"),
            bagging_type=bagging_type,
            insurance_opted=True
        )

        net_landed_cost = comm_breakdown["net_landed_cost_per_qtl"]
        total_order_cost = comm_breakdown["total_invoice"]

        escrow_advance_20 = round(total_order_cost * 0.20, 2)
        escrow_dispatch_70 = round(total_order_cost * 0.70, 2)
        escrow_final_10 = round(total_order_cost * 0.10, 2)

        quality = item.get("assaying", {
            "foreign_matter_pct": 0.8,
            "broken_pct": 1.5,
            "protein_pct": 11.2,
            "grain_length_mm": 6.8
        })
        quality_score = max(0.0, 10.0 - (quality.get("foreign_matter_pct", 0.8) * 2) - (quality.get("broken_pct", 1.5) * 1.5))

        cost_factor = max(0.0, 1.0 - (net_landed_cost / 4200.0)) * 40
        time_factor = max(0.0, 1.0 - (transit_hours / 48.0)) * 25
        weather_factor = (1.0 - effective_rain_risk) * 20
        quality_factor = quality_score * 1.5

        composite_prob = round(cost_factor + time_factor + weather_factor + quality_factor, 1)
        msp_differential = round(item["base_price_per_qtl"] - benchmark_msp, 2)
        msp_diff_pct = round((msp_differential / benchmark_msp) * 100.0, 1) if benchmark_msp else 0.0
        msp_badge = f"+₹{msp_differential:0.2f} (+{msp_diff_pct}%)" if msp_differential >= 0 else f"-₹{abs(msp_differential):0.2f} ({msp_diff_pct}%)"

        analyzed_options.append({
            **item,
            "distance_km": distance_km,
            "transit_hours": transit_hours,
            "routing_source": routing_source,
            "freight_per_qtl": freight_per_qtl,
            "freight_breakdown": {
                "fuel_distance_per_qtl": fuel_distance_per_qtl,
                "base_handling_per_qtl": base_handling_per_qtl,
                "toll_share_per_qtl": toll_per_qtl,
                "total_toll_trip_estimate": toll_estimate_total
            },
            "origin_weather": origin_weather,
            "waypoint_weather": waypoint_weather,
            "waypoint_name": waypoint_info["name"],
            "rain_risk_percent": int(effective_rain_risk * 100),
            "spoilage_risk_pct": spoilage_risk_pct,
            "spoilage_alert": spoilage_alert,
            "commercial_breakdown": comm_breakdown,
            "net_landed_cost_per_qtl": net_landed_cost,
            "total_order_cost": total_order_cost,
            "escrow_milestones": {
                "advance_20": escrow_advance_20,
                "dispatch_70": escrow_dispatch_70,
                "final_10": escrow_final_10
            },
            "benchmark_msp": benchmark_msp,
            "msp_differential": msp_differential,
            "msp_diff_pct": msp_diff_pct,
            "msp_badge": msp_badge,
            "is_above_msp": msp_differential >= 0,
            "recommendation_score": min(99.9, composite_prob)
        })

    analyzed_options.sort(key=lambda x: x["recommendation_score"], reverse=True)
    return analyzed_options