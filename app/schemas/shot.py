from pydantic import BaseModel, ConfigDict, field_validator
from typing import Any


class ShotIngest(BaseModel):
    """Input schema for ingesting shot data from the federation API."""
    equipo_id: int
    componente_id: str
    dorsal: str
    numero_periodo: int
    accion_tipo: str
    zona: str
    metido: int
    fallado: int
    posicion_x: float
    posicion_y: float

    @field_validator("posicion_x", "posicion_y", mode="before")
    @classmethod
    def clean_percentage(cls, v: Any) -> float:
        """Strip trailing '%' from coordinate strings before parsing as float."""
        if isinstance(v, str):
            v = v.replace("%", "").strip()
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0


class ShotResponse(BaseModel):
    """Output schema for shot chart visualization."""
    id: int
    game_id: str
    player_id: str
    action_type: str
    x: float
    y: float
    is_made: bool

    model_config = ConfigDict(from_attributes=True)