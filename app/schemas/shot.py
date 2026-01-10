from pydantic import BaseModel, ConfigDict, field_validator
from typing import Any

# 1. INPUT: Validación flexible
class ShotIngest(BaseModel):
    # Campos que coinciden con el JSON
    equipo_id: int
    componente_id: str
    dorsal: str
    numero_periodo: int
    accion_tipo: str
    zona: str
    metido: int
    fallado: int
    
    # Definimos como float, pero usamos el validador con mode='before'
    # para interceptar el string "13.88%" ANTES de que Pydantic se queje.
    posicion_x: float
    posicion_y: float

    @field_validator('posicion_x', 'posicion_y', mode='before')
    @classmethod
    def clean_percentage(cls, v: Any) -> float:
        # Si llega un string con %, lo limpiamos
        if isinstance(v, str):
            v = v.replace('%', '').strip()
        # Intentamos convertir a float
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

# 2. OUTPUT: DTO limpio
class ShotResponse(BaseModel):
    id: int
    game_id: str
    player_id: str
    action_type: str
    x: float
    y: float
    is_made: bool
    
    model_config = ConfigDict(from_attributes=True)