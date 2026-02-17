import requests
import json
import time
import urllib3
import logging
from urllib.parse import urlencode
from sqlalchemy.orm import Session, joinedload
from app.core.config import settings
from app.repositories.shot_repository import ShotRepository
from app.schemas.shot import ShotIngest
from app.models.stats import Game, PlayerStat, Player, GameFlow # Asegúrate de importar GameFlow

# Desactivar advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ScraperService:
    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        def clean(val):
            if not val: return ""
            return str(val).replace('"', '').replace("'", "").strip()

        self.base_url = clean(settings.FBPA_BASE_URL)
        self.id_dispositivo = clean(settings.FBPA_ID_DISPOSITIVO)
        self.id_fase = clean(settings.FBPA_ID_FASE)
        self.id_grupo = clean(settings.FBPA_ID_GRUPO)
        
        self.login_url = clean(settings.FBPA_LOGIN_URL)
        self.device_uid = clean(settings.FBPA_DEVICE_UID)
        self.push_token = clean(settings.FBPA_PUSH_TOKEN)
        self.app_version = clean(settings.FBPA_APP_VERSION)
        
        self.key = "" 
        logger.info(f"🔧 Configuración cargada: Fase='{self.id_fase}', Grupo='{self.id_grupo}'")

    def ingest_play_by_play(self, game_id: str):
        game_id = str(game_id).strip()
        url = "https://appaficionfbpa.indalweb.net/v2/envivo/partido.ashx"
        
        payload = {
            "key": self.key,
            "id_partido": game_id,
            "id_dispositivo": self.id_dispositivo
        }
        
        try:
            r = requests.post(url, data=urlencode(payload), headers=self.headers, verify=False, timeout=15)
            data = r.json()
            
            # --- 1. Obtener datos del partido de la BD para saber los IDs internos ---
            game = self.db.query(Game).filter(Game.id == game_id).first()
            if not game:
                logger.error(f"❌ Partido {game_id} no encontrado en BD local.")
                return False

            # --- 2. Crear Mapa de Traducción (ID Interno -> ID API) ---
            # Leemos los IDs oficiales del JSON
            api_home_id = str(data["partido"].get("idlocal"))
            api_visitor_id = str(data["partido"].get("idvisitante"))
            
            # Creamos el diccionario traductor
            # Ejemplo: { "1": "855360", "2": "855739" }
            id_map = {
                str(game.home_team_id): api_home_id,
                str(game.visitor_team_id): api_visitor_id
            }
            
            # --- 3. Preparar Mapa de Stats de la API ---
            envivo = data.get("envivo", {})
            players_data = envivo.get("jugadoresenpistalocal", []) + envivo.get("jugadoresenpistavisitante", [])
            
            if not players_data:
                logger.warning(f"⚠️ API devuelve lista de jugadores vacía para partido {game_id}")
                return False

            # Mapa: "ID_FEDERACION_DORSAL" -> Valor +/-
            pm_map = {}
            for p in players_data:
                tid = str(p.get("idequipo"))
                dorsal = str(p.get("dorsal"))
                pm = p.get("masMenos")
                if pm is not None:
                    pm_map[f"{tid}_{dorsal}"] = int(pm)

            # --- 4. Actualizar Base de Datos ---
            stats = (
                self.db.query(PlayerStat)
                .options(joinedload(PlayerStat.player)) # Cargar relación para leer team_id
                .filter(PlayerStat.game_id == game_id)
                .all()
            )
            
            count_updates = 0
            
            for s in stats:
                if not s.player: continue
                
                # A. Obtenemos ID interno del equipo (ej: 1)
                internal_tid = str(s.player.team_id)
                
                # B. Lo traducimos al ID de federación (ej: 1 -> 855360)
                external_tid = id_map.get(internal_tid)
                
                if not external_tid:
                    continue # Seguridad por si hay datos inconsistentes

                # C. Generamos la clave correcta para buscar en el mapa de la API
                key = f"{external_tid}_{s.dorsal}"
                
                if key in pm_map:
                    s.mas_menos = pm_map[key]
                    count_updates += 1
            
            self.db.commit()
            logger.info(f"   📊 +/- Actualizado: {count_updates} jugadores (Traducción: {id_map})")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error procesando Envivo {game_id}: {e}")
            return False

    # --- MÉTODOS PRIVADOS PARA GESTIÓN DE ENTIDADES ---
    def _get_or_create_team(self, raw_name: str):
        from app.models.stats import Team
        from app.core.normalization import normalize_team_name
        
        clean_name = normalize_team_name(raw_name)
        
        team = self.db.query(Team).filter(Team.name == clean_name).first()
        if not team:
            team = Team(name=clean_name)
            self.db.add(team)
            self.db.commit()
            self.db.refresh(team)
        return team

    def _get_or_create_player(self, raw_name: str, team_id: int):
        from app.models.stats import Player
        
        clean_name = " ".join(raw_name.split()).title()
        
        player = self.db.query(Player).filter(
            Player.name == clean_name, 
            Player.team_id == team_id
        ).first()
        
        if not player:
            player = Player(name=clean_name, team_id=team_id)
            self.db.add(player)
            self.db.commit()
            self.db.refresh(player)
        return player

    def login(self):
        payload = {
            "accion": "acceso",
            "uid": self.device_uid,
            "plataforma": "ios",
            "tipo_dispositivo": "mobile",
            "id_dispositivo": self.id_dispositivo, 
            "token_push": self.push_token,
            "version": self.app_version
        }
        body_str = urlencode(payload)
        
        try:
            logger.info("🔑 Autenticando en Gesdeportiva...")
            r = requests.post(self.login_url, data=body_str, headers=self.headers, verify=False, timeout=15)
            try:
                data = r.json()
            except:
                logger.error(f"❌ Error Login: Respuesta no JSON (Status {r.status_code})")
                return False

            if data.get("resultado") == "correcto" and data.get("key"):
                self.key = data.get("key")
                logger.info(f"✅ Login OK. Key recibida: {self.key[:10]}...")
                return True
            else:
                logger.error(f"❌ Login denegado: {data.get('error')}")
                return False
        except Exception as e:
            logger.error(f"⚠️ Excepción en Login: {e}")
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
            logger.info(f"🔄 Consultando calendario...")
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=15)
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=15)

            try:
                data = r.json()
            except:
                logger.error(f"❌ Error Calendario: No JSON. Status: {r.status_code}")
                return []
            
            if data.get("resultado") != "correcto":
                 if "key" in str(data.get("error", "")).lower():
                     logger.info("   🔄 Key caducada, reintentando login...")
                     if self.login():
                         payload_dict["key"] = self.key
                         payload_str = urlencode(payload_dict)
                         return self.get_calendar_from_team(id_equipo_hash)
                 logger.error(f"❌ Error API Calendario: {data.get('error')}")
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
            
            logger.info(f"✅ Partidos listos: {len(partidos_validos)}")
            return partidos_validos

        except Exception as e:
            logger.error(f"❌ Error crítico en calendario: {e}")
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
            # 1. Petición a la API (ESTO ES LO QUE FALTABA)
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=10)
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=10)

            data = r.json()

            if data.get("resultado") != "correcto":
                logger.warning(f"   ⚠️ API Error (Stats): {data.get('error')}")
                return False

            # 2. Gestión Relacional
            from app.models.stats import Game, PlayerStat
            
            info = data["partido"]
            home_team = self._get_or_create_team(info["local"])
            visitor_team = self._get_or_create_team(info["visitante"])

            existing = self.db.query(Game).filter(Game.id == game_hash).first()
            if existing:
                self.db.delete(existing)
                self.db.commit()

            try:
                pl = int(info.get("tanteo_local", 0))
                pv = int(info.get("tanteo_visitante", 0))
            except: pl, pv = 0, 0

            new_game = Game(
                id=game_hash,
                jornada=str(game_metadata["jornada"]),
                fecha=game_metadata["fecha"],
                home_team_id=home_team.id,
                visitor_team_id=visitor_team.id,
                puntos_local=pl,
                puntos_visitante=pv,
                estado=info["estado_partido"]
            )
            self.db.add(new_game)
            
            stats_root = data["estadisticas"]
            
            team_mapping = [
                ("estadisticasequipolocal", home_team), 
                ("estadisticasequipovisitante", visitor_team)
            ]

            for key_lista, current_team in team_mapping:
                jugadores = stats_root.get(key_lista, [])

                for j in jugadores:
                    if j["nombre"] == "TOTALES": continue
                    
                    player = self._get_or_create_player(j.get("nombre"), current_team.id)
                    
                    p_stat = PlayerStat(
                        game_id=game_hash,
                        player_id=player.id,
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
            logger.error(f"❌ Error guardando stats: {e}")
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
                logger.warning(f"   ⚠️ Error ShotChart: Respuesta no JSON")
                return False

            if data.get("resultado") != "correcto":
                logger.warning(f"   ⚠️ Error API ShotChart: {data.get('error')}")
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
            logger.error(f"❌ Excepción en ShotChart: {e}")
            return False