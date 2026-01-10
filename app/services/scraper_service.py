import requests
import json
import time
import random
import urllib3
from sqlalchemy.orm import Session
from app.models.stats import Game, PlayerStat
from app.core.config import settings
from app.repositories.shot_repository import ShotRepository
from app.schemas.shot import ShotIngest

# Desactivar advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ScraperService:
    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        # Clave inicial (se actualizará sola)
        self.key = "MUTC0u_ZKdBCdgfYN8bHO29S5MUjmgVSinRpzVPOCzpgPzPZLR1U2jafvsOMJQnLjEQ2YRD7JOuqRwe79ySg0snIsF7vPDRkqMpG8ZIhzfcoICBJwZSRFCt8RdfxF21UvisZAlYBG-uHmrRQQb5uIt8kMG0Gg6n7lin4D9i_1OYA-3nPZGRmVdX5tW81p_-f"
        self.base_url = settings.FBPA_BASE_URL
        self.id_dispositivo = settings.FBPA_ID_DISPOSITIVO
        self.id_fase = settings.FBPA_ID_FASE
        self.id_grupo = settings.FBPA_ID_GRUPO

    def get_calendar_from_team(self, id_equipo_hash):
        url = f"{self.base_url}/equipo.ashx"        
        payload = {
            "accion": "horariosJornadas", 
            "id_equipo": id_equipo_hash,
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo,
            "fecha_inicial": "2025-09-01 00:00",
            "fecha_final": "2026-06-30 23:59"
        }
        
        try:
            print(f"🔄 Consultando calendario...")
            r = requests.post(url, data=payload, headers=self.headers, verify=False)
            data = r.json()
            
            if data.get("resultado") != "correcto":
                 print(f"❌ Error API Calendario: {data.get('error')}")
                 return []
            
            # --- TRUCO: ACTUALIZAR LA CLAVE DINÁMICAMENTE ---
            nueva_key = data.get("key")
            if nueva_key:
                print(f"🔑 Clave API actualizada automáticamente.")
                self.key = nueva_key

            lista_raw = data.get("partidos", [])
            partidos_validos = []
            
            for p in lista_raw:
                estado = p.get("Estado", "")
                res = p.get("Resultados", {})
                pts_local = str(res.get("ResultadoLocal", ""))
                
                if estado == "Terminado" and pts_local and pts_local != "-" and pts_local != "0":
                    partidos_validos.append({
                        "id": p.get("IdPartido"),
                        "local": p.get("NombreEquipoLocal"),
                        "visitante": p.get("NombreEquipoVisitante"),
                        "fecha": p.get("Fecha"),
                        "jornada": p.get("NumeroJornada")
                    })
            
            print(f"✅ Partidos listos: {len(partidos_validos)}")
            return partidos_validos

        except Exception as e:
            print(f"❌ Error en calendario: {e}")
            return []

    def ingest_game_statistics(self, game_metadata):
        game_hash = game_metadata["id"]
        url = "https://appaficionfbpa.indalweb.net/v2/envivo/estadisticas.ashx"
        
        # CAMBIO CLAVE: Usamos POST en lugar de GET
        payload = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key, # Usamos la key actualizada
            "id_partido": game_hash,
            # Enviamos contexto por si acaso, aunque en el ejemplo original no estaba,
            # pero en POST no hace daño.
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo
        }

        try:
            # Petición POST
            r = requests.post(url, data=payload, headers=self.headers, verify=False, timeout=10)
            
            # Si POST falla con 405 Method Not Allowed, intentamos GET con la nueva key
            if r.status_code == 405:
                 r = requests.get(url, params=payload, headers=self.headers, verify=False, timeout=10)

            data = r.json()

            if data.get("resultado") != "correcto":
                print(f"   ⚠️ API Error (Stats): {data.get('error')}")
                return False

            # --- Lógica BD (Idéntica a antes) ---
            existing = self.db.query(Game).filter(Game.id == game_hash).first()
            if existing:
                self.db.delete(existing)
                self.db.commit()

            info = data["partido"]
            try:
                pl = int(info.get("tanteo_local", 0))
                pv = int(info.get("tanteo_visitante", 0))
            except:
                pl, pv = 0, 0

            new_game = Game(
                id=game_hash,
                jornada=str(game_metadata["jornada"]),
                fecha=game_metadata["fecha"],
                equipo_local=info["local"],
                equipo_visitante=info["visitante"],
                puntos_local=pl,
                puntos_visitante=pv,
                estado=info["estado_partido"]
            )
            self.db.add(new_game)
            
            stats_root = data["estadisticas"]
            
            for key_lista, key_nombre in [("estadisticasequipolocal", "equipolocal"), ("estadisticasequipovisitante", "equipovisitante")]:
                nombre_equipo = stats_root.get(key_nombre)
                jugadores = stats_root.get(key_lista, [])

                for j in jugadores:
                    if j["nombre"] == "TOTALES": continue
                    
                    p_stat = PlayerStat(
                        game_id=game_hash,
                        equipo=nombre_equipo,
                        nombre=j.get("nombre"),
                        dorsal=j.get("dorsal"),
                        es_titular=j.get("quintetotitular", False),
                        minutos=j.get("tiempo_jugado", "00:00"),
                        puntos=j.get("puntos", 0),
                        valoracion=j.get("valoracion", 0),
                        mas_menos=j.get("masMenos", 0),
                        rebotes_total=j.get("rebotes", 0),
                        rebotes_def=j.get("rebotedefensivo", 0),
                        rebotes_of=j.get("reboteofensivo", 0),
                        asistencias=j.get("asistencias", 0),
                        perdidas=j.get("perdidas", 0),
                        recuperaciones=j.get("recuperaciones", 0),
                        t1_anotados=j.get("canasta1p", 0),
                        t1_intentados=j.get("tiro1p", 0),
                        t2_anotados=j.get("canasta2p", 0),
                        t2_intentados=j.get("tiro2p", 0),
                        t3_anotados=j.get("canasta3p", 0),
                        t3_intentados=j.get("tiro3p", 0),
                        faltas_cometidas=j.get("faltascometidas", 0),
                        faltas_recibidas=j.get("faltasrecibidas", 0)
                    )
                    self.db.add(p_stat)
            
            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            print(f"❌ Error guardando: {e}")
            return False
        
    def ingest_shot_chart(self, game_id: str):
        """
        Extrae y guarda todos los eventos de tiro (coordenadas) de un partido.
        """
        url = f"{self.base_url}/envivo/mapa-de-tiro.ashx"
        payload = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_id
        }

        try:
            r = requests.post(url, data=payload, headers=self.headers, verify=False, timeout=10)
            data = r.json()

            if data.get("resultado") != "correcto":
                print(f"   ⚠️ Error ShotChart: {data.get('error')}")
                return False

            shots_raw = data.get("mapadetiro", {}).get("tiros", [])
            if not shots_raw:
                return True # No hay tiros registrados todavía

            # Preparamos los datos para el repositorio
            shots_to_ingest = []
            for s in shots_raw:
                shots_to_ingest.append(ShotIngest(
                    equipo_id=s["equipo_id"],
                    componente_id=s["componente_id"],
                    dorsal=s["dorsal"],
                    numero_periodo=s["numero_periodo"],
                    accion_tipo=s["accion_tipo"],
                    zona=s["zona"],
                    metido=s["metido"],
                    fallado=s["fallado"],
                    posicion_x=s["posicion_x"], # El validador de tu Schema limpiará el "%"
                    posicion_y=s["posicion_y"]
                ))

            # Guardamos en bloque usando el repositorio que ya tienes
            shot_repo = ShotRepository(self.db)
            count = shot_repo.create_batch(game_id, shots_to_ingest)
            print(f"   🎯 {count} eventos de tiro procesados.")
            return True

        except Exception as e:
            print(f"❌ Error en ingesta de tiros: {e}")
            return False