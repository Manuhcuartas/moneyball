import pandas as pd
from app.core.database import SessionLocal
from app.services.analytics import get_advanced_stats

def main():
    print("📊 Generando informe de laboratorio Moneyball...")
    db = SessionLocal()
    
    # Obtenemos TODOS los datos sin filtrar casi nada
    df = get_advanced_stats(db, min_games=1, min_minutes=5)
    
    if df.empty:
        print("❌ No hay datos suficientes en la base de datos.")
        return

    # Nombre del archivo
    filename = "moneyball_lab_data.xlsx"
    
    # Exportamos a Excel
    # Necesitas instalar openpyxl: pip install openpyxl
    try:
        df.to_excel(filename, index=False)
        print(f"✅ Datos exportados a: {filename}")
        print("   -> Abre este archivo para analizar percentiles y ajustar umbrales.")
    except ImportError:
        print("❌ Error: Necesitas instalar openpyxl (`pip install openpyxl`)")
        # Fallback a CSV
        df.to_csv("moneyball_lab_data.csv", index=False)
        print("✅ Datos exportados a CSV en su lugar.")

    db.close()

if __name__ == "__main__":
    main()