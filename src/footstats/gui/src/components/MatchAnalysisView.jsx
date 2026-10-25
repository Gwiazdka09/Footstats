import { useState, useEffect } from 'react';
import { Swords, Shield, Target, FileText, Search } from 'lucide-react';

// 10.09: sama statystyka drużyn — bez paska 1X2, Over/BTTS i „Analizy AI”
// (nasze typy nie pokazują się w GUI poza kreatorem „Stwórz Kupon”).
// Wyjątek 23.10: właściciel (claim adm) widzi na karcie „Opis (admin)” — patrz AdminOpis.

function TeamCol({ stats, align }) {
  return (
    <div className={align === 'right' ? 'text-right' : ''}>
      <div className="font-semibold" style={{ color: 'var(--text-main)' }}>{stats.team}</div>
      <div className="flex gap-3 mt-1 text-sm" style={{ color: 'var(--text-muted)',
        justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
        <span className="inline-flex items-center gap-1"><Target size={16} />{stats.gf_pg ?? '—'}</span>
        <span className="inline-flex items-center gap-1"><Shield size={16} />{stats.ga_pg ?? '—'}</span>
      </div>
      {stats.rating != null && (
        <div className="text-xs mt-1" style={{ color: 'var(--accent-primary)' }}>
          rating {Number(stats.rating).toFixed(2)}
        </div>
      )}
    </div>
  );
}

function TopScorers({ list, align }) {
  if (!list?.length) return null;
  return (
    <div className={`text-xs mt-2 ${align === 'right' ? 'text-right' : ''}`}
      style={{ color: 'var(--text-muted)' }}>
      <span style={{ color: 'var(--accent-primary)' }}>⚽ </span>
      {list.map(s => `${s.name} ${Math.round(s.goal_share * 100)}%`).join(' · ')}
    </div>
  );
}

function Injuries({ list, align }) {
  if (!list?.length) return null;
  return (
    <ul className={`text-xs mt-2 space-y-0.5 ${align === 'right' ? 'text-right' : ''}`}
      style={{ color: 'var(--text-muted)' }}>
      {list.map((i, k) => (
        <li key={k}>
          <span style={{ color: i.goal_share >= 0.15 ? 'var(--accent-secondary)' : 'var(--text-muted)' }}>
            {i.name}{i.goal_share ? ` · ${Math.round(i.goal_share * 100)}% goli` : ''}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Procenty z API: Poisson i rynek są w %, Bzzoiro bywa ułamkiem — normalizujemy.
const pct = v => (v == null ? '—' : `${(v <= 1 ? v * 100 : v).toFixed(1)}%`);

function WierszRynku({ nazwa, poisson, bzzoiro, rynek }) {
  return (
    <tr>
      <td className="pr-3" style={{ color: 'var(--text-muted)' }}>{nazwa}</td>
      <td className="pr-3 text-right">{pct(poisson)}</td>
      <td className="pr-3 text-right">{pct(bzzoiro)}</td>
      <td className="text-right">{pct(rynek)}</td>
    </tr>
  );
}

// Tylko admin (właściciel): opis meczu na żądanie — karta liczb + opis LLM
// ograniczony do tej karty. Zwykli użytkownicy nie widzą ani przycisku, ani danych
// (endpoint i tak wymaga claimu adm po stronie API).
function AdminOpis({ card, apiFetch }) {
  const [stan, setStan] = useState('zamkniety'); // zamkniety | ladowanie | gotowy | blad
  const [wynik, setWynik] = useState(null);
  const [blad, setBlad] = useState(null);

  const pobierz = () => {
    setStan('ladowanie');
    setBlad(null);
    apiFetch('/admin/opis-meczu', {
      method: 'POST',
      body: JSON.stringify({
        home: card.home ?? card.home_stats?.team,
        away: card.away ?? card.away_stats?.team,
        liga: card.liga,
        data: card.data,
      }),
    })
      .then(d => { setWynik(d); setStan('gotowy'); })
      .catch(e => { setBlad(e.message || 'Błąd połączenia'); setStan('blad'); });
  };

  if (stan === 'zamkniety') {
    return (
      <button type="button" className="btn-see-all mt-4 inline-flex items-center gap-2" onClick={pobierz}>
        <FileText size={16} /> Opis (admin)
      </button>
    );
  }
  if (stan === 'ladowanie') {
    return (
      <p className="mt-4 text-sm" style={{ color: 'var(--text-muted)' }}>
        Liczę kartę i opis… (pierwszy raz po starcie serwera do ~30 s)
      </p>
    );
  }
  if (stan === 'blad') {
    return <p className="mt-4 text-sm" style={{ color: 'var(--accent-secondary)' }}>{blad}</p>;
  }
  const k = wynik?.karta || {};
  const p = k.poisson || {};
  const b = k.bzzoiro || {};
  const r = k.rynek || {};
  return (
    <div className="mt-4 text-sm" data-testid="admin-opis">
      <table className="w-full mb-3" style={{ color: 'var(--text-main)' }}>
        <thead>
          <tr style={{ color: 'var(--text-muted)' }}>
            <th className="text-left font-normal">typ</th>
            <th className="text-right font-normal">Poisson</th>
            <th className="text-right font-normal">Bzzoiro</th>
            <th className="text-right font-normal">rynek</th>
          </tr>
        </thead>
        <tbody>
          <WierszRynku nazwa="1" poisson={p.p1} bzzoiro={b.p1} rynek={r.p1} />
          <WierszRynku nazwa="X" poisson={p.px} bzzoiro={b.px} rynek={r.px} />
          <WierszRynku nazwa="2" poisson={p.p2} bzzoiro={b.p2} rynek={r.p2} />
          <WierszRynku nazwa="Over 2.5" poisson={p.over25} bzzoiro={b.over25} rynek={r.over25} />
          <WierszRynku nazwa="BTTS" poisson={p.btts} bzzoiro={b.btts} rynek={null} />
        </tbody>
      </table>
      {k.poisson_powod && (
        <p className="mb-2" style={{ color: 'var(--text-muted)' }}>Poisson: {k.poisson_powod}</p>
      )}
      {wynik?.opis
        ? <p className="whitespace-pre-line" style={{ color: 'var(--text-main)' }}>{wynik.opis}</p>
        : (
          <p style={{ color: 'var(--text-muted)' }}>
            Opis niedostępny (model językowy nie odpowiedział) — powyżej sama karta liczb.
          </p>
        )}
    </div>
  );
}

function MatchCard({ card, isAdmin, apiFetch }) {
  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs px-2 py-0.5 rounded-full"
          style={{ background: 'rgba(129,140,248,0.12)', color: 'var(--accent-primary)' }}>
          {card.liga}
        </span>
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{card.data}</span>
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-3 my-3">
        <TeamCol stats={card.home_stats} align="left" />
        <div className="flex flex-col items-center pt-1">
          <Swords size={20} style={{ color: 'var(--text-muted)' }} />
          <span className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>vs</span>
        </div>
        <TeamCol stats={card.away_stats} align="right" />
      </div>

      {(card.top_scorers_home?.length > 0 || card.top_scorers_away?.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-1">
          <TopScorers list={card.top_scorers_home} align="left" />
          <TopScorers list={card.top_scorers_away} align="right" />
        </div>
      )}

      {(card.injuries_home?.length > 0 || card.injuries_away?.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-2">
          <Injuries list={card.injuries_home} align="left" />
          <Injuries list={card.injuries_away} align="right" />
        </div>
      )}
      {isAdmin && <AdminOpis card={card} apiFetch={apiFetch} />}
    </div>
  );
}

const MIN_ZNAKOW = 2;
const DEBOUNCE_MS = 400;

export default function MatchAnalysisView({ apiFetch, isAdmin = false }) {
  const [cards, setCards] = useState(null);
  const [err, setErr] = useState(null);
  const [wpisane, setWpisane] = useState('');
  const [zapytanie, setZapytanie] = useState('');

  // Debounce: do API idzie dopiero po przerwie w pisaniu; <2 znaki = widok domyślny.
  useEffect(() => {
    const t = setTimeout(() => {
      const q = wpisane.trim();
      setZapytanie(q.length >= MIN_ZNAKOW ? q : '');
    }, DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [wpisane]);

  useEffect(() => {
    let aktualne = true;
    const endpoint = zapytanie
      ? '/analyses/matches?q=' + encodeURIComponent(zapytanie)
      : '/analyses/matches';
    setErr(null);
    apiFetch(endpoint)
      .then(d => { if (!aktualne) return; setCards(d.matches || []); if (d.error) setErr(d.error); })
      .catch(e => { if (aktualne) setErr(e.message || 'Błąd połączenia'); });
    return () => { aktualne = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zapytanie]);

  return (
    <div>
      <h2 className="brand text-2xl mb-1" style={{ color: 'var(--text-main)' }}>Analizy meczów</h2>
      <p className="mb-6" style={{ color: 'var(--text-muted)' }}>
        Najważniejsze mecze tygodnia — gole zdobyte i stracone na mecz, strzelcy, kontuzje.
      </p>
      <p className="mb-6 -mt-4 text-xs inline-flex items-center gap-3" style={{ color: 'var(--text-muted)' }}>
        <span className="inline-flex items-center gap-1"><Target size={16} /> gole zdobyte / mecz</span>
        <span className="inline-flex items-center gap-1"><Shield size={16} /> gole stracone / mecz</span>
      </p>

      <label className="relative block mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2"
          style={{ color: 'var(--text-muted)' }} />
        <input
          type="search"
          aria-label="Szukaj meczu"
          placeholder="Szukaj meczu: drużyna lub liga"
          value={wpisane}
          maxLength={50}
          onChange={e => setWpisane(e.target.value)}
          className="w-full py-2 pl-9 pr-3 outline-none"
          style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-main)',
            borderRadius: 8, border: 'none' }}
        />
      </label>
      <p className="mb-4 text-xs" style={{ color: 'var(--text-muted)' }}>
        {zapytanie ? `Wyniki dla „${zapytanie}”` : 'Dziś i jutro'}
      </p>

      {err && <div className="glass-card p-4 mb-4" style={{ color: 'var(--accent-secondary)' }}>{err}</div>}
      {cards === null && <p style={{ color: 'var(--text-muted)' }}>Ładowanie…</p>}
      {cards?.length === 0 && !err && (
        <p style={{ color: 'var(--text-muted)' }}>
          {zapytanie ? `Brak nadchodzących meczów dla „${zapytanie}”` : 'Brak ważnych meczów w tym tygodniu.'}
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {cards?.map((c, i) => <MatchCard key={i} card={c} isAdmin={isAdmin} apiFetch={apiFetch} />)}
      </div>
    </div>
  );
}
