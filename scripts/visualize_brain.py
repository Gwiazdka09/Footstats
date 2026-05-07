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
    
    # 1. PEŁNA ARCHITEKTURA (Przywrócona z oryginału)
    nodes = [
        # Agenty
        {'id': 'daily_agent', 'label': 'daily_agent.py\n(MAIN)', 'color': '#FFD700', 'size': 40, 'shape': 'dot', 'title': 'Główny orchestrator'},
        {'id': 'evening_agent', 'label': 'evening_agent.py\n(SETTLEMENT)', 'color': '#FFC700', 'size': 35, 'shape': 'dot'},
        # AI/RAG
        {'id': 'analyzer', 'label': 'analyzer.py\n(LLM)', 'color': '#9370DB', 'size': 40, 'shape': 'dot'},
        {'id': 'post_match_analyzer', 'label': 'post_match_analyzer.py\n(RAG)', 'color': '#BA55D3', 'size': 35, 'shape': 'dot'},
        {'id': 'trainer', 'label': 'trainer.py\n(TRAINING)', 'color': '#DA70D6', 'size': 30, 'shape': 'dot'},
        # Frontend/API
        {'id': 'api_main', 'label': 'api/main.py\n(FastAPI)', 'color': '#4169E1', 'size': 35, 'shape': 'dot'},
        {'id': 'preview', 'label': 'dashboard.py\n(Streamlit)', 'color': '#1E90FF', 'size': 30, 'shape': 'dot'},
        # Database
        {'id': 'coupons_db', 'label': 'coupons\n(TABLE)', 'color': '#32CD32', 'size': 35, 'shape': 'dot'},
        {'id': 'predictions_db', 'label': 'predictions\n(TABLE)', 'color': '#3CB371', 'size': 30, 'shape': 'dot'},
        {'id': 'ai_feedback_db', 'label': 'ai_feedback\n(RAG MEMORY)', 'color': '#FF1493', 'size': 45, 'shape': 'dot', 'borderWidth': 3, 'title': 'RAG Memory — Wnioski z porażek'},
        {'id': 'db_main', 'label': 'footstats_backtest.db\n(SQLite)', 'color': '#228B22', 'size': 32, 'shape': 'database'},
        # Configuration
        {'id': 'config', 'label': 'config.py\n(CONFIG)', 'color': '#808080', 'size': 28, 'shape': 'dot'},
        # Core
        {'id': 'backtest', 'label': 'backtest.py\n(BACKTEST)', 'color': '#FF8C00', 'size': 30, 'shape': 'dot'},
        {'id': 'calibration', 'label': 'calibration.py\n(KELLY)', 'color': '#FF7F50', 'size': 28, 'shape': 'dot'},
        {'id': 'results_updater', 'label': 'results_updater.py\n(RESULTS)', 'color': '#6495ED', 'size': 30, 'shape': 'dot'},
    ]

    edges = [
        {'from': 'daily_agent', 'to': 'analyzer', 'color': '#9370DB', 'width': 4},
        {'from': 'analyzer', 'to': 'coupons_db', 'color': '#32CD32', 'width': 3},
        {'from': 'analyzer', 'to': 'ai_feedback_db', 'color': '#FF1493', 'width': 3, 'dashes': True},
        {'from': 'post_match_analyzer', 'to': 'ai_feedback_db', 'color': '#FF1493', 'width': 3},
        {'from': 'daily_agent', 'to': 'post_match_analyzer', 'color': '#DA70D6', 'width': 3},
        {'from': 'evening_agent', 'to': 'coupons_db', 'color': '#FFD700', 'width': 3},
        {'from': 'results_updater', 'to': 'predictions_db', 'color': '#6495ED', 'width': 2},
        {'from': 'backtest', 'to': 'trainer', 'color': '#DA70D6', 'width': 2, 'dashes': True, 'title': 'Trigger auto-training (co 20 wynikow)'},
        {'from': 'trainer', 'to': 'analyzer', 'color': '#DA70D6', 'width': 2, 'dashes': True, 'title': 'Inject calibration blocks'},
        {'from': 'trainer', 'to': 'db_main', 'color': '#228B22', 'width': 1, 'dashes': True},
        {'from': 'ai_feedback_db', 'to': 'db_main', 'color': '#228B22', 'width': 2, 'dashes': True},
        {'from': 'coupons_db', 'to': 'db_main', 'color': '#228B22', 'width': 1},
        {'from': 'predictions_db', 'to': 'db_main', 'color': '#228B22', 'width': 1},
        {'from': 'api_main', 'to': 'coupons_db', 'color': '#4169E1', 'width': 2},
        {'from': 'api_main', 'to': 'preview', 'color': '#4169E1', 'width': 2},
        {'from': 'daily_agent', 'to': 'calibration', 'color': '#FF8C00', 'width': 2},
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
