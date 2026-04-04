import os
import json
import logging
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("CardioAgent")

SCOPES = ['https://www.googleapis.com/auth/calendar']
TOKEN_PATH = 'token.json'

# Localização do consultório (centralizado)
CLINIC_LOCATION = "Avenida das Américas, 3500, Sala 701 – Barra da Tijuca, Rio de Janeiro, RJ"


class GoogleCalendarService:
    """
    Serviço singleton para operações no Google Calendar.
    Autentica via token.json (OAuth2) e auto-renova o access_token via refresh_token.
    """

    def __init__(self):
        self.creds: Credentials | None = None
        self._authenticate()

    def _authenticate(self):
        """Carrega e valida credenciais do token.json, renovando se necessário."""
        if not os.path.exists(TOKEN_PATH):
            logger.error(
                "Google Calendar: token.json não encontrado. "
                "Execute o script src/scripts/authorize_google.py para gerar o token."
            )
            return

        try:
            self.creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.error(f"Google Calendar: erro ao ler token.json — {e}")
            return

        # Token expirado mas com refresh_token → renova automaticamente
        if not self.creds.valid:
            if self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                    self._save_token()  # persiste o novo access_token
                    logger.info("Google Calendar: token renovado e salvo com sucesso.")
                except Exception as e:
                    logger.error(f"Google Calendar: falha ao renovar token — {e}")
                    self.creds = None
            else:
                logger.error(
                    "Google Calendar: token inválido e sem refresh_token. "
                    "Execute src/scripts/authorize_google.py novamente."
                )
                self.creds = None

    def _save_token(self):
        """Persiste as credenciais renovadas em disco."""
        try:
            with open(TOKEN_PATH, 'w', encoding='utf-8') as f:
                f.write(self.creds.to_json())
        except Exception as e:
            logger.warning(f"Google Calendar: não foi possível salvar token.json — {e}")

    def _get_service(self):
        """Retorna o serviço autenticado ou None se não autenticado."""
        if not self.creds:
            self._authenticate()

        if not self.creds or not self.creds.valid:
            logger.error("Google Calendar: serviço não autenticado. Operação ignorada.")
            return None

        return build('calendar', 'v3', credentials=self.creds, cache_discovery=False)

    # ─────────────────────────────────────────────────────────────
    # Operações Públicas
    # ─────────────────────────────────────────────────────────────

    def create_event(
        self,
        summary: str,
        description: str,
        start_time_iso: str,
        end_time_iso: str,
    ) -> str | None:
        """
        Cria um evento no calendário primário.

        Args:
            summary: Título do evento (ex: "Consulta: João Silva")
            description: Descrição com detalhes (convênio, etc.)
            start_time_iso: Início em ISO 8601 local (sem Z — Google interpreta como America/Sao_Paulo)
            end_time_iso: Fim em ISO 8601 local

        Returns:
            google_event_id (str) se sucesso, None se falha.
        """
        service = self._get_service()
        if not service:
            return None

        # Remove sufixo de timezone (Z ou +00:00) para que o Google Calendar
        # interprete o horário como horário local de Sao Paulo (America/Sao_Paulo)
        start_local = _strip_tz(start_time_iso)
        end_local = _strip_tz(end_time_iso)

        event_body = {
            'summary': summary,
            'location': CLINIC_LOCATION,
            'description': description,
            'start': {'dateTime': start_local, 'timeZone': 'America/Sao_Paulo'},
            'end': {'dateTime': end_local, 'timeZone': 'America/Sao_Paulo'},
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 dia antes
                    {'method': 'popup', 'minutes': 120},       # 2h antes
                ],
            },
        }

        try:
            event = service.events().insert(calendarId='primary', body=event_body).execute()
            event_id = event.get('id')
            logger.info(f"✅ Google Calendar: evento criado [{event_id}] — {summary}")
            return event_id
        except HttpError as e:
            logger.error(f"❌ Google Calendar: erro ao criar evento — HTTP {e.status_code}: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"❌ Google Calendar: erro inesperado ao criar evento — {e}")
            return None

    def update_event(
        self,
        event_id: str,
        summary: str = None,
        start_time_iso: str = None,
        end_time_iso: str = None,
        description: str = None,
    ) -> bool:
        """
        Atualiza campos de um evento existente.

        Returns:
            True se sucesso, False se falha.
        """
        service = self._get_service()
        if not service or not event_id:
            return False

        try:
            event = service.events().get(calendarId='primary', eventId=event_id).execute()

            if summary:
                event['summary'] = summary
            if description:
                event['description'] = description
            if start_time_iso:
                event['start']['dateTime'] = _strip_tz(start_time_iso)
                event['start']['timeZone'] = 'America/Sao_Paulo'
            if end_time_iso:
                event['end']['dateTime'] = _strip_tz(end_time_iso)
                event['end']['timeZone'] = 'America/Sao_Paulo'

            service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
            logger.info(f"✅ Google Calendar: evento atualizado [{event_id}]")
            return True
        except HttpError as e:
            if e.status_code == 404:
                logger.warning(f"Google Calendar: evento [{event_id}] não encontrado para atualizar.")
            else:
                logger.error(f"❌ Google Calendar: erro ao atualizar evento [{event_id}] — {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Google Calendar: erro inesperado ao atualizar [{event_id}] — {e}")
            return False

    def delete_event(self, event_id: str) -> bool:
        """
        Remove um evento do calendário.

        Returns:
            True se sucesso, False se falha.
        """
        service = self._get_service()
        if not service or not event_id:
            return False

        try:
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            logger.info(f"✅ Google Calendar: evento deletado [{event_id}]")
            return True
        except HttpError as e:
            if e.status_code == 404:
                logger.warning(f"Google Calendar: evento [{event_id}] já não existe (404). Ignorando.")
                return True  # Consideramos OK — já está fora da agenda
            logger.error(f"❌ Google Calendar: erro ao deletar evento [{event_id}] — {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Google Calendar: erro inesperado ao deletar [{event_id}] — {e}")
            return False


# ── Helpers ─────────────────────────────────────────────────────

def _strip_tz(dt_str: str) -> str:
    """
    Remove o sufixo de timezone (Z, +00:00, -03:00, etc.) do datetime.
    Isso permite que o Google Calendar interprete o horário como local
    de acordo com o campo timeZone ('America/Sao_Paulo').

    Exemplo: '2026-04-06T09:00:00Z' → '2026-04-06T09:00:00'
             '2026-04-06T09:00:00+00:00' → '2026-04-06T09:00:00'
    """
    if not dt_str:
        return dt_str
    # Remove microsegundos
    dt_str = dt_str.split(".")[0]
    # Remove Z final
    dt_str = dt_str.rstrip("Z")
    # Remove offset (+HH:MM ou -HH:MM)
    if len(dt_str) > 19 and dt_str[19] in ('+', '-'):
        dt_str = dt_str[:19]
    return dt_str


# ── Singleton ────────────────────────────────────────────────────
calendar_service = GoogleCalendarService()
