import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { Activity } from 'lucide-react';

// ISO "YYYY-MM-DD" -> "10.07" (bez roku, czytelniej na osi X wykresu).
const formatAxisDate = (iso) => {
  const [, month, day] = iso.split('-');
  return `${day}.${month}`;
};

// Tooltip PL: data + kumulatywny zysk + running win-rate w danym punkcie.
const ProgressTooltip = ({ active, payload, label }) => {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div className="glass-card p-3 text-xs" style={{ color: 'var(--text-main)' }}>
      <p className="font-bold mb-1">{label}</p>
      <p style={{ color: 'var(--accent-primary)' }}>
        Zysk: {point.cumulative_profit >= 0 ? '+' : ''}{point.cumulative_profit.toFixed(2)} PLN
      </p>
      <p style={{ color: 'var(--accent-secondary)' }}>
        Win rate: {(point.running_win_rate * 100).toFixed(1)}%
      </p>
      <p style={{ color: 'var(--text-muted)' }}>Rozliczonych: {point.settled_count}</p>
    </div>
  );
};

// Krzywa postępu (J3): cumulative_profit (lewa oś) + running_win_rate (prawa oś, %).
// <2 punktów (brak/1 rozliczony kupon) -> za mało danych do sensownej krzywej.
const ProgressChart = ({ series }) => {
  if (!series || series.length < 2) {
    return (
      <div className="glass-card p-6 text-center" style={{ color: 'var(--text-muted)' }}>
        Za mało danych — rozlicz kupony by zobaczyć postęp.
      </div>
    );
  }

  const data = series.map((point) => ({ ...point, dateLabel: formatAxisDate(point.date) }));

  return (
    <div className="glass-card p-6">
      <div className="flex items-center gap-2 mb-4" style={{ color: 'var(--text-muted)' }}>
        <Activity size={16} />
        <span className="text-xs font-bold uppercase tracking-widest">Postęp w czasie</span>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--text-muted)" opacity={0.2} />
          <XAxis dataKey="dateLabel" stroke="var(--text-muted)" tick={{ fontSize: 12 }} />
          <YAxis yAxisId="left" stroke="var(--accent-primary)" tick={{ fontSize: 12 }} />
          <YAxis
            yAxisId="right"
            orientation="right"
            stroke="var(--accent-secondary)"
            tick={{ fontSize: 12 }}
            domain={[0, 1]}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip content={<ProgressTooltip />} />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="cumulative_profit"
            name="Zysk (PLN)"
            stroke="var(--accent-primary)"
            strokeWidth={2}
            dot={false}
          />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="running_win_rate"
            name="Win rate"
            stroke="var(--accent-secondary)"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default ProgressChart;
