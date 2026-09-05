import os
import uuid
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import engine, get_db, Base
import models
from engine import CITY_COORDINATES, calculate_best_buy, calculate_commercial_invoice

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgriExchange Wholesaler Production Engine", version="4.5.0")

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

MOCK_USERS = {
    "buyer@mill.com": {"id": "USR-BUYER-01", "name": "Aryan Foods & Flour Mills", "role": "BUYER", "city": "Jalandhar", "phone": "+91 98765-11223"},
    "manager@doaba-fpo.org": {"id": "USR-FPO-01", "name": "Doaba Agri Producers Co.", "role": "FPO", "city": "Khanna", "phone": "+91 98765-44556"},
    "admin@khanna-mandi.gov": {"id": "USR-ADMIN-01", "name": "Khanna APMC Mandi Secretary", "role": "MANDI_ADMIN", "city": "Khanna", "phone": "+91 98765-77889"},
    "dispatch@truckunion.in": {"id": "USR-DRIVER-01", "name": "Punjab Highway Freight Fleet", "role": "TRANSPORTER", "city": "Ludhiana", "phone": "+91 98765-99001"}
}

def create_access_token(user_data: dict) -> str:
    payload = {
        **user_data,
        "exp": datetime.now(timezone.utc) + timedelta(days=2),
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    token = authorization.split(" ")[1]
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token.")

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: dict = Depends(get_current_user)):
        if user.get("role") not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied. Role required: {', '.join(self.allowed_roles)}"
            )
        return user

def seed_initial_data():
    db = next(get_db())
    if db.query(models.CropLot).count() == 0:
        initial_lots = [
            models.CropLot(
                id="FPO-LOT-101",
                commodity="Wheat",
                variety="PBW-725 Sharbati",
                mandi="Khanna, Punjab",
                fpo_name="Doaba Agri Producers Co.",
                base_price_per_qtl=2580.0,
                available_qty_qtl=1400,
                moisture_percent=11.2,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                assaying={"foreign_matter_pct": 0.4, "broken_pct": 1.1, "protein_pct": 12.8, "grain_length_mm": 7.1, "lab_name": "Agmark Patiala"},
                farmer_members=[{"member_id": "FARM-PB-01", "name": "Gurdev Singh", "pool_qty_qtl": 600}, {"member_id": "FARM-PB-02", "name": "Harbans Kaur", "pool_qty_qtl": 450}]
            ),
            models.CropLot(
                id="FPO-LOT-102",
                commodity="Wheat",
                variety="Malwa Lokwan Gold",
                mandi="Indore, MP",
                fpo_name="Malwa Kisan Samriddhi FPO",
                base_price_per_qtl=2420.0,
                available_qty_qtl=850,
                moisture_percent=10.5,
                bagging_type="50KG_PP_BAG",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                assaying={"foreign_matter_pct": 0.6, "broken_pct": 1.8, "protein_pct": 11.6, "grain_length_mm": 6.8, "lab_name": "MP State Assaying"},
                farmer_members=[{"member_id": "FARM-MP-11", "name": "Rajesh Patidar", "pool_qty_qtl": 500}]
            ),
            models.CropLot(
                id="FPO-LOT-201",
                commodity="Rice",
                variety="1121 Basmati Steam",
                mandi="Karnal, Haryana",
                fpo_name="Taraori Rice Growers Guild",
                base_price_per_qtl=4150.0,
                available_qty_qtl=450,
                moisture_percent=11.8,
                bagging_type="50KG_JUTE_GUNNY",
                bag_cost_included=True,
                apmc_cess_paid_at_source=True,
                assaying={"foreign_matter_pct": 0.2, "broken_pct": 0.8, "protein_pct": 8.5, "grain_length_mm": 8.35, "lab_name": "Taraori Lab"},
                farmer_members=[{"member_id": "FARM-HR-51", "name": "Naresh Kumar", "pool_qty_qtl": 250}]
            )
        ]
        db.add_all(initial_lots)
        db.commit()
    db.close()

seed_initial_data()

# Request Schemas
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

class OriginWeighbridgeSlip(BaseModel):
    order_id: str
    gross_weight_qtl: float
    tare_weight_qtl: float

class DestinationWeighbridgeAndCutter(BaseModel):
    order_id: str
    gross_weight_qtl: float
    tare_weight_qtl: float
    tested_moisture_pct: float
    tested_broken_pct: float

class BidPlacementRequest(BaseModel):
    commodity: str
    target_qty_qtl: float
    target_bid_price_per_qtl: float
    delivery_city: str

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
@app.get("/")
def serve_terminal():
    static_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "index.html")
    if not os.path.exists(static_file):
        static_file = os.path.join(os.path.dirname(__file__), "index.html")
    return FileResponse(static_file)

@app.get("/api/v1/auth/accounts")
def get_accounts():
    return [{"email": k, **v} for k, v in MOCK_USERS.items()]

@app.post("/api/v1/auth/login")
def login(req: LoginRequest):
    user = MOCK_USERS.get(req.email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    return {"status": "SUCCESS", "token": create_access_token(user), "user": user}

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
        "assaying": l.assaying,
        "farmer_members": l.farmer_members
    } for l in db_lots]

    results = await calculate_best_buy(
        commodity=query.commodity,
        buyer_city=query.buyer_city,
        required_qty_qtl=query.quantity_qtl,
        current_listings=lots_dicts
    )
    return {"best_pick": results[0] if results else None, "all_listings": results}

# 1. 1kg Sample Dispatch Workflow
@app.post("/api/v1/commercial/request-sample")
def order_physical_sample(req: SampleOrderRequest, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.id == req.lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Crop lot not found")

    sample_id = f"SMP-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    tracking = f"DTDC-AGRI-{uuid.uuid4().hex[:8].upper()}"
    
    sample_entry = models.SampleCourierRequest(
        sample_id=sample_id,
        lot_id=lot.id,
        buyer_name=user["name"],
        delivery_address=req.delivery_address,
        courier_tracking_no=tracking,
        fee_paid=450.0,
        status="DISPATCHED"
    )
    db.add(sample_entry)
    db.commit()

    return {
        "status": "SUCCESS",
        "message": f"Sealed 1kg tamper-evident parcel dispatched via Express Courier for {lot.variety}",
        "sample": {
            "sample_id": sample_id,
            "courier_tracking_no": tracking,
            "courier_partner": "DTDC Express Agri-Cold Courier",
            "fee_debited": 450.0
        }
    }

# 2. Commercial Escrow Order Execution
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
            freight_per_qtl=65.0, # Standard corridor freight
            state_origin=lot.mandi.split(",")[-1].strip(),
            bagging_type=order.bagging_type,
            insurance_opted=order.transit_insurance_opted
        )

        order_id = f"ORD-{int(datetime.now(timezone.utc).timestamp())}"
        eway_bill = f"EWB{uuid.uuid4().int % 1000000000000:012d}"
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
            freight_per_qtl=65.0,
            apmc_cess_amount=comm_invoice["apmc_cess_breakdown"]["total_cess"],
            tcs_tax_amount=comm_invoice["tcs_tax"],
            transit_insurance_opted=order.transit_insurance_opted,
            insurance_fee=comm_invoice["insurance_cost"],
            total_invoice_amount=total_amt,
            escrow_stages={
                "advance_20_pct": round(total_amt * 0.20, 2),
                "dispatch_70_pct": round(total_amt * 0.70, 2),
                "final_10_pct": round(total_amt * 0.10, 2)
            }
        )
        db.add(new_order)

    return {
        "status": "SUCCESS",
        "order": {
            "order_id": new_order.order_id,
            "eway_bill_no": new_order.eway_bill_no,
            "commercial_breakdown": comm_invoice,
            "escrow_stages": new_order.escrow_stages
        }
    }

# 3. Origin Weighbridge Tare & Gross Registration
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
        "message": f"Origin Net Weight Registered: {net_wt} qtl. 70% Dispatch Escrow Released to FPO."
    }

# 4. Destination Net Weight & Quality Deduction (Cutter / Battya) Execution
@app.post("/api/v1/commercial/weighbridge/destination-settle")
def destination_weighbridge_and_cutter(req: DestinationWeighbridgeAndCutter, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    with db.begin():
        order = db.query(models.Order).filter(models.Order.order_id == req.order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        dest_net = round(req.gross_weight_qtl - req.tare_weight_qtl, 2)
        order.destination_gross_wt_qtl = req.gross_weight_qtl
        order.destination_tare_wt_qtl = req.tare_weight_qtl
        order.destination_net_wt_qtl = dest_net

        # Shrinkage check: Allowed tolerance 0.3%
        origin_net = order.origin_net_wt_qtl or order.quantity_qtl
        shortage = round(origin_net - dest_net, 2)
        tolerance_qtl = round(origin_net * 0.003, 2)
        chargeable_shortage = max(0.0, shortage - tolerance_qtl)
        shortage_deduction = round(chargeable_shortage * order.base_price_per_qtl, 2)

        # Moisture Cutter Rule: ₹25/qtl penalty for every 0.5% moisture above contract limit of 11.5%
        contract_moisture_limit = 11.5
        excess_moisture = max(0.0, req.tested_moisture_pct - contract_moisture_limit)
        moisture_penalty_rate = (excess_moisture / 0.5) * 25.0
        moisture_cutter_total = round(moisture_penalty_rate * dest_net, 2)

        total_cutter = round(shortage_deduction + moisture_cutter_total, 2)
        order.tested_destination_moisture = req.tested_moisture_pct
        order.cutter_deduction_amount = total_cutter

        # Final Payout calculation
        final_escrow_pool = order.escrow_stages["final_10_pct"]
        settled_final_payout = max(0.0, round(final_escrow_pool - total_cutter, 2))
        order.final_settled_payout = settled_final_payout
        order.status = "COMPLETED_AND_SETTLED"

    return {
        "status": "SUCCESS",
        "settlement_audit": {
            "origin_net_qtl": origin_net,
            "destination_net_qtl": dest_net,
            "transit_loss_qtl": shortage,
            "allowed_tolerance_qtl": tolerance_qtl,
            "shortage_penalty": shortage_deduction,
            "tested_moisture": req.tested_moisture_pct,
            "moisture_cutter_deduction": moisture_cutter_total,
            "total_deductions": total_cutter,
            "original_final_10pct_escrow": final_escrow_pool,
            "net_final_released_to_fpo": settled_final_payout
        }
    }

# Retain Auction, Slots, and Queue Endpoints
@app.post("/api/v1/bids/create")
def place_buyer_bid(bid: BidPlacementRequest, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    bid_id = f"BID-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
    new_bid = models.BuyerBid(
        bid_id=bid_id,
        buyer_id=user["id"],
        buyer_name=user["name"],
        buyer_phone=user["phone"],
        commodity=bid.commodity,
        target_qty_qtl=bid.target_qty_qtl,
        target_bid_price_per_qtl=bid.target_bid_price_per_qtl,
        delivery_city=bid.delivery_city
    )
    db.add(new_bid)
    db.commit()
    return {"status": "SUCCESS", "bid": {"bid_id": new_bid.bid_id}}

@app.get("/api/v1/bids/live")
def get_live_buyer_bids(db: Session = Depends(get_db)):
    bids = db.query(models.BuyerBid).order_by(models.BuyerBid.created_at.desc()).limit(50).all()
    return [{
        "bid_id": b.bid_id,
        "buyer_name": b.buyer_name,
        "commodity": b.commodity,
        "target_qty_qtl": b.target_qty_qtl,
        "target_bid_price_per_qtl": b.target_bid_price_per_qtl,
        "delivery_city": b.delivery_city,
        "status": b.status
    } for b in bids]

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
                detail=f"Capacity Collision Hazard: '{rule['label']}' is full ({rule['max_capacity']} trucks limit)."
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
            booked_by=user["name"]
        )
        db.add(new_slot)

    return {
        "status": "SUCCESS",
        "slot": {
            "slot_id": new_slot.slot_id,
            "token_number": new_slot.token_number,
            "window_label": new_slot.window_label
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

    return {"status": "SUCCESS", "cancelled_bookings_count": count}