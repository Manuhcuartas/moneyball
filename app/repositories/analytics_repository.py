from sqlalchemy.orm import Session
from sqlalchemy import select, func, Integer  # <--- IMPORTANTE: Añadir Integer
from app.models.shot import Shot
from app.models.stats import PlayerStat
from app.schemas.stats import PlayerAdvancedStats, ZoneStat

class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_shooting_stats_by_game(self, game_id: str):
        """
        Calcula estadísticas de tiro agrupadas por Equipo y Zona.
        """
        stmt = (
            select(
                Shot.team_id,
                Shot.zone,
                func.count(Shot.id).label("total"),
                func.sum(func.cast(Shot.is_made, Integer)).label("made") 
            )
            .where(Shot.game_id == game_id)
            .group_by(Shot.team_id, Shot.zone)
        )
        
        results = self.db.execute(stmt).all()
        
        stats_by_team = {}
        
        for team_id, zone, total, made in results:
            if team_id not in stats_by_team:
                stats_by_team[team_id] = []
            
            # Protección contra nulls si no hay tiros metidos
            made_safe = made if made is not None else 0
                
            efficiency = (made_safe / total) * 100 if total > 0 else 0.0
            
            stats_by_team[team_id].append(ZoneStat(
                zone=zone,
                total_shots=total,
                made_shots=made_safe,
                efficiency=round(efficiency, 2)
            ))
            
        return stats_by_team
    
    def get_advanced_player_stats(self, game_id: str):
        """
        Calcula TS% REAL y eFG% usando los datos oficiales del acta (PlayerStat).
        """
        stmt = (
            select(PlayerStat)
            .where(PlayerStat.game_id == game_id)
            # Ordenamos por puntos para el ranking por defecto
            .order_by(PlayerStat.puntos.desc())
        )
        
        results = self.db.execute(stmt).scalars().all()
        advanced_stats = []
        
        for p in results:
            # Extracción de datos seguros (el acta ya tiene los datos)
            fga2 = p.t2_intentados or 0
            fgm2 = p.t2_anotados or 0
            fga3 = p.t3_intentados or 0
            fgm3 = p.t3_anotados or 0
            fta = p.t1_intentados or 0   # <--- AHORA SÍ TENEMOS TIROS LIBRES
            ftm = p.t1_anotados or 0
            
            total_attempts = fga2 + fga3
            total_points = p.puntos
            
            # --- CÁLCULOS MONEYBALL REALES ---
            
            # 1. eFG%: (FG + 0.5 * 3P) / FGA
            efg = 0.0
            if total_attempts > 0:
                efg = ((fgm2 + fgm3) + (0.5 * fgm3)) / total_attempts * 100

            # 2. TS%: Pts / (2 * (FGA + 0.44 * FTA))
            ts = 0.0
            ts_denominator = 2 * (total_attempts + (0.44 * fta))
            if ts_denominator > 0:
                ts = (total_points / ts_denominator) * 100

            # 3. Distribución de tiro
            dist_2p = (fga2 / total_attempts * 100) if total_attempts > 0 else 0
            dist_3p = (fga3 / total_attempts * 100) if total_attempts > 0 else 0
            
            # Parsear minutos "MM:SS" a float para el proxy si es necesario
            minutes_val = 0.0
            if p.minutos and ":" in str(p.minutos):
                try:
                    m, s = map(int, p.minutos.split(":"))
                    minutes_val = m + (s/60)
                except: pass

            advanced_stats.append(PlayerAdvancedStats(
                player_id=p.player_id,
                dorsal=str(p.dorsal),
                team_id=p.player.team_id if p.player else 0, # Asegúrate de tener la relación cargada o usa p.id si aplica
                minutes_proxy=minutes_val, # Ahora usamos minutos reales
                points=total_points,
                fg2_made=fgm2,
                fg2_attempted=fga2,
                fg3_made=fgm3,
                fg3_attempted=fga3,
                efg_percentage=round(efg, 1),
                ts_proxy=round(ts, 1),     # <--- DATO REAL
                shot_distribution_2p=round(dist_2p, 1),
                shot_distribution_3p=round(dist_3p, 1)
            ))
            
        return advanced_stats