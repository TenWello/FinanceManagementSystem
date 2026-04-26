import { useState, useEffect } from "react";
import { API } from "../App";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from "recharts";

const fmt = (n) => new Intl.NumberFormat("uz-UZ").format(Math.round(n || 0)) + " so'm";

const COLORS = [
  "#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6",
  "#06b6d4","#f97316","#84cc16","#ec4899","#38bdf8"
];

function PieCard({ title, data, total }) {
  if (!data?.length) return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <h3 className="font-semibold text-gray-800 mb-8">{title}</h3>
      <div className="h-48 flex items-center justify-center text-gray-400 text-sm">Ma'lumot yo'q</div>
    </div>
  );

  const pct = (v) => total ? ((v / total) * 100).toFixed(1) : 0;

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
      <h3 className="font-semibold text-gray-800 mb-4">{title}</h3>
      <div className="flex gap-6">
        <div className="flex-shrink-0">
          <ResponsiveContainer width={180} height={180}>
            <PieChart>
              <Pie data={data} dataKey="total" nameKey="category"
                cx="50%" cy="50%" outerRadius={80} innerRadius={50}>
                {data.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={v => fmt(v)} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0">
          {data.slice(0, 6).map((item, i) => (
            <div key={item.category} className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }} />
              <span className="text-xs text-gray-600 flex-1 truncate capitalize">{item.category}</span>
              <span className="text-xs font-medium text-gray-800">{pct(item.total)}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function Analytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/analytics`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-400">Yuklanmoqda...</div>
  );

  if (!data || data.total_transactions === 0) return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-8">Tahlil</h1>
      <div className="bg-white rounded-2xl border border-dashed border-gray-200 p-12 text-center">
        <div className="text-4xl mb-4">📊</div>
        <h3 className="text-lg font-semibold text-gray-800 mb-2">Tahlil uchun ma'lumot yo'q</h3>
        <p className="text-gray-500 text-sm">Avval bir necha tranzaksiya qo'shing</p>
      </div>
    </div>
  );

  const totalIncome = data.category_income.reduce((s,c)=>s+c.total,0);
  const totalExpense = data.category_expense.reduce((s,c)=>s+c.total,0);

  const monthlyFormatted = data.monthly.map(m => ({
    ...m,
    label: m.month.slice(5) + "-oy",
  }));

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Tahlil</h1>
        <p className="text-gray-500 text-sm mt-1">Jami {data.total_transactions} ta tranzaksiya tahlili</p>
      </div>

      {/* Monthly bar chart */}
      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100 mb-5">
        <h3 className="font-semibold text-gray-800 mb-4">Oylik kirim vs chiqim (so'nggi 6 oy)</h3>
        {monthlyFormatted.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={monthlyFormatted} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `${(v/1000000).toFixed(1)}M`} />
              <Tooltip formatter={v => fmt(v)} />
              <Legend />
              <Bar dataKey="income" name="Kirim" fill="#10b981" radius={[6,6,0,0]} />
              <Bar dataKey="expense" name="Chiqim" fill="#ef4444" radius={[6,6,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-48 flex items-center justify-center text-gray-400 text-sm">
            Oylik ma'lumot yetarli emas
          </div>
        )}
      </div>

      {/* Pie charts */}
      <div className="grid grid-cols-2 gap-5 mb-5">
        <PieCard title="Kirim kategoriyalari" data={data.category_income} total={totalIncome} />
        <PieCard title="Chiqim kategoriyalari" data={data.category_expense} total={totalExpense} />
      </div>

      {/* Top categories table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-5 border-b border-gray-50">
          <h3 className="font-semibold text-gray-800">Kategoriyalar bo'yicha taqsimot</h3>
        </div>
        <div className="divide-y divide-gray-50">
          {[...data.category_expense]
            .sort((a, b) => b.total - a.total)
            .slice(0, 8)
            .map((cat, i) => (
              <div key={cat.category} className="flex items-center gap-4 px-5 py-3.5">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white"
                  style={{ backgroundColor: COLORS[i % COLORS.length] }}>
                  {i + 1}
                </div>
                <span className="flex-1 capitalize text-sm text-gray-700">{cat.category}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-1.5 mx-4">
                  <div className="h-1.5 rounded-full"
                    style={{
                      width: `${(cat.total / (data.category_expense[0]?.total || 1)) * 100}%`,
                      backgroundColor: COLORS[i % COLORS.length]
                    }} />
                </div>
                <span className="font-semibold text-sm text-gray-800 w-36 text-right">{fmt(cat.total)}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}
