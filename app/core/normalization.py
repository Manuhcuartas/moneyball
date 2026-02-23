def normalize_team_name(raw_name: str) -> str:
    """Map federation team names to their canonical form."""
    if not raw_name:
        return "DESCONOCIDO"

    name = raw_name.upper().strip()

    TEAM_MAP = {
        "PUMARIN": "C.B. PUMARIN",
        "CIRCULO": "CIRCULO GIJÓN",
        "CÍRCULO": "CIRCULO GIJÓN",
        "AVILES SUR": "C.D.B. AVILES SUR",
        "ART-CHIVO": "CD ART-CHIVO",
        "OVIEDO BALONCESTO": "ALIMERKA OVIEDO",
        "OVIEDO C.B.": "ALIMERKA OVIEDO",
        "GRUPO DE CULTURA": "RGCC",
        "VILLA DE MIERES": "BVM 2012",
        "BVM 2012": "BVM 2012",
        "CENTRO ASTURIANO": "CENTRO ASTURIANO",
        "COSTA NORTE": "COSTA NORTE",
        "ARGAÑOSA": "C.B. LA ARGAÑOSA",
        "GIJON BASKET": "GIJON BASKET",
    }

    for pattern, canonical in TEAM_MAP.items():
        if pattern in name:
            return canonical

    return name