from sqlalchemy.orm import Session
from sqlalchemy import select, func, Integer  # <--- IMPORTANTE: Añadir Integer
from app.models.shot import Shot
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
                # CORRECCIÓN AQUÍ: Usamos Integer (SQL) en lugar de int (Python)
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
        Calcula eFG%, distribución de tiro y puntos generados por jugador.
        """
        stmt = (
            select(
                Shot.player_id,
                Shot.dorsal,
                Shot.team_id,
                # Tiros de 2
                func.sum(func.cast(Shot.action_type.like('%2%'), Integer)).label("fga2"),
                func.sum(func.cast(Shot.action_type.like('%CANASTA-2P%'), Integer)).label("fgm2"),
                # Tiros de 3
                func.sum(func.cast(Shot.action_type.like('%3%'), Integer)).label("fga3"),
                func.sum(func.cast(Shot.action_type.like('%CANASTA-3P%'), Integer)).label("fgm3"),
            )
            .where(Shot.game_id == game_id)
            .group_by(Shot.player_id, Shot.dorsal, Shot.team_id)
        )
        
        results = self.db.execute(stmt).all()
        advanced_stats = []
        
        for pid, dorsal, tid, fga2, fgm2, fga3, fgm3 in results:
            # Limpieza de Nones
            fga2, fgm2 = fga2 or 0, fgm2 or 0
            fga3, fgm3 = fga3 or 0, fgm3 or 0
            
            total_attempts = fga2 + fga3
            total_points = (fgm2 * 2) + (fgm3 * 3)
            
            # --- CÁLCULOS MONEYBALL ---
            
            # 1. eFG%: (FG + 0.5 * 3P) / FGA
            # Simplificado: (Puntos Totales / 2) / Tiros Intentados
            efg = 0.0
            if total_attempts > 0:
                efg = ((fgm2 + fgm3) + (0.5 * fgm3)) / total_attempts * 100

            # 2. Shot Distribution (Tendencia del jugador)
            dist_2p = (fga2 / total_attempts * 100) if total_attempts > 0 else 0
            dist_3p = (fga3 / total_attempts * 100) if total_attempts > 0 else 0
            
            # 3. TS% Proxy (True Shooting)
            # Como no tenemos Tiros Libres aún, el TS% es similar al eFG% pero ajustado
            # TS% = Pts / (2 * FGA). En este caso sin TL, es matemáticamente igual al eFG% / 100 * 100
            
            advanced_stats.append(PlayerAdvancedStats(
                player_id=pid,
                dorsal=dorsal,
                team_id=tid,
                minutes_proxy=total_attempts,
                points=total_points,
                fg2_made=fgm2,
                fg2_attempted=fga2,
                fg3_made=fgm3,
                fg3_attempted=fga3,
                efg_percentage=round(efg, 1),
                ts_proxy=round(efg, 1), # Placeholder hasta tener TL
                shot_distribution_2p=round(dist_2p, 1),
                shot_distribution_3p=round(dist_3p, 1)
            ))
            
        # Ordenamos por puntos (de mayor a menor)
        advanced_stats.sort(key=lambda x: x.points, reverse=True)
        
        return advanced_stats