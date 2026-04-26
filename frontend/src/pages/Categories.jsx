import { useState, useEffect } from "react";
import { API } from "../App";
import { Plus, Trash2, Tag } from "lucide-react";

const PRESET_COLORS = [
  "#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6",
  "#06b6d4","#f97316","#84cc16","#ec4899","#38bdf8","#64748b","#a78bfa"
];

export default function Categories() {
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState({ name: "", type: "expense", color: "#6366f1" });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [error, setError] = useState("");

  const load = () =>
    fetch(`${API}/categories`).then(r => r.json()).then(setCategories);

  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.name.trim()) { setError("Nom kiritish kerak"); return; }
    setSaving(true); setError("");
    try {
      const r = await fetch(`${API}/categories`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, name: form.name.toLowerCase().trim() }),
      });
      if (r.status === 409) { setError("Bu kategoriya allaqachon mavjud"); return; }
      setForm({ name: "", type: "expense", color: "#6366f1" });
      load();
    } finally { setSaving(false); }
  };

  const del = async (name) => {
    setDeleting(name);
    await fetch(`${API}/categories/${encodeURIComponent(name)}`, { method: "DELETE" });
    setDeleting(null);
    load();
  };

  const income = categories.filter(c => c.type === "income");
  const expense = categories.filter(c => c.type === "expense");
  const both = categories.filter(c => c.type === "both");

  function CatList({ cats, label }) {
    if (!cats.length) return null;
    return (
      <div className="mb-6">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">{label}</h3>
        <div className="grid grid-cols-2 gap-3">
          {cats.map(cat => (
            <div key={cat.name}
              className="flex items-center gap-3 p-4 bg-white rounded-xl border border-gray-100 shadow-sm group">
              <div className="w-9 h-9 rounded-xl flex-shrink-0"
                style={{ backgroundColor: cat.color + "22" }}>
                <div className="w-full h-full rounded-xl flex items-center justify-center">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: cat.color }} />
                </div>
              </div>
              <span className="flex-1 capitalize text-sm font-medium text-gray-700">{cat.name}</span>
              <button onClick={() => del(cat.name)} disabled={deleting === cat.name}
                className="opacity-0 group-hover:opacity-100 p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all">
                {deleting === cat.name ? "..." : <Trash2 size={14} />}
              </button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Kategoriyalar</h1>
        <p className="text-gray-500 text-sm mt-1">Kirim va chiqim kategoriyalarini boshqarish</p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Add form */}
        <div className="col-span-1">
          <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 sticky top-8">
            <div className="flex items-center gap-2 mb-5">
              <div className="w-8 h-8 bg-indigo-100 rounded-xl flex items-center justify-center">
                <Plus size={16} className="text-indigo-600" />
              </div>
              <h3 className="font-semibold text-gray-800">Yangi kategoriya</h3>
            </div>

            <div className="space-y-3">
              <input type="text" placeholder="Kategoriya nomi"
                value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />

              <div className="flex gap-2 p-1 bg-gray-100 rounded-xl">
                {[
                  { val: "income", label: "💰 Kirim" },
                  { val: "expense", label: "💸 Chiqim" },
                  { val: "both", label: "🔄 Ikkisi" },
                ].map(opt => (
                  <button key={opt.val} onClick={() => setForm(f => ({ ...f, type: opt.val }))}
                    className={`flex-1 py-1.5 text-xs font-medium rounded-lg transition-all ${
                      form.type === opt.val ? "bg-white shadow text-gray-800" : "text-gray-500"
                    }`}>
                    {opt.label}
                  </button>
                ))}
              </div>

              <div>
                <p className="text-xs text-gray-500 mb-2">Rang tanlang</p>
                <div className="grid grid-cols-6 gap-2">
                  {PRESET_COLORS.map(c => (
                    <button key={c} onClick={() => setForm(f => ({ ...f, color: c }))}
                      className={`w-7 h-7 rounded-lg transition-all ${form.color === c ? "ring-2 ring-offset-1 ring-indigo-400 scale-110" : ""}`}
                      style={{ backgroundColor: c }} />
                  ))}
                </div>
              </div>

              {error && <p className="text-xs text-red-500">{error}</p>}

              <button onClick={save} disabled={saving}
                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-2.5 rounded-xl font-medium text-sm transition-colors">
                {saving ? "Saqlanmoqda..." : "Qo'shish"}
              </button>
            </div>
          </div>
        </div>

        {/* Category lists */}
        <div className="col-span-2">
          <CatList cats={income} label="Kirim kategoriyalari" />
          <CatList cats={expense} label="Chiqim kategoriyalari" />
          <CatList cats={both} label="Umumiy" />
          {categories.length === 0 && (
            <div className="text-center py-12 text-gray-400">
              <Tag size={40} className="mx-auto mb-3 opacity-30" />
              <p>Kategoriyalar yo'q</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
