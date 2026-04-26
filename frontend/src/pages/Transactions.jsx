import { useState, useEffect, useCallback } from "react";
import { API } from "../App";
import { Search, Filter, Pencil, Trash2, Check, X, ChevronLeft, ChevronRight } from "lucide-react";

const fmt = (n) => new Intl.NumberFormat("uz-UZ").format(Math.round(n || 0)) + " so'm";

function EditModal({ tx, categories, onSave, onClose }) {
  const [form, setForm] = useState({ ...tx });
  const [saving, setSaving] = useState(false);

  const filtered = categories.filter(c => c.type === form.type || c.type === "both");

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`${API}/transactions/${tx.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, amount: parseFloat(form.amount) }),
      });
      onSave();
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-bold text-gray-900">Tranzaksiyani tahrirlash</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20}/></button>
        </div>

        <div className="space-y-3">
          <div className="flex gap-2 p-1 bg-gray-100 rounded-xl">
            {["income","expense"].map(t => (
              <button key={t} onClick={() => setForm(f=>({...f,type:t}))}
                className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${
                  form.type===t ? t==="income"?"bg-emerald-500 text-white":"bg-red-500 text-white" : "text-gray-600"
                }`}>
                {t==="income"?"💰 Kirim":"💸 Chiqim"}
              </button>
            ))}
          </div>

          <input type="number" value={form.amount}
            onChange={e=>setForm(f=>({...f,amount:e.target.value}))}
            placeholder="Summa"
            className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />

          <select value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))}
            className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
            {filtered.map(c=><option key={c.name} value={c.name}>{c.name}</option>)}
          </select>

          <input type="date" value={form.date} onChange={e=>setForm(f=>({...f,date:e.target.value}))}
            className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />

          <input type="text" value={form.note||""} onChange={e=>setForm(f=>({...f,note:e.target.value}))}
            placeholder="Izoh"
            className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />

          <div className="flex gap-3 pt-2">
            <button onClick={onClose} className="flex-1 border border-gray-200 rounded-xl py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">
              Bekor
            </button>
            <button onClick={save} disabled={saving}
              className="flex-1 bg-indigo-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-indigo-700">
              {saving ? "Saqlanmoqda..." : "Saqlash"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Transactions() {
  const [txs, setTxs] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editTx, setEditTx] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [filters, setFilters] = useState({
    type: "", category: "", date_from: "", date_to: "", search: ""
  });
  const [page, setPage] = useState(0);
  const PER_PAGE = 15;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: PER_PAGE,
        offset: page * PER_PAGE,
        ...Object.fromEntries(Object.entries(filters).filter(([,v]) => v)),
      });
      const [data, cats] = await Promise.all([
        fetch(`${API}/transactions?${params}`).then(r => r.json()),
        fetch(`${API}/categories`).then(r => r.json()),
      ]);
      setTxs(data);
      setCategories(cats);
    } finally { setLoading(false); }
  }, [filters, page]);

  useEffect(() => { load(); }, [load]);

  const deleteTx = async (id) => {
    setDeleting(id);
    await fetch(`${API}/transactions/${id}`, { method: "DELETE" });
    setDeleting(null);
    load();
  };

  const totalIncome = txs.filter(t=>t.type==="income").reduce((s,t)=>s+t.amount,0);
  const totalExpense = txs.filter(t=>t.type==="expense").reduce((s,t)=>s+t.amount,0);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Tranzaksiyalar</h1>
        <p className="text-gray-500 text-sm mt-1">Barcha moliyaviy operatsiyalar</p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl p-5 shadow-sm border border-gray-100 mb-5">
        <div className="grid grid-cols-5 gap-3">
          <div className="col-span-2 relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"/>
            <input type="text" placeholder="Qidirish..."
              value={filters.search}
              onChange={e=>{ setFilters(f=>({...f,search:e.target.value})); setPage(0); }}
              className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300" />
          </div>

          <select value={filters.type}
            onChange={e=>{ setFilters(f=>({...f,type:e.target.value})); setPage(0); }}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
            <option value="">Hammasi</option>
            <option value="income">💰 Kirim</option>
            <option value="expense">💸 Chiqim</option>
          </select>

          <select value={filters.category}
            onChange={e=>{ setFilters(f=>({...f,category:e.target.value})); setPage(0); }}
            className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300">
            <option value="">Barcha kat.</option>
            {categories.map(c=><option key={c.name} value={c.name}>{c.name}</option>)}
          </select>

          <div className="flex gap-2">
            <input type="date" value={filters.date_from}
              onChange={e=>{ setFilters(f=>({...f,date_from:e.target.value})); setPage(0); }}
              className="flex-1 border border-gray-200 rounded-xl px-2 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300" />
            <input type="date" value={filters.date_to}
              onChange={e=>{ setFilters(f=>({...f,date_to:e.target.value})); setPage(0); }}
              className="flex-1 border border-gray-200 rounded-xl px-2 py-2.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-300" />
          </div>
        </div>

        {/* Summary bar */}
        {txs.length > 0 && (
          <div className="flex gap-6 mt-4 pt-4 border-t border-gray-50">
            <span className="text-sm text-gray-500">
              <span className="font-semibold text-emerald-600">{fmt(totalIncome)}</span> kirim
            </span>
            <span className="text-sm text-gray-500">
              <span className="font-semibold text-red-500">{fmt(totalExpense)}</span> chiqim
            </span>
            <span className="text-sm text-gray-500">
              Sof: <span className={`font-semibold ${totalIncome-totalExpense>=0?"text-indigo-600":"text-orange-500"}`}>
                {fmt(totalIncome - totalExpense)}
              </span>
            </span>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-50 bg-gray-50/50">
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Tur</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Summa</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Kategoriya</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Sana</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Kim</th>
              <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Izoh</th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              <tr><td colSpan={7} className="text-center py-12 text-gray-400">Yuklanmoqda...</td></tr>
            ) : txs.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-12 text-gray-400">Tranzaksiyalar topilmadi</td></tr>
            ) : txs.map(tx => (
              <tr key={tx.id} className="hover:bg-gray-50/50 transition-colors group">
                <td className="px-6 py-4">
                  <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                    tx.type==="income"?"bg-emerald-50 text-emerald-700":"bg-red-50 text-red-600"
                  }`}>
                    {tx.type==="income"?"💰 Kirim":"💸 Chiqim"}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`font-semibold ${tx.type==="income"?"text-emerald-600":"text-red-500"}`}>
                    {tx.type==="income"?"+":"-"}{fmt(tx.amount)}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className="capitalize text-sm text-gray-700">{tx.category}</span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-500">{tx.date}</td>
                <td className="px-6 py-4">
                  {tx.added_by_name ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-indigo-50 text-indigo-600 rounded-full text-xs font-medium">
                      👤 {tx.added_by_name.split(' ')[0]}
                    </span>
                  ) : <span className="text-gray-300 text-xs">—</span>}
                </td>
                <td className="px-6 py-4 text-sm text-gray-400 max-w-[150px] truncate">{tx.note || "—"}</td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => setEditTx(tx)}
                      className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors">
                      <Pencil size={15}/>
                    </button>
                    <button onClick={() => deleteTx(tx.id)} disabled={deleting===tx.id}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors">
                      {deleting===tx.id ? <span className="text-xs">...</span> : <Trash2 size={15}/>}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-50">
          <span className="text-sm text-gray-500">{txs.length} ta natija</span>
          <div className="flex gap-2">
            <button onClick={()=>setPage(p=>Math.max(0,p-1))} disabled={page===0}
              className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
              <ChevronLeft size={16}/>
            </button>
            <span className="px-3 py-2 text-sm text-gray-600">{page+1}-sahifa</span>
            <button onClick={()=>setPage(p=>p+1)} disabled={txs.length<PER_PAGE}
              className="p-2 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-40">
              <ChevronRight size={16}/>
            </button>
          </div>
        </div>
      </div>

      {editTx && (
        <EditModal tx={editTx} categories={categories}
          onSave={() => { setEditTx(null); load(); }}
          onClose={() => setEditTx(null)} />
      )}
    </div>
  );
}
