"""
calendar_sync.py
────────────────
Handler do Webhook do Supabase para sincronização automática com Google Calendar.

Fluxo:
  Supabase (INSERT/UPDATE/DELETE em `appointments`)
    → POST /webhook/supabase
      → calendar_sync.handle_supabase_event()
        → GoogleCalendarService (create / update / delete)

Este módulo é o único ponto de contato entre o banco de dados e o Google Calendar.
O restante do bot (handlers, db_service) não precisa saber da existência do Google.
"""

import logging
from src.services.google_calendar import calendar_service
from src.database.client import db_service

logger = logging.getLogger("CardioAgent")


def _build_event_summary(patient_name: str) -> str:
    return f"Consulta: {patient_name}"


def _build_event_description(record: dict) -> str:
    insurance = record.get("insurance", "Não informado")
    return (
        f"📋 Convênio: {insurance}\n"
        f"📱 Agendado via Bot WhatsApp."
    )


async def _fetch_patient_info(patient_id: str) -> dict:
    """Busca nome e convênio do paciente para montar o evento."""
    try:
        res = db_service.client.table("patients").select("name, insurance").eq("id", patient_id).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        logger.warning(f"CalendarSync: não foi possível buscar dados do paciente {patient_id} — {e}")
    return {"name": "Paciente", "insurance": "Não informado"}


async def handle_supabase_event(payload: dict) -> dict:
    """
    Processa eventos do Supabase Webhook e sincroniza com o Google Calendar.

    Payload esperado (formato padrão do Supabase Webhook):
    {
        "type": "INSERT" | "UPDATE" | "DELETE",
        "table": "appointments",
        "record": { ...campos do registro novo/atualizado... },
        "old_record": { ...campos do registro antes da mudança (só em UPDATE/DELETE)... }
    }

    Returns:
        dict com resultado da operação.
    """
    event_type = payload.get("type", "").upper()
    table = payload.get("table", "")
    record = payload.get("record") or {}
    old_record = payload.get("old_record") or {}

    logger.info(f"CalendarSync: evento recebido — type={event_type}, table={table}")

    if table != "appointments":
        logger.debug(f"CalendarSync: tabela '{table}' ignorada.")
        return {"status": "ignored", "reason": "tabela não monitorada"}

    # ────────────────────────────────────────────────────
    # INSERT → Nova consulta agendada → Criar evento
    # ────────────────────────────────────────────────────
    if event_type == "INSERT":
        patient_id = record.get("patient_id")
        start_time = record.get("start_time")
        end_time = record.get("end_time")
        appointment_id = record.get("id")
        status = record.get("status", "")

        # Só cria evento para consultas agendadas
        if status != "scheduled":
            return {"status": "ignored", "reason": f"status '{status}' não requer evento no Google"}

        if not all([patient_id, start_time, end_time, appointment_id]):
            logger.warning("CalendarSync: INSERT com dados incompletos. Ignorando.")
            return {"status": "ignored", "reason": "dados incompletos"}

        # Busca dados do paciente
        patient_info = await _fetch_patient_info(patient_id)
        summary = _build_event_summary(patient_info.get("name", "Paciente"))
        description = _build_event_description(patient_info)

        # Normaliza formato ISO para o Google Calendar
        start_iso = _normalize_iso(start_time)
        end_iso = _normalize_iso(end_time)

        # Cria evento no Google Calendar
        g_event_id = calendar_service.create_event(summary, description, start_iso, end_iso)

        if g_event_id:
            # Persiste o google_event_id no Supabase para sincronizações futuras
            try:
                db_service.client.table("appointments").update(
                    {"google_event_id": g_event_id}
                ).eq("id", appointment_id).execute()
                logger.info(f"CalendarSync: google_event_id [{g_event_id}] salvo no appointment [{appointment_id}]")
            except Exception as e:
                logger.error(f"CalendarSync: falha ao salvar google_event_id no Supabase — {e}")

            return {"status": "created", "google_event_id": g_event_id}
        else:
            return {"status": "error", "reason": "falha ao criar evento no Google Calendar"}

    # ────────────────────────────────────────────────────
    # UPDATE → Status mudou (ex: cancelled) → Deletar/atualizar evento
    # ────────────────────────────────────────────────────
    elif event_type == "UPDATE":
        new_status = record.get("status")
        old_status = old_record.get("status")
        g_event_id = record.get("google_event_id") or old_record.get("google_event_id")

        # Consulta foi cancelada
        if new_status in ("cancelled", "no_show") and old_status == "scheduled":
            if g_event_id:
                deleted = calendar_service.delete_event(g_event_id)
                return {"status": "deleted" if deleted else "error", "google_event_id": g_event_id}
            return {"status": "ignored", "reason": "sem google_event_id"}

        # Consulta foi reagendada (mudou start_time)
        old_start = old_record.get("start_time")
        new_start = record.get("start_time")
        old_end = old_record.get("end_time")
        new_end = record.get("end_time")

        if new_status == "scheduled" and g_event_id and (new_start != old_start or new_end != old_end):
            updated = calendar_service.update_event(
                g_event_id,
                start_time_iso=_normalize_iso(new_start) if new_start else None,
                end_time_iso=_normalize_iso(new_end) if new_end else None,
            )
            return {"status": "updated" if updated else "error", "google_event_id": g_event_id}

        return {"status": "ignored", "reason": "nenhuma mudança relevante detectada"}

    # ────────────────────────────────────────────────────
    # DELETE → Registro deletado fisicamente → Deletar evento
    # ────────────────────────────────────────────────────
    elif event_type == "DELETE":
        g_event_id = old_record.get("google_event_id")

        if not g_event_id:
            logger.info("CalendarSync: DELETE sem google_event_id — nada a fazer no Google.")
            return {"status": "ignored", "reason": "sem google_event_id"}

        deleted = calendar_service.delete_event(g_event_id)
        return {"status": "deleted" if deleted else "error", "google_event_id": g_event_id}

    else:
        return {"status": "ignored", "reason": f"tipo de evento '{event_type}' não tratado"}


def _normalize_iso(dt_str: str) -> str:
    """
    Garante que o datetime esteja no formato ISO 8601 com 'Z' no final,
    compatível com o Google Calendar API.
    """
    if not dt_str:
        return dt_str
    # Remove microsegundos e garante Z
    dt_str = dt_str.split(".")[0].replace("+00:00", "")
    if not dt_str.endswith("Z"):
        dt_str += "Z"
    return dt_str
