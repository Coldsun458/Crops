import math
import httpx
from datetime import datetime, timezone
from typing import Dict, List

MSP_BENCHMARKS = {
    "Wheat": 2425.0,
    "Rice": 2320.0
}

# Statutory APMC Cess Rates by Origin State
APMC_CESS_RATES = {
    "Punjab": {"mandi_fee_pct": 2.0, "rdf_pct": 2.0},
    "Haryana": {"mandi_fee_pct": 2.0, "rdf_pct": 2.0},
    "Madhya Pradesh": {"mandi_fee_pct": 1.5, "rdf_pct": 0.0},
    "Rajasthan": {"mandi_fee_pct": 1.6, "rdf_pct": 0.0},
    "Default": {"mandi_fee_pct": 1.5, "rdf_pct": 0.5}
}

BAGGING_PREMIUMS = {
    "50KG_JUTE_GUNNY": {"name": "New Jute Bags (B-Twill)", "charge_per_qtl": 65.0},
    "50KG_PP_BAG": {"name": "HDPE Woven PP Bags", "charge_per_qtl": 28.0},
    "BULK_LOOSE_TIPPER": {"name": "Loose Bulk Tipper", "charge_per_qtl": 0.0}
}

CORRIDOR_WAYPOINTS = {
    "NH44_NORTH": {"name": "Ambala-Panipat Corridor", "lat": 30.0, "lon": 76.9},
    "NH48_WEST": {"name": "Jaipur-Kotputli Bypass", "lat": 27.5, "lon": 76.1},
    "NH46_CENTRAL": {"name": "Gwalior-Jhansi Segment", "lat": 25.8, "lon": 78.3}
}

MANDI_REGISTRY = {
    "Khanna": {"lat": 30.7071, "lon": 76.2197, "state": "Punjab", "fpo": "Doaba Agri Producers Co."},
    "Karnal": {"lat": 29.6857, "lon": 76.9905, "state": "Haryana", "fpo": "Karnal Green Fields FPO"},
    "Indore": {"lat": 22.7196, "lon": 75.8577, "state": "Madhya Pradesh", "fpo": "Malwa Kisan Samriddhi FPO"},
    "Kota": {"lat": 25.2138, "lon": 75.8648, "state": "Rajasthan", "fpo": "Hadoti Krishi Vikash"},
    "Bareilly": {"lat": 28.3670, "lon": 79.4304, "state": "Uttar Pradesh", "fpo": "Rohilkhand Kisan Union"},
    "Rajkot": {"lat": 22.3039, "lon": 70.8022, "state": "Gujarat", "fpo": "Saurashtra Agro Cluster"},
    "Bhatinda": {"lat": 30.2110, "lon": 74.9455, "state": "Punjab", "fpo": "Bathinda Farmers Producer Co."}
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

async def fetch_live_weather(lat: float, lon: float) -> dict:
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,precipitation&hourly=precipitation_probability&forecast_days=1"
    try:
        async with httpx.AsyncClient(timeout=3.5) as client:
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

    return {
        "crop_base_total": round(crop_base_total, 2),
        "total_bagging_cost": round(total_bagging_cost, 2),
        "freight_total": round(freight_total, 2),
        "apmc_cess_breakdown": {
            "mandi_fee": round(apmc_mandi_fee, 2),
            "rdf_fee": round(apmc_rdf_fee, 2),
            "total_cess": total_cess
        },
        "tcs_tax": tcs_tax,
        "insurance_cost": insurance_cost,
        "total_invoice": total_invoice,
        "net_landed_cost_per_qtl": net_landed_cost_per_qtl
    }

async def calculate_best_buy(
    commodity: str,
    buyer_city: str,
    required_qty_qtl: float,
    current_listings: List[Dict]
) -> List[Dict]:
    buyer_coords = CITY_COORDINATES.get(buyer_city, CITY_COORDINATES["Jalandhar"])
    analyzed_options = []
    benchmark_msp = MSP_BENCHMARKS.get(commodity, 2400.0)

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

        origin_weather = await fetch_live_weather(hub["lat"], hub["lon"])
        waypoint_weather = await fetch_live_weather(
            CORRIDOR_WAYPOINTS["NH44_NORTH"]["lat"],
            CORRIDOR_WAYPOINTS["NH44_NORTH"]["lon"]
        )
        effective_rain_risk = max(origin_weather["rain_prob"], waypoint_weather["rain_prob"])

        distance_km = haversine_distance(
            hub["lat"], hub["lon"], buyer_coords["lat"], buyer_coords["lon"]
        )

        transit_hours = round(distance_km / 45.0, 1)
        toll_estimate = round(distance_km * 0.85, 2)
        freight_per_qtl = round((distance_km * 0.038) + 25.0 + (toll_estimate / 100), 2)

        # Calculate comprehensive commercial invoice
        comm_breakdown = calculate_commercial_invoice(
            base_price_per_qtl=item["base_price_per_qtl"],
            quantity_qtl=required_qty_qtl,
            freight_per_qtl=freight_per_qtl,
            state_origin=hub.get("state", "Punjab"),
            bagging_type=item.get("bagging_type", "50KG_JUTE_GUNNY"),
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

        analyzed_options.append({
            **item,
            "distance_km": distance_km,
            "transit_hours": transit_hours,
            "freight_per_qtl": freight_per_qtl,
            "origin_weather": origin_weather,
            "waypoint_weather": waypoint_weather,
            "rain_risk_percent": int(effective_rain_risk * 100),
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
            "is_above_msp": msp_differential >= 0,
            "recommendation_score": min(99.9, composite_prob)
        })

    analyzed_options.sort(key=lambda x: x["recommendation_score"], reverse=True)
    return analyzed_options