import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON, ForeignKey, Index
from database import Base

class CropLot(Base):
    __tablename__ = "crop_lots"

    id = Column(String(32), primary_key=True, index=True)
    commodity = Column(String(32), index=True, nullable=False)
    variety = Column(String(64), nullable=False)
    mandi = Column(String(64), index=True, nullable=False)
    fpo_name = Column(String(128), nullable=False)
    base_price_per_qtl = Column(Float, nullable=False)
    available_qty_qtl = Column(Float, nullable=False)
    moisture_percent = Column(Float, nullable=False)
    
    # Commercial Wholesaler Parameters
    bagging_type = Column(String(32), default="50KG_JUTE_GUNNY")  # 50KG_JUTE_GUNNY, 50KG_PP_BAG, BULK_LOOSE_TIPPER
    bag_cost_included = Column(Boolean, default=True)
    apmc_cess_paid_at_source = Column(Boolean, default=True)
    mform_document_hash = Column(String(64), default="M-FORM-VERIFIED-PUNJAB-2026")
    
    assaying = Column(JSON, default=dict)
    farmer_members = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(String(32), primary_key=True, index=True)
    eway_bill_no = Column(String(32), unique=True, index=True, nullable=False)
    lot_id = Column(String(32), ForeignKey("crop_lots.id"), nullable=False)
    buyer_id = Column(String(32), nullable=False)
    buyer_name = Column(String(128), nullable=False)
    buyer_phone = Column(String(20), nullable=False)
    delivery_address = Column(String(256), nullable=False)
    gstin = Column(String(20), nullable=False)
    payment_method = Column(String(32), default="ESCROW_UPI")
    quantity_qtl = Column(Float, nullable=False)
    
    # Financial Breakdown
    base_price_per_qtl = Column(Float, nullable=False)
    freight_per_qtl = Column(Float, nullable=False)
    apmc_cess_amount = Column(Float, nullable=False)
    tcs_tax_amount = Column(Float, nullable=False)
    transit_insurance_opted = Column(Boolean, default=True)
    insurance_fee = Column(Float, default=0.0)
    total_invoice_amount = Column(Float, nullable=False)
    
    # Escrow Milestone Balances
    escrow_stages = Column(JSON, nullable=False)
    
    # Weighbridge Double-Slip Reconciliation
    origin_gross_wt_qtl = Column(Float, nullable=True)
    origin_tare_wt_qtl = Column(Float, nullable=True)
    origin_net_wt_qtl = Column(Float, nullable=True)
    destination_gross_wt_qtl = Column(Float, nullable=True)
    destination_tare_wt_qtl = Column(Float, nullable=True)
    destination_net_wt_qtl = Column(Float, nullable=True)
    transit_weight_loss_qtl = Column(Float, default=0.0)
    
    # Quality Cutter / Battya Deductions
    tested_destination_moisture = Column(Float, nullable=True)
    cutter_deduction_amount = Column(Float, default=0.0)
    final_settled_payout = Column(Float, nullable=True)

    bagging_type = Column(String(32), default="50KG_JUTE_GUNNY")
    tested_destination_broken = Column(Float, nullable=True)
    tested_foreign_matter = Column(Float, nullable=True)
    insurance_policy_no = Column(String(64), nullable=True)

    status = Column(String(32), default="ADVANCE_ESCROW_LOCKED", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class SampleCourierRequest(Base):
    __tablename__ = "sample_requests"

    sample_id = Column(String(32), primary_key=True, index=True)
    lot_id = Column(String(32), ForeignKey("crop_lots.id"), nullable=False)
    buyer_name = Column(String(128), nullable=False)
    buyer_phone = Column(String(20), nullable=True)
    delivery_address = Column(String(256), nullable=False)
    courier_tracking_no = Column(String(64), nullable=False)
    courier_partner = Column(String(64), default="DTDC Express Agri-Cold Courier")
    fee_paid = Column(Float, default=450.0)
    status = Column(String(32), default="DISPATCHED", index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class BuyerBid(Base):
    __tablename__ = "buyer_bids"

    bid_id = Column(String(32), primary_key=True, index=True)
    buyer_id = Column(String(32), nullable=False)
    buyer_name = Column(String(128), nullable=False)
    buyer_phone = Column(String(20), nullable=False)
    commodity = Column(String(32), index=True, nullable=False)
    target_qty_qtl = Column(Float, nullable=False)
    target_bid_price_per_qtl = Column(Float, nullable=False)
    delivery_city = Column(String(64), nullable=False)
    status = Column(String(32), default="OPEN_AUCTION", index=True)
    accepted_by_fpo = Column(String(128), nullable=True)
    counter_price_per_qtl = Column(Float, nullable=True)
    counter_fpo_name = Column(String(128), nullable=True)
    counter_notes = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ScheduledSlot(Base):
    __tablename__ = "scheduled_slots"

    slot_id = Column(String(32), primary_key=True, index=True)
    token_number = Column(Integer, nullable=False)
    mandi_hub = Column(String(64), index=True, nullable=False)
    slot_date = Column(String(16), index=True, nullable=False)
    window_key = Column(String(32), index=True, nullable=False)
    window_label = Column(String(64), nullable=False)
    truck_reg_number = Column(String(24), nullable=False)
    commodity = Column(String(32), nullable=False)
    quantity_qtl = Column(Float, nullable=False)
    booked_by = Column(String(128), nullable=False)
    status = Column(String(32), default="CONFIRMED", index=True)
    delay_minutes = Column(Integer, default=0)
    delay_reason = Column(String(256), nullable=True)
    cancellation_reason = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_slot_collision_check", "mandi_hub", "slot_date", "window_key", "status"),
    )