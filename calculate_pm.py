import requests
import json
import time
from urllib.parse import urlencode
import urllib3
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.models.stats import Game, PlayerStat, Player, GameFlow
from app.core.config import settings
import sys

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Config
LOGIN_URL = settings.FBPA_LOGIN_URL
PBP_URL = "https://appaficionfbpa.indalweb.net/v2/envivo/partido.ashx"

def get_auth_key():
    payload = {
        "accion": "acceso",
        "uid": settings.FBPA_DEVICE_UID,
        "plataforma": "ios",
        "tipo_dispositivo": "mobile",
        "id_dispositivo": settings.FBPA_ID_DISPOSITIVO,
        "token_push": settings.FBPA_PUSH_TOKEN,
        "version": settings.FBPA_APP_VERSION
    }
    
    try:
        r = requests.post(
            LOGIN_URL, 
            data=urlencode(payload), 
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                "Content-Type": "application/x-www-form-urlencoded"
            }, 
            verify=False, 
            timeout=15
        )
        
        data = r.json()
        if data.get("resultado") == "correcto" and data.get("key"):
            print(f"Login OK. Key: {data['key'][:10]}...")
            return data["key"]
        else:
            print(f"Login Failed: {data.get('error')}")
            return None
    except Exception as e:
        print(f"Login Exception: {e}")
        return None

def get_game_pbp(game_id, key):
    payload = {
        "key": key,
        "id_partido": game_id,
        "id_dispositivo": settings.FBPA_ID_DISPOSITIVO
    }
    try:
        r = requests.post(
            PBP_URL, 
            data=urlencode(payload), 
            headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                "Content-Type": "application/x-www-form-urlencoded"
            }, 
            verify=False, 
            timeout=15
        )
        return r.json()
    except Exception as e:
        print(f"Error fetching PBP: {e}")
        return {}

def calculate_pm_for_game(db: Session, game_id: str, key: str):
    print(f"Processing Game {game_id}...")
    
    # 1. Fetch Game
    game = db.query(Game).filter(Game.id == game_id).first()
    if not game:
        print("Game not found in DB")
        return
        
    # 2. Fetch PBP
    pbp_data = get_game_pbp(game_id, key)
    if not pbp_data:
        print(f"PBP fetch failed for game {game_id}")
        return

    actions = pbp_data.get("historialacciones", [])
    if not actions:
        print(f"No actions found for game {game_id}")
        print(f"Response Keys: {list(pbp_data.keys())}")
        if "partido" in pbp_data:
            print(f"Match Meta: {json.dumps(pbp_data['partido'], indent=2)}")
        else:
             print(f"Full Response (truncated): {str(pbp_data)[:500]}")
        return
        
    print(f"DEBUG: Found {len(actions)} actions")

    # 3. Setup Metadata & Players
    meta = pbp_data.get("partido", {})
    id_local = meta.get("idlocal")
    
    # Fetch players from DB
    stats = db.query(PlayerStat).filter(PlayerStat.game_id == game_id).all()
    
    local_players = {}   # dorsal -> PlayerStat 
    visitor_players = {} # dorsal -> PlayerStat
    
    # Reset PM & Map players
    for s in stats:
        s.mas_menos = 0
        p = s.player
        # Verify team mapping
        # We'll assume the DB team_id matches appropriately to home/visitor
        if p.team_id == game.home_team_id:
            local_players[str(s.dorsal)] = s
        else:
            visitor_players[str(s.dorsal)] = s
            
    # Clear existing flow data
    db.query(GameFlow).filter(GameFlow.game_id == game_id).delete()
            
    on_court_local = set()
    on_court_visitor = set()
    
    # Initialize starters
    for s in stats:
        if s.es_titular:
            dorsal = str(s.dorsal)
            if s.player.team_id == game.home_team_id:
                on_court_local.add(dorsal)
            else:
                on_court_visitor.add(dorsal)
                
    # 4. Process Events
    # Sort by autoincremental_id to ensure chronological order
    actions.sort(key=lambda x: x.get("autoincremental_id", 0))
    
    current_home_score = 0
    current_visitor_score = 0
    sequence = 0
    
    # Create initial 0-0 flow point
    db.add(GameFlow(
        game_id=game_id, 
        minute="00:00", 
        sequence_order=sequence, 
        puntos_local=0, 
        puntos_visitante=0, 
        diff=0
    ))
    sequence += 1

    def get_dorsal_str(action):
        d = action.get("dorsal")
        return str(d) if d is not None else None

    for action in actions:
        action_type = action.get("accion_tipo")
        
        # Determine strict side match for substitutions
        # API usually provides team_id in action
        team_id = action.get("equipo_id")
        
        is_local_team_action = False
        if id_local and team_id:
            is_local_team_action = (str(team_id) == str(id_local))
        
        # Get points data (Assuming DELTA based on user feedback)
        # "puntos_local": 2  => Local team scored 2 points in this action
        pts_home_delta = int(action.get("puntos_local") or 0)
        pts_visitor_delta = int(action.get("puntos_visitante") or 0)
        
        dorsal = get_dorsal_str(action)
        score_changed = False
        
        # --- SCORING LOGIC ---
        if pts_home_delta > 0:
            current_home_score += pts_home_delta
            # Update PM for ON COURT players
            for d in on_court_local:
                if d in local_players: local_players[d].mas_menos += pts_home_delta
            for d in on_court_visitor:
                if d in visitor_players: visitor_players[d].mas_menos -= pts_home_delta
            score_changed = True
            
        if pts_visitor_delta > 0:
            current_visitor_score += pts_visitor_delta
            # Update PM for ON COURT players
            for d in on_court_visitor:
                if d in visitor_players: visitor_players[d].mas_menos += pts_visitor_delta
            for d in on_court_local:
                if d in local_players: local_players[d].mas_menos -= pts_visitor_delta
            score_changed = True

        if score_changed:
            # Add Flow Point
            db.add(GameFlow(
                game_id=game_id,
                minute=action.get("momento", "00:00"),
                sequence_order=sequence,
                puntos_local=current_home_score,
                puntos_visitante=current_visitor_score,
                diff=current_home_score - current_visitor_score
            ))
            sequence += 1
            
        # --- SUBSTITUTION LOGIC ---
        if action_type == "CAMBIO-JUGADOR-ENTRA":
            if dorsal:
                if is_local_team_action:
                    on_court_local.add(dorsal)
                else:
                    on_court_visitor.add(dorsal)
                
        elif action_type == "CAMBIO-JUGADOR-SALE":
            if dorsal:
                if is_local_team_action:
                    on_court_local.discard(dorsal)
                else:
                    on_court_visitor.discard(dorsal)
                    
    # 5. Commit
    try:
        db.commit()
        print(f"Success: Game {game_id} - Final Score {current_home_score}-{current_visitor_score}")
    except Exception as e:
        print(f"Error committing game {game_id}: {e}")
        db.rollback()

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    print("Authenticating...")
    key = get_auth_key()
    if not key:
        print("Could not retrieve auth key. Exiting.")
        db.close()
        return

    # Check for target game file, or process all
    target_id = None
    try:
        with open('game_id.txt', 'r') as f:
            target_id = f.read().strip()
    except:
        pass

    if target_id:
        print(f"Targeting single game from file: {target_id}")
        games = [db.query(Game).filter(Game.id == target_id).first()]
    else:
        # Fetch all valid games (e.g. Round 7+)
        print("Fetching all games from DB...")
        games = db.query(Game).all()
        # Optionally filter? 
        # games = [g for g in games if g.jornada and int(g.jornada) >= 7]

    print(f"Processing {len(games)} games...")
    
    for game in games:
        if not game: continue
        try:
            calculate_pm_for_game(db, game.id, key)
        except Exception as e:
            print(f"Error processing game {game.id}: {e}")
            import traceback
            traceback.print_exc()
            
    db.close()

if __name__ == "__main__":
    main()
