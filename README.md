# 🌾 KisanVyapar Mandi Desk (राष्ट्रीय कृषि थोक व्यापार मंच)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=flat&logo=react&logoColor=black)](https://reactjs.org/)
[![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC.svg?style=flat&logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![SQLite](https://img.shields.io/badge/Database-SQLite%20%2F%20PostgreSQL-003B57.svg?style=flat&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A high-performance B2B agricultural commodity trading desk connecting registered **Farmer Producer Companies (FPCs)** across India directly with flour millers, rice processors, and institutional buyers. Built to model authentic Indian APMC Mandi dynamics with transparent landed cost calculations, live double-auction bidding, 3-stage milestone escrow, and farmer member pool passbook traceability.

---

## 📋 Table of Contents
- [Key Features](#-key-features)
- [Trading Personas & Registered Entities](#-trading-personas--registered-entities)
- [Commercial Bhao Formula](#-commercial-bhao-formula)
- [Architecture & Tech Stack](#-architecture--tech-stack)
- [Project Structure](#-project-structure)
- [Quick Start & Installation](#-quick-start--installation)
- [API Reference](#-api-reference)
- [Production Deployment](#-production-deployment)
- [License](#-license)

---

## 🌟 Key Features

### 1. 🔍 शुद्ध लैंडेड भाव कैलकुलेटर (Landed Bhao Calculator)
- Calculates true per-quintal delivered cost incorporating:
  - **Mandi Base Bhao (मंडी मूल भाव)**
  - **Packaging / Bardana (बारदाना)** (50kg New Jute Gunny, PP Woven, or Bulk Tipper)
  - **Highway Gaddi Bhada (गाड़ी भाड़ा)** with live highway network routing (NH-44, NH-48, NH-46)
  - **Statutory APMC Cess & RDF (मंडी सेस + ग्रामीण विकास निधि)** by origin state (Punjab, Haryana, MP, Rajasthan, UP, Gujarat)
  - **Statutory TCS (0.1%)** on agricultural transactions exceeding statutory thresholds
  - **Transit Marine Insurance (0.08%)** with National Insurance Company Ltd.
- Live weather & precipitation hazard monitoring via Open-Meteo along transit corridors to calculate spoilage risk.

### 2. ⚡ 1-Click खरीदार / विक्रेता डेस्क (Buyer & Seller Dual Desk)
- Seamless 1-click toggle between **🌾 खरीदार पोर्टल (Buyer Desk)** and **🚜 विक्रेता पोर्टल (FPO Seller Desk)**.
- **Buyer Desk**: Instant buy at best mandi quote, request 1kg sealed courier sample, or place target price demand bids.
- **FPO Seller Desk**: Counter buyer bids, accept contracts, review member pool quotas, and verify dispatch weighbridge slips.

### 3. 🔒 3-चरणीय सुरक्षित अमानत प्रणाली (3-Stage Milestone Escrow)
- **Stage 1 (20% Advance Escrow)**: Locked immediately upon contract agreement / bid acceptance to secure grain lot allocation.
- **Stage 2 (70% Dispatch Escrow)**: Released directly to the FPO upon origin gate dispatch and 12-digit GST E-Way Bill generation.
- **Stage 3 (10% Final Settlement)**: Settled upon destination weighbridge net weight confirmation and moisture inspection.

### 4. 👨‍🌾 किसान सदस्य बही खाता (Farmer Member Pool Passbook)
- Complete transparency for farmer members contributing to aggregated FPO lots.
- Displays member names, authentic villages, contributed quintals, share ratios, APMC cess deductions, masked bank account numbers, and valid 11-character Indian banking IFSC codes (`SBIN0000662`, `PUNB0024300`, `HDFC0000287`, `BARB0INDORE`).
- 1-click switching across all 7 registered FPO crop lots.

### 5. 📜 सरकारी अनुपालन एवं नमूना ट्रैकिंग (Compliance & Sample Dispatch)
- **12-Digit GST E-Way Bill**: Authentic e-Way Bill slips (e.g. `2418 9034 5122`) verified under CGST Rule 138 with valid HSN codes (1001 for Wheat, 1006 for Rice).
- **APMC Digital M-Form / Anugya Patra**: State Agricultural Marketing Board clearance hash exempt from highway checkpoint seizure.
- **1kg Sealed Courier Samples**: Tamper-evident courier parcels dispatched via DTDC Express & Blue Dart Agri Cargo services.

---

## 🏢 Trading Personas & Registered Entities

| Entity Name | Role | City / Mandi | GSTIN / Registration |
| :--- | :--- | :--- | :--- |
| **Aryan Foods & Flour Mills Pvt. Ltd.** | Buyer (Flour Miller) | Jalandhar, Punjab | `03AAACA4582K1ZD` |
| **Delhi Agro Processing Corp Pvt. Ltd.** | Buyer (Food Processor) | Lawrence Road, Delhi | `07AABCD8821L1ZM` |
| **Doaba Farmer Producer Company Ltd.** | FPO Seller | Khanna APMC Mandi, Punjab | `03AAACD9182P1ZQ` |
| **Taraori Basmati Growers Farmer Producer Co.** | FPO Seller | Karnal Mandi, Haryana | `06AABCK7712M1ZF` |
| **Malwa Kisan Samriddhi Producer Co. Ltd.** | FPO Seller | Indore Mandi, MP | `23AAACM5182Q1Z8` |
| **Hadoti Kisan Vikas Agro Producer Co. Ltd.** | FPO Seller | Kota Mandi, Rajasthan | `08AAACH4192L1Z3` |
| **Punjab Mandi Board (Secretary Office)** | APMC Administrator | Asia's Biggest Grain Market, Khanna | `03-APMC-KHN-BOARD` |
| **Punjab Highway Freight Fleet** | Transporter Guild | Ludhiana Transport Nagar | `03-TRANSP-LDH-44` |

---

## 🧮 Commercial Bhao Formula

$$\text{Net Landed Cost} = \frac{\text{Mandi Base} + \text{Packaging} + \text{Freight} + \text{APMC Cess} + \text{TCS (0.1\%)} + \text{Insurance (0.08\%)}}{\text{Quantity (Qtl)}}$$

Where:
- **Packaging**: Jute Gunny (+₹65/qtl), PP Bag (+₹28/qtl), Bulk Loose (+₹0/qtl).
- **APMC Cess**: State-specific statutory rates (Punjab/Haryana: 2% Mandi Fee + 2% RDF = 4%; MP: 1.5%; UP: 2.5%; Gujarat: 1.5%).
- **Freight**: Dynamic road distance ($\text{km} \times ₹0.038) + ₹25.00\text{ handling} + \text{toll share}$.

---

## 🛠 Architecture & Tech Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn, SQLAlchemy, Pydantic, PyJWT, HTTPX.
- **Routing & Weather**: OpenStreetMap OSRM road network router + Open-Meteo live API.
- **Frontend**: Single-Page Application (SPA) with React 18, Babel standalone, Tailwind CSS.
- **Typography**: `Rozha One` (Mandi Serif), `Inter` (UI Sans), `Fira Code` (Numeric/Financial Mono).
- **Database**: SQLite (default) / PostgreSQL (production-ready).
- **Networking**: Cloudflare Quick Tunnels, Docker containerization.

---

## 📂 Project Structure

```text
Crops/
├── backend/                  # Backend replica & deployment package
│   ├── main.py               # FastAPI application, auth, and trading endpoints
│   ├── engine.py             # Mandi scoring, OSRM routing & invoice calculation
│   ├── models.py             # SQLAlchemy database models
│   ├── database.py           # Database engine & session maker
│   └── static/               # Static web assets
├── static/
│   └── index.html            # Main React 18 frontend dashboard
├── index.html                # Root web bundle
├── main.py                   # Main FastAPI runner
├── engine.py                 # Core recommendation & trade engine
├── models.py                 # ORM models (CropLot, BuyerBid, Order, etc.)
├── database.py               # SQLite / PostgreSQL configuration
├── Dockerfile                # Production multi-stage Docker build
├── docker-compose.yml        # Multi-container orchestration
├── deploy.sh                 # Zero-downtime deployment script
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation
```

---

## 🚀 Quick Start & Installation

### Prerequisites
- Python 3.10+ (Python 3.12 recommended)
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/Coldsun458/Crops.git
cd Crops
```

### 2. Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Access the Platform
- **Trading Desk Dashboard**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 📡 API Reference

### Authentication & Profiles
- `GET  /api/v1/auth/accounts` — Returns authentic trading accounts with GSTINs and roles.
- `POST /api/v1/auth/login` — Issues signed JWT access token for selected persona.
- `GET  /api/v1/auth/me` — Verifies active token and persona identity.

### Mandi Recommendations & Landed Bhao
- `POST /api/v1/recommendations` — Scans all regional lots and ranks options by landed cost, highway corridor weather, and quality scores.
- `GET  /api/v1/market/registry` — Returns registered APMC mandis and destination cities with coordinates.

### Double Auction & Bidding
- `GET  /api/v1/bids/live` (or `/api/v1/bids/all`) — Lists all active buyer bids and FPO counter-offers.
- `POST /api/v1/bids/create` — Submits a new demand bid or FPO sale offer.
- `POST /api/v1/bids/{bid_id}/accept` — Locks deal into Stage 1 Escrow (20%).
- `POST /api/v1/bids/{bid_id}/counter` — Submits FPO price counter-offer.
- `POST /api/v1/bids/{bid_id}/counter-accept` — Accepts counter-offer and binds contract.

### Commercial Orders & Escrow
- `POST /api/v1/orders/buy` — Places spot order and generates 12-digit GST E-Way Bill.
- `GET  /api/v1/orders/all` — Lists orders with real-time escrow milestone statuses.
- `POST /api/v1/orders/{order_id}/dispatch` — 1-click dispatch releasing Stage 2 (70%) Escrow.
- `POST /api/v1/orders/{order_id}/confirm-delivery` — Final settlement (10%) upon destination weighbridge confirmation.

### FPO Member Passbook & Compliance
- `GET  /api/v1/fpo/farmer-passbook/{lot_id}` — Member-wise pool breakdown and bank account ledger.
- `GET  /api/v1/compliance/mform/{mform_hash}` — Validates digital APMC M-Form clearance.
- `GET  /api/v1/compliance/eway-bill/{eway_bill_no}` — Validates 12-digit GST E-Way Bill slip.
- `GET  /api/v1/commercial/samples` — Tracks sealed 1kg courier sample requests.

---

## 🌐 Production Deployment

### Docker Deployment
```bash
docker build -t kisanvyapar-mandi:latest .
docker run -d -p 8000:8000 --name kisanvyapar kisanvyapar-mandi:latest
```

### Docker Compose
```bash
docker-compose up -d
```

### Cloudflare Quick Tunnel
```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

---

## 📄 License
This project is open-source and distributed under the **MIT License**.
