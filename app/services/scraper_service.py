import requests
import json
import time
import urllib3
from urllib.parse import urlencode
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
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # Limpieza de variables
        def clean(val):
            if not val: return ""
            return str(val).replace('"', '').replace("'", "").strip()

        self.base_url = clean(settings.FBPA_BASE_URL)
        self.id_dispositivo = clean(settings.FBPA_ID_DISPOSITIVO)
        self.id_fase = clean(settings.FBPA_ID_FASE)
        self.id_grupo = clean(settings.FBPA_ID_GRUPO)
        
        # Nuevas variables limpias
        self.login_url = clean(settings.FBPA_LOGIN_URL)
        self.device_uid = clean(settings.FBPA_DEVICE_UID)
        self.push_token = clean(settings.FBPA_PUSH_TOKEN)
        self.app_version = clean(settings.FBPA_APP_VERSION)
        
        self.key = "" 

        print(f"🔧 Configuración cargada: Fase='{self.id_fase}', Grupo='{self.id_grupo}'")

    def login(self):
        """
        Login usando credenciales desde variables de entorno.
        """
        payload = {
            "accion": "acceso",
            "uid": self.device_uid,          # <-- VARIABLE
            "plataforma": "ios",
            "tipo_dispositivo": "mobile",
            "id_dispositivo": self.id_dispositivo, 
            "token_push": self.push_token,   # <-- VARIABLE
            "version": self.app_version      # <-- VARIABLE
        }
        
        body_str = urlencode(payload)
        
        try:
            print("🔑 Autenticando en Gesdeportiva...")
            # Usamos la URL desde variable de entorno
            r = requests.post(self.login_url, data=body_str, headers=self.headers, verify=False, timeout=15)
            
            try:
                data = r.json()
            except:
                print(f"❌ Error Login: Respuesta no JSON (Status {r.status_code})")
                return False

            if data.get("resultado") == "correcto" and data.get("key"):
                self.key = data.get("key")
                print(f"✅ Login OK. Key recibida: {self.key[:10]}...")
                return True
            else:
                print(f"❌ Login denegado: {data.get('error')}")
                return False
                
        except Exception as e:
            print(f"⚠️ Excepción en Login: {e}")
            return False

    def get_calendar_from_team(self, id_equipo_hash):
        id_equipo_hash = str(id_equipo_hash).replace('"', '').replace("'", "").strip()
        url = f"{self.base_url}/equipo.ashx"        
        
        payload_dict = {
            "accion": "horariosJornadas", 
            "id_equipo": id_equipo_hash,
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo,
            "id_ronda": "",
            "fecha_inicial": "2025-09-01 00:00",
            "fecha_final": "2026-06-30 23:59"
        }
        
        payload_str = urlencode(payload_dict)
        
        try:
            print(f"🔄 Consultando calendario...")
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=15)
            
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=15)

            try:
                data = r.json()
            except:
                print(f"❌ Error Calendario: No JSON. Status: {r.status_code}")
                return []
            
            print(f"🔍 DEBUG API CALENDARIO:")
            print(f"   - IDs enviados: Fase='{self.id_fase[:5]}...', Grupo='{self.id_grupo[:5]}...', Equipo='{id_equipo_hash[:5]}...'")
            lista_raw = data.get("partidos", [])
            print(f"   - Partidos en bruto recibidos: {len(lista_raw)}")
            if len(lista_raw) > 0:
                print(f"   - Ejemplo estado partido 1: {lista_raw[0].get('Estado')} | Local: {lista_raw[0].get('Resultados', {}).get('ResultadoLocal')}")
            else:
                print(f"   - La API devolvió lista vacía. Revisa FASE y GRUPO.")
            
            if data.get("resultado") != "correcto":
                 # Reintento de login si la key caducó
                 if "key" in str(data.get("error", "")).lower():
                     print("   🔄 Key caducada, reintentando login...")
                     if self.login():
                         payload_dict["key"] = self.key
                         payload_str = urlencode(payload_dict)
                         return self.get_calendar_from_team(id_equipo_hash)
                 
                 print(f"❌ Error API Calendario: {data.get('error')}")
                 return []
            
            if data.get("key"): self.key = data.get("key")

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
        
        payload_dict = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_hash,
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo
        }
        payload_str = urlencode(payload_dict)

        try:
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=10)
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=10)

            data = r.json()

            if data.get("resultado") != "correcto":
                print(f"   ⚠️ API Error (Stats): {data.get('error')}")
                return False

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
            print(f"❌ Error guardando stats: {e}")
            return False
        
    def ingest_shot_chart(self, game_id: str):
        game_id = str(game_id).strip()
        url = f"{self.base_url}/envivo/mapa-de-tiro.ashx"
        
        payload_dict = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_id
        }
        payload_str = urlencode(payload_dict)

        try:
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=10)
            if r.status_code >= 400:
                 time.sleep(0.5)
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=10)

            try:
                data = r.json()
            except:
                print(f"   ⚠️ Error ShotChart: Respuesta no JSON")
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