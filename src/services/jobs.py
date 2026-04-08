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


async def force_refresh_google_token_job():
    """
    Roda a cada 6 horas para forçar a renovação proativa do token do Google.
    Evita expiração súbita de tokens do tipo Testing na GCP (que morrem em 7 dias silenciadamente
    se não houver recarga ou verificação proativa frequente).
    """
    from src.services.google_calendar import calendar_service
    from google.auth.transport.requests import Request
    if calendar_service.creds and calendar_service.creds.refresh_token:
        try:
            calendar_service.creds.refresh(Request())
            calendar_service._save_token()
            logger.info("CronJob 🔁 Google Calendar: token renovado preventivamente com sucesso.")
        except Exception as e:
            logger.error(f"CronJob ❌ Google Calendar: falha ao forçar renovação de token — {e}")



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
    from src.services.sessions import active_sessions, create_initial_state
    from src.config.messages import MSG_REMINDER_CONFIRM_PROMPT

    # ── LEMBRETE 24H ─────────────────────────────────────────
    in_24h_start = now + timedelta(hours=23)
    in_24h_end = now + timedelta(hours=25)

    res_24h = (db_service.client.table("appointments")
               .select("id, start_time, patients(id, name, phone, remote_jid, email, cpf, cep, address, insurance, birth_date)")
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
                "Até lá! 💙\n\n"
                f"{MSG_REMINDER_CONFIRM_PROMPT}"
            )
            await evo_service.send_text_message(phone, msg_wa)
            
            # Atualiza estado da sessão
            if phone not in active_sessions:
                active_sessions[phone] = create_initial_state(phone, patient)
            active_sessions[phone]["conversation_step"] = "waiting_reminder_confirmation"
            active_sessions[phone]["pending_confirmation_appt_id"] = appt["id"]
            active_sessions[phone]["pending_confirmation_appt_time"] = time_str
            active_sessions[phone]["last_message_at"] = datetime.now(timezone.utc)

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
              .select("id, start_time, patients(id, name, phone, remote_jid, email, cpf, cep, address, insurance, birth_date)")
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
                "Nos vemos em breve! 💙\n\n"
                f"{MSG_REMINDER_CONFIRM_PROMPT}"
            )
            await evo_service.send_text_message(phone, msg_wa)
            
            # Atualiza estado da sessão
            if phone not in active_sessions:
                active_sessions[phone] = create_initial_state(phone, patient)
            active_sessions[phone]["conversation_step"] = "waiting_reminder_confirmation"
            active_sessions[phone]["pending_confirmation_appt_id"] = appt["id"]
            active_sessions[phone]["pending_confirmation_appt_time"] = time_str
            active_sessions[phone]["last_message_at"] = datetime.now(timezone.utc)

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

# ═══════════════════════════════════════════════════════════════
#  SERVIÇOS PROATIVOS (15 Minutos, Agendas, Churn)
# ═══════════════════════════════════════════════════════════════

async def check_proactive_alerts_job():
    """
    Verifica pacientes cujo atendimento começa em 15min e que ainda não tem status 'waiting' (Na Espera).
    Agendado para cada 5 min.
    """
    if not db_service.client: return
    now = datetime.now(timezone.utc)
    target = now + timedelta(minutes=15)
    
    start_window = target - timedelta(minutes=3)
    end_window = target + timedelta(minutes=3)
    
    # Busca pacientes com consulta daqui a 15min que ainda estão scheduled ou confirmed
    try:
        res = (db_service.client.table("appointments")
               .select("id, start_time, status, patients(remote_jid)")
               .in_("status", ["scheduled", "confirmed"])
               .gte("start_time", start_window.isoformat())
               .lte("start_time", end_window.isoformat())
               .execute())
               
        from src.config.messages import MSG_ALERT_15MIN
        for a in (res.data or []):
            jid = a.get("patients", {}).get("remote_jid")
            if jid:
                await evo_service.send_text_message(jid, MSG_ALERT_15MIN)
    except Exception as e:
        logger.error(f"Erro no check_proactive_alerts_job: {e}")

async def churn_check_job():
    """
    Prevenção de churn: Envia Whatsapp/Email para pacientes com >60 dias sem consulta.
    Agendado para rodar a cada 7 dias, ou 1 vez no dia.
    """
    if not db_service.client: return
    # Logica MVP: em produção usaremos query SQL especifica.
    # Disparará o texto MSG_CHURN_WHATSAPP
    pass

async def daily_admin_agenda_job():
    """
    Envia a lista 12h e 1h antes do primeiro atendimento para o email e admin whatsapp.
    Agendado para checar a cada hora (ex: 1 vez a cada hora).
    """
    if not db_service.client: return
    now = datetime.now(timezone.utc)
    target_12h = now + timedelta(hours=12)
    target_1h = now + timedelta(hours=1)
    
    for target, label in [(target_12h, "12h"), (target_1h, "1h")]:
        start_date = target.replace(hour=0, minute=0, second=0)
        end_date = target.replace(hour=23, minute=59, second=59)
        
        # Pega a primeira consulta do dia do target
        res = (db_service.client.table("appointments")
               .select("start_time, patients(name)")
               .in_("status", ["scheduled", "confirmed"])
               .gte("start_time", start_date.isoformat())
               .lte("start_time", end_date.isoformat())
               .order("start_time")
               .limit(1)
               .execute())
               
        appointments = res.data or []
        if appointments:
            first_appt_time = datetime.fromisoformat(appointments[0]["start_time"].replace("Z", "+00:00"))
            
            # Checa se o target está dentro de 1 hora da primeira consulta
            diff = abs((first_appt_time - target).total_seconds())
            if diff < 3600:
                # É hora de enviar o relatório!
                all_res = (db_service.client.table("appointments")
                           .select("start_time, patients(name)")
                           .in_("status", ["scheduled", "confirmed"])
                           .gte("start_time", start_date.isoformat())
                           .lte("start_time", end_date.isoformat())
                           .order("start_time")
                           .execute())
                           
                msg = f"🏥 *Agenda Clínica - Aviso de {label}*\n\nPacientes aguardados:\n"
                for a in all_res.data:
                    dt = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                    pname = a.get("patients", {}).get("name", "Desconhecido")
                    msg += f"- {dt.strftime('%H:%M')} | {pname}\n"
                    
                # Disparo Whatsapp para Admins
                admins = db_service.list_admins()
                for adm in admins:
                    if adm.get("phone"):
                        from src.services.evolution import evo_service
                        import asyncio
                        asyncio.create_task(evo_service.send_text_message(adm["phone"], msg))
                        
                # Disparo Email
                from src.services.email_service import send_email
                send_email("gutofarias.32@gmail.com", f"Agenda Médica - Aviso de {label}", msg)

async def supabase_keepalive_job():
    """
    Cria um evento oculto (agendamento) e deleta logo após para evitar a inatividade do Supabase.
    Usa o CPF teste "10809681722" informado.
    """
    if not db_service.client: return
    logger.info("Executando Keep-Alive do Supabase...")
    
    try:
        # 1. Pega paciente
        p = db_service.get_patient_by_cpf("10809681722")
        if not p:
            logger.warning("Supabase Keep-Alive: Paciente teste 10809681722 não encontrado. Job ignorado.")
            return
            
        doc = db_service.get_doctor_by_name("Dr. João")
        if not doc: return
        
        # 2. Agenda para data oculta no futuro distante (ex: daqui 30 dias na madruga)
        start = datetime.now(timezone.utc) + timedelta(days=30)
        start = start.replace(hour=3, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        
        # Faz insert silencioso
        res = db_service.client.table("appointments").insert({
            "patient_id": p["id"],
            "doctor_id": doc["id"],
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "status": "scheduled",
            "google_event_id": "KEEPALIVE" # Evita que on sync envie para o Google Agenda
        }).execute()
        
        if res.data:
            appt_id = res.data[0]["id"]
            import asyncio
            # Espera 1 minuto para contar como atividade persistente de IO
            await asyncio.sleep(60)
            
            # Deleta permanentemente para não poluir
            db_service.client.table("appointments").delete().eq("id", appt_id).execute()
            logger.info("Supabase Keep-Alive: Sucesso (Insert -> Sleep -> Delete).")
            
    except Exception as e:
        logger.error(f"Erro no Supabase Keep-Alive: {e}")
