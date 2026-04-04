from fastapi import FastAPI, BackgroundTasks, Request, Header, HTTPException
import logging
import os
import asyncio
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config.messages import *
from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.jobs import send_reminders_job, sync_calendar_job
from src.services.calendar_sync import handle_supabase_event
from src.services.realtime_sync import start_realtime_listener, stop_realtime_listener
from src.agents.state import AgentState
from src.agents.classifier import check_out_of_context

# Import Handlers
from src.handlers.onboarding import handle_onboarding
from src.handlers.menu import handle_menu
from src.handlers.scheduling import handle_scheduling

# ── Logging ──────────────────────────────────────────────────
os.makedirs("src/logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("src/logs/agent.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("CardioAgent")

# ── Memória de sessão ─────────────────────────────────────────
from src.services.sessions import active_sessions, create_initial_state

# ── Scheduler ─────────────────────────────────────────────────
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.services.jobs import check_inactivity_job
    scheduler.add_job(send_reminders_job, "interval", minutes=60)
    scheduler.add_job(check_inactivity_job, "interval", seconds=30, args=[active_sessions])
    scheduler.add_job(sync_calendar_job, "interval", minutes=2, id="google_calendar_sync")
    scheduler.start()
    logger.info("Scheduler iniciado (lembretes, inatividade, sync Google Calendar).")
    
    # Inicia o listener Supabase Realtime → Google Calendar (sem precisar de URL pública)
    realtime_task = asyncio.create_task(start_realtime_listener())
    logger.info("Realtime listener agendado.")
    
    yield
    
    # Shutdown
    realtime_task.cancel()
    await stop_realtime_listener()
    scheduler.shutdown()

app = FastAPI(title="Consultório Dr. João — Agente de Agendamento", lifespan=lifespan)

# ═══════════════════════════════════════════════════════════════
#  WEBHOOK
# ═══════════════════════════════════════════════════════════════

@app.post("/webhook/whatsapp")
async def evolution_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Erro no parse do payload: {e}")
        return {"status": "error"}

    data = payload.get("data", {})
    message_data = data.get("message", {})

    # Detecta texto
    text = ""
    if "conversation" in message_data:
        text = message_data["conversation"]
    elif "extendedTextMessage" in message_data:
        text = message_data["extendedTextMessage"].get("text", "")
    
    # Se não for texto, pode ser mídia (botão Enviar Exames)
    is_media = any(k in message_data for k in ["imageMessage", "documentMessage", "videoMessage", "audioMessage"])

    remote_jid = data.get("key", {}).get("remoteJid", None)
    from_me = data.get("key", {}).get("fromMe", False)

    if (not text and not is_media) or not remote_jid or from_me or "status@broadcast" in remote_jid:
        return {"status": "ignored"}

    logger.info(f"Recebido '{text}' de {remote_jid} (Media: {is_media})")
    background_tasks.add_task(process_message, remote_jid, text, message_data)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK SUPABASE → GOOGLE CALENDAR SYNC
# ═══════════════════════════════════════════════════════════════

SUPABASE_WEBHOOK_SECRET = os.environ.get("SUPABASE_WEBHOOK_SECRET", "")

@app.post("/webhook/supabase")
async def supabase_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str = Header(default="", alias="x-webhook-secret"),
):
    """
    Endpoint chamado automaticamente pelo Supabase Database Webhooks.
    Sincroniza INSERT/UPDATE/DELETE na tabela `appointments` com o Google Calendar.
    """
    # Valida secret se configurado no .env
    if SUPABASE_WEBHOOK_SECRET and x_webhook_secret != SUPABASE_WEBHOOK_SECRET:
        logger.warning("CalendarSync: webhook recebido com secret inválido. Rejeitado.")
        raise HTTPException(status_code=401, detail="Webhook secret inválido.")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"CalendarSync: erro ao parsear payload do Supabase — {e}")
        raise HTTPException(status_code=400, detail="Payload inválido.")

    logger.info(f"CalendarSync: payload recebido do Supabase — type={payload.get('type')}, table={payload.get('table')}")

    # Processa em background para não bloquear o Supabase
    background_tasks.add_task(handle_supabase_event, payload)
    return {"status": "received"}

# ═══════════════════════════════════════════════════════════════
#  PROCESSAMENTO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

async def send(remote_jid: str, text: str):
    await evo_service.send_text_message(remote_jid, text)

async def process_message(remote_jid: str, text: str, message_data: dict = None):
    text = text.strip()
    txt_lower = text.lower()
    
    # Extração robusta do número (evita erros de desempacotamento de comandos)
    import re
    match = re.search(r'\d+', text)
    num_text = match.group() if match else ""

    # 1. Gerencia Sessão
    if remote_jid not in active_sessions:
        patient = db_service.get_patient_by_phone(remote_jid)
        active_sessions[remote_jid] = create_initial_state(remote_jid, patient)
        
        state = active_sessions[remote_jid]
        if patient and patient.get("name") and patient["name"] != "Paciente Novo":
             state["conversation_step"] = "menu"
             await send(remote_jid, MSG_WELCOME_BACK.format(name=patient["name"]))
        else:
             state["conversation_step"] = "ask_is_patient"
             await send(remote_jid, MSG_WELCOME_NEW)
        return

    state = active_sessions[remote_jid]
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    
    # RESET FORÇADO: Se a sessão existir mas estiver inativa há mais de 15 min
    # Mesmo que o job de inatividade tenha falhado, garantimos o fluxo novo.
    if state.get("last_message_at") and (now - state["last_message_at"]) > timedelta(minutes=15):
        if state.get("is_registered"):
            state["conversation_step"] = "menu"
            state["last_message_at"] = now
            await send(remote_jid, MSG_WELCOME_BACK.format(name=state.get("name", "paciente")))
            return
        else:
            del active_sessions[remote_jid]
            # Deixa o código abaixo recriar a sessão limpa
            return await process_message(remote_jid, text, message_data)

    state["last_message_at"] = now
    state["inactivity_prompt_sent"] = False # Reseta sinalizador de inatividade
    step = state["conversation_step"]

    # 2. Comando Global: Encerrar
    if txt_lower == "encerrar":
        if remote_jid in active_sessions: del active_sessions[remote_jid]
        await send(remote_jid, MSG_ENCERRAR)
        return

    # 3. Tratamento de Fallbacks de Erro (Regra de Ouro)
    if step == "waiting_golden_rule_response":
        if num_text == "1" or txt_lower in SIM_OPTIONS or "prosseguir" in txt_lower or "voltar" in txt_lower:
            state["conversation_step"] = "menu"
            state["loop_count"] = 0
            await send(remote_jid, "Entendido! Vamos voltar ao menu principal.")
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
            return
        elif num_text == "2" or "encerrar" in txt_lower:
            if remote_jid in active_sessions: del active_sessions[remote_jid]
            await send(remote_jid, MSG_ENCERRAR)
            return

    # 4. Verificação de Contexto (Hybrid LLM + Deterministic)
    if len(text) > 3 and step not in ["waiting_for_exams", "scheduling", "register_name"]:
        context_status = check_out_of_context(text)
        if context_status:
            # Se o usuário escolher "1" em um menu de fora de contexto, forçamos o retorno ao menu.
            from src.config.messages import (MSG_OUT_OF_CONTEXT_OFFENSIVE, MSG_OUT_OF_CONTEXT_DEFAULT)
            if num_text == "1":
                 state["conversation_step"] = "menu"
                 await send(remote_jid, "Entendido! Vamos voltar ao atendimento do consultório.")
                 await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
                 return
                 
            if context_status == "offensive":
                await send(remote_jid, MSG_OUT_OF_CONTEXT_OFFENSIVE)
            elif context_status == "off_topic":
                await send(remote_jid, MSG_OUT_OF_CONTEXT_DEFAULT)
            return

    # 5. Roteamento para Handlers baseados no Step
    try:
        # Onboarding & Registro
        if step in ["welcome", "ask_is_patient", "ask_update", "ask_cpf_existing", "ask_update_phone", "register_cpf_confirm"] or step.startswith("register_"):
            await handle_onboarding(remote_jid, state, text)
        
        # Menu Principal & Funcionalidades
        elif step in ["menu", "menu_post_register", "waiting_for_exams", "update_profile", "info_appointments", "info_address", "info_phone"]:
            await handle_menu(remote_jid, state, text, message_data)
        
        # Agendamento & Cancelamento
        elif step == "scheduling" or step.startswith("cancel_"):
            await handle_scheduling(remote_jid, state, text)
            
        else:
            # FALLBACK GLOBAL: Se caiu aqui, o passo é desconhecido ou não mapeado
            logger.warning(f"Step não mapeado: {step}. Redirecionando para menu.")
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))

    except Exception as e:
        logger.error(f"Erro crítico no process_message de {remote_jid}: {e}", exc_info=True)
        # Regra de Ouro: Escalonamento após erros
        state["loop_count"] = state.get("loop_count", 0) + 1
        if state["loop_count"] >= 2:
            state["conversation_step"] = "waiting_golden_rule_response"
            await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
            state["loop_count"] = 0
        else:
            await send(remote_jid, f"👉 Por favor, tente escolher uma das opções numéricas do menu acima ou digite *ENCERRAR*.\n(Erro interno: {type(e).__name__})")

# Fim do Maestro
