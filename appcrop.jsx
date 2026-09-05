import React, { useState, useEffect } from 'react';
import { 
  TrendingUp, Truck, CloudRain, CheckCircle, 
  MapPin, ShieldCheck, ArrowUpDown, Calendar, DollarSign 
} from 'lucide-react';

const API_BASE = "http://localhost:8000/api/v1";

export default function App() {
  const [activeTab, setActiveTab] = useState("buyer"); // "buyer" or "farmer"
  
  // Buyer Terminal State
  const [commodity, setCommodity] = useState("Wheat");
  const [city, setCity] = useState("Jalandhar");
  const [quantity, setQuantity] = useState(150);
  const [listings, setListings] = useState([]);
  const [bestPick, setBestPick] = useState(null);
  const [loading, setLoading] = useState(false);
  const [notification, setNotification] = useState(null);

  // Farmer Slot Booking State
  const [farmerForm, setFarmerForm] = useState({
    farmer_name: "",
    phone_number: "",
    fpo_mandi: "Khanna, Punjab",
    commodity: "Wheat",
    expected_qty_qtl: 80,
    proposed_price_per_qtl: 2500,
    slot_date: "2026-09-08",
    time_window: "08:00 AM - 12:00 PM"
  });

  const fetchRecommendations = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/recommendations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          commodity,
          buyer_city: city,
          quantity_qtl: Number(quantity)
        })
      });
      const data = await res.json();
      setListings(data.all_listings || []);
      setBestPick(data.best_pick || null);
    } catch (err) {
      console.error("API error:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecommendations();
  }, [commodity, city, quantity]);

  const handleBuy = async (lot) => {
    try {
      const res = await fetch(`${API_BASE}/orders/buy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lot_id: lot.id,
          buyer_name: "Aryan Trading Co.",
          buyer_city: city,
          quantity_qtl: Number(quantity),
          agreed_landed_price: lot.net_landed_cost_per_qtl
        })
      });
      const data = await res.json();
      if (res.ok) {
        setNotification(`Order Confirmed! ₹${data.order.total_amount.toLocaleString()} locked in Escrow. Lot: ${lot.id}`);
        fetchRecommendations();
      } else {
        alert(data.detail || "Order failed");
      }
    } catch (err) {
      alert("Network error processing order");
    }
  };

  const handleBookSlot = async (e) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/fpo/book-slot`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(farmerForm)
      });
      const data = await res.json();
      if (res.ok) {
        setNotification(`Slot Reserved! Gate Pass Code: ${data.booking.booking_id} for ${data.booking.slot_date}`);
      }
    } catch (err) {
      alert("Error booking slot");
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Header Bar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex flex-wrap justify-between items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="bg-emerald-500/20 text-emerald-400 p-2 rounded-lg border border-emerald-500/30">
            <TrendingUp className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-wide flex items-center gap-2">
              AGRI-EXCHANGE <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">SPOT v1.0</span>
            </h1>
            <p className="text-xs text-slate-400">Nationwide Commodity Arbitrage & Supply Chain Engine</p>
          </div>
        </div>

        {/* Tab Toggle */}
        <div className="flex bg-slate-800 p-1 rounded-lg border border-slate-700">
          <button 
            onClick={() => setActiveTab("buyer")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${activeTab === 'buyer' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>
            Wholesale Terminal
          </button>
          <button 
            onClick={() => setActiveTab("farmer")}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition ${activeTab === 'farmer' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-white'}`}>
            Farmer / FPO Portal
          </button>
        </div>
      </header>

      {/* Notification Toast */}
      {notification && (
        <div className="bg-emerald-950 border border-emerald-500 text-emerald-200 px-6 py-3 mx-6 mt-4 rounded-lg flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm">
            <CheckCircle className="w-5 h-5 text-emerald-400" />
            {notification}
          </span>
          <button onClick={() => setNotification(null)} className="text-xs underline font-mono">Dismiss</button>
        </div>
      )}

      {activeTab === "buyer" ? (
        <main className="p-6 max-w-7xl mx-auto space-y-6">
          {/* Filter Bar */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-900 border border-slate-800 p-4 rounded-xl">
            <div>
              <label className="text-xs text-slate-400 font-medium mb-1 block">Commodity</label>
              <select 
                value={commodity} 
                onChange={(e) => setCommodity(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500">
                <option value="Wheat">Wheat (Gahu)</option>
                <option value="Rice">Rice (Chawal)</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-400 font-medium mb-1 block">Your Destination City</label>
              <select 
                value={city} 
                onChange={(e) => setCity(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500">
                <option value="Jalandhar">Jalandhar, Punjab</option>
                <option value="Delhi">Delhi NCR</option>
                <option value="Chandigarh">Chandigarh</option>
                <option value="Jaipur">Jaipur, Rajasthan</option>
                <option value="Mumbai">Mumbai, MH</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-slate-400 font-medium mb-1 block">Quantity (Quintals)</label>
              <input 
                type="number" 
                value={quantity} 
                onChange={(e) => setQuantity(e.target.value)}
                min="10"
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="flex items-end">
              <button 
                onClick={fetchRecommendations}
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-medium py-2 rounded-lg text-sm transition">
                {loading ? "Calculating Routes..." : "Run Arbitrage Model"}
              </button>
            </div>
          </div>

          {/* AI Recommended Pick Spotlight */}
          {bestPick && (
            <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900 to-slate-900 border border-emerald-500/40 rounded-xl p-5 shadow-lg">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="bg-emerald-500 text-black text-xs font-bold px-2 py-0.5 rounded uppercase">Best Landed Value</span>
                    <span className="text-slate-400 text-xs font-mono">ID: {bestPick.id}</span>
                  </div>
                  <h2 className="text-xl font-bold text-white">{bestPick.mandi} — {bestPick.variety}</h2>
                  <p className="text-sm text-slate-300">Managed by {bestPick.fpo_name} • Moisture: {bestPick.moisture_percent}%</p>
                </div>

                <div className="flex flex-wrap items-center gap-6">
                  <div>
                    <div className="text-xs text-slate-400">Total Landed Cost</div>
                    <div className="text-2xl font-black text-emerald-400">₹{bestPick.net_landed_cost_per_qtl} <span className="text-xs font-normal text-slate-400">/ qtl</span></div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-400">Recommendation Score</div>
                    <div className="text-2xl font-black text-white">{bestPick.recommendation_score}%</div>
                  </div>
                  <button 
                    onClick={() => handleBuy(bestPick)}
                    className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold px-6 py-2.5 rounded-lg transition shadow-md">
                    Lock Price & Buy
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Marketplace Order Book Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow">
            <div className="px-5 py-3 border-b border-slate-800 flex justify-between items-center">
              <h3 className="font-semibold text-sm text-slate-200">Regional Spot Order Ladder (Sorted by Feasibility)</h3>
              <span className="text-xs text-slate-500 font-mono">Refreshed live with weather & toll index</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-950/60 text-slate-400 uppercase font-mono text-xs border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4">Origin / Mandi</th>
                    <th className="py-3 px-4">Base Mandi Price</th>
                    <th className="py-3 px-4">Distance / Transit</th>
                    <th className="py-3 px-4">Weather & Road</th>
                    <th className="py-3 px-4">Landed Cost / qtl</th>
                    <th className="py-3 px-4">Total Order</th>
                    <th className="py-3 px-4 text-center">Score</th>
                    <th className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {listings.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-800/40 transition">
                      <td className="py-3.5 px-4">
                        <div className="font-medium text-white">{item.mandi}</div>
                        <div className="text-xs text-slate-400">{item.variety} • {item.fpo_name}</div>
                      </td>
                      <td className="py-3.5 px-4 font-mono">
                        ₹{item.base_price_per_qtl}
                      </td>
                      <td className="py-3.5 px-4 font-mono text-xs">
                        <div>{item.distance_km} km</div>
                        <div className="text-slate-400">~{item.transit_hours} hrs ETA</div>
                      </td>
                      <td className="py-3.5 px-4 text-xs">
                        <div className="flex items-center gap-1 text-slate-300">
                          <CloudRain className="w-3.5 h-3.5 text-blue-400" />
                          {item.weather_forecast} ({item.rain_risk_percent}% rain)
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-mono font-semibold text-emerald-400">
                        ₹{item.net_landed_cost_per_qtl}
                      </td>
                      <td className="py-3.5 px-4 font-mono">
                        ₹{item.total_order_cost.toLocaleString()}
                      </td>
                      <td className="py-3.5 px-4 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold ${
                          item.recommendation_score > 75 
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" 
                            : "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                        }`}>
                          {item.recommendation_score}%
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <button 
                          onClick={() => handleBuy(item)}
                          className="bg-slate-800 hover:bg-emerald-600 hover:text-white text-slate-200 border border-slate-700 text-xs px-3.5 py-1.5 rounded-md font-medium transition">
                          Buy Now
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </main>
      ) : (
        /* Farmer & FPO Slot Booking Screen */
        <main className="p-6 max-w-2xl mx-auto space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow">
            <h2 className="text-lg font-bold text-white mb-1 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-emerald-400" />
              Book Mandi Unloading Gate Pass
            </h2>
            <p className="text-xs text-slate-400 mb-6">
              Lock your sale price with verified buyers and schedule queue-free delivery at partner FPOs.
            </p>

            <form onSubmit={handleBookSlot} className="space-y-4">
              <div>
                <label className="text-xs text-slate-400 font-medium block mb-1">Farmer / Entity Full Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g. Harpreet Singh"
                  value={farmerForm.farmer_name}
                  onChange={(e) => setFarmerForm({...farmerForm, farmer_name: e.target.value})}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Phone (for SMS Gate Pass)</label>
                  <input 
                    type="tel" 
                    required
                    placeholder="98XXXXXXXX"
                    value={farmerForm.phone_number}
                    onChange={(e) => setFarmerForm({...farmerForm, phone_number: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Target FPO / Mandi Hub</label>
                  <select 
                    value={farmerForm.fpo_mandi}
                    onChange={(e) => setFarmerForm({...farmerForm, fpo_mandi: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500">
                    <option value="Khanna, Punjab">Khanna Mandi, Punjab</option>
                    <option value="Karnal, Haryana">Karnal Mandi, Haryana</option>
                    <option value="Indore, MP">Indore Mandi, MP</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Estimated Quantity (Quintals)</label>
                  <input 
                    type="number" 
                    required
                    value={farmerForm.expected_qty_qtl}
                    onChange={(e) => setFarmerForm({...farmerForm, expected_qty_qtl: Number(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Expected Rate (₹ per Quintal)</label>
                  <input 
                    type="number" 
                    required
                    value={farmerForm.proposed_price_per_qtl}
                    onChange={(e) => setFarmerForm({...farmerForm, proposed_price_per_qtl: Number(e.target.value)})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Slot Date</label>
                  <input 
                    type="date" 
                    required
                    value={farmerForm.slot_date}
                    onChange={(e) => setFarmerForm({...farmerForm, slot_date: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 font-medium block mb-1">Arrival Window</label>
                  <select 
                    value={farmerForm.time_window}
                    onChange={(e) => setFarmerForm({...farmerForm, time_window: e.target.value})}
                    className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-emerald-500">
                    <option value="06:00 AM - 10:00 AM">06:00 AM - 10:00 AM (Early)</option>
                    <option value="10:00 AM - 02:00 PM">10:00 AM - 02:00 PM (Midday)</option>
                    <option value="02:00 PM - 06:00 PM">02:00 PM - 06:00 PM (Evening)</option>
                  </select>
                </div>
              </div>

              <button 
                type="submit"
                className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded-lg transition mt-2">
                Generate Digital Gate Pass
              </button>
            </form>
          </div>
        </main>
      )}
    </div>
  );
}