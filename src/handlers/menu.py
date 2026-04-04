import logging
from src.config.messages import *
from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.sessions import active_sessions

logger = logging.getLogger("CardioAgent")

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

async def handle_menu(remote_jid, state, text, message_data=None):
    step = state["conversation_step"]
    txt_lower = text.lower().strip()
    
    # Extração robusta do número (evita confusão entre 1 e 10)
    import re
    match = re.search(r'\d+', text)
    num_text = match.group() if match else ""

    if step == "menu":
        if num_text == "1":
            from src.handlers.scheduling import start_scheduling
            await start_scheduling(remote_jid, state)
        elif num_text == "2":
            from src.handlers.scheduling import handle_reschedule
            await handle_reschedule(remote_jid, state)
        elif num_text == "3":
            from src.handlers.scheduling import start_cancellation
            await start_cancellation(remote_jid, state)
        elif num_text == "4":
            state["conversation_step"] = "info_appointments"
            await _show_appointments(remote_jid, state)
        elif num_text == "5":
            state["conversation_step"] = "info_address"
            await send(remote_jid, MSG_OFFICE_ADDRESS)
        elif num_text == "6":
            state["conversation_step"] = "info_phone"
            await send(remote_jid, MSG_OFFICE_PHONE)
        elif num_text == "7":
            state["conversation_step"] = "waiting_for_exams"
            await send(remote_jid, MSG_WAITING_EXAMS)
        elif num_text == "8":
            state["intent"] = "update"
            state["conversation_step"] = "update_profile"
            await send(remote_jid, MSG_PROFILE_UPDATE_MENU)
        elif num_text == "9":
            await _terminate_session(remote_jid)
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))

    elif step == "menu_post_register":
        if num_text == "1":
            from src.handlers.scheduling import start_scheduling
            await start_scheduling(remote_jid, state)
        elif num_text == "2":
            state["conversation_step"] = "info_address"
            await send(remote_jid, MSG_OFFICE_ADDRESS)
        elif num_text == "3":
            state["conversation_step"] = "info_phone"
            await send(remote_jid, MSG_OFFICE_PHONE)
        elif num_text == "4":
            await _terminate_session(remote_jid)
        else:
            first_name = state["name"].split()[0] if state.get("name") else "paciente"
            await send(remote_jid, MSG_REGISTER_DONE.format(first_name=first_name))

    elif step == "waiting_for_exams":
        # Handle media or text options
        if num_text == "1":
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        elif num_text == "2":
            await _terminate_session(remote_jid)
        elif message_data and any(k in message_data for k in ["imageMessage", "documentMessage", "videoMessage"]):
            await _process_exam_media(remote_jid, state, message_data)
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "Por favor, anexe seu exame (PDF ou Foto) ou escolha uma opção do menu. 😊")

    elif step == "info_appointments":
        if num_text == "1" or txt_lower in NAO_OPTIONS: # 1 ou Voltar
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        elif num_text == "2":
            await _terminate_session(remote_jid)
        else:
            await send(remote_jid, "🤔 Digite *1* para voltar ao menu ou *2* para encerrar o atendimento.")
            
    elif step == "info_address" or step == "info_phone":
        if num_text == "1" or txt_lower in NAO_OPTIONS: # 1 ou Voltar
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        elif num_text == "2":
            await _terminate_session(remote_jid)
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "🤔 Digite *1* para voltar ao menu ou *2* para encerrar o atendimento.")

    elif step == "update_profile":
        if num_text == "1":
            state["conversation_step"] = "register_cep"
            await send(remote_jid, MSG_ASK_CEP_NEW)
        elif num_text == "2":
            state["conversation_step"] = "register_email"
            await send(remote_jid, MSG_ASK_EMAIL_NEW)
        elif num_text == "3":
            state["conversation_step"] = "register_insurance_pick"
            await send(remote_jid, MSG_ASK_INSURANCE_MENU)
        elif num_text == "4" or txt_lower in NAO_OPTIONS: # 4 ou Voltar
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "🤔 Escolha uma opção de *1* a *3* para atualizar, ou *4* para voltar ao menu principal.")
        return

async def _show_appointments(remote_jid, state):
    apps = db_service.get_appointments_by_patient(state["patient_id"])
    if not apps:
        await send(remote_jid, MSG_APPOINTMENTS_NONE)
        return
    
    lines = ["📅 *Suas consultas agendadas:*"]
    for a in apps:
        dt = a["start_time"] # ISO string
        try:
            from datetime import datetime
            dt_obj = datetime.fromisoformat(dt.replace("Z", ""))
            lines.append(f"- {dt_obj.strftime('%d/%m/%Y %H:%M')} com Dr. João")
        except:
            lines.append(f"- {dt} com Dr. João")
            
    lines.append(MSG_MENU_FOOTER)
    await send(remote_jid, "\n".join(lines))

async def _terminate_session(remote_jid):
    if remote_jid in active_sessions:
        del active_sessions[remote_jid]
    await send(remote_jid, MSG_ENCERRAR)

async def _process_exam_media(remote_jid, state, message_data):
    # Determine file type and name
    media_type = ""
    file_name = "exame_anexado"
    
    if "imageMessage" in message_data:
        media_type = "image/jpeg"
        file_name = f"exame_{state.get('patient_id')}.jpg"
    elif "documentMessage" in message_data:
        media_type = message_data["documentMessage"].get("mimetype", "application/pdf")
        file_name = message_data["documentMessage"].get("fileName", "exame.pdf")

    # In a real scenario, we'd need to download the media from Evolution API
    # and then upload to Supabase. For now, we'll simulate the save.
    # Note: The 'file_url' would come from Supabase Storage.
    fake_url = "https://supabase.storage.url/placeholder"
    fake_path = f"exams/{remote_jid}/{file_name}"
    
    db_service.save_exam(
        patient_id=state["patient_id"],
        file_name=file_name,
        file_path=fake_path,
        file_url=fake_url,
        file_type=media_type
    )
    
    await send(remote_jid, MSG_EXAM_RECEIVED)
