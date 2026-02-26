from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.stats import Player, PlayerStat, PlayerSeasonStat, LeagueAverage
from functools import reduce
import logging

logger = logging.getLogger(__name__)

def parse_minutes(time_str: str) -> float:
    """Converts a time string MM:SS or simply MM to float minutes."""
    if not time_str:
        return 0.0
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            return float(parts[0]) + float(parts[1]) / 60.0
        return float(time_str)
    except:
        return 0.0

def float_to_minutes_str(minutes_float: float) -> str:
    """Converts float minutes to MM:SS string."""
    m = int(minutes_float)
    s = int((minutes_float - m) * 60)
    return f"{m:02d}:{s:02d}"

def calculate_all_season_stats(db: Session):
    """
    Computes and saves season averages for all players based on their individual Game logs (PlayerStat).
    This runs entirely locally and eliminates the need to query the slow federation API for season totals.
    """
    logger.info("📊 Iniciando cálculo local de promedios de temporada...")
    
    # 1. Fetch ALL game stats to compute league averages
    all_stats = db.query(PlayerStat).all()
    
    if not all_stats:
        logger.warning("No hay stats de partidos para agregar.")
        return

    # Basic league accumulators
    total_league_games = len(all_stats)
    
    league_totals = {
        "minutes": sum(parse_minutes(s.minutos) for s in all_stats),
        "points": sum(s.puntos or 0 for s in all_stats),
        "valoracion": sum(s.valoracion or 0 for s in all_stats),
        "mas_menos": sum(s.mas_menos or 0 for s in all_stats),
        "rebounds": sum(s.rebotes_total or 0 for s in all_stats),
        "assists": sum(s.asistencias or 0 for s in all_stats),
        "steals": sum(s.recuperaciones or 0 for s in all_stats),
        "turnovers": sum(s.perdidas or 0 for s in all_stats),
        "fouls_drawn": sum(s.faltas_recibidas or 0 for s in all_stats),
        "fouls_committed": sum(s.faltas_cometidas or 0 for s in all_stats),
        "ft_made": sum(s.t1_anotados or 0 for s in all_stats),
        "ft_attempted": sum(s.t1_intentados or 0 for s in all_stats),
        "fg_made": sum((s.t2_anotados or 0) + (s.t3_anotados or 0) for s in all_stats),
        "fg_attempted": sum((s.t2_intentados or 0) + (s.t3_intentados or 0) for s in all_stats),
        "two_made": sum(s.t2_anotados or 0 for s in all_stats),
        "two_attempted": sum(s.t2_intentados or 0 for s in all_stats),
        "three_made": sum(s.t3_anotados or 0 for s in all_stats),
        "three_attempted": sum(s.t3_intentados or 0 for s in all_stats),
    }

    def safe_div(a, b):
        return float(a) / float(b) if b and b > 0 else 0.0

    league_avg_model = db.query(LeagueAverage).first()
    if not league_avg_model:
        league_avg_model = LeagueAverage()
        db.add(league_avg_model)
        
    league_avg_model.minutes_avg = safe_div(league_totals["minutes"], total_league_games)
    league_avg_model.points_avg = safe_div(league_totals["points"], total_league_games)
    league_avg_model.valoracion_avg = safe_div(league_totals["valoracion"], total_league_games)
    league_avg_model.mas_menos_avg = safe_div(league_totals["mas_menos"], total_league_games)
    league_avg_model.rebounds_avg = safe_div(league_totals["rebounds"], total_league_games)
    league_avg_model.assists_avg = safe_div(league_totals["assists"], total_league_games)
    league_avg_model.steals_avg = safe_div(league_totals["steals"], total_league_games)
    league_avg_model.turnovers_avg = safe_div(league_totals["turnovers"], total_league_games)
    league_avg_model.fouls_drawn_avg = safe_div(league_totals["fouls_drawn"], total_league_games)
    league_avg_model.fouls_committed_avg = safe_div(league_totals["fouls_committed"], total_league_games)
    league_avg_model.blocks_avg = 0.0

    league_avg_model.ft_pct = safe_div(league_totals["ft_made"], league_totals["ft_attempted"]) * 100.0
    league_avg_model.fg_pct = safe_div(league_totals["fg_made"], league_totals["fg_attempted"]) * 100.0
    league_avg_model.two_pct = safe_div(league_totals["two_made"], league_totals["two_attempted"]) * 100.0
    league_avg_model.three_pct = safe_div(league_totals["three_made"], league_totals["three_attempted"]) * 100.0

    # Group stats by player_id and calculate team totals for USG%
    player_stats_map = {}
    team_totals = {}
    for stat in all_stats:
        pid = stat.player_id
        if pid not in player_stats_map:
            player_stats_map[pid] = []
        player_stats_map[pid].append(stat)

        if stat.player and stat.player.team_id:
            tid = stat.player.team_id
            if tid not in team_totals:
                team_totals[tid] = {"fga": 0, "fta": 0, "tov": 0, "mp": 0.0}
            team_totals[tid]["fga"] += (stat.t2_intentados or 0) + (stat.t3_intentados or 0)
            team_totals[tid]["fta"] += (stat.t1_intentados or 0)
            team_totals[tid]["tov"] += (stat.perdidas or 0)
            team_totals[tid]["mp"] += parse_minutes(stat.minutos)

    # Calculate and update season stats for each player
    count = 0
    for player_id, p_stats in player_stats_map.items():
        games_played = len(p_stats)
        if games_played == 0:
            continue

        totals = {
            "minutes": sum(parse_minutes(s.minutos) for s in p_stats),
            "points": sum(s.puntos or 0 for s in p_stats),
            "valoracion": sum(s.valoracion or 0 for s in p_stats),
            "mas_menos": sum(s.mas_menos or 0 for s in p_stats),
            "rebounds": sum(s.rebotes_total or 0 for s in p_stats),
            "assists": sum(s.asistencias or 0 for s in p_stats),
            "steals": sum(s.recuperaciones or 0 for s in p_stats),
            "turnovers": sum(s.perdidas or 0 for s in p_stats),
            "fouls_drawn": sum(s.faltas_recibidas or 0 for s in p_stats),
            "fouls_committed": sum(s.faltas_cometidas or 0 for s in p_stats),
            "ft_made": sum(s.t1_anotados or 0 for s in p_stats),
            "ft_attempted": sum(s.t1_intentados or 0 for s in p_stats),
            "fg_made": sum((s.t2_anotados or 0) + (s.t3_anotados or 0) for s in p_stats),
            "fg_attempted": sum((s.t2_intentados or 0) + (s.t3_intentados or 0) for s in p_stats),
            "two_made": sum(s.t2_anotados or 0 for s in p_stats),
            "two_attempted": sum(s.t2_intentados or 0 for s in p_stats),
            "three_made": sum(s.t3_anotados or 0 for s in p_stats),
            "three_attempted": sum(s.t3_intentados or 0 for s in p_stats),
        }

        season_stat = db.query(PlayerSeasonStat).filter(PlayerSeasonStat.player_id == player_id).first()
        if not season_stat:
            season_stat = PlayerSeasonStat(player_id=player_id)
            db.add(season_stat)

        # Apply player averages
        season_stat.games_played = games_played
        season_stat.total_points = totals["points"]
        season_stat.total_minutes = float_to_minutes_str(totals["minutes"])
        season_stat.total_valoracion = totals["valoracion"]
        season_stat.total_rebounds = totals["rebounds"]
        season_stat.total_assists = totals["assists"]
        season_stat.total_steals = totals["steals"]
        season_stat.total_turnovers = totals["turnovers"]
        season_stat.total_blocks = 0

        season_stat.minutes_avg = safe_div(totals["minutes"], games_played)
        season_stat.points_avg = safe_div(totals["points"], games_played)
        season_stat.valoracion_avg = safe_div(totals["valoracion"], games_played)
        season_stat.mas_menos_avg = safe_div(totals["mas_menos"], games_played)
        season_stat.rebounds_avg = safe_div(totals["rebounds"], games_played)
        season_stat.assists_avg = safe_div(totals["assists"], games_played)
        season_stat.steals_avg = safe_div(totals["steals"], games_played)
        season_stat.turnovers_avg = safe_div(totals["turnovers"], games_played)
        season_stat.blocks_avg = 0.0
        season_stat.fouls_drawn_avg = safe_div(totals["fouls_drawn"], games_played)
        season_stat.fouls_committed_avg = safe_div(totals["fouls_committed"], games_played)

        season_stat.ft_pct = safe_div(totals["ft_made"], totals["ft_attempted"]) * 100.0
        season_stat.fg_pct = safe_div(totals["fg_made"], totals["fg_attempted"]) * 100.0
        season_stat.two_pct = safe_div(totals["two_made"], totals["two_attempted"]) * 100.0
        season_stat.three_pct = safe_div(totals["three_made"], totals["three_attempted"]) * 100.0

        # Advanced Stats
        season_stat.ts_pct = safe_div(totals["points"], 2 * (totals["fg_attempted"] + 0.44 * totals["ft_attempted"])) * 100.0
        season_stat.efg_pct = safe_div(totals["fg_made"] + 0.5 * totals["three_made"], totals["fg_attempted"]) * 100.0
        
        tid = p_stats[0].player.team_id if p_stats and p_stats[0].player else None
        if tid and tid in team_totals:
            tt = team_totals[tid]
            player_poss = totals["fg_attempted"] + 0.44 * totals["ft_attempted"] + totals["turnovers"]
            team_poss = tt["fga"] + 0.44 * tt["fta"] + tt["tov"]
            season_stat.usg_pct = safe_div(100 * player_poss * (tt["mp"] / 5), (totals["minutes"] or 9999) * team_poss)
        else:
            season_stat.usg_pct = 0.0

        # Finally, update the player's basic ppg and mpg fields if needed
        player = db.query(Player).filter(Player.id == player_id).first()
        if player:
            player.ppg = season_stat.points_avg
            player.mpg = season_stat.minutes_avg

        count += 1

    # Commit averages
    db.commit()
    logger.info(f"✅ Calculadas y guardadas estadísticas de temporada para {len(player_stats_map)} jugadores.")
    
    # Calculate percentiles relative to league
    all_season_stats = db.query(PlayerSeasonStat).filter(PlayerSeasonStat.games_played > 0).all()
    if all_season_stats:
        def set_pctile(stat_field, pctile_field):
            # Sort stats: ascending. Index 0 gets 0 (worst), Index N-1 gets 100 (best)
            sorted_stats = sorted(all_season_stats, key=lambda x: getattr(x, stat_field))
            n = len(sorted_stats)
            for i, pStat in enumerate(sorted_stats):
                if n > 1:
                    pct = int((i / (n - 1)) * 100)
                else:
                    pct = 50
                setattr(pStat, pctile_field, pct)
                
        set_pctile('points_avg', 'points_pctile')
        set_pctile('rebounds_avg', 'rebounds_pctile')
        set_pctile('assists_avg', 'assists_pctile')
        set_pctile('steals_avg', 'steals_pctile')
        set_pctile('blocks_avg', 'blocks_pctile')
        set_pctile('valoracion_avg', 'valoracion_pctile')
        set_pctile('mas_menos_avg', 'mas_menos_pctile')
        db.commit()
        logger.info(f"✅ Calculados percentiles para {len(all_season_stats)} jugadores.")

    
    return True
