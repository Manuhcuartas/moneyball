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

        self.base_url = clean(settings.FEDERATION_BASE_URL)
        self.id_dispositivo = clean(settings.FEDERATION_ID_DISPOSITIVO)
        self.id_fase = clean(settings.FEDERATION_ID_FASE)
        self.id_grupo = clean(settings.FEDERATION_ID_GRUPO)
        
        self.login_url = clean(settings.FEDERATION_LOGIN_URL)
        self.device_uid = clean(settings.FEDERATION_DEVICE_UID)
        self.push_token = clean(settings.FEDERATION_PUSH_TOKEN)
        self.app_version = clean(settings.FEDERATION_APP_VERSION)
        
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
    def _decode_hex_string(self, hex_str: str) -> str:
        """Decodes '78003800...' to 'x86Dad...' (UTF-16LE)"""
        if not hex_str: return ""
        try:
            return bytes.fromhex(hex_str).decode('utf-16-le')
        except:
            return ""

    def _get_or_create_team(self, raw_name: str, escudo_hex: str = None):
        from app.models.stats import Team
        from app.core.normalization import normalize_team_name

        clean_name = normalize_team_name(raw_name)
        team = self.db.query(Team).filter(Team.name == clean_name).first()

        if not team:
            team = Team(name=clean_name, logo_url=escudo_hex or None)
            self.db.add(team)
            self.db.commit()
            self.db.refresh(team)
        elif escudo_hex and team.logo_url != escudo_hex:
            team.logo_url = escudo_hex
            self.db.commit()
            self.db.refresh(team)

        return team


    def _get_or_create_player(self, raw_name: str, team_id: int, componente_id: str = None):
        from app.models.stats import Player
        
        clean_name = " ".join(raw_name.split()).title()
        
        # 1. Exact match by unique component ID (safest)
        if componente_id:
            player = self.db.query(Player).filter(Player.componente_id == componente_id).first()
            if player:
                return player

        # 2. Fallback to name match
        player = self.db.query(Player).filter(
            Player.name == clean_name, 
            Player.team_id == team_id
        ).first()
        
        if not player:
            player = Player(name=clean_name, team_id=team_id, componente_id=componente_id or None)
            self.db.add(player)
            self.db.commit()
            self.db.refresh(player)
        elif componente_id and player.componente_id != componente_id:
            player.componente_id = componente_id
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
                # Ahora aceptamos TODOS los partidos, no solo terminados
                # Extraemos nuevos campos
                partidos_validos.append({
                    "id": p.get("IdPartido"),
                    "local": p.get("NombreEquipoLocal"),
                    "visitante": p.get("NombreEquipoVisitante"),
                    "img_local": p.get("ImgEquipoLocal"),
                    "img_visitante": p.get("ImgEquipoVisitante"),
                    "fecha": p.get("Fecha"),
                    "jornada": p.get("NumeroJornada"),
                    "estado": p.get("Estado"), # Pass raw status
                    # New fields
                    "hora": p.get("Hora", "00:00"),
                    "campo": p.get("CampoJuego", ""),
                    "direccion": p.get("DireccionCampo", ""),
                    "video": p.get("UrlOTT", "")
                })
            
            logger.info(f"✅ Partidos listos: {len(partidos_validos)}")
            return partidos_validos

        except Exception as e:
            logger.error(f"❌ Error crítico en calendario: {e}")
            return []

    def should_scrape(self, game_id: str, source_status: str, force: bool = False) -> bool:
        """
        Determine whether a game needs to be scraped.
        Returns True if stats should be downloaded, False to skip.
        """
        if force:
            return source_status == "Terminado"

        game = self.db.query(Game).filter(Game.id == game_id).first()

        # New game — always scrape
        if not game:
            return True

        # Source says finished but DB doesn't — scrape
        if game.estado != "Terminado" and source_status == "Terminado":
            return True

        # Game is "Terminado" in DB but has incomplete data (no stats or 0-0 score)
        if game.estado == "Terminado":
            stat_count = self.db.query(PlayerStat).filter(PlayerStat.game_id == game_id).count()
            if stat_count == 0:
                logger.info(f"   🔄 Re-scraping: marked Terminado but has 0 stats")
                return True
            if game.puntos_local == 0 and game.puntos_visitante == 0:
                logger.info(f"   🔄 Re-scraping: marked Terminado but score is 0-0")
                return True

        return False


    def upsert_game_metadata(self, game_metadata):
        game_hash = game_metadata["id"]
        try:
            from app.models.stats import Game
            
            # 1. Resolve Teams with Logos
            home_team = self._get_or_create_team(
                game_metadata["local"], 
                game_metadata.get("img_local")
            )
            visitor_team = self._get_or_create_team(
                game_metadata["visitante"],
                game_metadata.get("img_visitante")
            )
            
            # Determine status from metadata or default
            raw_status = game_metadata.get("estado")
            status_to_save = raw_status if raw_status else "Pendiente"

            # 2. Update or Create Game
            existing = self.db.query(Game).filter(Game.id == game_hash).first()
            if existing: # Update
                existing.jornada = str(game_metadata.get("jornada"))
                existing.fecha = game_metadata.get("fecha")
                existing.time = game_metadata.get("hora")
                existing.venue = game_metadata.get("campo")
                existing.address = game_metadata.get("direccion")
                existing.video_url = game_metadata.get("video")
                
                # Update Teams (Fix for DESCONOCIDO)
                existing.home_team_id = home_team.id
                existing.visitor_team_id = visitor_team.id

                # Always update status if not finished
                if existing.estado != "Terminado":
                     existing.estado = status_to_save
            else: # Create
                new_game = Game(
                    id=game_hash,
                    jornada=str(game_metadata.get("jornada")),
                    fecha=game_metadata.get("fecha"),
                    home_team_id=home_team.id,
                    visitor_team_id=visitor_team.id,
                    puntos_local=0,
                    puntos_visitante=0,
                    estado=status_to_save, 
                    time=game_metadata.get("hora"),
                    venue=game_metadata.get("campo"),
                    address=game_metadata.get("direccion"),
                    video_url=game_metadata.get("video")
                )
                self.db.add(new_game)
                # We need to commit here to ensure game exists for FKs if we proceed
            self.db.commit() 
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error saving Game metadata {game_hash}: {e}")
            return False

    def fetch_game_stats(self, game_id: str):
        url = "https://appaficionfbpa.indalweb.net/v2/envivo/estadisticas.ashx"
        
        payload_dict = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_id,
            "id_fase": self.id_fase,
            "id_grupo": self.id_grupo
        }
        payload_str = urlencode(payload_dict)

        try:
            from app.models.stats import Game, PlayerStat

            # 1. Petición a la API
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=10)
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=10)

            data = r.json()

            if data.get("resultado") != "correcto":
                # Likely pending game or error
                logger.warning(f"   ⚠️ API (Stats) unavailable for {game_id}: {data.get('error')}. ")
                return False

            # If correct, update stats
            info = data["partido"]
            
            # Load Game to get Teams
            game = self.db.query(Game).filter(Game.id == game_id).first()
            if not game:
                logger.error(f"❌ Game {game_id} not found in DB during stats fetch")
                return False

            # Update scores if we have them
            try:
                game.puntos_local = int(info.get("tanteo_local", 0))
                game.puntos_visitante = int(info.get("tanteo_visitante", 0))
                game.estado = info.get("estado_partido", "Terminado")
            except: pass
            
            # Clear old stats
            self.db.query(PlayerStat).filter(PlayerStat.game_id == game_id).delete()
            
            stats_root = data["estadisticas"]
            
            # We need to associate players with teams
            # We assume "estadisticasequipolocal" corresponds to game.home_team_id
            # But wait, we need the Team OBJECTS or IDs
            
            team_mapping = [
                ("estadisticasequipolocal", game.home_team_id), 
                ("estadisticasequipovisitante", game.visitor_team_id)
            ]

            for key_lista, team_id in team_mapping:
                jugadores = stats_root.get(key_lista, [])

                for j in jugadores:
                    if j["nombre"] == "TOTALES": continue
                    
                    cid = j.get("componente_id") or None
                    player = self._get_or_create_player(j.get("nombre"), team_id, componente_id=cid)
                    
                    p_stat = PlayerStat(
                        game_id=game_id,
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

    def ingest_standings(self):
        """
        Descarga la clasificación actual y la guarda en BD.
        """
        url = f"{self.base_url}/equipo.ashx"
        
        # Usamos el payload descrito por el usuario
        payload_dict = {
            "accion": "clasificacion",
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_grupo": self.id_grupo,
            "tipo_fase": "LIGA" # Parametro hardcoded según request del usuario
        }
        
        # Opcional: Si la API requiere id_fase también, lo añadimos.
        # En el ejemplo del usuario no estaba, pero en otros calls sí. 
        # Lo dejaremos tal cual el ejemplo del usuario primero.
        
        payload_str = urlencode(payload_dict)

        try:
            logger.info("🏆 Consultando Clasificación...")
            r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=15)
            
            # Retry logic simple
            if r.status_code >= 400:
                 r = requests.get(url, params=payload_dict, headers=self.headers, verify=False, timeout=15)

            try:
                data = r.json()
            except:
                logger.error(f"❌ Error Clasificación: No JSON. Status {r.status_code}")
                return False

            if data.get("resultado") != "correcto":
                if "key" in str(data.get("error", "")).lower():
                     logger.info("   🔄 Key caducada en Clasificación, reintentando login...")
                     if self.login():
                         payload_dict["key"] = self.key
                         payload_str = urlencode(payload_dict)
                         # Recursive simple (cuidado con infinite loops, pero login maneja timeouts)
                         # Mejor hacemos una llamada directa
                         r = requests.post(url, data=payload_str, headers=self.headers, verify=False, timeout=15)
                         data = r.json()
                     else:
                         return False
                
                if data.get("resultado") != "correcto":
                    logger.error(f"❌ Error API Clasificación: {data.get('error')}")
                    return False

            # Procesar datos
            clasificacion = data.get("clasificacion", [])
            if not clasificacion:
                logger.warning("⚠️ Clasificación vacía recibida.")
                return True

            from app.models.stats import TeamStanding, Team
            
            # Limpiamos la clasificación actual para este grupo/temporada? 
            # O hacemos upsert? Upsert por Equipo es mejor.
            
            count = 0
            for item in clasificacion:
                team_name = item.get("NombreEquipo")
                escudo_hex = item.get("Escudo")
                team = self._get_or_create_team(team_name, escudo_hex)

                # Save federation hex ID for roster sync
                fed_hex = item.get("IdEquipo")
                if fed_hex and not team.federation_hex:
                    team.federation_hex = fed_hex
                
                # Buscamos si ya existe el standing para este equipo
                standing = self.db.query(TeamStanding).filter(TeamStanding.team_id == team.id).first()
                
                if not standing:
                    standing = TeamStanding(team_id=team.id)
                    self.db.add(standing)
                
                # Actualizamos campos
                standing.position = item.get("Posicion")
                standing.season = item.get("Temporada")
                standing.played = item.get("PartidosJugados")
                standing.won = item.get("PartidosGanados")
                standing.lost = item.get("PartidosPerdidos")
                standing.points = item.get("Puntos")
                standing.win_rate = item.get("CocienteVictorias")
                
                count += 1
            
            self.db.commit()
            logger.info(f"✅ Clasificación actualizada: {count} equipos.")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error crítico ingestando clasificación: {e}")
            return False

    def sync_roster(self, id_equipo_hash):
        """Fetch roster from federation and sync federation IDs, PPG, MPG."""
        id_equipo_hash = str(id_equipo_hash).replace('"', '').replace("'", "").strip()
        url = f"{self.base_url}/equipo.ashx"

        payload = {
            "accion": "jugadores",
            "id_equipo": id_equipo_hash,
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
        }

        try:
            logger.info("🔄 Sincronizando roster (federation IDs)...")
            r = requests.post(url, data=urlencode(payload), headers=self.headers, verify=False, timeout=15)
            data = r.json()

            if data.get("resultado") != "correcto":
                logger.error(f"❌ Error roster sync: {data.get('error')}")
                return False

            if data.get("key"):
                self.key = data["key"]

            jugadores = data.get("misjugadores", [])
            count = 0

            for j in jugadores:
                fed_name = j.get("Nombre", "")
                fed_id = j.get("Id", "")
                ppg = j.get("PuntosPorPartido", 0)
                mpg = j.get("MinutosPorPartido", 0)

                # Match by normalized name
                import unicodedata
                clean_name = " ".join(fed_name.split()).title()
                clean_name = ''.join(c for c in unicodedata.normalize('NFD', clean_name)
                                     if unicodedata.category(c) != 'Mn')

                player = self.db.query(Player).filter(Player.name == clean_name).first()
                if not player:
                    continue

                updated = False
                if fed_id and player.federation_id != fed_id:
                    player.federation_id = fed_id
                    updated = True
                if ppg and player.ppg != ppg:
                    player.ppg = ppg
                    updated = True
                if mpg and player.mpg != mpg:
                    player.mpg = mpg
                    updated = True

                if updated:
                    count += 1

            self.db.commit()
            logger.info(f"✅ Roster sincronizado: {count} jugadores actualizados, {len(jugadores)} en federation.")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error sincronizando roster: {e}")
            return False

    def sync_player_federation_stats(self, player_id: int) -> bool:
        """Fetch federation API for player season stats and save to DB."""
        from app.models.stats import PlayerSeasonStat
        
        player = self.db.query(Player).filter(Player.id == player_id).first()
        if not player or not player.federation_id:
            return False

        url = f"{self.base_url}/jugador.ashx"
        id_equipo_hash = player.team.federation_hex if player.team and player.team.federation_hex else str(settings.FEDERATION_ID_EQUIPO_PROPIO).replace('"', '').replace("'", "").strip()

        payload = {
            "accion": "datosGlobalesJugadorEquipo",
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_jugador": player.federation_id,
            "id_equipo": id_equipo_hash,
            "id_componente_club": player.componente_id or "",
            "id_temporada": "32005100440055006700580046004800690048006600680054006100410053002B0030004F005500730051003D003D00",
        }

        try:
            r = requests.post(url, data=urlencode(payload), headers=self.headers, verify=False, timeout=15)
            data = r.json()

            if data.get("resultado") != "correcto":
                logger.error(f"❌ Error syncing player stats: {data.get('error')}")
                return False

            if data.get("key"):
                self.key = data["key"]

            raw_stats = data

            stat = self.db.query(PlayerSeasonStat).filter(PlayerSeasonStat.player_id == player_id).first()
            if not stat:
                stat = PlayerSeasonStat(player_id=player_id)
                self.db.add(stat)

            stat.minutes_avg = float(raw_stats.get("minutosMediaJugador", 0) or 0)
            stat.points_avg = float(raw_stats.get("PuntosMediaJugador", 0) or 0)
            stat.valoracion_avg = float(raw_stats.get("ValoracionMediaJugador", 0) or 0)
            stat.mas_menos_avg = float(raw_stats.get("MasMenosMediaJugador", 0) or 0)
            stat.rebounds_avg = float(raw_stats.get("RebotesMediaJugador", 0) or 0)
            stat.assists_avg = float(raw_stats.get("AsistenciaMediaJugador", 0) or 0)
            stat.steals_avg = float(raw_stats.get("RecuperacionesMediaJugador", 0) or 0)
            stat.turnovers_avg = float(raw_stats.get("PerdidasMediaJugador", 0) or 0)
            stat.blocks_avg = float(raw_stats.get("TaponesCometidoMediaJugador", 0) or 0)
            stat.fouls_drawn_avg = float(raw_stats.get("FaltaRecibidaMediaJugador", 0) or 0)
            stat.fouls_committed_avg = float(raw_stats.get("FaltaCometidaMediaJugador", 0) or 0)

            stat.league_minutes_avg = float(raw_stats.get("minutosMedia", 0) or 0)
            stat.league_points_avg = float(raw_stats.get("PuntosMedia", 0) or 0)
            stat.league_valoracion_avg = float(raw_stats.get("ValoracionMedia", 0) or 0)
            stat.league_mas_menos_avg = float(raw_stats.get("MasMenosMedia", 0) or 0)
            stat.league_rebounds_avg = float(raw_stats.get("RebotesMedia", 0) or 0)
            stat.league_assists_avg = float(raw_stats.get("AsistenciaMedia", 0) or 0)
            stat.league_steals_avg = float(raw_stats.get("RecuperacionesMedia", 0) or 0)
            stat.league_turnovers_avg = float(raw_stats.get("PerdidasMedia", 0) or 0)
            stat.league_blocks_avg = float(raw_stats.get("TaponesCometidoMedia", 0) or 0)
            stat.league_fouls_drawn_avg = float(raw_stats.get("FaltaRecibidaMedia", 0) or 0)
            stat.league_fouls_committed_avg = float(raw_stats.get("FaltaCometidaMedia", 0) or 0)

            stat.ft_pct = float(raw_stats.get("PorcentajeTirosLibresJugador", 0) or 0)
            stat.fg_pct = float(raw_stats.get("PorcentajeTirosCampoJugador", 0) or 0)
            stat.two_pct = float(raw_stats.get("PorcentajeTirosDe2Jugador", 0) or 0)
            stat.three_pct = float(raw_stats.get("PorcentajeTriplesJugador", 0) or 0)

            stat.league_ft_pct = float(raw_stats.get("PorcentajeTirosLibres", 0) or 0)
            stat.league_fg_pct = float(raw_stats.get("PorcentajeTirosCampo", 0) or 0)
            stat.league_two_pct = float(raw_stats.get("PorcentajeTirosDe2", 0) or 0)
            stat.league_three_pct = float(raw_stats.get("PorcentajeTriples", 0) or 0)

            points_avg = float(raw_stats.get("PuntosMediaJugador", 1) or 1)
            points_avg = max(points_avg, 0.1)
            stat.games_played = int(float(raw_stats.get("minutosMediaJugador", 0) or 0) > 0 and float(raw_stats.get("PuntosTotalesJugador", 0) or 0) / points_avg)
            
            stat.total_points = int(float(raw_stats.get("PuntosTotalesJugador", 0) or 0))
            stat.total_minutes = str(raw_stats.get("MinutosTotalesJugador", "00:00"))
            stat.total_valoracion = int(float(raw_stats.get("ValoracionTotalJugador", 0) or 0))
            stat.total_rebounds = int(float(raw_stats.get("RebotesTotalesJugador", 0) or 0))
            stat.total_assists = int(float(raw_stats.get("AsistenciasTotalesJugador", 0) or 0))
            stat.total_steals = int(float(raw_stats.get("RecuperacionesTotalesJugador", 0) or 0))
            stat.total_turnovers = int(float(raw_stats.get("PerdidasTotalesJugador", 0) or 0))
            stat.total_blocks = int(float(raw_stats.get("TaponesCometidosTotalesJugador", 0) or 0))

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"❌ Error syncing federation player stats: {e}")
            return False

    def ingest_game_video(self, game_id: str):
        """Fetch and store YouTube video URL for a game."""
        url = f"{self.base_url}/envivo/videos.ashx"

        payload = {
            "id_dispositivo": self.id_dispositivo,
            "key": self.key,
            "id_partido": game_id,
        }

        try:
            r = requests.post(url, data=urlencode(payload), headers=self.headers, verify=False, timeout=15)
            data = r.json()

            if data.get("resultado") != "correcto":
                return False

            if data.get("key"):
                self.key = data["key"]

            videos = data.get("videos", [])
            if videos and len(videos) > 0:
                video_url = videos[0].get("url", "")
                if video_url:
                    game = self.db.query(Game).filter(Game.id == game_id).first()
                    if game and game.video_url != video_url:
                        game.video_url = video_url
                        self.db.commit()
                        return True

            return False

        except Exception as e:
            logger.error(f"❌ Error fetching game video: {e}")
            return False

