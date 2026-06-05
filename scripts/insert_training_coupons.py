"""Insert 10 historical training coupons for Admin_JG (user_id=2)."""
import json
import sys
import os
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[1] / 'src'))
from dotenv import load_dotenv
load_dotenv()
from footstats.utils.db import connect

coupons = [
    # WON x4
    {
        'date': '2026-05-10', 'status': 'WON', 'type': 'PEWNIACZEK', 'stake': 10.0,
        'legs': [
            {'home': 'Bayern München', 'away': 'Wolfsburg', 'league': 'Bundesliga', 'tip': '1', 'odds': 1.45, 'result': '3-1'},
            {'home': 'Borussia Dortmund', 'away': 'Mainz', 'league': 'Bundesliga', 'tip': 'Over 2.5', 'odds': 1.62, 'result': '4-0'},
        ],
        'total_odds': round(1.45*1.62, 2),
        'reasoning': 'Bayern dominuje u siebie, BVB w dobrym gazie ofensywnym.',
        'score': 72,
    },
    {
        'date': '2026-05-17', 'status': 'WON', 'type': 'SINGIEL', 'stake': 8.0,
        'legs': [
            {'home': 'Real Madrid', 'away': 'Getafe', 'league': 'La Liga', 'tip': '1', 'odds': 1.38, 'result': '2-0'},
        ],
        'total_odds': 1.38,
        'reasoning': 'Real bez presji na koniec sezonu, Getafe bez formy wyjazdowej.',
        'score': 65,
    },
    {
        'date': '2026-05-24', 'status': 'WON', 'type': 'AKO', 'stake': 12.0,
        'legs': [
            {'home': 'Inter Milan', 'away': 'Udinese', 'league': 'Serie A', 'tip': '1', 'odds': 1.42, 'result': '3-0'},
            {'home': 'Napoli', 'away': 'Salernitana', 'league': 'Serie A', 'tip': 'Over 2.5', 'odds': 1.72, 'result': '4-1'},
            {'home': 'Juventus', 'away': 'Frosinone', 'league': 'Serie A', 'tip': '1X', 'odds': 1.25, 'result': '2-0'},
        ],
        'total_odds': round(1.42*1.72*1.25, 2),
        'reasoning': 'Trzy pewne faworyzowane druzyny Serie A na koniec sezonu.',
        'score': 78,
    },
    {
        'date': '2026-05-31', 'status': 'WON', 'type': 'PEWNIACZEK', 'stake': 10.0,
        'legs': [
            {'home': 'PSG', 'away': 'Metz', 'league': 'Ligue 1', 'tip': '1', 'odds': 1.30, 'result': '5-0'},
            {'home': 'Marseille', 'away': 'Lens', 'league': 'Ligue 1', 'tip': 'BTTS', 'odds': 1.80, 'result': '2-1'},
        ],
        'total_odds': round(1.30*1.80, 2),
        'reasoning': 'PSG nie traci z Metz, Marsylia vs Lens bramkowy klasyk.',
        'score': 69,
    },
    # LOST x6
    {
        'date': '2026-05-12', 'status': 'LOST', 'type': 'SINGIEL', 'stake': 8.0,
        'legs': [
            {'home': 'Arsenal', 'away': 'Manchester City', 'league': 'Premier League', 'tip': '1', 'odds': 2.45, 'result': '1-2'},
        ],
        'total_odds': 2.45,
        'reasoning': 'Arsenal u siebie, City zmeczony po europejskich rozgrywkach.',
        'score': 55,
    },
    {
        'date': '2026-05-16', 'status': 'LOST', 'type': 'AKO', 'stake': 10.0,
        'legs': [
            {'home': 'Barcelona', 'away': 'Real Sociedad', 'league': 'La Liga', 'tip': '1', 'odds': 1.55, 'result': '1-1'},
            {'home': 'Atletico Madrid', 'away': 'Sevilla', 'league': 'La Liga', 'tip': 'Under 2.5', 'odds': 1.75, 'result': '3-1'},
        ],
        'total_odds': round(1.55*1.75, 2),
        'reasoning': 'Barca faworyt, Atletico gra zachowawczo.',
        'score': 58,
    },
    {
        'date': '2026-05-22', 'status': 'LOST', 'type': 'PEWNIACZEK', 'stake': 10.0,
        'legs': [
            {'home': 'Leverkusen', 'away': 'Eintracht Frankfurt', 'league': 'Bundesliga', 'tip': '1', 'odds': 1.68, 'result': '0-2'},
            {'home': 'RB Leipzig', 'away': 'Freiburg', 'league': 'Bundesliga', 'tip': 'Over 2.5', 'odds': 1.78, 'result': '1-1'},
        ],
        'total_odds': round(1.68*1.78, 2),
        'reasoning': 'Leverkusen silny u siebie, Leipzig otwarty styl.',
        'score': 61,
    },
    {
        'date': '2026-05-28', 'status': 'LOST', 'type': 'SINGIEL', 'stake': 8.0,
        'legs': [
            {'home': 'Chelsea', 'away': 'Liverpool', 'league': 'Premier League', 'tip': 'BTTS', 'odds': 1.70, 'result': '0-0'},
        ],
        'total_odds': 1.70,
        'reasoning': 'Chelsea vs Liverpool historycznie bramkowy.',
        'score': 53,
    },
    {
        'date': '2026-06-01', 'status': 'LOST', 'type': 'AKO', 'stake': 12.0,
        'legs': [
            {'home': 'Ajax', 'away': 'Feyenoord', 'league': 'Eredivisie', 'tip': '1', 'odds': 1.90, 'result': '1-2'},
            {'home': 'PSV', 'away': 'AZ Alkmaar', 'league': 'Eredivisie', 'tip': 'Over 2.5', 'odds': 1.65, 'result': '2-0'},
        ],
        'total_odds': round(1.90*1.65, 2),
        'reasoning': 'Ajax u siebie w derbach, PSV atakujacy styl.',
        'score': 60,
    },
    {
        'date': '2026-06-03', 'status': 'LOST', 'type': 'PEWNIACZEK', 'stake': 10.0,
        'legs': [
            {'home': 'Lech Poznan', 'away': 'Zaglebie Lubin', 'league': 'PKO BP Ekstraklasa', 'tip': '1', 'odds': 1.72, 'result': '0-1'},
            {'home': 'Legia Warszawa', 'away': 'Piast Gliwice', 'league': 'PKO BP Ekstraklasa', 'tip': 'Over 2.5', 'odds': 1.85, 'result': '1-0'},
        ],
        'total_odds': round(1.72*1.85, 2),
        'reasoning': 'Lech atakuje u siebie, Legia potrzebuje punktow.',
        'score': 56,
    },
]

with connect() as conn:
    for c in coupons:
        odds = c['total_odds']
        stake = c['stake']
        payout = round(stake * odds * 0.88, 2) if c['status'] == 'WON' else None
        roi = round((payout - stake) / stake * 100, 1) if payout else -100.0

        row = conn.execute(
            """
            INSERT INTO coupons
              (phase, status, kupon_type, legs_json, total_odds, stake_pln, payout_pln,
               roi_pct, groq_reasoning, decision_score, match_date_first, user_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 2, %s::timestamp)
            RETURNING id
            """,
            (
                'final', c['status'], c['type'],
                json.dumps(c['legs']),
                odds, stake, payout, roi,
                c['reasoning'], c['score'],
                c['date'],
                c['date'] + ' 08:30:00',
            ),
        ).fetchone()
        cid = row['id']
        print(f"#{cid} {c['status']:6} {c['type']:12} @{odds:.2f}  {len(c['legs'])} legs  {c['date']}")
    conn.commit()

print("Done — 10 training coupons inserted for user_id=2.")
