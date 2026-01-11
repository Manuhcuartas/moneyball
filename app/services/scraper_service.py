import requests
import json
import time
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
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        # Clave inicial
        self.key = "MUTC0u_ZKdBCdgfYN8bHO29S5MUjmgVSinRpzVPOCzpgPzPZLR1U2jafvsOMJQnLjEQ2YRD7JOuqRwe79ySg0snIsF7vPDRkqMpG8ZIhzfcoICBJwZSRFCt8RdfxF21UvisZAlYBG-uHmrRQQb5uIt8kMG0Gg6n7lin4D9i_1OYA-3nPZGRmVdX5tW81p_-f"
        
        # --- LIMPIEZA DE VARIABLES (CRÍTICO PARA GITHUB ACTIONS) ---
        # Eliminamos comillas dobles, simples y espacios que se cuelan en los Secretos
        def clean(val):
            if not val: return ""
            return str(val).replace('"', '').replace("'", "").strip()

        self.base_url = clean(settings.FBPA_BASE_URL)
        self.id_dispositivo = clean(settings.FBPA_ID_DISPOSITIVO)
        self.id_fase = clean(settings.FBPA_ID_FASE)
        self.id_grupo = clean(settings.FBPA_ID_GRUPO)
        
        # Imprimimos traza de seguridad (parcial)
        print(f"🔧 Configuración cargada: Fase='{self.id_fase}', Grupo='{self.id_grupo}'")

    def get_calendar_from_team(self, id_equipo_hash):
        # Limpieza extra del ID del equipo
        id_equipo_hash = id_equipo_hash.replace('"', '').replace("'", "").strip()
        
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
            print(f"🔄 Consultando calendario para equipo {id_equipo_hash[:5]}...")
            # Probamos POST, si falla, GET (algunas versiones de la API cambian)
            r = requests.post(url, data=payload, headers=self.headers, verify=False)
            
            # Si el servidor dice Method Not Allowed o Not Found, probamos GET
            if r.status_code >= 400:
                 r = requests.get(url, params=payload, headers=self.headers, verify=False)

            data = r.json()
            
            if data.get("resultado") != "correcto":
                 # Imprimir error completo para depurar
                 print(f"❌ Error API Calendario: {data.get('error')} | Respuesta: {data}")
                 return []
            
            # Actualización de Key dinámica
            nueva_key = data.get("key")
            if nueva_key:
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
            print(f"❌ Error crítico en calendario: {e}")
            return []

    def ingest_game_statistics(self, game_metadata):
        game_hash = game_metadata["id"]
        url = "https://appaficionfbpa.indalweb.net/v2/envivo/estadisticas.ashx"
        
        payload = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_hash,
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo
        }

        try:
            r = requests.post(url, data=payload, headers=self.headers, verify=False, timeout=10)
            if r.status_code == 405:
                 r = requests.get(url, params=payload, headers=self.headers, verify=False, timeout=10)

            data = r.json()

            if data.get("resultado") != "correcto":
                print(f"   ⚠️ API Error (Stats): {data.get('error')}")
                return False

            # --- Lógica BD ---
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
        # Limpieza preventiva del ID
        game_id = str(game_id).strip()
        
        url = f"{self.base_url}/envivo/mapa-de-tiro.ashx"
        payload = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_id
        }

        try:
            # Plan A: POST
            r = requests.post(url, data=payload, headers=self.headers, verify=False, timeout=10)
            
            # Plan B: GET (Si POST falla)
            if r.status_code >= 400:
                 time.sleep(0.5) 
                 r = requests.get(url, params=payload, headers=self.headers, verify=False, timeout=10)

            try:
                data = r.json()
            except json.JSONDecodeError:
                print(f"   ⚠️ Error ShotChart: Respuesta no JSON (Status {r.status_code})")
                return False

            if data.get("resultado") != "correcto":
                print(f"   ⚠️ Error API ShotChart: {data.get('error')}")
                return False

            shots_raw = data.get("mapadetiro", {}).get("tiros", [])
            
            from app.models.shot import Shot
            self.db.query(Shot).filter(Shot.game_id == game_id).delete()
            self.db.commit()
            
            if not shots_raw:
                return True 

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
                    posicion_x=s["posicion_x"],
                    posicion_y=s["posicion_y"]
                ))

            shot_repo = ShotRepository(self.db)
            count = shot_repo.create_batch(game_id, shots_to_ingest)
            if count > 0:
                print(f"   🎯 {count} tiros guardados.")
            return True

        except Exception as e:
            self.db.rollback() 
            print(f"❌ Excepción en ShotChart: {e}")
            return False