import os
import uuid
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import engine, get_db, Base
import models
from engine import (
    CITY_COORDINATES,
    MANDI_REGISTRY,
    APMC_CESS_RATES,
    BAGGING_PREMIUMS,
    CORRIDOR_WAYPOINTS,
    MSP_BENCHMARKS,
    calculate_best_buy,
    calculate_commercial_invoice,
    haversine_distance
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="KisanVyapar Mandi Wholesaler Trading Desk",
    description="National B2B Grain Wholesaler Desk: Mandi Bhao, Landed Calculator, Double Auction & Escrow",
    version="5.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = os.getenv("SECRET_KEY", "agri-exchange-jwt-secret-key-2026")
JWT_ALGORITHM = os.getenv("ALGORITHM", "HS256")

WINDOW_RULES = {
    "EARLY_MORNING": {"label": "Early Morning (03:00 AM - 09:00 AM)", "start": "03:00", "end": "09:00", "max_capacity": 5},
    "LATE_MORNING_AFTERNOON": {"label": "Late Morning - Afternoon (10:00 AM - 02:00 PM)", "start": "10:00", "end": "14:00", "max_capacity": 4},
    "CLOSURE_EVENING": {"label": "Closure - Evening (08:00 PM - 10:00 PM)", "start": "20:00", "end": "22:00", "max_capacity": 3}
}

TRADING_ACCOUNTS = {
    "buyer@mill.com": {
        "id": "USR-BUYER-01",
        "name": "Aryan Foods & Flour Mills Pvt. Ltd.",
        "role": "BUYER",
        "city": "Jalandhar",
        "phone": "+91 98140-72641",
        "gstin": "03AAACA4582K1ZD",
        "address": "Plot No. 48-52, Focal Point Phase-V, GT Road Bypass, Jalandhar, Punjab - 144050"
    },
    "delhi.miller@agro.com": {
        "id": "USR-BUYER-02",
        "name": "Delhi Agro Processing Corp Pvt. Ltd.",
        "role": "BUYER",
        "city": "Delhi",
        "phone": "+91 98110-38492",
        "gstin": "07AABCD8821L1ZM",
        "address": "Shed No. 12-14, Lawrence Road Industrial Area, New Delhi - 110035"
    },
    "manager@doaba-fpo.org": {
        "id": "USR-FPO-01",
        "name": "Doaba Farmer Producer Company Ltd.",
        "role": "FPO",
        "city": "Khanna",
        "phone": "+91 98150-64219",
        "gstin": "03AAACD9182P1ZQ",
        "cin": "U01114PB2021PTC053912",
        "address": "Shop No. 24-B, New Grain Market, GT Road, Khanna, Punjab - 141401"
    },
    "karnal.fpo@haryana.org": {
        "id": "USR-FPO-02",
        "name": "Karnal Kisan Samriddhi Agro Producer Co. Ltd.",
        "role": "FPO",
        "city": "Karnal",
        "phone": "+91 94160-52834",
        "gstin": "06AABCK7712M1ZF",
        "cin": "U01111HR2020PTC048192",
        "address": "Old Grain Market, Taraori Road, Karnal, Haryana - 132001"
    },
    "admin@khanna-mandi.gov": {
        "id": "USR-ADMIN-01",
        "name": "Punjab Mandi Board (Khanna APMC Secretary)",
        "role": "MANDI_ADMIN",
        "city": "Khanna",
        "phone": "01628-224510",
        "office": "Market Committee Office, Asia's Biggest Grain Market, Khanna, Punjab - 141401"
    },
    "dispatch@truckunion.in": {
        "id": "USR-DRIVER-01",
        "name": "Punjab Highway Freight Fleet (Ludhiana Transporters Guild)",
        "role": "TRANSPORTER",
        "city": "Ludhiana",
        "phone": "+91 98142-88715",
        "address": "Transport Nagar, Ludhiana, Punjab - 141008"
    }
}
MOCK_USERS = TRADING_ACCOUNTS

def create_access_token(user_data: dict) -> str:
    payload = {
        **user_data,
        "exp": datetime.now(timezone.utc) + timedelta(days=2),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication token required.")
    token = authorization.split(" ")[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token.")

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        if user.get("role") not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied. Role required: {', '.join(self.allowed_roles)} (Active role: {user.get('role')})"
            )
        return user

def seed_initial_data(force: bool = False):
    db = next(get_db())
    
    # Check if existing data has placeholder patterns like 98765 or fake GSTIN
    has_dummy = db.query(models.Order).filter(models.Order.gstin.like("%AAAAA%")).first() is not None
    if force or has_dummy or db.query(models.CropLot).count() == 0:
        # Cleanly purge old synthetic test data
        db.query(models.Order).delete()
        db.query(models.BuyerBid).delete()
        db.query(models.SampleCourierRequest).delete()
        db.query(models.ScheduledSlot).delete()
        db.query(models.CropLot).delete()
        db.commit()

        initial_lots = [
            models.CropLot(
                id="FPO-LOT-101",
                commodity="Wheat",
                variety="PBW-725 Sharbati (PAU Certified Seed)",
                mandi="Khanna, Punjab",
                fpo_name="Doaba Farmer Producer Company Ltd.",
                base_price_per_qtl=2580.0,
                available_qty_qtl=1400.0,
                moisture_percent=11.2,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="PMB/M-FORM/2026/04/KHN-89412",
                assaying={
                    "foreign_matter_pct": 0.4,
                    "broken_pct": 1.1,
                    "protein_pct": 12.8,
                    "grain_length_mm": 7.1,
                    "lab_name": "Agmark Central Quality Control Laboratory, Regional Office, Patiala",
                    "nabl_cert_no": "TC-7412",
                    "grade": "Grade-A FAQ Sharbati"
                },
                farmer_members=[
                    {"member_id": "FARM-PB-01", "name": "Gurdev Singh", "village": "Alour, Khanna", "pool_qty_qtl": 600.0, "aadhar_masked": "XXXX-XXXX-4102", "bank_account": "30489182741", "ifsc": "SBIN0000662"},
                    {"member_id": "FARM-PB-02", "name": "Harbans Kaur", "village": "Libra, Khanna", "pool_qty_qtl": 450.0, "aadhar_masked": "XXXX-XXXX-7721", "bank_account": "0243000100293814", "ifsc": "PUNB0024300"},
                    {"member_id": "FARM-PB-03", "name": "Jagtar Singh", "village": "Bhadla, Khanna", "pool_qty_qtl": 350.0, "aadhar_masked": "XXXX-XXXX-9912", "bank_account": "02871000039281", "ifsc": "HDFC0000287"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-102",
                commodity="Wheat",
                variety="Malwa Lokwan Premium Gold",
                mandi="Indore, Madhya Pradesh",
                fpo_name="Malwa Kisan Samriddhi Producer Co. Ltd.",
                base_price_per_qtl=2420.0,
                available_qty_qtl=850.0,
                moisture_percent=10.5,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="MPAMB/AP-2026/IND-44192",
                assaying={
                    "foreign_matter_pct": 0.6,
                    "broken_pct": 1.4,
                    "protein_pct": 11.6,
                    "grain_length_mm": 6.8,
                    "lab_name": "MP State Agricultural Marketing Board Quality Assaying Lab, Laxmibai Nagar Mandi, Indore",
                    "nabl_cert_no": "TC-8120",
                    "grade": "Lokwan Premium Mill Grade"
                },
                farmer_members=[
                    {"member_id": "FARM-MP-11", "name": "Rajesh Patidar", "village": "Sanwer, Indore", "pool_qty_qtl": 500.0, "aadhar_masked": "XXXX-XXXX-1142", "bank_account": "01120100028194", "ifsc": "BARB0INDORE"},
                    {"member_id": "FARM-MP-12", "name": "Shivram Yadav", "village": "Depalpur, Indore", "pool_qty_qtl": 350.0, "aadhar_masked": "XXXX-XXXX-8821", "bank_account": "38910284712", "ifsc": "SBIN0030018"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-103",
                commodity="Wheat",
                variety="HD-3086 Superior Milling Grain",
                mandi="Bathinda, Punjab",
                fpo_name="Bathinda Progressive Farmers Producer Co. Ltd.",
                base_price_per_qtl=2490.0,
                available_qty_qtl=1100.0,
                moisture_percent=11.4,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="PMB/M-FORM/2026/04/BTI-77219",
                assaying={
                    "foreign_matter_pct": 0.5,
                    "broken_pct": 1.2,
                    "protein_pct": 12.1,
                    "grain_length_mm": 7.0,
                    "lab_name": "PAU Regional Research Quality Lab, Bathinda",
                    "nabl_cert_no": "TC-6891",
                    "grade": "Grade-A Milling Wheat"
                },
                farmer_members=[
                    {"member_id": "FARM-PB-21", "name": "Sukhwinder Singh", "village": "Goniana, Bathinda", "pool_qty_qtl": 600.0, "aadhar_masked": "XXXX-XXXX-3381", "bank_account": "31294819203", "ifsc": "SBIN0050074"},
                    {"member_id": "FARM-PB-22", "name": "Balwinder Kaur", "village": "Talwandi Sabo", "pool_qty_qtl": 500.0, "aadhar_masked": "XXXX-XXXX-5520", "bank_account": "0445000100381922", "ifsc": "PUNB0044500"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-104",
                commodity="Mustard",
                variety="Pusa Mustard-25 Bold Seed (41.5% Oil)",
                mandi="Kota, Rajasthan",
                fpo_name="Hadoti Kisan Vikas Agro Producer Co. Ltd.",
                base_price_per_qtl=5480.0,
                available_qty_qtl=600.0,
                moisture_percent=7.8,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="RSAMB/AP-2026/KOT-38910",
                assaying={
                    "foreign_matter_pct": 0.6,
                    "broken_pct": 0.8,
                    "protein_pct": 19.4,
                    "grain_length_mm": 3.2,
                    "oil_content_pct": 41.5,
                    "lab_name": "Rajasthan State Agricultural Marketing Board Assaying House, Bhamashah Mandi, Kota",
                    "nabl_cert_no": "TC-5934",
                    "grade": "High-Oil FAQ Bold Seed"
                },
                farmer_members=[
                    {"member_id": "FARM-RJ-01", "name": "Ramprasad Meena", "village": "Ladpura, Kota", "pool_qty_qtl": 350.0, "aadhar_masked": "XXXX-XXXX-6612", "bank_account": "02190100048192", "ifsc": "BARB0KOTAMA"},
                    {"member_id": "FARM-RJ-02", "name": "Gopal Gurjar", "village": "Sangod, Kota", "pool_qty_qtl": 250.0, "aadhar_masked": "XXXX-XXXX-9941", "bank_account": "32948192041", "ifsc": "SBIN0031264"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-105",
                commodity="Wheat",
                variety="UP-2628 Golden Flour Grain",
                mandi="Bareilly, Uttar Pradesh",
                fpo_name="Rohilkhand Krishak Utpadan Producer Co. Ltd.",
                base_price_per_qtl=2390.0,
                available_qty_qtl=950.0,
                moisture_percent=11.9,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="UPMP/M-PASS/2026/BLY-29104",
                assaying={
                    "foreign_matter_pct": 0.7,
                    "broken_pct": 1.5,
                    "protein_pct": 11.2,
                    "grain_length_mm": 6.7,
                    "lab_name": "UP State Agricultural Produce Market Board Quality Lab, Bareilly",
                    "nabl_cert_no": "TC-7119",
                    "grade": "Standard Flour Mill Grade"
                },
                farmer_members=[
                    {"member_id": "FARM-UP-01", "name": "Rameshwar Gangwar", "village": "Nawabganj, Bareilly", "pool_qty_qtl": 550.0, "aadhar_masked": "XXXX-XXXX-4421", "bank_account": "0372000100492817", "ifsc": "PUNB0037200"},
                    {"member_id": "FARM-UP-02", "name": "Dinesh Maurya", "village": "Faridpur, Bareilly", "pool_qty_qtl": 400.0, "aadhar_masked": "XXXX-XXXX-7719", "bank_account": "34918274192", "ifsc": "SBIN0001114"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-106",
                commodity="Wheat",
                variety="GW-496 Gujarat Sharbati Tukdi",
                mandi="Rajkot, Gujarat",
                fpo_name="Saurashtra Kisan Samriddhi Agro Cluster Ltd.",
                base_price_per_qtl=2620.0,
                available_qty_qtl=700.0,
                moisture_percent=10.2,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="GSAMB/GATEPASS/2026/RJK-78192",
                assaying={
                    "foreign_matter_pct": 0.3,
                    "broken_pct": 0.9,
                    "protein_pct": 13.1,
                    "grain_length_mm": 7.3,
                    "lab_name": "Gujarat State Agricultural Marketing Board Agmark Assaying Center, Rajkot",
                    "nabl_cert_no": "TC-8492",
                    "grade": "Export Grade Sharbati Tukdi"
                },
                farmer_members=[
                    {"member_id": "FARM-GJ-01", "name": "Mansukh Patel", "village": "Gondal, Rajkot", "pool_qty_qtl": 400.0, "aadhar_masked": "XXXX-XXXX-2291", "bank_account": "01190100039182", "ifsc": "BARB0GONDAL"},
                    {"member_id": "FARM-GJ-02", "name": "Bhavesh Jadeja", "village": "Jasdan, Rajkot", "pool_qty_qtl": 300.0, "aadhar_masked": "XXXX-XXXX-8812", "bank_account": "01240100028193", "ifsc": "BARB0JASDAN"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-201",
                commodity="Rice",
                variety="1121 Traditional Basmati Steam Grain",
                mandi="Karnal, Haryana",
                fpo_name="Taraori Basmati Growers Farmer Producer Co. Ltd.",
                base_price_per_qtl=4150.0,
                available_qty_qtl=450.0,
                moisture_percent=11.8,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="HSAMB/M-FORM/2026/04/KRL-55219",
                assaying={
                    "foreign_matter_pct": 0.2,
                    "broken_pct": 0.8,
                    "protein_pct": 8.5,
                    "grain_length_mm": 8.35,
                    "lab_name": "Haryana State Agricultural Marketing Board Basmati Quality Lab, Taraori (Karnal)",
                    "nabl_cert_no": "TC-6121",
                    "grade": "Extra Long Basmati Export Grade"
                },
                farmer_members=[
                    {"member_id": "FARM-HR-51", "name": "Naresh Kumar", "village": "Taraori, Karnal", "pool_qty_qtl": 250.0, "aadhar_masked": "XXXX-XXXX-9910", "bank_account": "35918274102", "ifsc": "SBIN0002494"},
                    {"member_id": "FARM-HR-52", "name": "Rakesh Sharma", "village": "Nilokheri, Karnal", "pool_qty_qtl": 200.0, "aadhar_masked": "XXXX-XXXX-5519", "bank_account": "1121000100381928", "ifsc": "PUNB0112100"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-301",
                commodity="Maize",
                variety="Yellow Feed Grade Premium",
                mandi="Kota, Rajasthan",
                fpo_name="Hadoti Kisan Vikas Agro Producer Co. Ltd.",
                base_price_per_qtl=2240.0,
                available_qty_qtl=800.0,
                moisture_percent=12.0,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="RSAMB/AP-2026/KOT-99412",
                assaying={
                    "foreign_matter_pct": 0.8,
                    "broken_pct": 1.2,
                    "protein_pct": 9.2,
                    "grain_length_mm": 5.4,
                    "lab_name": "Rajasthan State Agricultural Marketing Board, Kota",
                    "nabl_cert_no": "TC-5935",
                    "grade": "Feed Quality Grade-1"
                },
                farmer_members=[
                    {"member_id": "FARM-RJ-11", "name": "Mohan Lal", "village": "Digod, Kota", "pool_qty_qtl": 450.0, "aadhar_masked": "XXXX-XXXX-8812", "bank_account": "02190100055192", "ifsc": "BARB0KOTAMA"},
                    {"member_id": "FARM-RJ-12", "name": "Kishan Singh", "village": "Sultanpur, Kota", "pool_qty_qtl": 350.0, "aadhar_masked": "XXXX-XXXX-3341", "bank_account": "32948192088", "ifsc": "SBIN0031264"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-302",
                commodity="Maize",
                variety="Malwa Sweet Golden Corn",
                mandi="Indore, Madhya Pradesh",
                fpo_name="Malwa Kisan Samriddhi Producer Co. Ltd.",
                base_price_per_qtl=2210.0,
                available_qty_qtl=650.0,
                moisture_percent=11.5,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="MPAMB/AP-2026/IND-88129",
                assaying={
                    "foreign_matter_pct": 0.7,
                    "broken_pct": 1.1,
                    "protein_pct": 9.6,
                    "grain_length_mm": 5.6,
                    "lab_name": "MP State Marketing Board Quality Lab, Indore",
                    "nabl_cert_no": "TC-8122",
                    "grade": "Milling Grade Yellow Maize"
                },
                farmer_members=[
                    {"member_id": "FARM-MP-31", "name": "Dinesh Solanki", "village": "Mhow, Indore", "pool_qty_qtl": 350.0, "aadhar_masked": "XXXX-XXXX-7712", "bank_account": "01120100099194", "ifsc": "BARB0INDORE"},
                    {"member_id": "FARM-MP-32", "name": "Radheshyam Jat", "village": "Betma, Indore", "pool_qty_qtl": 300.0, "aadhar_masked": "XXXX-XXXX-4431", "bank_account": "38910284999", "ifsc": "SBIN0030018"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-401",
                commodity="Gram",
                variety="Desi Chana Bold (Malwa Special)",
                mandi="Indore, Madhya Pradesh",
                fpo_name="Malwa Kisan Samriddhi Producer Co. Ltd.",
                base_price_per_qtl=5450.0,
                available_qty_qtl=500.0,
                moisture_percent=9.5,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="MPAMB/AP-2026/IND-99120",
                assaying={
                    "foreign_matter_pct": 0.5,
                    "broken_pct": 0.8,
                    "protein_pct": 21.4,
                    "grain_length_mm": 6.2,
                    "lab_name": "MP Quality Testing Center, Indore",
                    "nabl_cert_no": "TC-8125",
                    "grade": "Bold Premium Desi Chana"
                },
                farmer_members=[
                    {"member_id": "FARM-MP-41", "name": "Vikram Patel", "village": "Hatod, Indore", "pool_qty_qtl": 300.0, "aadhar_masked": "XXXX-XXXX-6651", "bank_account": "01120100077194", "ifsc": "BARB0INDORE"},
                    {"member_id": "FARM-MP-42", "name": "Mukesh Sharma", "village": "Depalpur, Indore", "pool_qty_qtl": 200.0, "aadhar_masked": "XXXX-XXXX-1129", "bank_account": "38910284555", "ifsc": "SBIN0030018"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-402",
                commodity="Gram",
                variety="Rajasthan Desi Chana Katia",
                mandi="Kota, Rajasthan",
                fpo_name="Hadoti Kisan Vikas Agro Producer Co. Ltd.",
                base_price_per_qtl=5420.0,
                available_qty_qtl=420.0,
                moisture_percent=9.8,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="RSAMB/AP-2026/KOT-77123",
                assaying={
                    "foreign_matter_pct": 0.6,
                    "broken_pct": 0.9,
                    "protein_pct": 20.8,
                    "grain_length_mm": 6.0,
                    "lab_name": "Rajasthan Marketing Board Assaying Lab, Kota",
                    "nabl_cert_no": "TC-5936",
                    "grade": "Standard Grade Chana"
                },
                farmer_members=[
                    {"member_id": "FARM-RJ-21", "name": "Prahlad Bairwa", "village": "Itawa, Kota", "pool_qty_qtl": 250.0, "aadhar_masked": "XXXX-XXXX-4412", "bank_account": "02190100066192", "ifsc": "BARB0KOTAMA"},
                    {"member_id": "FARM-RJ-22", "name": "Harish Meena", "village": "Chechat, Kota", "pool_qty_qtl": 170.0, "aadhar_masked": "XXXX-XXXX-9955", "bank_account": "32948192077", "ifsc": "SBIN0031264"}
                ]
            ),
            models.CropLot(
                id="FPO-LOT-202",
                commodity="Rice",
                variety="PR-126 Supreme Milling Paddy",
                mandi="Khanna, Punjab",
                fpo_name="Doaba Farmer Producer Company Ltd.",
                base_price_per_qtl=3850.0,
                available_qty_qtl=900.0,
                moisture_percent=11.6,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                mform_document_hash="PMB/M-FORM/2026/04/KHN-77112",
                assaying={
                    "foreign_matter_pct": 0.3,
                    "broken_pct": 1.0,
                    "protein_pct": 9.1,
                    "grain_length_mm": 7.8,
                    "lab_name": "Agmark Regional Quality Lab, Khanna",
                    "nabl_cert_no": "TC-7414",
                    "grade": "Grade-A Long Grain Rice"
                },
                farmer_members=[
                    {"member_id": "FARM-PB-31", "name": "Baldev Singh", "village": "Samrala, Khanna", "pool_qty_qtl": 500.0, "aadhar_masked": "XXXX-XXXX-1199", "bank_account": "30489182999", "ifsc": "SBIN0000662"},
                    {"member_id": "FARM-PB-32", "name": "Jaswant Kaur", "village": "Alour, Khanna", "pool_qty_qtl": 400.0, "aadhar_masked": "XXXX-XXXX-8833", "bank_account": "0243000100298888", "ifsc": "PUNB0024300"}
                ]
            )
        ]
        db.add_all(initial_lots)
        db.commit()

        initial_bids = [
            models.BuyerBid(
                bid_id="BID-9901",
                buyer_id="USR-BUYER-01",
                buyer_name="Aryan Foods & Flour Mills Pvt. Ltd.",
                buyer_phone="+91 98140-72641",
                commodity="Wheat",
                target_qty_qtl=250.0,
                target_bid_price_per_qtl=2460.0,
                delivery_city="Jalandhar",
                status="OPEN_AUCTION"
            ),
            models.BuyerBid(
                bid_id="BID-9902",
                buyer_id="USR-BUYER-02",
                buyer_name="Delhi Agro Processing Corp Pvt. Ltd.",
                buyer_phone="+91 98110-38492",
                commodity="Rice",
                target_qty_qtl=150.0,
                target_bid_price_per_qtl=4100.0,
                delivery_city="Delhi",
                status="COUNTER_OFFERED",
                counter_price_per_qtl=4140.0,
                counter_fpo_name="Taraori Basmati Growers Farmer Producer Co. Ltd.",
                counter_notes="100% शुद्ध ग्रेड-A तरावड़ी 1121 बासमती (8.35mm दाना), HSAMB लैब NABL रिपोर्ट सहित तुरंत रवानगी।"
            )
        ]
        db.add_all(initial_bids)
        db.commit()

        db.add(models.ScheduledSlot(
            slot_id="SLOT-8801",
            token_number=1,
            mandi_hub="Khanna, Punjab",
            slot_date="2026-09-08",
            window_key="EARLY_MORNING",
            window_label="Early Morning (03:00 AM - 09:00 AM)",
            truck_reg_number="PB 10 CT 4821",
            commodity="Wheat",
            quantity_qtl=250.0,
            booked_by="Punjab Highway Freight Fleet (Ludhiana Transporters Guild)",
            status="CONFIRMED"
        ))
        db.commit()

        # Seed Authentic Orders with 12-digit GST E-Way Bills
        ord1_invoice = calculate_commercial_invoice(2580.0, 100.0, 42.0, "Punjab", "50KG_JUTE_GUNNY", True)
        total1 = ord1_invoice["total_invoice"]
        ord1 = models.Order(
            order_id="SAUDA-2026-KHN-0101",
            eway_bill_no="2418 9034 5122",
            lot_id="FPO-LOT-101",
            buyer_id="USR-BUYER-01",
            buyer_name="Aryan Foods & Flour Mills Pvt. Ltd.",
            buyer_phone="+91 98140-72641",
            delivery_address="Plot No. 48-52, Focal Point Phase-V, GT Road Bypass, Jalandhar, Punjab - 144050",
            gstin="03AAACA4582K1ZD",
            payment_method="ESCROW_RTGS",
            quantity_qtl=100.0,
            base_price_per_qtl=2580.0,
            bagging_type="50KG_JUTE_GUNNY",
            freight_per_qtl=42.0,
            apmc_cess_amount=ord1_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=ord1_invoice["tcs_tax"],
            transit_insurance_opted=True,
            insurance_fee=ord1_invoice["insurance_cost"],
            insurance_policy_no="NICL-MARINE-2026-88129",
            total_invoice_amount=total1,
            escrow_stages={
                "advance_20_pct": round(total1 * 0.20, 2),
                "dispatch_70_pct": round(total1 * 0.70, 2),
                "final_10_pct": round(total1 * 0.10, 2)
            },
            status="ADVANCE_ESCROW_LOCKED"
        )

        ord2_invoice = calculate_commercial_invoice(2420.0, 150.0, 88.0, "Madhya Pradesh", "50KG_PP_BAG", True)
        total2 = ord2_invoice["total_invoice"]
        ord2 = models.Order(
            order_id="SAUDA-2026-IND-0102",
            eway_bill_no="2418 9034 5123",
            lot_id="FPO-LOT-102",
            buyer_id="USR-BUYER-01",
            buyer_name="Aryan Foods & Flour Mills Pvt. Ltd.",
            buyer_phone="+91 98140-72641",
            delivery_address="Industrial Area, Delhi Road, Jalandhar, Punjab - 144004",
            gstin="03AAACA4582K1ZD",
            payment_method="ESCROW_RTGS",
            quantity_qtl=150.0,
            base_price_per_qtl=2420.0,
            bagging_type="50KG_PP_BAG",
            freight_per_qtl=88.0,
            apmc_cess_amount=ord2_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=ord2_invoice["tcs_tax"],
            transit_insurance_opted=True,
            insurance_fee=ord2_invoice["insurance_cost"],
            insurance_policy_no="NICL-MARINE-2026-88130",
            total_invoice_amount=total2,
            escrow_stages={
                "advance_20_pct": round(total2 * 0.20, 2),
                "dispatch_70_pct": round(total2 * 0.70, 2),
                "final_10_pct": round(total2 * 0.10, 2)
            },
            origin_gross_wt_qtl=195.4,
            origin_tare_wt_qtl=45.4,
            origin_net_wt_qtl=150.0,
            status="DISPATCH_70_RELEASED"
        )

        ord3_invoice = calculate_commercial_invoice(2490.0, 100.0, 38.0, "Punjab", "50KG_JUTE_GUNNY", True)
        total3 = ord3_invoice["total_invoice"]
        ord3 = models.Order(
            order_id="SAUDA-2026-BTI-0103",
            eway_bill_no="2418 9034 5124",
            lot_id="FPO-LOT-103",
            buyer_id="USR-BUYER-01",
            buyer_name="Aryan Foods & Flour Mills Pvt. Ltd.",
            buyer_phone="+91 98140-72641",
            delivery_address="GT Road Agro Park, Jalandhar, Punjab - 144001",
            gstin="03AAACA4582K1ZD",
            payment_method="ESCROW_RTGS",
            quantity_qtl=100.0,
            base_price_per_qtl=2490.0,
            bagging_type="50KG_JUTE_GUNNY",
            freight_per_qtl=38.0,
            apmc_cess_amount=ord3_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=ord3_invoice["tcs_tax"],
            transit_insurance_opted=True,
            insurance_fee=ord3_invoice["insurance_cost"],
            insurance_policy_no="NICL-MARINE-2026-88131",
            total_invoice_amount=total3,
            escrow_stages={
                "advance_20_pct": round(total3 * 0.20, 2),
                "dispatch_70_pct": round(total3 * 0.70, 2),
                "final_10_pct": round(total3 * 0.10, 2)
            },
            origin_gross_wt_qtl=142.5,
            origin_tare_wt_qtl=42.5,
            origin_net_wt_qtl=100.0,
            destination_gross_wt_qtl=142.3,
            destination_tare_wt_qtl=42.5,
            destination_net_wt_qtl=99.8,
            transit_weight_loss_qtl=0.2,
            tested_destination_moisture=11.4,
            status="COMPLETED_AND_SETTLED"
        )
        db.add_all([ord1, ord2, ord3])
        db.commit()

        # Seed Authentic Sample Requests
        smp1 = models.SampleCourierRequest(
            sample_id="SMP-9821",
            lot_id="FPO-LOT-101",
            buyer_name="Aryan Foods & Flour Mills Pvt. Ltd.",
            buyer_phone="+91 98140-72641",
            delivery_address="Plot No. 48-52, Focal Point Phase-V, GT Road Bypass, Jalandhar, Punjab - 144050",
            courier_tracking_no="DTDC981240182",
            courier_partner="DTDC Express Ltd. - Agri Logistic Division",
            fee_paid=450.0,
            status="DISPATCHED"
        )
        smp2 = models.SampleCourierRequest(
            sample_id="SMP-9822",
            lot_id="FPO-LOT-201",
            buyer_name="Delhi Agro Processing Corp Pvt. Ltd.",
            buyer_phone="+91 98110-38492",
            delivery_address="Shed No. 12-14, Lawrence Road Industrial Area, New Delhi - 110035",
            courier_tracking_no="BDART781920412",
            courier_partner="Blue Dart Express - Agri Cargo Services",
            fee_paid=450.0,
            status="DELIVERED"
        )
        db.add_all([smp1, smp2])
        db.commit()

    db.close()

seed_initial_data(force=True)

# Schemas
class LoginRequest(BaseModel):
    email: str

class BestBuyQuery(BaseModel):
    commodity: str = "Wheat"
    buyer_city: str = "Jalandhar"
    quantity_qtl: float = 100.0
    min_price_per_qtl: Optional[float] = 1000.0
    max_price_per_qtl: Optional[float] = 6000.0

class OrderRequest(BaseModel):
    lot_id: str
    delivery_address: str
    gstin: str
    payment_method: str = "ESCROW_UPI"
    quantity_qtl: float
    bagging_type: str = "50KG_JUTE_GUNNY"
    transit_insurance_opted: bool = True

class SampleOrderRequest(BaseModel):
    lot_id: str
    delivery_address: str
    buyer_phone: Optional[str] = "+91 98140 22341"

class OriginWeighbridgeSlip(BaseModel):
    order_id: str
    gross_weight_qtl: float
    tare_weight_qtl: float
    weighbridge_slip_no: Optional[str] = "WB-ORIGIN-001"

class DestinationWeighbridgeAndCutter(BaseModel):
    order_id: str
    gross_weight_qtl: float
    tare_weight_qtl: float
    tested_moisture_pct: float
    tested_broken_pct: Optional[float] = 1.2
    tested_foreign_matter_pct: Optional[float] = 0.4

class BidPlacementRequest(BaseModel):
    commodity: str
    target_qty_qtl: float
    target_bid_price_per_qtl: float
    delivery_city: str

class BidCounterRequest(BaseModel):
    counter_price_per_qtl: float
    counter_notes: str = "Official FPO counter-offer"

class CropLotCreate(BaseModel):
    commodity: str
    variety: str
    mandi: str
    fpo_name: str
    base_price_per_qtl: float
    available_qty_qtl: float
    moisture_percent: float
    bagging_type: str = "50KG_JUTE_GUNNY"
    foreign_matter_pct: float = 0.5
    broken_pct: float = 1.0
    protein_pct: float = 12.0
    grain_length_mm: float = 7.0
    farmer_members: List[dict] = []

class SlotBookingCreate(BaseModel):
    truck_reg_number: str
    mandi_hub: str
    commodity: str
    quantity_qtl: float
    slot_date: str
    window_key: str

class DelayNotificationRequest(BaseModel):
    slot_id: str
    delay_minutes: int
    delay_reason: str

class DayCancellationRequest(BaseModel):
    mandi_hub: str
    target_date: str
    cancellation_reason: str

# Endpoints
@app.get("/health")
def healthcheck(db: Session = Depends(get_db)):
    try:
        db.execute(func.now())
        db_status = "connected"
    except Exception:
        db_status = "sqlite_active"
    return {
        "status": "healthy",
        "service": "KisanVyapar Mandi Wholesaler Trading Desk",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "version": "5.0.0"
    }

@app.get("/")
def serve_terminal():
    candidate_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html"),
        os.path.join(os.path.dirname(__file__), "static", "index.html"),
        os.path.join(os.path.dirname(__file__), "index.html"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return FileResponse(p)
    return JSONResponse(status_code=404, content={"detail": "Terminal UI index.html not found"})

@app.get("/api/v1/auth/accounts")
def get_accounts():
    return [{"email": k, **v} for k, v in MOCK_USERS.items()]

@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    user = MOCK_USERS.get(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return {"status": "SUCCESS", "token": create_access_token(user), "user": user}

@app.get("/api/v1/auth/me")
def verify_current_identity(user: dict = Depends(get_current_user)):
    return {"status": "AUTHENTICATED", "user": user}

@app.get("/api/v1/market/registry")
def get_market_registry():
    return {
        "origin_mandis": MANDI_REGISTRY,
        "destination_cities": CITY_COORDINATES,
        "corridor_checkpoints": CORRIDOR_WAYPOINTS,
        "apmc_cess_rules": APMC_CESS_RATES,
        "bagging_options": BAGGING_PREMIUMS,
        "msp_benchmarks": MSP_BENCHMARKS
    }

@app.get("/api/v1/market/lots")
def get_market_lots(db: Session = Depends(get_db)):
    lots = db.query(models.CropLot).all()
    return [{
        "id": l.id,
        "commodity": l.commodity,
        "variety": l.variety,
        "mandi": l.mandi,
        "fpo_name": l.fpo_name,
        "base_price_per_qtl": l.base_price_per_qtl,
        "available_qty_qtl": l.available_qty_qtl,
        "moisture_percent": l.moisture_percent,
        "bagging_type": l.bagging_type,
        "mform_document_hash": l.mform_document_hash,
        "assaying": l.assaying
    } for l in lots]

@app.post("/api/v1/recommendations")
async def get_market_recommendations(query: BestBuyQuery, db: Session = Depends(get_db)):
    db_lots = db.query(models.CropLot).filter(
        models.CropLot.commodity.ilike(query.commodity),
        models.CropLot.base_price_per_qtl >= (query.min_price_per_qtl or 0),
        models.CropLot.base_price_per_qtl <= (query.max_price_per_qtl or 100000)
    ).all()

    lots_dicts = [{
        "id": l.id,
        "commodity": l.commodity,
        "variety": l.variety,
        "mandi": l.mandi,
        "fpo_name": l.fpo_name,
        "base_price_per_qtl": l.base_price_per_qtl,
        "available_qty_qtl": l.available_qty_qtl,
        "moisture_percent": l.moisture_percent,
        "bagging_type": l.bagging_type,
        "mform_document_hash": l.mform_document_hash,
        "apmc_cess_paid_at_source": l.apmc_cess_paid_at_source,
        "assaying": l.assaying,
        "farmer_members": l.farmer_members
    } for l in db_lots]

    results = await calculate_best_buy(
        commodity=query.commodity,
        buyer_city=query.buyer_city,
        required_qty_qtl=query.quantity_qtl,
        current_listings=lots_dicts
    )
    return {
        "best_pick": results[0] if results else None,
        "all_listings": results,
        "total_lots_scanned": len(results),
        "destination_city": query.buyer_city,
        "benchmark_msp": MSP_BENCHMARKS.get(query.commodity, 2425.0)
    }

# 1. 1kg Sealed Sample Dispatch
@app.post("/api/v1/commercial/request-sample")
def order_physical_sample(req: SampleOrderRequest, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.id == req.lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Crop lot not found")

    sample_id = f"SMP-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    tracking = f"DTDC-AGRI-COLD-{uuid.uuid4().hex[:6].upper()}"
    
    sample_entry = models.SampleCourierRequest(
        sample_id=sample_id,
        lot_id=lot.id,
        buyer_name=user["name"],
        buyer_phone=req.buyer_phone or user.get("phone", "+91 98140 22341"),
        delivery_address=req.delivery_address,
        courier_tracking_no=tracking,
        courier_partner="DTDC Express Agri-Cold Courier",
        fee_paid=450.0,
        status="DISPATCHED"
    )
    db.add(sample_entry)
    db.commit()

    return {
        "status": "SUCCESS",
        "message": f"Sealed 1kg tamper-evident sample parcel dispatched via Express Agri-Cold Courier for {lot.variety}",
        "sample": {
            "sample_id": sample_id,
            "lot_id": lot.id,
            "lot_variety": lot.variety,
            "courier_tracking_no": tracking,
            "courier_partner": "DTDC Express Agri-Cold Courier",
            "fee_debited": 450.0,
            "tamper_seal_serial": f"SEAL-{uuid.uuid4().hex[:8].upper()}"
        }
    }

@app.get("/api/v1/commercial/samples")
def list_sample_requests(db: Session = Depends(get_db)):
    samples = db.query(models.SampleCourierRequest).order_by(models.SampleCourierRequest.created_at.desc()).all()
    return [{
        "sample_id": s.sample_id,
        "lot_id": s.lot_id,
        "buyer_name": s.buyer_name,
        "delivery_address": s.delivery_address,
        "courier_tracking_no": s.courier_tracking_no,
        "courier_partner": s.courier_partner,
        "fee_paid": s.fee_paid,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None
    } for s in samples]

# 2. Commercial Orders & Multi-Stage Escrow
@app.post("/api/v1/orders/buy")
def place_commercial_order(order: OrderRequest, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    with db.begin():
        lot = db.query(models.CropLot).filter(models.CropLot.id == order.lot_id).first()
        if not lot:
            raise HTTPException(status_code=404, detail="Crop lot not found")
        if lot.available_qty_qtl < order.quantity_qtl:
            raise HTTPException(status_code=400, detail="Requested quantity exceeds stock balance")

        lot.available_qty_qtl -= order.quantity_qtl
        
        # Calculate full commercial breakdown
        comm_invoice = calculate_commercial_invoice(
            base_price_per_qtl=lot.base_price_per_qtl,
            quantity_qtl=order.quantity_qtl,
            freight_per_qtl=58.0,
            state_origin=lot.mandi.split(",")[-1].strip(),
            bagging_type=order.bagging_type,
            insurance_opted=order.transit_insurance_opted
        )

        order_id = f"ORD-{int(datetime.now(timezone.utc).timestamp()) % 1000000}"
        eway_bill = f"2418{uuid.uuid4().int % 100000000:08d}"
        total_amt = comm_invoice["total_invoice"]

        new_order = models.Order(
            order_id=order_id,
            eway_bill_no=eway_bill,
            lot_id=lot.id,
            buyer_id=user["id"],
            buyer_name=user["name"],
            buyer_phone=user["phone"],
            delivery_address=order.delivery_address,
            gstin=order.gstin,
            payment_method=order.payment_method,
            quantity_qtl=order.quantity_qtl,
            base_price_per_qtl=lot.base_price_per_qtl,
            bagging_type=order.bagging_type,
            freight_per_qtl=58.0,
            apmc_cess_amount=comm_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=comm_invoice["tcs_tax"],
            transit_insurance_opted=order.transit_insurance_opted,
            insurance_fee=comm_invoice["insurance_cost"],
            insurance_policy_no=f"NICL-MARINE-2026-{uuid.uuid4().hex[:8].upper()}" if order.transit_insurance_opted else None,
            total_invoice_amount=total_amt,
            escrow_stages={
                "advance_20_pct": round(total_amt * 0.20, 2),
                "dispatch_70_pct": round(total_amt * 0.70, 2),
                "final_10_pct": round(total_amt * 0.10, 2)
            },
            status="ADVANCE_ESCROW_LOCKED"
        )
        db.add(new_order)

    return {
        "status": "SUCCESS",
        "message": f"Order {order_id} confirmed. Stage 1 (20%) Advance Escrow Locked!",
        "order": {
            "order_id": new_order.order_id,
            "eway_bill_no": new_order.eway_bill_no,
            "status": new_order.status,
            "commercial_breakdown": comm_invoice,
            "escrow_stages": new_order.escrow_stages
        }
    }

@app.get("/api/v1/orders/all")
def get_all_orders(db: Session = Depends(get_db)):
    orders = db.query(models.Order).order_by(models.Order.created_at.desc()).all()
    return [{
        "order_id": o.order_id,
        "eway_bill_no": o.eway_bill_no,
        "lot_id": o.lot_id,
        "buyer_name": o.buyer_name,
        "quantity_qtl": o.quantity_qtl,
        "base_price_per_qtl": o.base_price_per_qtl,
        "bagging_type": o.bagging_type,
        "total_invoice_amount": o.total_invoice_amount,
        "status": o.status,
        "escrow_stages": o.escrow_stages,
        "origin_net_wt_qtl": o.origin_net_wt_qtl,
        "destination_net_wt_qtl": o.destination_net_wt_qtl,
        "transit_weight_loss_qtl": o.transit_weight_loss_qtl,
        "tested_destination_moisture": o.tested_destination_moisture,
        "cutter_deduction_amount": o.cutter_deduction_amount,
        "final_settled_payout": o.final_settled_payout,
        "created_at": o.created_at.isoformat() if o.created_at else None
    } for o in orders]

@app.get("/api/v1/orders/{order_id}")
def get_order_details(order_id: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# 1-Click Simple Dispatch -> Releases 70% Stage 2 Escrow
@app.post("/api/v1/orders/{order_id}/dispatch")
def dispatch_order(order_id: str, db: Session = Depends(get_db)):
    with db.begin():
        order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        order.status = "DISPATCHED_70_RELEASED"
        order.origin_net_wt_qtl = order.quantity_qtl

    return {
        "status": "SUCCESS",
        "message": f"Order {order_id} marked dispatched. Stage 2 (70%) Escrow released to FPO!",
        "order_id": order.order_id,
        "released_dispatch_70": order.escrow_stages.get("stage_2_dispatch_70", {}).get("amount", 0.0),
        "order_status": order.status
    }

# 1-Click Simple Delivery Confirmation -> Releases 10% Final Escrow
@app.post("/api/v1/orders/{order_id}/deliver")
def deliver_order(order_id: str, db: Session = Depends(get_db)):
    with db.begin():
        order = db.query(models.Order).filter(models.Order.order_id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        order.status = "DELIVERED_AND_SETTLED"
        order.destination_net_wt_qtl = order.quantity_qtl
        order.final_settled_payout = order.total_invoice_amount

    return {
        "status": "SUCCESS",
        "message": f"Order {order_id} delivered successfully. Stage 3 (10%) Escrow released in full!",
        "order_id": order.order_id,
        "released_final_10": order.escrow_stages.get("stage_3_delivery_10", {}).get("amount", 0.0),
        "order_status": order.status
    }

# 3. Origin Weighbridge Slip -> Releases 70% Stage 2 Escrow
@app.post("/api/v1/commercial/weighbridge/origin-slip")
def submit_origin_weighbridge(slip: OriginWeighbridgeSlip, user: dict = Depends(RoleChecker(["FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        order = db.query(models.Order).filter(models.Order.order_id == slip.order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        net_wt = round(slip.gross_weight_qtl - slip.tare_weight_qtl, 2)
        if net_wt <= 0:
            raise HTTPException(status_code=400, detail="Gross weight must be strictly higher than tare weight")

        order.origin_gross_wt_qtl = slip.gross_weight_qtl
        order.origin_tare_wt_qtl = slip.tare_weight_qtl
        order.origin_net_wt_qtl = net_wt
        order.status = "DISPATCH_70_RELEASED"

    return {
        "status": "SUCCESS",
        "message": f"Origin Net Weight Registered: {net_wt} qtl. Stage 2 (70%) Dispatch Escrow Released to FPO!",
        "order_id": order.order_id,
        "released_dispatch_escrow": order.escrow_stages["dispatch_70_pct"],
        "status": order.status
    }

# 4. Destination Weighbridge, Shrinkage Reconciliation & Cutter Audit -> Releases Stage 3 Escrow
@app.post("/api/v1/commercial/weighbridge/destination-settle")
def destination_weighbridge_and_cutter(req: DestinationWeighbridgeAndCutter, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    with db.begin():
        order = db.query(models.Order).filter(models.Order.order_id == req.order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        dest_net = round(req.gross_weight_qtl - req.tare_weight_qtl, 2)
        if dest_net <= 0:
            raise HTTPException(status_code=400, detail="Gross weight must exceed tare weight")

        order.destination_gross_wt_qtl = req.gross_weight_qtl
        order.destination_tare_wt_qtl = req.tare_weight_qtl
        order.destination_net_wt_qtl = dest_net

        # Shrinkage check: Allowed transit loss shrinkage tolerance is 0.3%
        origin_net = order.origin_net_wt_qtl or order.quantity_qtl
        shortage = round(max(0.0, origin_net - dest_net), 2)
        tolerance_qtl = round(origin_net * 0.003, 2)
        chargeable_shortage = max(0.0, round(shortage - tolerance_qtl, 2))
        shortage_deduction = round(chargeable_shortage * order.base_price_per_qtl, 2)
        order.transit_weight_loss_qtl = shortage

        # Moisture Cutter Rule: ₹25/qtl penalty for every 0.5% moisture above contract limit of 11.5%
        contract_moisture_limit = 11.5
        excess_moisture = max(0.0, round(req.tested_moisture_pct - contract_moisture_limit, 2))
        moisture_penalty_rate = (excess_moisture / 0.5) * 25.0
        moisture_cutter_total = round(moisture_penalty_rate * dest_net, 2)

        # Broken Grain Cutter Rule: ₹10/qtl penalty per 1.0% broken grain over 1.5% limit
        excess_broken = max(0.0, round((req.tested_broken_pct or 1.0) - 1.5, 2))
        broken_cutter_total = round(excess_broken * 10.0 * dest_net, 2)

        total_cutter = round(shortage_deduction + moisture_cutter_total + broken_cutter_total, 2)
        order.tested_destination_moisture = req.tested_moisture_pct
        order.tested_destination_broken = req.tested_broken_pct
        order.tested_foreign_matter = req.tested_foreign_matter_pct
        order.cutter_deduction_amount = total_cutter

        # Final Stage 3 (10%) Escrow Release Calculation
        final_escrow_pool = order.escrow_stages["final_10_pct"]
        settled_final_payout = max(0.0, round(final_escrow_pool - total_cutter, 2))
        order.final_settled_payout = settled_final_payout
        order.status = "COMPLETED_AND_SETTLED"

    return {
        "status": "SUCCESS",
        "message": f"Destination Weighbridge & Cutter Audit Completed. Final Escrow released post-deductions.",
        "settlement_audit": {
            "order_id": order.order_id,
            "origin_net_qtl": origin_net,
            "destination_net_qtl": dest_net,
            "transit_loss_qtl": shortage,
            "allowed_0_3pct_tolerance_qtl": tolerance_qtl,
            "unapproved_shortage_qtl": chargeable_shortage,
            "shortage_penalty_inr": shortage_deduction,
            "tested_moisture_pct": req.tested_moisture_pct,
            "contract_moisture_limit_pct": contract_moisture_limit,
            "excess_moisture_pct": excess_moisture,
            "moisture_cutter_deduction_inr": moisture_cutter_total,
            "broken_grain_cutter_inr": broken_cutter_total,
            "total_cutter_deductions": total_cutter,
            "original_final_10pct_escrow": final_escrow_pool,
            "net_final_released_to_fpo": settled_final_payout,
            "order_status": order.status
        }
    }

# 5. Double Auction Bidding Engine (Buyers & FPOs can Bid)
@app.post("/api/v1/bids/create")
def place_buyer_bid(bid: BidPlacementRequest, user: dict = Depends(RoleChecker(["BUYER", "FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    bid_id = f"BID-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    bid_status = "OPEN_FPO_OFFER" if user.get("role") == "FPO" else "OPEN_AUCTION"
    new_bid = models.BuyerBid(
        bid_id=bid_id,
        buyer_id=user["id"],
        buyer_name=user["name"],
        buyer_phone=user["phone"],
        commodity=bid.commodity,
        target_qty_qtl=bid.target_qty_qtl,
        target_bid_price_per_qtl=bid.target_bid_price_per_qtl,
        delivery_city=bid.delivery_city,
        status=bid_status
    )
    db.add(new_bid)
    db.commit()
    tag = "FPO बिक्री प्रस्ताव" if user.get("role") == "FPO" else "खरीदार मांग बोली"
    return {
        "status": "SUCCESS",
        "message": f"{tag} #{bid_id} listed on Open Board for {bid.commodity} ({bid.target_qty_qtl} qtl @ ₹{bid.target_bid_price_per_qtl}/qtl)",
        "bid": {
            "bid_id": new_bid.bid_id,
            "commodity": new_bid.commodity,
            "target_bid_price_per_qtl": new_bid.target_bid_price_per_qtl,
            "status": new_bid.status
        }
    }

@app.get("/api/v1/bids/live")
@app.get("/api/v1/bids/all")
def get_live_buyer_bids(db: Session = Depends(get_db)):
    bids = db.query(models.BuyerBid).order_by(models.BuyerBid.created_at.desc()).limit(50).all()
    return [{
        "bid_id": b.bid_id,
        "buyer_name": b.buyer_name,
        "buyer_phone": b.buyer_phone,
        "commodity": b.commodity,
        "target_qty_qtl": b.target_qty_qtl,
        "target_bid_price_per_qtl": b.target_bid_price_per_qtl,
        "delivery_city": b.delivery_city,
        "status": b.status,
        "accepted_by_fpo": b.accepted_by_fpo,
        "counter_price_per_qtl": b.counter_price_per_qtl,
        "counter_fpo_name": b.counter_fpo_name,
        "counter_notes": b.counter_notes,
        "created_at": b.created_at.isoformat() if b.created_at else None
    } for b in bids]

@app.post("/api/v1/bids/{bid_id}/accept")
def accept_buyer_bid(bid_id: str, user: dict = Depends(RoleChecker(["FPO", "BUYER", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        bid = db.query(models.BuyerBid).filter(models.BuyerBid.bid_id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
        if bid.status not in ["OPEN_AUCTION", "OPEN_FPO_OFFER", "COUNTER_OFFERED"]:
            raise HTTPException(status_code=400, detail=f"Bid cannot be accepted in '{bid.status}' state")

        bid.status = "ACCEPTED"
        bid.accepted_by_fpo = user["name"]

        # Automatically bind contract and generate order with 20% Advance Escrow
        order_id = f"ORD-AUC-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        eway_bill = f"2418{uuid.uuid4().int % 100000000:08d}"
        
        comm_invoice = calculate_commercial_invoice(
            base_price_per_qtl=bid.target_bid_price_per_qtl,
            quantity_qtl=bid.target_qty_qtl,
            freight_per_qtl=55.0,
            state_origin="Punjab",
            bagging_type="50KG_JUTE_GUNNY",
            insurance_opted=True
        )
        total_amt = comm_invoice["total_invoice"]

        # Determine buyer and seller
        if bid.status == "OPEN_FPO_OFFER" or "FPO" in bid.buyer_name:
            final_buyer_name = user["name"]
            final_buyer_id = user["id"]
            final_buyer_phone = user["phone"]
            final_buyer_gstin = user.get("gstin", "03AAACA4582K1ZD")
        else:
            final_buyer_name = bid.buyer_name
            final_buyer_id = bid.buyer_id
            final_buyer_phone = bid.buyer_phone
            final_buyer_gstin = "03AAACA4582K1ZD"

        matched_order = models.Order(
            order_id=order_id,
            eway_bill_no=eway_bill,
            lot_id=f"AUC-MATCH-{bid.bid_id}",
            buyer_id=final_buyer_id,
            buyer_name=final_buyer_name,
            buyer_phone=final_buyer_phone,
            delivery_address=f"Central Grain Terminal, {bid.delivery_city}",
            gstin=final_buyer_gstin,
            payment_method="ESCROW_UPI",
            quantity_qtl=bid.target_qty_qtl,
            base_price_per_qtl=bid.target_bid_price_per_qtl,
            bagging_type="50KG_JUTE_GUNNY",
            freight_per_qtl=55.0,
            apmc_cess_amount=comm_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=comm_invoice["tcs_tax"],
            transit_insurance_opted=True,
            insurance_fee=comm_invoice["insurance_cost"],
            insurance_policy_no=f"NICL-MARINE-2026-{uuid.uuid4().hex[:8].upper()}",
            total_invoice_amount=total_amt,
            escrow_stages={
                "advance_20_pct": round(total_amt * 0.20, 2),
                "dispatch_70_pct": round(total_amt * 0.70, 2),
                "final_10_pct": round(total_amt * 0.10, 2)
            },
            status="ADVANCE_ESCROW_LOCKED"
        )
        db.add(matched_order)

    return {
        "status": "SUCCESS",
        "message": f"Bid #{bid_id} accepted! Deal locked with 20% Advance Escrow.",
        "order": {
            "order_id": order_id,
            "eway_bill_no": eway_bill,
            "total_invoice": total_amt,
            "escrow_stages": matched_order.escrow_stages
        }
    }

@app.post("/api/v1/bids/{bid_id}/counter")
def counter_buyer_bid(bid_id: str, req: BidCounterRequest, user: dict = Depends(RoleChecker(["FPO", "BUYER", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        bid = db.query(models.BuyerBid).filter(models.BuyerBid.bid_id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
        bid.status = "COUNTER_OFFERED"
        bid.counter_price_per_qtl = req.counter_price_per_qtl
        bid.counter_fpo_name = user["name"]
        bid.counter_notes = req.counter_notes

    return {
        "status": "SUCCESS",
        "message": f"Counter offer of ₹{req.counter_price_per_qtl}/qtl submitted by {user['name']}.",
        "bid_id": bid.bid_id,
        "counter_price_per_qtl": req.counter_price_per_qtl
    }

@app.post("/api/v1/bids/{bid_id}/counter-accept")
def accept_counter_offer(bid_id: str, user: dict = Depends(RoleChecker(["BUYER", "FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        bid = db.query(models.BuyerBid).filter(models.BuyerBid.bid_id == bid_id).first()
        if not bid:
            raise HTTPException(status_code=404, detail="Bid not found")
        if bid.status != "COUNTER_OFFERED" or not bid.counter_price_per_qtl:
            raise HTTPException(status_code=400, detail="No active counter offer to accept")

        bid.status = "ACCEPTED"
        agreed_price = bid.counter_price_per_qtl

        order_id = f"ORD-CTR-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        eway_bill = f"2418{uuid.uuid4().int % 100000000:08d}"
        
        comm_invoice = calculate_commercial_invoice(
            base_price_per_qtl=agreed_price,
            quantity_qtl=bid.target_qty_qtl,
            freight_per_qtl=55.0,
            state_origin="Punjab",
            bagging_type="50KG_JUTE_GUNNY",
            insurance_opted=True
        )
        total_amt = comm_invoice["total_invoice"]

        matched_order = models.Order(
            order_id=order_id,
            eway_bill_no=eway_bill,
            lot_id=f"CTR-MATCH-{bid.bid_id}",
            buyer_id=user["id"],
            buyer_name=user["name"],
            buyer_phone=user["phone"],
            delivery_address=f"Central Grain Terminal, {bid.delivery_city}",
            gstin=user.get("gstin", "03AAACA4582K1ZD"),
            payment_method="ESCROW_UPI",
            quantity_qtl=bid.target_qty_qtl,
            base_price_per_qtl=agreed_price,
            bagging_type="50KG_JUTE_GUNNY",
            freight_per_qtl=55.0,
            apmc_cess_amount=comm_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=comm_invoice["tcs_tax"],
            transit_insurance_opted=True,
            insurance_fee=comm_invoice["insurance_cost"],
            insurance_policy_no=f"NICL-MARINE-2026-{uuid.uuid4().hex[:8].upper()}",
            total_invoice_amount=total_amt,
            escrow_stages={
                "advance_20_pct": round(total_amt * 0.20, 2),
                "dispatch_70_pct": round(total_amt * 0.70, 2),
                "final_10_pct": round(total_amt * 0.10, 2)
            },
            status="ADVANCE_ESCROW_LOCKED"
        )
        db.add(matched_order)

    return {
        "status": "SUCCESS",
        "message": f"FPO Counter Offer of ₹{agreed_price}/qtl Accepted. Contract locked into Stage 1 Escrow!",
        "order": {
            "order_id": order_id,
            "eway_bill_no": eway_bill,
            "total_invoice": total_amt
        }
    }

# 6. FPO Operations & Farmer Member Passbook Traceability
@app.get("/api/v1/fpo/farmer-passbook/{lot_id}")
def get_farmer_pool_passbook(lot_id: str, db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Crop lot not found")

    orders = db.query(models.Order).filter(models.Order.lot_id == lot.id).all()
    members = lot.farmer_members or []
    total_pool_qty = sum(m.get("pool_qty_qtl", 0) for m in members) or lot.available_qty_qtl or 1.0

    total_gross_realized = sum(o.total_invoice_amount for o in orders)
    total_cutter_deductions = sum(o.cutter_deduction_amount or 0.0 for o in orders)
    has_settled_order = any(o.status == "COMPLETED_AND_SETTLED" for o in orders)

    farmer_ledgers = []
    for m in members:
        qty = m.get("pool_qty_qtl", 0)
        share_ratio = qty / total_pool_qty
        
        gross_value = round(qty * lot.base_price_per_qtl, 2)
        mandi_cess_share = round(gross_value * 0.04, 2) if ("Punjab" in lot.mandi or "Haryana" in lot.mandi) else round(gross_value * 0.015, 2)
        cutter_deduction_share = round(total_cutter_deductions * share_ratio, 2)
        net_payable = max(0.0, round(gross_value - mandi_cess_share - cutter_deduction_share, 2))

        payout_status = "CREDITED_VIA_RTGS" if has_settled_order else "HELD_IN_ESCROW"

        acct_raw = str(m.get("bank_account", "30489182741"))
        acct_masked = f"••••••{acct_raw[-4:]}" if len(acct_raw) >= 4 else acct_raw
        ifsc_val = m.get("ifsc", "SBIN0000662")
        farmer_name = m.get("name", "Unknown Member")

        farmer_ledgers.append({
            "member_id": m.get("member_id", f"FARM-MEM-{uuid.uuid4().hex[:4].upper()}"),
            "name": farmer_name,
            "farmer_name": farmer_name,
            "village": m.get("village", lot.mandi.split(",")[0] + " Gram"),
            "aadhar_masked": m.get("aadhar_masked", "XXXX-XXXX-8921"),
            "pool_qty_qtl": qty,
            "pool_quantity_qtl": qty,
            "share_percentage": round(share_ratio * 100.0, 2),
            "gross_mandi_value": gross_value,
            "gross_payable": gross_value,
            "mandi_cess_share": mandi_cess_share,
            "fpo_handling_deduction": mandi_cess_share,
            "cutter_deductions_share": cutter_deduction_share,
            "net_payout_amount": net_payable,
            "net_disbursed_to_bank": net_payable,
            "bank_account": acct_raw,
            "bank_account_masked": acct_masked,
            "ifsc_code": ifsc_val,
            "ifsc": ifsc_val,
            "payout_status": payout_status
        })

    return {
        "status": "SUCCESS",
        "lot_id": lot.id,
        "fpo_name": lot.fpo_name,
        "commodity": lot.commodity,
        "variety": lot.variety,
        "mandi": lot.mandi,
        "base_price_per_qtl": lot.base_price_per_qtl,
        "total_pool_qty_qtl": total_pool_qty,
        "total_gross_pool_value": round(total_pool_qty * lot.base_price_per_qtl, 2),
        "total_orders_placed": len(orders),
        "total_gross_realized": round(total_gross_realized, 2),
        "total_cutter_deductions_applied": round(total_cutter_deductions, 2),
        "farmer_members_count": len(farmer_ledgers),
        "farmer_ledgers": farmer_ledgers,
        "farmer_records": farmer_ledgers
    }

@app.get("/api/v1/fpo/lots")
def get_fpo_lots(user: dict = Depends(RoleChecker(["FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    lots = db.query(models.CropLot).all()
    return [{
        "id": l.id,
        "commodity": l.commodity,
        "variety": l.variety,
        "mandi": l.mandi,
        "fpo_name": l.fpo_name,
        "base_price_per_qtl": l.base_price_per_qtl,
        "available_qty_qtl": l.available_qty_qtl,
        "moisture_percent": l.moisture_percent,
        "bagging_type": l.bagging_type,
        "mform_document_hash": l.mform_document_hash,
        "assaying": l.assaying,
        "farmer_count": len(l.farmer_members or [])
    } for l in lots]

@app.post("/api/v1/fpo/lots/create")
def create_new_crop_lot(lot_in: CropLotCreate, user: dict = Depends(RoleChecker(["FPO"])), db: Session = Depends(get_db)):
    lot_id = f"FPO-LOT-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    mform_hash = f"MFORM-SRC-{uuid.uuid4().hex[:12].upper()}"

    new_lot = models.CropLot(
        id=lot_id,
        commodity=lot_in.commodity,
        variety=lot_in.variety,
        mandi=lot_in.mandi,
        fpo_name=user["name"],
        base_price_per_qtl=lot_in.base_price_per_qtl,
        available_qty_qtl=lot_in.available_qty_qtl,
        moisture_percent=lot_in.moisture_percent,
        bagging_type=lot_in.bagging_type,
        bag_cost_included=True,
        apmc_cess_paid_at_source=True,
        mform_document_hash=mform_hash,
        assaying={
            "foreign_matter_pct": lot_in.foreign_matter_pct,
            "broken_pct": lot_in.broken_pct,
            "protein_pct": lot_in.protein_pct,
            "grain_length_mm": lot_in.grain_length_mm,
            "lab_name": f"{user['name']} Assaying Lab",
            "nabl_cert_no": f"NABL-FPO-{uuid.uuid4().hex[:6].upper()}"
        },
        farmer_members=lot_in.farmer_members or [
            {"member_id": f"FARM-{uuid.uuid4().hex[:4].upper()}", "name": "Primary Pool Member", "pool_qty_qtl": lot_in.available_qty_qtl, "village": lot_in.mandi.split(",")[0]}
        ]
    )
    db.add(new_lot)
    db.commit()

    return {"status": "SUCCESS", "lot": {"id": new_lot.id, "variety": new_lot.variety, "mform_hash": mform_hash}}

# 7. Regulatory Compliance & Tracking (M-Form & e-Way Bill)
@app.get("/api/v1/compliance/mform/{mform_hash}")
def verify_mform(mform_hash: str, db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.mform_document_hash == mform_hash).first()
    origin_mandi = lot.mandi if lot else "Khanna Mandi, Punjab"
    origin_state = origin_mandi.split(",")[-1].strip()
    cess_rule = APMC_CESS_RATES.get(origin_state, APMC_CESS_RATES["Default"])

    return {
        "status": "VERIFIED_COMPLIANT",
        "mform_document_hash": mform_hash,
        "origin_apmc_mandi": origin_mandi,
        "issuing_board": f"State Agricultural Marketing Board ({origin_state})",
        "mandi_fee_verified_rate": f"{cess_rule['mandi_fee_pct']}%",
        "rdf_verified_rate": f"{cess_rule['rdf_pct']}%",
        "cess_paid_at_source": True,
        "enforcement_clearance": "EXEMPT_FROM_HIGHWAY_CHECKPOINT_SEIZURE",
        "qr_verification_string": f"AGRI-MFORM|{mform_hash}|{origin_state}|CLEAR",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/v1/compliance/eway-bill/{eway_bill_no}")
def verify_eway_bill(eway_bill_no: str, db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.eway_bill_no == eway_bill_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="e-Way Bill not found")

    return {
        "status": "ACTIVE_AND_VALID",
        "eway_bill_no": order.eway_bill_no,
        "order_id": order.order_id,
        "hsn_code": "1001" if "Wheat" in (order.lot_id or "") else "1006",
        "commodity": "Agricultural Produce (Bulk Wholesaler)",
        "quantity_qtl": order.quantity_qtl,
        "invoice_value": order.total_invoice_amount,
        "supplier_gstin": "03AAACD9182P1ZQ",
        "buyer_gstin": order.gstin,
        "delivery_destination": order.delivery_address,
        "vehicle_number": order.truck_reg_number or "PB 10 CT 4821",
        "valid_until": (order.created_at + timedelta(hours=72)).isoformat() if order.created_at else "2026-09-12T00:00:00Z",
        "escrow_stage": order.status
    }

# 8. Mandi Time Slots & Logistics Queue
@app.post("/api/v1/slots/book")
def book_time_slot(booking: SlotBookingCreate, user: dict = Depends(RoleChecker(["TRANSPORTER", "FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    rule = WINDOW_RULES.get(booking.window_key)
    if not rule:
        raise HTTPException(status_code=400, detail="Invalid time window key")

    with db.begin():
        active_count = db.query(func.count(models.ScheduledSlot.slot_id)).filter(
            models.ScheduledSlot.mandi_hub == booking.mandi_hub,
            models.ScheduledSlot.slot_date == booking.slot_date,
            models.ScheduledSlot.window_key == booking.window_key,
            models.ScheduledSlot.status.in_(["CONFIRMED", "DELAYED"])
        ).scalar()

        if active_count >= rule["max_capacity"]:
            raise HTTPException(
                status_code=409,
                detail=f"Capacity Collision Hazard: '{rule['label']}' is fully booked ({rule['max_capacity']} trucks limit)."
            )

        slot_id = f"SLOT-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
        new_slot = models.ScheduledSlot(
            slot_id=slot_id,
            token_number=active_count + 1,
            mandi_hub=booking.mandi_hub,
            slot_date=booking.slot_date,
            window_key=booking.window_key,
            window_label=rule["label"],
            truck_reg_number=booking.truck_reg_number,
            commodity=booking.commodity,
            quantity_qtl=booking.quantity_qtl,
            booked_by=user["name"],
            status="CONFIRMED"
        )
        db.add(new_slot)

    return {
        "status": "SUCCESS",
        "slot": {
            "slot_id": new_slot.slot_id,
            "token_number": new_slot.token_number,
            "window_label": new_slot.window_label,
            "truck_reg_number": new_slot.truck_reg_number
        }
    }

@app.get("/api/v1/slots/active")
def get_active_slots(db: Session = Depends(get_db)):
    slots = db.query(models.ScheduledSlot).order_by(models.ScheduledSlot.created_at.desc()).limit(100).all()
    return [{
        "slot_id": s.slot_id,
        "token_number": s.token_number,
        "truck_reg_number": s.truck_reg_number,
        "window_label": s.window_label,
        "slot_date": s.slot_date,
        "booked_by": s.booked_by,
        "delay_minutes": s.delay_minutes,
        "status": s.status
    } for s in slots]

@app.post("/api/v1/slots/delay")
def inform_and_delay_slot(req: DelayNotificationRequest, user: dict = Depends(RoleChecker(["FPO", "MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        slot = db.query(models.ScheduledSlot).filter(models.ScheduledSlot.slot_id == req.slot_id).first()
        if not slot:
            raise HTTPException(status_code=404, detail="Slot not found")
        slot.delay_minutes += req.delay_minutes
        slot.delay_reason = req.delay_reason
        slot.status = "DELAYED"
    return {"status": "SUCCESS", "message": f"Slot delayed by {req.delay_minutes} min"}

@app.post("/api/v1/slots/cancel-entire-day")
def cancel_entire_day(req: DayCancellationRequest, user: dict = Depends(RoleChecker(["MANDI_ADMIN"])), db: Session = Depends(get_db)):
    with db.begin():
        slots = db.query(models.ScheduledSlot).filter(
            models.ScheduledSlot.mandi_hub == req.mandi_hub,
            models.ScheduledSlot.slot_date == req.target_date,
            models.ScheduledSlot.status != "CANCELLED"
        ).all()

        count = len(slots)
        for s in slots:
            s.status = "CANCELLED"
            s.cancellation_reason = f"EMERGENCY APMC CLOSURE: {req.cancellation_reason}"

    return {"status": "SUCCESS", "cancelled_bookings_count": count, "message": f"APMC Mandi closed on {req.target_date}. {count} truck bookings notified and cancelled."}
