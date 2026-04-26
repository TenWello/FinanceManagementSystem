import { useState, useEffect } from "react";
import { API } from "../App";
import {
  TrendingUp, TrendingDown, DollarSign, Plus, X, Check,
  ArrowUpRight, ArrowDownRight, Clock, Zap
} from "lucide-react";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from "recharts";

const fmt = (n) =>
  new Intl.NumberFormat("uz-UZ").format(Math.round(n || 0)) + " so'm";

const pct = (curr, prev) => {
  if (!prev) return null;
  const d = ((curr - prev) / prev) * 100;
  return d.toFixed(1);
};

function StatCard({ label, value, prev, type, icon: Icon, color }) {
  const change = pct(value, prev);
  const up = change > 0;

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${color}`}>
          <Icon size={20} className="text-white" />
        </div>
        {change !== null && (
          <span className={`flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full ${
            up ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"
          }`}>
            {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
            {Math.abs(change)}%
          </span>
        )}
      </div>
      <p className="text-2xl font-bold text-gray-900 mb-1">{fmt(value)}</p>
      <p className="text-sm text-gray-500">{label}</p>
      {prev !== undefined && (
        <p className="text-xs text-gray-400 mt-1">O'tgan oy: {fmt(prev)}</p>
      )}
    </div>
  );
}

function QuickAdd({ onAdded }) {
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ type: "income", amount: "", category: "sotuv", note: "" });
  const [categories, setCategories] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API}/categories`)
      .then(r => r.json())
      .then(setCategories)
      .catch(() => {});
  }, []);

  const filtered = categories.filter(c => c.type === form.type || c.type === "both");

  const submit = async () => {
    if (!form.amount || isNaN(form.amount)) return;
    setSaving(true);
    try {
      await fetch(`${API}/transactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...form,
          amount: parseFloat(form.amount),
          date: new Date().toISOString().slice(0, 10),
        }),
      });
      setForm({ type: "income", amount: "", category: "sotuv", note: "" });
      setShow(false);
      onAdded?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100">
      {!show ? (
        <button
          onClick={() => setShow(true)}
          className="w-full flex items-center gap-3 p-5 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-2xl transition-all group"
        >
          <div className="w-9 h-9 bg-indigo-100 group-hover:bg-indigo-200 rounded-xl flex items-center justify-center transition-colors">
            <Plus size={18} className="text-indigo-600" />
          </div>
          <span className="font-medium">Yangi tranzaksiya qo'shish</span>
          <Zap size={14} className="ml-auto text-indigo-400" />
        </button>
      ) : (
        <div className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-gray-800">Tez qo'shish</h3>
            <button onClick={() => setShow(false)} className="text-gray-400 hover:text-gray-600">
              <X size={18} />
            </button>
          </div>

          {/* Type toggle */}
          <div className="flex gap-2 mb-4 p-1 bg-gray-100 rounded-xl">
            {["income", "expense"].map(t => (
              <button
                key={t}
                onClick={() => setForm(f => ({ ...f, type: t, category: t === "income" ? "sotuv" : "maosh" }))}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                  form.type === t
                    ? t === "income" ? "bg-emerald-500 text-white" : "bg-red-500 text-white"
                    : "text-gray-600"
                }`}
              >
                {t === "income" ? "💰 Kirim" : "💸 Chiqim"}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            <input
              type="number"
              placeholder="Summa (so'm)"
              value={form.amount}
              onChange={e => setForm(f => ({ ...f, amount: e.target.value }))}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <select
              value={form.category}
              onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              {filtered.map(c => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Izoh (ixtiyoriy)"
              value={form.note}
              onChange={e => setForm(f => ({ ...f, note: e.target.value }))}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
            <button
              onClick={submit}
              disabled={saving}
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2.5 rounded-xl font-medium text-sm transition-colors flex items-center justify-center gap-2"
            >
              <Check size={16} />
              {saving ? "Saqlanmoqda..." : "Saqlash"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-white rounded-2xl border border-dashed border-gray-200 p-12 text-center">
      <div className="w-16 h-16 bg-indigo-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
        <DollarSign size={28} className="text-indigo-400" />
      </div>
      <h3 className="text-lg font-semibold text-gray-800 mb-2">Hali ma'lumot yo'q</h3>
      <p className="text-gray-500 text-sm max-w-xs mx-auto mb-6">
        Birinchi tranzaksiyangizni qo'shing yoki Telegram bot orqali yuborishni boshlang.
      </p>
      <div className="bg-gray-50 rounded-xl p-4 text-left max-w-xs mx-auto">
        <p className="text-xs text-gray-500 font-medium mb-2">Bot misoli:</p>
        <p className="text-sm font-mono text-indigo-600">"Sotuv 500 000 so'm tushdi"</p>
        <p className="text-sm font-mono text-red-500 mt-1">"Ijara 2 mln to'ladik"</p>
      </div>
    </div>
  );
}

export default function Overview() {
  const [report, setReport] = useState(null);
  const [recent, setRecent] = useState([]);
  const [period, setPeriod] = useState("month");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [rep, txs] = await Promise.all([
        fetch(`${API}/report?period=${period}`).then(r => r.json()),
        fetch(`${API}/transactions?limit=8`).then(r => r.json()),
      ]);
      setReport(rep);
      setRecent(txs);
    } catch {}
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [period]);

  const chartData = (() => {
    if (!report?.daily) return [];
    const map = {};
    report.daily.forEach(({ date, type, amount }) => {
      if (!map[date]) map[date] = { date, income: 0, expense: 0 };
      map[date][type] += amount;
    });
    return Object.values(map);
  })();

  const periods = [
    { key: "today", label: "Bugun" },
    { key: "week", label: "Hafta" },
    { key: "month", label: "Oy" },
    { key: "year", label: "Yil" },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bosh sahifa</h1>
          <p className="text-gray-500 text-sm mt-1">Kompaniya moliyaviy ko'rsatkichlari</p>
        </div>
        <div className="flex gap-1 bg-white border border-gray-200 rounded-xl p-1">
          {periods.map(p => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                period === p.key ? "bg-indigo-600 text-white" : "text-gray-600 hover:bg-gray-50"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48 text-gray-400">Yuklanmoqda...</div>
      ) : !report || (report.income === 0 && report.expense === 0 && recent.length === 0) ? (
        <>
          <QuickAdd onAdded={load} />
          <div className="mt-6">
            <EmptyState />
          </div>
        </>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-5 mb-6">
            <StatCard
              label="Jami kirim"
              value={report.income}
              prev={report.prev_income}
              icon={TrendingUp}
              color="bg-emerald-500"
            />
            <StatCard
              label="Jami chiqim"
              value={report.expense}
              prev={report.prev_expense}
              icon={TrendingDown}
              color="bg-red-500"
            />
            <StatCard
              label="Sof foyda"
              value={report.net}
              prev={report.prev_net}
              icon={DollarSign}
              color={report.net >= 0 ? "bg-indigo-600" : "bg-orange-500"}
            />
          </div>

          {/* Chart + Quick Add */}
          <div className="grid grid-cols-3 gap-5 mb-6">
            <div className="col-span-2 bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
              <h3 className="font-semibold text-gray-800 mb-4">Kirim / Chiqim dinamikasi</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="cIncome" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="cExpense" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000).toFixed(0)}K`} />
                    <Tooltip formatter={v => fmt(v)} />
                    <Area type="monotone" dataKey="income" stroke="#10b981" fill="url(#cIncome)" strokeWidth={2} name="Kirim" />
                    <Area type="monotone" dataKey="expense" stroke="#ef4444" fill="url(#cExpense)" strokeWidth={2} name="Chiqim" />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
                  Grafik uchun ma'lumot yetarli emas
                </div>
              )}
            </div>
            <QuickAdd onAdded={load} />
          </div>

          {/* Recent transactions */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 p-5 border-b border-gray-50">
              <Clock size={16} className="text-gray-400" />
              <h3 className="font-semibold text-gray-800">So'nggi tranzaksiyalar</h3>
            </div>
            <div className="divide-y divide-gray-50">
              {recent.map(tx => (
                <div key={tx.id} className="flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm ${
                      tx.type === "income" ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-500"
                    }`}>
                      {tx.type === "income" ? "💰" : "💸"}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-gray-800 capitalize">{tx.category}</p>
                      <p className="text-xs text-gray-400">{tx.note || tx.date}</p>
                    </div>
                  </div>
                  <span className={`font-semibold text-sm ${
                    tx.type === "income" ? "text-emerald-600" : "text-red-500"
                  }`}>
                    {tx.type === "income" ? "+" : "-"}{fmt(tx.amount)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
