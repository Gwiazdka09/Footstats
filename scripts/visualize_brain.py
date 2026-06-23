"""
FootStats "Second Mind" Dynamic Graph Visualization v3.6
Automatycznie pobiera dane z bazy i generuje PREMIUM mapę wiedzy AI.
"""

import json
import os
import sqlite3
import logging
from datetime import datetime

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _connect():
    """Bezpośrednie połączenie do lokalnej bazy SQLite."""
    db_path = os.path.join('data', 'footstats_backtest.db')
    if not os.path.exists(db_path):
        db_path = os.path.join('..', 'data', 'footstats_backtest.db')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_dynamic_data():
    """Pobiera ostatnie wnioski z ai_feedback i tworzy węzły/krawędzie."""
    nodes = []
    edges = []
    
    try:
        with _connect() as conn:
            # Pobierz 20 ostatnich lekcji dla bogatszego grafu
            query = """
                SELECT f.id, f.reason_for_failure, f.created_at, 
                       p.team_home, p.team_away, p.actual_result, p.match_date
                FROM ai_feedback f
                JOIN predictions p ON p.id = f.match_id
                ORDER BY f.created_at DESC
                LIMIT 20
            """
            rows = conn.execute(query).fetchall()
            
            for row in rows:
                lesson_id = f"lesson_{row['id']}"
                match_label = f"{row['team_home']} vs {row['team_away']}"
                
                # Węzeł lekcji (Neon Pink Diamond)
                nodes.append({
                    'id': lesson_id,
                    'label': f"LEKCJA: {match_label}",
                    'color': '#FF1493',
                    'title': f"<b>Data meczu:</b> {row['match_date']}<br><b>Wynik:</b> {row['actual_result']}<br><b>Wniosek:</b> {row['reason_for_failure']}",
                    'size': 25,
                    'shape': 'diamond',
                    'font': {'size': 10, 'color': '#FF1493'}
                })
                
                # Połączenie lekcji z bazą wiedzy
                edges.append({
                    'from': 'ai_feedback_db',
                    'to': lesson_id,
                    'color': '#FF1493',
                    'width': 1,
                    'dashes': True
                })
                
                # Dodaj węzły drużyn
                for team in [row['team_home'], row['team_away']]:
                    team_id = f"team_{team.replace(' ', '_')}"
                    if not any(n['id'] == team_id for n in nodes):
                        nodes.append({
                            'id': team_id,
                            'label': team,
                            'color': '#00CED1',
                            'size': 15,
                            'shape': 'dot',
                            'font': {'size': 9, 'color': '#00CED1'}
                        })
                    edges.append({
                        'from': lesson_id,
                        'to': team_id,
                        'color': '#00CED1',
                        'width': 0.5,
                        'arrows': 'none'
                    })
                    
    except Exception as e:
        logger.error(f"Błąd danych dynamicznych: {e}")
        
    return nodes, edges

def create_brain_graph():
    """Generuje interaktywną mapę PREMIUM (Pełna Architektura + Live Data)"""
    
    # 1. PEŁNA ARCHITEKTURA — szczegółowa, warstwowa (aktualna 2026-06-23).
    # Kolory = warstwa. Rozmiar = centralność. Kształt database = tabela Neon PG.
    C = {  # palety per warstwa
        'agent': '#FFD700', 'phase': '#FF8C00', 'ai': '#9370DB', 'model': '#FF6B6B',
        'money': '#32CD32', 'scrape': '#4DABF7', 'source': '#20C997', 'data': '#A0522D',
        'api': '#4169E1', 'front': '#15AABF', 'db': '#2F9E44', 'cfg': '#868E96',
    }
    def N(i, lbl, layer, size=26, shape='dot', **kw):
        return {'id': i, 'label': lbl, 'color': C[layer], 'size': size, 'shape': shape, 'group': layer, **kw}

    nodes = [
        # ── Agenty / scheduler (08:00 draft, 11:00 final, 23:00 evening) ──
        N('daily_agent', 'daily_agent.py\n(ORCHESTRATOR)', 'agent', 42, title='Główny pipeline: fetch→enrich→Groq→kupony→predykcje'),
        N('scheduler', 'daily_agent_scheduler\n(draft-wait-final)', 'agent', 28),
        N('evening_agent', 'evening_agent.py\n(SETTLEMENT 23:00)', 'agent', 34, title='Rozlicza kupony+predykcje wszystkich userów; auto-refit kalibracji'),
        N('daily_phases', 'core/daily_phases.py\n(FAZY: forma/kelly/odds-fallback)', 'phase', 30),
        # ── AI / RAG / LLM ──
        N('analyzer', 'ai/analyzer.py\n(Groq LLM selekcja)', 'ai', 36),
        N('analyzer_helpers', 'ai/analyzer_helpers.py\n(+D3 guard, zapis predykcji)', 'ai', 26),
        N('rag', 'ai/rag.py\n(RAG kontekst/faktory)', 'ai', 24),
        N('post_match', 'ai/post_match_analyzer.py\n(RAG: wnioski z porażek)', 'ai', 28),
        N('trainer', 'ai/trainer.py\n(kalibracja→prompt)', 'ai', 24),
        # ── Model core (Poisson / Dixon-Coles / ensemble / rynki) ──
        N('quick_picks', 'core/quick_picks.py\n(pewniaczki 2dni)', 'model', 30),
        N('poisson', 'core/poisson.py\n(predict_match)', 'model', 30),
        N('dc', 'core/poisson_bayesian.py\n(Dixon-Coles)', 'model', 28),
        N('ensemble', 'core/ensemble.py\n(blend devig)', 'model', 24),
        N('markets', 'core/markets.py\n(katalog: 1X2/Over/GG2H...)', 'model', 26),
        N('betbuilder', 'core/bet_builder + betbuilder_rules\n(macierz, combo)', 'model', 24),
        N('system_paper', 'core/system_paper.py\n(paper-trading System)', 'model', 26),
        N('calibrator', 'core/probability_calibrator.py\n(gate OFF, auto-refit)', 'model', 24),
        N('wf_harness', 'core/wf_harness.py\n(walk-forward offline)', 'model', 24),
        # ── Settlement / pieniądze ──
        N('settlement', 'core/coupon_settlement.py\n(rozliczenie + stale-VOID)', 'money', 30),
        N('coupon_tracker', 'core/coupon_tracker.py\n(save/active/promote)', 'money', 26),
        N('bankroll', 'core/bankroll.py\n(Kelly, stop-loss)', 'money', 24),
        N('betting', 'utils/betting.py\n(oblicz_tip_correct +HT)', 'money', 24),
        # ── Scrapery (źródła surowe) ──
        N('bzzoiro', 'scrapers/bzzoiro.py\n(ML predykcje + kursy)', 'scrape', 30),
        N('api_football', 'scrapers/api_football.py\n(/odds /fixtures +HT)', 'scrape', 30),
        N('form_scraper', 'scrapers/form_scraper.py\n(Sofascore forma, stealth)', 'scrape', 22),
        # ── Framework multi-source (cross-walidacja) ──
        N('aggregator', 'sources/aggregator.py\n(compare/consensus)', 'source', 30, borderWidth=3, title='Cross-walidacja źródeł'),
        N('af_source', 'sources/af_source', 'source', 20),
        N('fd_source', 'sources/footballdata_source\n(CSV +HT)', 'source', 20),
        N('fs_source', 'sources/flashscore_source\n(mobi FT)', 'source', 20),
        # ── Dane / config ──
        N('hist_loader', 'data/historical_loader.py\n(cache 10 lig, 32k)', 'data', 24),
        N('config', 'config.py\n(whitelist, flagi, env)', 'cfg', 22),
        # ── API / front ──
        N('api_main', 'api/main.py\n(FastAPI + GUI /preview)', 'api', 32),
        N('routes_coupons', 'api/routes/coupons.py\n(build_tips, markets)', 'api', 24),
        N('auth', 'api/auth.py\n(JWT, register)', 'api', 24),
        N('mailer', 'utils/mailer.py\n(Resend email)', 'api', 20),
        N('gui', 'gui/ (React+Tailwind)\n(kreator, dashboard)', 'front', 30),
        # ── DB (Neon PostgreSQL) ──
        N('predictions_db', 'predictions\n(+prob, HT)', 'db', 30, shape='database'),
        N('coupons_db', 'coupons', 'db', 30, shape='database'),
        N('feedback_db', 'ai_feedback\n(RAG MEMORY)', 'db', 34, shape='database', borderWidth=3),
        N('users_db', 'users / bankroll_state', 'db', 24, shape='database'),
    ]

    def E(a, b, layer, w=2, dashes=False, **kw):
        return {'from': a, 'to': b, 'color': C[layer], 'width': w, 'dashes': dashes, **kw}
    edges = [
        # pipeline główny
        E('scheduler', 'daily_agent', 'agent', 2), E('daily_agent', 'daily_phases', 'phase', 3),
        E('daily_agent', 'quick_picks', 'model', 3), E('quick_picks', 'bzzoiro', 'scrape', 2),
        E('quick_picks', 'poisson', 'model', 2), E('poisson', 'dc', 'model', 2),
        E('poisson', 'ensemble', 'model', 2), E('daily_phases', 'api_football', 'scrape', 2, title='fallback kursów /odds'),
        E('daily_agent', 'analyzer', 'ai', 3), E('analyzer', 'analyzer_helpers', 'ai', 2),
        E('analyzer_helpers', 'rag', 'ai', 1, dashes=True), E('analyzer_helpers', 'predictions_db', 'db', 3),
        E('analyzer', 'coupons_db', 'money', 2), E('daily_phases', 'system_paper', 'model', 2),
        E('system_paper', 'coupons_db', 'money', 2), E('daily_agent', 'markets', 'model', 1),
        E('markets', 'betbuilder', 'model', 1), E('daily_agent', 'bankroll', 'money', 2),
        E('hist_loader', 'poisson', 'data', 1, dashes=True), E('hist_loader', 'wf_harness', 'data', 1, dashes=True),
        # settlement
        E('evening_agent', 'settlement', 'money', 3), E('settlement', 'betting', 'money', 2),
        E('settlement', 'coupon_tracker', 'money', 2), E('coupon_tracker', 'coupons_db', 'db', 2),
        E('settlement', 'api_football', 'scrape', 2), E('settlement', 'aggregator', 'source', 1, dashes=True, title='konsensus (planowane)'),
        E('evening_agent', 'calibrator', 'model', 1, dashes=True, title='auto-refit co +30 settled'),
        E('betting', 'predictions_db', 'db', 1),
        # multi-source
        E('aggregator', 'af_source', 'source', 1), E('aggregator', 'fd_source', 'source', 1),
        E('aggregator', 'fs_source', 'source', 1), E('af_source', 'api_football', 'scrape', 1, dashes=True),
        # RAG memory loop
        E('daily_agent', 'post_match', 'ai', 2), E('post_match', 'feedback_db', 'db', 3),
        E('rag', 'feedback_db', 'db', 2, dashes=True), E('trainer', 'analyzer', 'ai', 1, dashes=True, title='inject kalibracja'),
        # API / front
        E('api_main', 'routes_coupons', 'api', 2), E('routes_coupons', 'markets', 'model', 2),
        E('api_main', 'auth', 'api', 1), E('auth', 'mailer', 'api', 1, dashes=True),
        E('api_main', 'gui', 'front', 2), E('routes_coupons', 'coupons_db', 'db', 1),
        E('auth', 'users_db', 'db', 1),
        # config
        E('config', 'daily_agent', 'cfg', 1, dashes=True), E('config', 'quick_picks', 'cfg', 1, dashes=True),
    ]

    # 2. DYNAMIKA: Pobierz lekcje
    dyn_nodes, dyn_edges = fetch_dynamic_data()
    nodes.extend(dyn_nodes)
    edges.extend(dyn_edges)

    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    # 3. PREMIUM HTML & CSS (Przywrócone i ulepszone)
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>FootStats Second Mind v3.6 (Live)</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            width: 100vw; height: 100vh; overflow: hidden;
            font-family: 'Segoe UI', sans-serif;
            background: radial-gradient(circle at center, #1a1a2e 0%, #0a0e27 100%);
            color: #e0e0e0;
        }}
        #mynetwork {{ width: 100%; height: 100%; }}
        
        #header {{
            position: absolute; top: 20px; left: 20px; z-index: 10;
            background: rgba(26, 26, 46, 0.9); padding: 20px;
            border-radius: 12px; border-left: 5px solid #FF1493;
            backdrop-filter: blur(10px); box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }}
        #header h1 {{ font-size: 24px; color: #FF1493; margin-bottom: 5px; letter-spacing: 1px; }}
        #header p {{ font-size: 12px; opacity: 0.7; }}
        
        .legend {{
            position: absolute; bottom: 20px; right: 20px; z-index: 10;
            background: rgba(26, 26, 46, 0.9); padding: 20px;
            border-radius: 12px; border-left: 5px solid #4169E1;
            backdrop-filter: blur(10px); box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            font-size: 12px; min-width: 200px;
        }}
        .legend h3 {{ color: #4169E1; margin-bottom: 10px; font-size: 14px; text-transform: uppercase; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 6px; }}
        .dot {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; }}
        .diamond {{ width: 12px; height: 12px; transform: rotate(45deg); margin-right: 10px; }}
        
        .controls {{
            position: absolute; top: 20px; right: 20px; z-index: 10;
            display: flex; gap: 10px;
        }}
        .btn {{
            background: #FF1493; color: white; border: none; padding: 8px 15px;
            border-radius: 6px; cursor: pointer; font-size: 11px; font-weight: bold;
            transition: 0.3s;
        }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 5px 15px rgba(255,20,147,0.4); }}
    </style>
</head>
<body>
    <div id="header">
        <h1>SECOND MIND v3.6</h1>
        <p>Live Knowledge Graph & Architecture</p>
    </div>
    
    <div class="controls">
        <button class="btn" onclick="network.fit()">FIT VIEW</button>
        <button class="btn" style="background:#4169E1" onclick="location.reload()">REFRESH DATA</button>
    </div>

    <div id="mynetwork"></div>

    <div class="legend">
        <h3>LEGENDA</h3>
        <div class="legend-item"><div class="dot" style="background:#FFD700"></div><span>Orchestration (Agents)</span></div>
        <div class="legend-item"><div class="dot" style="background:#9370DB"></div><span>AI Core (Groq LLM)</span></div>
        <div class="legend-item"><div class="dot" style="background:#4169E1"></div><span>Interface (Dashboard/API)</span></div>
        <div class="legend-item"><div class="dot" style="background:#32CD32"></div><span>Database Tables</span></div>
        <div class="legend-item"><div class="diamond" style="background:#FF1493"></div><span style="color:#FF1493; font-weight:bold">AI LESSONS (LIVE)</span></div>
        <div class="legend-item"><div class="dot" style="background:#00CED1"></div><span>Connected Teams</span></div>
    </div>

    <script>
        var nodes = new vis.DataSet({nodes_json});
        var edges = new vis.DataSet({edges_json});
        var container = document.getElementById('mynetwork');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            physics: {{
                enabled: true,
                barnesHut: {{ gravitationalConstant: -25000, centralGravity: 0.3, springLength: 180, springConstant: 0.04 }},
                stabilization: {{ iterations: 150 }}
            }},
            interaction: {{ hover: true, tooltipDelay: 200, zoomView: true, dragView: true }},
            nodes: {{ 
                font: {{ color: '#ffffff', size: 13, face: 'Segoe UI' }},
                borderWidth: 2, shadow: {{ enabled: true, color: 'rgba(0,0,0,0.5)', size: 10 }}
            }},
            edges: {{ 
                arrows: {{ to: {{ enabled: true, scaleFactor: 0.5 }} }},
                color: {{ inherit: 'from' }}, 
                smooth: {{ type: 'continuous' }},
                width: 1.5
            }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>"""

    output_path = 'brain_graph.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"[OK] Premium Visual Brain zaktualizowany: {output_path}")
    return output_path

if __name__ == "__main__":
    create_brain_graph()
