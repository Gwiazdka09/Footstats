import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { PlusCircle } from 'lucide-react';
import HistoryCouponRow from './HistoryCouponRow';
import ManualCouponForm from './ManualCouponForm';

const HistoryView = ({ apiFetch }) => {
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showManualForm, setShowManualForm] = useState(false);

  const loadCoupons = () => apiFetch('/coupons?limit=50').then(data => {
    setCoupons(data);
    setLoading(false);
  });

  useEffect(() => {
    loadCoupons();
  }, []);

  if (loading) return <div className="text-center py-20">Ładowanie historii...</div>;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
    >
      <div className="mb-12 flex flex-col md:flex-row md:items-end md:justify-between gap-6">
        <div>
          <h1 className="text-4xl font-bold mb-2">Pełna Historia</h1>
          <p className="text-slate-400">Podgląd wszystkich Twoich kuponów. Kliknij kupon by rozwinąć typy.</p>
        </div>
        <button
          onClick={() => setShowManualForm(true)}
          className="btn-primary flex items-center gap-2 self-start"
        >
          <PlusCircle size={16} /> Dodaj kupon
        </button>
      </div>
      <div className="grid grid-cols-1 gap-4">
        {coupons.length > 0 ? coupons.map((c) => (
          <HistoryCouponRow key={c.id} c={c} apiFetch={apiFetch} onRefresh={loadCoupons} />
        )) : (
          <div className="text-center p-24 glass-card text-slate-500">Historia jest pusta.</div>
        )}
      </div>
      {showManualForm && (
        <ManualCouponForm
          apiFetch={apiFetch}
          onClose={() => setShowManualForm(false)}
          onSaved={() => { setShowManualForm(false); loadCoupons(); }}
        />
      )}
    </motion.div>
  );
};

export default HistoryView;
