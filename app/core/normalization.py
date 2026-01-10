# app/core/normalization.py

def normalize_team_name(raw_name: str) -> str:
    """
    Recibe el nombre sucio de la Federación y devuelve el Nombre Canónico.
    """
    if not raw_name:
        return "DESCONOCIDO"

    name = raw_name.upper().strip()

    # --- REGLAS DE MAPEO ---
    
    # 1. PUMARÍN
    if "PUMARIN" in name:
        return "C.B. PUMARIN"
    
    # 2. CIRCULO GIJÓN
    if "CIRCULO" in name or "CÍRCULO" in name:
        return "CIRCULO GIJÓN"
    
    # 3. AVILÉS SUR
    if "AVILES SUR" in name:
        return "C.D.B. AVILES SUR"
    
    # 4. ART-CHIVO
    if "ART-CHIVO" in name:
        return "CD ART-CHIVO"
    
    # 5. OVIEDO BALONCESTO (OCB)
    if "OVIEDO BALONCESTO" in name or "OVIEDO C.B." in name:
        return "ALIMERKA OVIEDO"
    
    # 6. GRUPO COVADONGA
    if "GRUPO DE CULTURA" in name:
        return "RGCC"
    
    # 7. VILLA DE MIERES (BVM2012)
    if "VILLA DE MIERES" in name or "BVM 2012" in name:
        return "BVM 2012"
    
    # 8. CENTRO ASTURIANO
    if "CENTRO ASTURIANO" in name:
        return "CENTRO ASTURIANO"
    
    # 9. COSTA NORTE
    if "COSTA NORTE" in name:
        return "COSTA NORTE"
    
    # 10. ARGAÑOSA
    if "ARGAÑOSA" in name:
        return "C.B. LA ARGAÑOSA"
    
    # 11. GIJON BASKET
    if "GIJON BASKET" in name:
        return "GIJON BASKET"

    # Si no coincide con nada, devolvemos el original limpio
    return name