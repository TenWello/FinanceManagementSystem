import { useState } from "react";
import { BrowserRouter, Routes, Route, NavLink, useLocation } from "react-router-dom";
import Overview from "./pages/Overview";
import Transactions from "./pages/Transactions";
import Analytics from "./pages/Analytics";
import Categories from "./pages/Categories";
import { LayoutDashboard, ArrowLeftRight, BarChart3, Tag, TrendingUp } from "lucide-react";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
export { API };

function Sidebar() {
  const navItems = [
    { to: "/", icon: LayoutDashboard, label: "Bosh sahifa" },
    { to: "/transactions", icon: ArrowLeftRight, label: "Tranzaksiyalar" },
    { to: "/analytics", icon: BarChart3, label: "Tahlil" },
    { to: "/categories", icon: Tag, label: "Kategoriyalar" },
  ];

  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col min-h-screen fixed left-0 top-0">
      <div className="p-6 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-indigo-500 rounded-xl flex items-center justify-center">
            <TrendingUp size={18} />
          </div>
          <div>
            <h1 className="font-bold text-sm leading-tight">Finance Manager</h1>
            <p className="text-gray-400 text-xs">Business Dashboard</p>
          </div>
        </div>
      </div>

      <nav className="flex-1 p-4 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all ${
                isActive
                  ? "bg-indigo-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="p-4 border-t border-gray-700">
        <div className="bg-gray-800 rounded-xl p-3 text-xs text-gray-400">
          <p className="font-medium text-gray-300 mb-1">💬 Telegram Bot</p>
          <p>@finance_data365_bot orqali ham tranzaksiya qo'shishingiz mumkin</p>
        </div>
      </div>
    </aside>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="flex bg-gray-50 min-h-screen">
        <Sidebar />
        <main className="ml-64 flex-1 p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/categories" element={<Categories />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
