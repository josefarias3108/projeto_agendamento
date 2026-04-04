import logging
from datetime import datetime, timedelta
from src.config.messages import *
from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.sessions import active_sessions

logger = logging.getLogger("CardioAgent")

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

async def start_scheduling(remote_jid, state):
    state["intent"] = "agendar"
    state["conversation_step"] = "scheduling"
    msg, dates, has_more = db_service.find_next_available_dates()
    state["date_options"] = dates
    state["hour_options"] = []
    await send(remote_jid, msg)

async def handle_reschedule(remote_jid, state):
    state["intent"] = "remarcar"
    state["conversation_step"] = "scheduling"
    
    # Busca consultas agendadas
    apps = db_service.get_appointments_by_patient(state["patient_id"])
    if not apps:
        await send(remote_jid, "Você não possui consultas agendadas para remarcar. 😊")
        state["conversation_step"] = "menu"
        await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        return

    # Cancela a primeira encontrada (simplificação ou pode perguntar qual)
    target = apps[0]
    db_service.cancel_appointment(target["id"])
    await send(remote_jid, "Entendido! Vamos escolher uma nova data para sua consulta. 📅")
    
    msg, dates, has_more = db_service.find_next_available_dates()
    state["date_options"] = dates
    state["hour_options"] = []
    await send(remote_jid, msg)

async def start_cancellation(remote_jid, state):
    state["intent"] = "cancelar"
    
    # Busca consultas agendadas
    apps = db_service.get_appointments_by_patient(state["patient_id"])
    if not apps:
        state["conversation_step"] = "menu"
        await send(remote_jid, MSG_CANCEL_NONE)
        return

    state["conversation_step"] = "cancel_select"
    state["cancel_options"] = apps
    
    # Construir a lista de mensagens
    lines = []
    for i, a in enumerate(apps, 1):
        dt = a["start_time"]
        try:
            from datetime import datetime
            dt_obj = datetime.fromisoformat(dt.replace("Z", ""))
            lines.append(f"{i}️⃣ {dt_obj.strftime('%d/%m/%Y %H:%M')} com Dr. João")
        except:
            lines.append(f"{i}️⃣ {dt} com Dr. João")
            
    appointments_list = "\n".join(lines)
    msg = MSG_CANCEL_LIST_HEADER.format(appointments_list=appointments_list)
    await send(remote_jid, msg)

async def handle_scheduling(remote_jid, state, text):
    # Extração robusta do número (extrai o primeiro número encontrado na mensagem)
    import re
    match = re.search(r'\d+', text)
    num_text = match.group() if match else ""
    txt_lower = text.lower().strip()

    step = state.get("conversation_step", "scheduling")

    # ── CANCELAMENTO ────────────────────────────────────────────────
    if step == "cancel_select":
        if text.strip() == "0" or "voltar" in txt_lower:
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
            return
            
        import re
        nums = [int(n) for n in re.findall(r'\d+', text)]
        options = state.get("cancel_options", [])
        
        selected_apps = []
        for n in nums:
            if 1 <= n <= len(options):
                selected_apps.append(options[n-1])
                
        if not selected_apps:
            await send(remote_jid, "🤔 Não consegui identificar os números das consultas que deseja cancelar.\n👉 Por favor, digite os números corretos (ex: 1, 2) ou 0 para voltar.")
            return
            
        state["cancel_selected"] = selected_apps
        state["conversation_step"] = "cancel_confirm"
        
        # Format the confirmation message
        lines = []
        for a in selected_apps:
            dt = a["start_time"]
            try:
                from datetime import datetime
                dt_obj = datetime.fromisoformat(dt.replace("Z", ""))
                lines.append(f"• {dt_obj.strftime('%d/%m/%Y %H:%M')}")
            except:
                lines.append(f"• {dt}")
                
        plural = "s" if len(selected_apps) > 1 else ""
        msg = MSG_CANCEL_CONFIRM.format(plural=plural, appointments_list="\n".join(lines))
        await send(remote_jid, msg)
        return
        
    if step == "cancel_confirm":
        if num_text == "1" or txt_lower in SIM_OPTIONS:
            selected_apps = state.get("cancel_selected", [])
            for a in selected_apps:
                db_service.cancel_appointment(a["id"])
                
            estado_plural = "s" if len(selected_apps) > 1 else ""
            msg = MSG_CANCEL_SUCCESS.format(count=len(selected_apps), plural=estado_plural)
            
            state["conversation_step"] = "menu"
            state["cancel_options"] = []
            state["cancel_selected"] = []
            await send(remote_jid, msg)
            # Envia o menu inicial depois para guiar o usuario
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
            return
        elif num_text == "2" or txt_lower in NAO_OPTIONS:
            # Volta para selecao de cancelamento
            await start_cancellation(remote_jid, state)
            return
        else:
            await send(remote_jid, "🤔 Por favor, responda com *1* (Sim, cancelar) ou *2* (Não, voltar).")
            return

    # ── AGENDAMENTO ─────────────────────────────────────────────────
    # 1. SELEÇÃO DE DATA
    if step == "scheduling" and state.get("date_options") and num_text.isdigit():
        idx = int(num_text) - 1
        
        # Recalcula se tem prróxima página 
        msg_check, dates_check, has_more = db_service.find_next_available_dates(offset_count=state.get("date_page", 0))
        
        # Opção 8: Ver mais
        if idx == 7 and has_more: 
            state["date_page"] = state.get("date_page", 0) + 7
            msg, dates, has_more = db_service.find_next_available_dates(offset_count=state["date_page"])
            if not dates:
                 await send(remote_jid, "Não há mais datas disponíveis no momento.")
                 return
            state["date_options"] = dates
            await send(remote_jid, msg)
            return

        # Opção Voltar
        btn_voltar_idx = 8 if has_more else len(state["date_options"])
        if idx == btn_voltar_idx:
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
            return

        # Escolha efetiva da data
        if 0 <= idx < len(state["date_options"]):
            chosen_date = state["date_options"][idx]
            msg, hours = db_service.get_hours_menu(chosen_date)
            if hours:
                state["selected_date"] = chosen_date
                state["hour_options"] = hours
                state["date_options"] = []
                await send(remote_jid, msg)
            else:
                await send(remote_jid, "Desculpe, não há horários disponíveis para esta data. Por favor, escolha outra.")
            return

    # 2. SELEÇÃO DE HORÁRIO
    if state.get("hour_options") and not state.get("date_options"):
        if num_text.isdigit():
            idx = int(num_text) - 1
            if idx == len(state["hour_options"]): # Voltar
                state["hour_options"] = []
                msg, dates, has_more = db_service.find_next_available_dates(offset_count=state.get("date_page", 0))
                state["date_options"] = dates
                await send(remote_jid, msg)
                return
                
            if 0 <= idx < len(state["hour_options"]):
                chosen_hour = state["hour_options"][idx]
                await _finalize_booking(remote_jid, state, state["selected_date"], chosen_hour)
                return

    # 3. Comandos de Texto (Voltar / Mudar Data)
    if "mudar data" in txt_lower or "voltar" in txt_lower or txt_lower in NAO_OPTIONS:
        state["date_page"] = 0
        state["hour_options"] = []
        msg, dates, has_more = db_service.find_next_available_dates(offset_count=0)
        state["date_options"] = dates
        await send(remote_jid, msg)
        return

    # Fallback Regra de Ouro
    state["loop_count"] = state.get("loop_count", 0) + 1
    if state["loop_count"] >= 2:
        await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
        state["loop_count"] = 0
    else:
        await send(remote_jid, "👉 Por favor, selecione apenas o *número* da opção desejada no menu acima ou escreva *Voltar*.")

async def _finalize_booking(remote_jid, state, chosen_date, chosen_hour):
    try:
        start = datetime.fromisoformat(chosen_date).replace(hour=chosen_hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        
        doc = db_service.get_doctor_by_name("Dr. João")
        pid = state.get("patient_id")
        
        res = db_service.book_appointment(pid, doc["id"], start.isoformat(), end.isoformat())
        
        if res.get("success"):
            state.update({"date_options": [], "hour_options": [], "conversation_step": "menu"})
            
            # Formata mensagem de sucesso
            details = (
                f"📅 {start.strftime('%d/%m/%Y')}\n"
                f"🕒 {start.strftime('%H:%M')}\n"
                f"👨‍⚕️ Dr. João – Cardiologista\n\n"
                f"📍 Local: Avenida das Américas, 3500, sala 701 – Barra da Tijuca\n\n"
            )
            
            if state.get("insurance") == "Particular":
                msg = f"✅ Agendamento confirmado!\n\n{details}💳 Valor: R$ 400,00\n🪪 Leve documento com foto."
            else:
                msg = f"✅ Agendamento confirmado!\n\n{details}📄 Leve documento com foto e sua carteirinha do plano."
            
            await send(remote_jid, msg)
            
            # Encerramento gentil solicitado
            thanks_msg = "Obrigado por escolher nosso consultório! 😊 Desejamos um ótimo dia e nos vemos em breve. O atendimento será encerrado."
            await send(remote_jid, thanks_msg)
            
            if remote_jid in active_sessions:
                del active_sessions[remote_jid]
        else:
            await send(remote_jid, f"Erro ao agendar: {res.get('error', 'Erro desconhecido')}")
    except Exception as e:
        logger.error(f"Erro booking: {e}")
        await send(remote_jid, "Desculpe, ocorreu um erro técnico ao finalizar seu agendamento. 🙏")
