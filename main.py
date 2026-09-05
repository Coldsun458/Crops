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

from database import engine, get_db, Base
import models
from engine import CITY_COORDINATES, calculate_best_buy, calculate_commercial_invoice

Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgriExchange Wholesaler Production Engine", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JWT_SECRET = os.getenv("SECRET_KEY", "agri-exchange-jwt-secret-key-2026")
JWT_ALGORITHM = os.getenv("ALGORITHM", "HS256")

MOCK_USERS = {
    "buyer@mill.com": {"id": "USR-BUYER-01", "name": "Aryan Foods & Flour Mills", "role": "BUYER", "city": "Jalandhar", "phone": "+91 98765-11223"},
    "manager@doaba-fpo.org": {"id": "USR-FPO-01", "name": "Doaba Agri Producers Co.", "role": "FPO", "city": "Khanna", "phone": "+91 98765-44556"}
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

class FPONewLotListing(BaseModel):
    commodity: str
    variety: str
    mandi: str
    total_qty_qtl: float
    asking_price_per_qtl: float
    moisture_percent: float
    bagging_type: str = "50KG_JUTE_GUNNY"

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
        "message": f"Sealed 1kg parcel dispatched via Express Courier for {lot.variety}",
        "sample": {
            "sample_id": sample_id,
            "courier_tracking_no": tracking,
            "courier_partner": "DTDC Express Agri-Cold Courier",
            "fee_debited": 450.0
        }
    }

@app.post("/api/v1/orders/buy")
def place_commercial_order(order: OrderRequest, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.id == order.lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Crop lot not found")
    if lot.available_qty_qtl < order.quantity_qtl:
        raise HTTPException(status_code=400, detail="Requested quantity exceeds stock balance")

    lot.available_qty_qtl -= order.quantity_qtl
    
    comm_invoice = calculate_commercial_invoice(
        base_price_per_qtl=lot.base_price_per_qtl,
        quantity_qtl=order.quantity_qtl,
        freight_per_qtl=65.0,
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
    db.commit()

    return {
        "status": "SUCCESS",
        "order": {
            "order_id": new_order.order_id,
            "eway_bill_no": new_order.eway_bill_no,
            "commercial_breakdown": comm_invoice,
            "escrow_stages": new_order.escrow_stages
        }
    }

@app.post("/api/v1/commercial/weighbridge/destination-settle")
def destination_weighbridge_and_cutter(req: DestinationWeighbridgeAndCutter, user: dict = Depends(RoleChecker(["BUYER"])), db: Session = Depends(get_db)):
    order = db.query(models.Order).filter(models.Order.order_id == req.order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    dest_net = round(req.gross_weight_qtl - req.tare_weight_qtl, 2)
    order.destination_gross_wt_qtl = req.gross_weight_qtl
    order.destination_tare_wt_qtl = req.tare_weight_qtl
    order.destination_net_wt_qtl = dest_net

    origin_net = order.origin_net_wt_qtl or order.quantity_qtl
    shortage = round(origin_net - dest_net, 2)
    tolerance_qtl = round(origin_net * 0.003, 2)
    chargeable_shortage = max(0.0, shortage - tolerance_qtl)
    shortage_deduction = round(chargeable_shortage * order.base_price_per_qtl, 2)

    contract_moisture_limit = 11.5
    excess_moisture = max(0.0, req.tested_moisture_pct - contract_moisture_limit)
    moisture_penalty_rate = (excess_moisture / 0.5) * 25.0
    moisture_cutter_total = round(moisture_penalty_rate * dest_net, 2)

    total_cutter = round(shortage_deduction + moisture_cutter_total, 2)
    order.tested_destination_moisture = req.tested_moisture_pct
    order.cutter_deduction_amount = total_cutter

    final_escrow_pool = order.escrow_stages["final_10_pct"]
    settled_final_payout = max(0.0, round(final_escrow_pool - total_cutter, 2))
    order.final_settled_payout = settled_final_payout
    order.status = "COMPLETED_AND_SETTLED"
    db.commit()

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

@app.post("/api/v1/bids/{bid_id}/accept")
def accept_buyer_bid(bid_id: str, user: dict = Depends(RoleChecker(["FPO"])), db: Session = Depends(get_db)):
    bid = db.query(models.BuyerBid).filter(models.BuyerBid.bid_id == bid_id).first()
    if not bid:
        raise HTTPException(status_code=404, detail="Bid not found")
    bid.status = "MATCHED_AND_LOCKED"
    bid.accepted_by_fpo = user["name"]
    db.commit()
    return {"status": "SUCCESS", "message": f"Bid matched with {user['name']}"}

@app.post("/api/v1/fpo/create-lot")
def create_fpo_lot(lot: FPONewLotListing, user: dict = Depends(RoleChecker(["FPO"])), db: Session = Depends(get_db)):
    new_id = f"FPO-LOT-{int(datetime.now(timezone.utc).timestamp()) % 10000}"
    new_entry = models.CropLot(
        id=new_id,
        fpo_name=user["name"],
        commodity=lot.commodity,
        variety=lot.variety,
        mandi=lot.mandi,
        base_price_per_qtl=lot.asking_price_per_qtl,
        available_qty_qtl=lot.total_qty_qtl,
        moisture_percent=lot.moisture_percent,
        bagging_type=lot.bagging_type,
        assaying={"foreign_matter_pct": 0.5, "broken_pct": 1.0, "protein_pct": 12.0, "lab_name": f"{lot.mandi} NABL Center"},
        farmer_members=[{"member_id": f"FARM-{uuid.uuid4().hex[:4].upper()}", "name": "Aggregated Cluster Member", "pool_qty_qtl": lot.total_qty_qtl}]
    )
    db.add(new_entry)
    db.commit()
    return {"status": "SUCCESS", "lot": {"id": new_entry.id}}

@app.get("/api/v1/fpo/farmer-passbook/{lot_id}")
def get_farmer_passbook(lot_id: str, user: dict = Depends(RoleChecker(["FPO"])), db: Session = Depends(get_db)):
    lot = db.query(models.CropLot).filter(models.CropLot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot not found")
    return {"lot_id": lot.id, "rate_per_qtl": lot.base_price_per_qtl, "farmers": lot.farmer_members or []}