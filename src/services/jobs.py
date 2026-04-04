import logging
from datetime import datetime, timedelta, timezone
from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.email_service import send_email_reminder

logger = logging.getLogger("CardioAgent")


# ═══════════════════════════════════════════════════════════════
#  SYNC AUTOMÁTICO → GOOGLE CALENDAR (roda a cada 2 minutos)
# ═══════════════════════════════════════════════════════════════

def _strip_tz(dt_str: str) -> str:
    """Remove sufixo de timezone para enviar ao Google Calendar como horário local."""
    if not dt_str:
        return dt_str
    dt_str = dt_str.split(".")[0].rstrip("Z")
    if len(dt_str) > 19 and dt_str[19] in ("+", "-"):
        dt_str = dt_str[:19]
    return dt_str


async def sync_calendar_job():
    """
    Roda a cada 2 minutos via APScheduler.
    Sincroniza a tabela `appointments` com o Google Calendar:

    ✅ scheduled + sem google_event_id  → CRIA evento no Google Calendar
    🗑️ cancelled  + com google_event_id → DELETA evento do Google Calendar
    """
    if not db_service.client:
        return

    from src.services.google_calendar import calendar_service

    # ── 1. CRIAR: scheduled sem google_event_id ───────────────
    try:
        res = (
            db_service.client
            .table("appointments")
            .select("id, patient_id, start_time, end_time")
            .eq("status", "scheduled")
            .is_("google_event_id", "null")
            .execute()
        )
        to_create = res.data or []
    except Exception as e:
        logger.error(f"SyncCalendar: erro ao buscar pendentes de criação — {e}")
        to_create = []

    for appt in to_create:
        appt_id = appt.get("id")
        patient_id = appt.get("patient_id")
        start_time = appt.get("start_time", "")
        end_time = appt.get("end_time", "")

        # Busca nome/convênio do paciente
        try:
            res_p = db_service.client.table("patients").select("name, insurance").eq("id", patient_id).execute()
            patient = res_p.data[0] if res_p.data else {}
        except Exception:
            patient = {}

        patient_name = patient.get("name") or "Paciente"
        insurance = patient.get("insurance") or "Não informado"

        summary = f"Consulta: {patient_name}"
        description = f"📋 Convênio: {insurance}\n📱 Agendado via Bot WhatsApp."

        try:
            g_event_id = calendar_service.create_event(summary, description, start_time, end_time)
            if g_event_id:
                db_service.client.table("appointments").update(
                    {"google_event_id": g_event_id}
                ).eq("id", appt_id).execute()
                logger.info(f"SyncCalendar ✅ CRIADO: {patient_name} | {start_time} → [{g_event_id}]")
        except Exception as e:
            logger.error(f"SyncCalendar: erro ao criar evento para {appt_id} — {e}")

    # ── 2. DELETAR: cancelled com google_event_id ─────────────
    try:
        res = (
            db_service.client
            .table("appointments")
            .select("id, google_event_id")
            .eq("status", "cancelled")
            .not_.is_("google_event_id", "null")
            .execute()
        )
        to_delete = res.data or []
    except Exception as e:
        logger.error(f"SyncCalendar: erro ao buscar cancelamentos — {e}")
        to_delete = []

    for appt in to_delete:
        appt_id = appt.get("id")
        g_event_id = appt.get("google_event_id")
        try:
            deleted = calendar_service.delete_event(g_event_id)
            if deleted:
                # Limpa o google_event_id para não tentar deletar de novo
                db_service.client.table("appointments").update(
                    {"google_event_id": None}
                ).eq("id", appt_id).execute()
                logger.info(f"SyncCalendar 🗑️ DELETADO: evento [{g_event_id}] do appointment [{appt_id}]")
        except Exception as e:
            logger.error(f"SyncCalendar: erro ao deletar evento {g_event_id} — {e}")

    if to_create or to_delete:
        logger.info(f"SyncCalendar ✅ Ciclo completo: +{len(to_create)} criados, -{len(to_delete)} deletados.")


async def send_reminders_job():
    """
    Roda a cada hora via APScheduler.
    Envia lembretes por WhatsApp e e-mail:
      - 24h antes da consulta
      - 2h antes da consulta
    """
    if not db_service.client:
        logger.warning("Supabase indisponível. Lembretes ignorados.")
        return

    now = datetime.now(timezone.utc)

    # ── LEMBRETE 24H ─────────────────────────────────────────
    in_24h_start = now + timedelta(hours=23)
    in_24h_end = now + timedelta(hours=25)

    res_24h = (db_service.client.table("appointments")
               .select("id, start_time, patients(name, phone, remote_jid, email)")
               .eq("status", "scheduled")
               .gte("start_time", in_24h_start.isoformat())
               .lte("start_time", in_24h_end.isoformat())
               .execute())

    for appt in (res_24h.data or []):
        patient = appt.get("patients", {})
        phone = patient.get("remote_jid")
        email = patient.get("email")
        name = patient.get("name", "Paciente")

        try:
            start_dt = datetime.fromisoformat(appt["start_time"])
            time_str = start_dt.strftime("%d/%m/%Y às %H:%M")
        except Exception:
            time_str = appt["start_time"]

        # WhatsApp
        if phone:
            msg_wa = (
                f"Olá, {name}! 😊\n\n"
                f"Lembrando que você tem uma consulta com o *Dr. João* amanhã em {time_str}.\n\n"
                f"📄 *Documentos para trazer:*\n"
                f"• Carteirinha do plano de saúde ({patient.get('insurance', 'Plano')})\n"
                f"• Documento de identidade (RG, CNH ou outro)\n\n"
                "Até lá! 💙"
            )
            await evo_service.send_text_message(phone, msg_wa)

        # E-mail
        if email:
            await send_email_reminder(email, name, time_str, "24h")

        # Omitindo update por enquanto para evitar erro de coluna inexistente
        # db_service.client.table("appointments").update({"notified_24h": True}).eq("id", appt["id"]).execute()
        logger.info(f"Lembrete 24h enviado para {name} ({phone})")

    # ── LEMBRETE 2H ──────────────────────────────────────────
    in_2h_start = now + timedelta(hours=1, minutes=30)
    in_2h_end = now + timedelta(hours=2, minutes=30)

    res_2h = (db_service.client.table("appointments")
              .select("id, start_time, patients(name, phone, remote_jid, email)")
              .eq("status", "scheduled")
              .gte("start_time", in_2h_start.isoformat())
              .lte("start_time", in_2h_end.isoformat())
              .execute())

    for appt in (res_2h.data or []):
        patient = appt.get("patients", {})
        phone = patient.get("remote_jid")
        email = patient.get("email")
        name = patient.get("name", "Paciente")

        try:
            start_dt = datetime.fromisoformat(appt["start_time"])
            time_str = start_dt.strftime("%H:%M")
        except Exception:
            time_str = appt["start_time"]

        # WhatsApp
        if phone:
            msg_wa = (
                f"Oi, {name}! ⏰\n\n"
                f"Sua consulta com o *Dr. João* é hoje às *{time_str}* — em cerca de 2 horas.\n\n"
                f"📄 *Não esqueça de trazer:*\n"
                f"• Carteirinha do plano de saúde ({patient.get('insurance', 'Plano')})\n"
                f"• Documento de identidade (RG, CNH ou outro)\n\n"
                "Nos vemos em breve! 💙"
            )
            await evo_service.send_text_message(phone, msg_wa)

        # E-mail
        if email:
            await send_email_reminder(email, name, time_str, "2h")

        # db_service.client.table("appointments").update({"notified_same_day": True}).eq("id", appt["id"]).execute()
        logger.info(f"Lembrete 2h enviado para {name} ({phone})")

async def check_inactivity_job(active_sessions: dict):
    """
    Verifica sessões inativas:
      - 3 minutos: Envia prompt de inatividade.
      - 5 minutos: Encerra o atendimento por inatividade.
    """
    from src.config.messages import MSG_INACTIVITY_PROMPT, MSG_INACTIVITY_TERMINATION
    from datetime import datetime, timedelta, timezone
    
    now = datetime.now(timezone.utc)
    to_remove = []

    for jid, state in active_sessions.items():
        last_at = state.get("last_message_at")
        if not last_at: continue
        
        # Ignora se estiver no passo inicial 'welcome' (sessão recém-criada)
        if state.get("conversation_step") == "welcome": continue
        
        diff = now - last_at

        # 5 MINUTOS: ENCERRAMENTO TOTAL SILENCIOSO (SEM PERGUNTAS)
        if diff > timedelta(minutes=5):
            try:
                await evo_service.send_text_message(jid, MSG_INACTIVITY_TERMINATION)
                to_remove.append(jid)
                logger.info(f"Sessão encerrada silenciosamente por inatividade (5 min): {jid}")
            except Exception as e:
                logger.error(f"Erro ao encerrar sessão {jid}: {e}")
            continue

    for jid in to_remove:
        if jid in active_sessions:
            del active_sessions[jid]
