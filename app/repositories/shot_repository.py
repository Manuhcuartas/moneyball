from sqlalchemy.orm import Session
from app.models.shot import Shot
from app.schemas.shot import ShotIngest

class ShotRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_batch(self, game_id: str, shots_data: list[ShotIngest]):
        """Guarda una lista masiva de tiros de golpe (Batch Insert)"""
        db_shots = []
        for data in shots_data:
            # Convertimos del DTO (Pydantic) a la Entidad (SQLAlchemy)
            shot = Shot(
                game_id=game_id,
                team_id=data.equipo_id,
                player_id=data.componente_id,
                dorsal=data.dorsal,
                period=data.numero_periodo,
                action_type=data.accion_tipo,
                x=data.posicion_x, # Ya viene limpio (float)
                y=data.posicion_y,
                zone=data.zona,
                is_made=bool(data.metido)
            )
            db_shots.append(shot)
        
        if db_shots:
            self.db.add_all(db_shots)
            self.db.commit()
            return len(db_shots)
        return 0