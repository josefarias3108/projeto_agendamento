import logging
import asyncio
from datetime import datetime, timedelta
from src.config.messages import *
from src.database.client import db_service
from src.services.evolution import evo_service
from src.services.sessions import active_sessions, create_initial_state

logger = logging.getLogger("CardioAgent")

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

# ----------------- INÍCIO DE FLUXOS -----------------

async def start_clinic_scheduling(remote_jid, state):
    state["clinic_step"] = "scheduling_select_date"
    msg, dates, has_more = db_service.find_next_available_dates()
    state["date_options"] = dates
    state["hour_options"] = []
    await send(remote_jid, f"📅 *Agendamento (Uso Restrito)*\n\n{msg}")

async def start_clinic_reschedule(remote_jid, state):
    state["clinic_step"] = "scheduling_ask_cpf_reschedule"
    await send(remote_jid, "🔄 *Remarcar Consulta*\n\nPor favor, informe o *CPF* do paciente (apenas números):")

async def start_clinic_cancellation(remote_jid, state):
    state["clinic_step"] = "scheduling_ask_cpf_cancel"
    await send(remote_jid, "❌ *Cancelar Consulta*\n\nPor favor, informe o *CPF* do paciente (apenas números):")

async def start_clinic_cancellation_consultorio(remote_jid, state):
    """Opção 5: Cancelamento em Massa/Consultório."""
    from src.handlers.clinic import format_and_send_date_pagination
    await format_and_send_date_pagination(remote_jid, state, "scheduling_bulk_cancel_select_date", 0)

# Fluxos iniciados via Ficha Completa
async def start_clinic_scheduling_for_patient(remote_jid, state, patient):
    state["clinic_target_patient"] = patient
    await start_clinic_scheduling(remote_jid, state)

async def start_clinic_reschedule_for_patient(remote_jid, state, patient):
    state["clinic_target_patient"] = patient
    apps = db_service.get_appointments_by_patient(patient["id"])
    if not apps:
        await send(remote_jid, "Não há consultas agendadas para este paciente.")
        from src.handlers.clinic import MSG_CLINIC_DETAILS_SEARCH_MENU
        await send(remote_jid, MSG_CLINIC_DETAILS_SEARCH_MENU)
        return
    
    state["cancel_options"] = apps
    state["clinic_step"] = "scheduling_reschedule_select"
    lines = [f"{i}️⃣ {datetime.fromisoformat(a['start_time'].replace('Z', '')).strftime('%d/%m/%Y %H:%M')}" for i, a in enumerate(apps, 1)]
    await send(remote_jid, f"🗓️ *Remarcar Consulta - {patient['name']}*\n\n" + "\n".join(lines) + "\n\n👉 Escolha a consulta.")

async def start_clinic_cancellation_for_patient(remote_jid, state, patient):
    state["clinic_target_patient"] = patient
    apps = db_service.get_appointments_by_patient(patient["id"])
    if not apps:
        await send(remote_jid, "Não há consultas agendadas para este paciente.")
        from src.handlers.clinic import MSG_CLINIC_DETAILS_SEARCH_MENU
        await send(remote_jid, MSG_CLINIC_DETAILS_SEARCH_MENU)
        return
    
    state["cancel_options"] = apps
    state["clinic_step"] = "scheduling_cancel_select"
    lines = [f"{i}️⃣ {datetime.fromisoformat(a['start_time'].replace('Z', '')).strftime('%d/%m/%Y %H:%M')}" for i, a in enumerate(apps, 1)]
    await send(remote_jid, MSG_CANCEL_LIST_HEADER.format(appointments_list="\n".join(lines)))

# ----------------- MANIPULADOR PRINCIPAL -----------------

async def handle_clinic_scheduling(remote_jid, state, text):
    import re
    match = re.search(r'\d+', text)
    num_text = match.group() if match else ""
    txt_lower = text.lower().strip()

    step = state.get("clinic_step", "")

    # ========== CANCELAMENTO / REMARCAÇÃO (BUSCA POR CPF) ==========
    if step in ("scheduling_ask_cpf_cancel", "scheduling_ask_cpf_reschedule"):
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return

        clean_cpf = "".join(filter(str.isdigit, text))
        if len(clean_cpf) != 11:
            await send(remote_jid, "CPF inválido. Digite 11 números ou 9 para voltar.")
            return

        patient = db_service.get_patient_by_cpf(clean_cpf)
        if not patient:
            await send(remote_jid, "❌ Paciente não encontrado com esse CPF.\nDigite outro CPF ou 9 para voltar.")
            return

        state["clinic_target_patient"] = patient
        apps = db_service.get_appointments_by_patient(patient["id"])
        
        # Filtra apenas consultas futuras e 'scheduled' ou 'confirmed'
        from datetime import timezone
        now = datetime.now(timezone.utc)
        valid_apps = []
        for a in apps:
            if a.get("status") in ("scheduled", "confirmed"):
                try:
                    dt_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                    if dt_obj >= now:
                        valid_apps.append(a)
                except:
                    pass

        if not valid_apps:
            await send(remote_jid, f"O paciente {patient.get('name')} não possui consultas futuras agendadas.\n↩️ Voltando ao menu.")
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return

        # Prepara a lista
        state["cancel_options"] = valid_apps
        
        lines = []
        for i, a in enumerate(valid_apps, 1):
            try:
                dt_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                lines.append(f"{i}️⃣ {dt_obj.strftime('%d/%m/%Y %H:%M')} - {patient.get('name')}")
            except:
                lines.append(f"{i}️⃣ {a['start_time']}")
                
        appointments_list = "\n".join(lines)
        
        if step == "scheduling_ask_cpf_cancel":
            state["clinic_step"] = "scheduling_cancel_select"
            msg = MSG_CANCEL_LIST_HEADER.format(appointments_list=appointments_list)
            msg = msg.replace("0️⃣ Voltar ao menu principal sem cancelar", "9️⃣ Voltar ao menu do consultório")
        else: # Reschedule
            state["clinic_step"] = "scheduling_reschedule_select"
            msg = f"🗓️ *Consultas Agendadas de {patient.get('name')}*\n\n{appointments_list}\n\n👉 Digite o número da consulta que deseja *REMARCAR*.\n↩️ 9️⃣ Voltar ao menu"

        await send(remote_jid, msg)
        return

    if step == "scheduling_cancel_select":
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        nums = [int(n) for n in re.findall(r'\d+', text)]
        options = state.get("cancel_options", [])
        
        selected_apps = []
        for n in nums:
            if 1 <= n <= len(options):
                selected_apps.append(options[n-1])
                
        if not selected_apps:
            await send(remote_jid, "🤔 Não consegui identificar os números corretamente. Digite 9 para voltar.")
            return
            
        state["cancel_selected"] = selected_apps
        state["clinic_step"] = "scheduling_cancel_confirm"
        
        lines = []
        for a in selected_apps:
            try:
                dt_obj = datetime.fromisoformat(a["start_time"].replace("Z", ""))
                lines.append(f"• {dt_obj.strftime('%d/%m/%Y %H:%M')}")
            except:
                lines.append(f"• {a['start_time']}")
                
        plural = "s" if len(selected_apps) > 1 else ""
        msg = MSG_CANCEL_CONFIRM.format(plural=plural, appointments_list="\n".join(lines))
        await send(remote_jid, msg)
        return
        
    if step == "scheduling_cancel_confirm":
        is_sim = num_text == "1" or txt_lower in SIM_OPTIONS or any(opt in txt_lower for opt in SIM_OPTIONS)
        is_nao = num_text == "2" or txt_lower in NAO_OPTIONS or any(opt in txt_lower for opt in NAO_OPTIONS)

        if is_sim:
            selected_apps = state.get("cancel_selected", [])
            if not selected_apps:
                logger.error("scheduling_cancel_confirm: cancel_selected está vazio ou ausente.")
                await send(remote_jid, "⚠️ Erro: Não encontrei as consultas selecionadas. Por favor, tente novamente.")
                state["clinic_step"] = "menu"
                await send(remote_jid, MSG_CLINIC_MENU)
                return

            cancelled_count = 0
            state_patient = state.get("clinic_target_patient")

            for a in selected_apps:
                try:
                    appt_id = a.get("id")
                    if appt_id:
                        # AJUSTE: Sincronização com o banco de dados
                        db_service.cancel_appointment(appt_id)
                        cancelled_count += 1
                        from src.services.logger_service import log_audit
                        asyncio.create_task(log_audit("secretaria", "cancel_appointment", "appointment", remote_jid, target_id=str(appt_id)))
                    
                    # Identificar o paciente para notificação
                    target_pid = a.get("patient_id")
                    p = None
                    if target_pid:
                        p = db_service.get_patient(target_pid)
                    elif state_patient:
                        p = state_patient
                    
                    if p:
                        # Prioriza o telefone para notificação
                        target_to = p.get("phone") or p.get("remote_jid")
                        if target_to:
                            try:
                                # Formatação de data e hora
                                start_time_str = a.get("start_time", "")
                                try:
                                    d_obj = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                                    d_str = d_obj.strftime("%d/%m/%Y")
                                    h_str = d_obj.strftime("%H:%M")
                                except:
                                    d_str = start_time_str
                                    h_str = ""

                                # MENSAGEM INTERATIVA (Padronizada no messages.py)
                                notification = MSG_CLINIC_CANCELLATION_PROACTIVE.format(
                                    name=p.get("name", "Paciente"),
                                    date=d_str,
                                    hour=h_str
                                )
                                asyncio.create_task(evo_service.send_text_message(target_to, notification))
                                
                                # ATUALIZA ESTADO DO PACIENTE (para permitir a interação de reagendamento)
                                p_jid = p.get("remote_jid") or (f"{p['phone']}@s.whatsapp.net" if "@" not in str(p.get("phone", "")) else p.get("phone"))
                                p_state = active_sessions.get(p_jid) or create_initial_state(p_jid, p)
                                p_state["conversation_step"] = "waiting_proactive_cancel_response"
                                p_state["last_message_at"] = datetime.now(timezone.utc)
                                active_sessions[p_jid] = p_state
                                
                                logger.info(f"Notificação de cancelamento enviada para {target_to}")
                            except Exception as e_msg:
                                logger.error(f"Erro ao notificar paciente: {e_msg}")
                except Exception as e:
                    logger.error(f"Erro cancelando no banco ou notificando: {e}")

            # Notificação de ADMINs
            if cancelled_count > 0:
                try:
                    target_p = state_patient or {}
                    app_time = selected_apps[0].get("start_time", "Desconhecido")
                    asyncio.create_task(notify_admins_event("❌ Consulta Cancelada", target_p, app_time))
                except:
                    pass

            # MENSAGEM SOLICITADA PARA O FUNCIONÁRIO
            await send(remote_jid, "OK. cancelamento feito ✅")
            
            # Limpeza de estado e retorno ao menu
            state["clinic_step"] = "menu"
            state["cancel_options"] = []
            state["cancel_selected"] = []
            state["clinic_target_patient"] = None
            
            from src.config.messages import MSG_CLINIC_MENU
            await send(remote_jid, MSG_CLINIC_MENU)
            return

        elif is_nao:
            # Volta para a seleção ou para o início do cancelamento
            await send(remote_jid, "Entendido. Cancelamento não realizado.")
            state["clinic_step"] = "menu"
            from src.config.messages import MSG_CLINIC_MENU
            await send(remote_jid, MSG_CLINIC_MENU)
            return
        else:
            await send(remote_jid, "🤔 Opção não reconhecida. Por favor, responda com *1* (Sim) ou *2* (Não).")
            return

    if step == "scheduling_reschedule_select":
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        idx = int(num_text) - 1 if num_text else -1
        options = state.get("cancel_options", [])
        
        if 0 <= idx < len(options):
            target = options[idx]
            db_service.cancel_appointment(target["id"])
            from src.services.logger_service import log_audit
            asyncio.create_task(log_audit("secretaria", "reschedule_appointment", "appointment", remote_jid, target_id=str(target["id"])))
            
            # NOVO: Notificar o paciente que a consulta antiga foi cancelada visando a remarcação
            p = state.get("clinic_target_patient")
            if p:
                try:
                    d_obj = datetime.fromisoformat(target["start_time"].replace("Z", "+00:00"))
                    patient_msg_reschedule = f"Olá, {p.get('name')}! 😊\nSua consulta do dia {d_obj.strftime('%d/%m/%Y às %H:%M')} foi desmarcada para darmos andamento à sua remarcação.\nLogo em seguida confirmaremos o seu novo horário!"
                    if p.get("phone"):
                        asyncio.create_task(evo_service.send_text_message(p["phone"], patient_msg_reschedule))
                    if p.get("email"):
                        from src.services.email_service import send_email
                        asyncio.create_task(asyncio.to_thread(send_email, p["email"], "Aviso de Remarcação", patient_msg_reschedule))
                except: pass
            
            # Notificação de ADMINs (Regra da Remarcação - Fase Cancelamento Antigo)
            asyncio.create_task(notify_admins_event("🔄 Consulta Remarcada (Horário Anterior Liberado)", state.get("clinic_target_patient", {}), target["start_time"]))

            await send(remote_jid, f"Antiga consulta cancelada. Vamos escolher a *nova data* para {state['clinic_target_patient']['name']}. 📅")
            state["clinic_step"] = "scheduling_select_date"
            msg, dates, has_more = db_service.find_next_available_dates()
            state["date_options"] = dates
            state["hour_options"] = []
            await send(remote_jid, msg)
            return
        else:
            await send(remote_jid, "Opção inválida. Digite 9 para voltar.")
            return

    # ========== CANCELAMENTO CONSULTÓRIO (OPÇÃO 5) ==========
    
    if step == "scheduling_bulk_cancel_select_date":
        if text == "9" or txt_lower in ("voltar", "v"):
            state["clinic_date_map"] = {}
            from src.config.messages import MSG_CLINIC_MENU
            await send(remote_jid, MSG_CLINIC_MENU)
            return
        
        # Opção 8: Ver mais datas
        if text == "8":
            from src.handlers.clinic import format_and_send_date_pagination
            offset = state.get("clinic_date_offset", 0) + 7
            await format_and_send_date_pagination(remote_jid, state, "scheduling_bulk_cancel_select_date", offset)
            return

        date_map = state.get("clinic_date_map", {})
        if text in date_map:
            selected_date = date_map[text]
            state["selected_bulk_cancel_date"] = selected_date
            
            # Busca horários ocupados para a data selecionada
            try:
                dt_obj_date = datetime.fromisoformat(selected_date).date()
            except:
                dt_obj_date = datetime.strptime(selected_date, "%Y-%m-%d").date()
                
            appts = db_service.get_appointments_by_date(dt_obj_date)
            if not appts:
                await send(remote_jid, "Não há consultas agendadas para este dia.\n↩️ 9️⃣ Voltar.")
                return
                
            msg = "Veja os horários disponíveis para o dia escolhido:\n\n"
            cancel_time_map = {}
            for i, a in enumerate(appts):
                idx = i + 1
                try:
                    h_str = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00")).strftime("%H:%M")
                except: h_str = "??"
                p_name = (a.get("patients") or {}).get("name", "Desconhecido")
                msg += f"{idx}️⃣ {h_str} - {p_name}\n"
                cancel_time_map[str(idx)] = a
            
            msg += f"\n{len(appts)+1}️⃣ *Todos os horários*\n"
            msg += "\n↩️ 7️⃣ Voltar para escolher outra data"
            msg += "\n\n👉 Me diga o número ou os números (separados por vírgula) das opções:"
            
            state["clinic_bulk_cancel_time_map"] = cancel_time_map
            state["clinic_step"] = "scheduling_bulk_cancel_select_times"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "Opção inválida. Escolha um número da lista ou 9️⃣ Voltar.")
        return

    elif step == "scheduling_bulk_cancel_select_times":
        if text == "7" or txt_lower == "voltar":
            await start_clinic_cancellation_consultorio(remote_jid, state)
            return
            
        cancel_time_map = state.get("clinic_bulk_cancel_time_map", {})
        choices = [c.strip() for c in text.split(",")]
        
        selected_appts = []
        if str(len(cancel_time_map) + 1) in choices or txt_lower == "todos":
            selected_appts = list(cancel_time_map.values())
        else:
            for c in choices:
                if c in cancel_time_map:
                    selected_appts.append(cancel_time_map[c])
        
        if selected_appts:
            state["selected_bulk_cancel_appts"] = selected_appts
            state["clinic_step"] = "scheduling_bulk_cancel_confirm"
            
            lines = []
            for a in selected_appts:
                try:
                    h_str = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00")).strftime("%H:%M")
                except: h_str = "??"
                p_name = (a.get("patients") or {}).get("name", "Desconhecido")
                lines.append(f"• {h_str} - {p_name}")
                
            msg = f"⚠️ *Confirmar Cancelamento em Massa*\n\nVocê selecionou {len(selected_appts)} consulta(s):\n"
            msg += "\n".join(lines)
            msg += "\n\nOs pacientes receberão uma mensagem automática informando o cancelamento e convidando para remarcar.\n\n1️⃣ Confirmar e Enviar\n2️⃣ Voltar"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "Não identifiquei as opções. Digite os números ou 9️⃣ Voltar.")

    elif step == "scheduling_bulk_cancel_confirm":
        if text == "1" or txt_lower in SIM_OPTIONS:
            selected_appts = state.get("selected_bulk_cancel_appts", [])
            await send(remote_jid, f"⏳ Iniciando cancelamentos e notificações para {len(selected_appts)} pacientes...")
            
            count = 0
            for a in selected_appts:
                try:
                    # 1. Cancelar no Banco
                    db_service.cancel_appointment(a["id"])
                    from src.services.logger_service import log_audit
                    asyncio.create_task(log_audit("secretaria", "bulk_cancel", "appointment", remote_jid, target_id=str(a["id"])))
                    
                    # 2. Enviar mensagem proativa para o paciente
                    p = a.get("patients") or {}
                    if p.get("phone"):
                        try:
                            d_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                            d_str = d_obj.strftime("%d/%m/%Y")
                            
                            # MENSAGEM PERSONALIZADA CONFORME SOLICITADO
                            notification = MSG_CLINIC_CANCELLATION_PROACTIVE_BULK.format(
                                name=p.get("name", "Paciente"),
                                date=d_str
                            )
                            asyncio.create_task(evo_service.send_text_message(p["phone"], notification))
                            
                            # Notificar Admin
                            asyncio.create_task(notify_admins_event("❌ Cancelamento via Consultório (Em massa)", p, a["start_time"]))
                        except: pass
                    count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Erro no loop de cancelamento em massa: {e}")

            await send(remote_jid, "OK. cancelamento feito ✅")
            from src.config.messages import MSG_ENCERRAR
            await send(remote_jid, MSG_ENCERRAR)
            from src.services.sessions import active_sessions
            if remote_jid in active_sessions:
                del active_sessions[remote_jid]
            return
        else:
            await start_clinic_cancellation_consultorio(remote_jid, state)

    # ========== AGENDAMENTO / ESCOLHA DE DATA E HORA ==========

    # 1. SELEÇÃO DE DATA
    if step == "scheduling_select_date" and state.get("date_options") and num_text.isdigit():
        idx = int(num_text) - 1
        
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
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return

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
                state["selected_hour"] = chosen_hour
                
                # SE JÁ TIVERMOS O PACIENTE (Vindo da Remarcação), AGENDA DIRETO
                if state.get("clinic_target_patient"):
                    await finalize_clinic_booking(remote_jid, state, state["clinic_target_patient"])
                    return

                # SENÃO PEDE O CPF (Agendamento Novo)
                state["clinic_step"] = "scheduling_ask_cpf_book"
                await send(remote_jid, "⏱️ Horário travado temporariamente.\n\nPor favor, digite o *CPF* do paciente para vincular à consulta:")
                return

    # 3. RECEBER CPF DE AGENDAMENTO NOVO
    if step == "scheduling_ask_cpf_book":
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        clean_cpf = "".join(filter(str.isdigit, text))
        if len(clean_cpf) != 11:
            await send(remote_jid, "CPF inválido. Digite 11 números ou 9 para cancelar o agendamento e voltar.")
            return
            
        patient = db_service.get_patient_by_cpf(clean_cpf)
        if patient:
            await finalize_clinic_booking(remote_jid, state, patient)
            return
        else:
            # PACIENTE NÃO CADASTRADO - Desviar para fluxo de novo cadastro do consultorio
            state["clinic_cpf_to_register"] = clean_cpf
            await send(remote_jid, "⚠️ Este CPF ainda não está cadastrado no sistema.\n\nFaremos um *Cadastro Rápido* agora!")
            
            from src.handlers.clinic_onboarding import start_clinic_onboarding_fast
            await start_clinic_onboarding_fast(remote_jid, state, clean_cpf)
            return


async def finalize_clinic_booking(remote_jid, state, patient):
    chosen_date = state.get("selected_date")
    chosen_hour = state.get("selected_hour")
    
    try:
        start = datetime.fromisoformat(chosen_date).replace(hour=chosen_hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        doc = db_service.get_doctor_by_name("Dr. João")
        pid = patient["id"]
        
        res = db_service.book_appointment(pid, doc["id"], start.isoformat(), end.isoformat())
        
        if res.get("success"):
            state["clinic_step"] = "menu"
            state["hour_options"] = []
            state["clinic_target_patient"] = None
            
            # Notificação de ADMINs (Agendamento) - Optei por enviar tambem, mas o usuario disse "so alertar pra cancelamento e remarcação".
            # Irei seguir a regra restrita do usuário, não chamarei notify_admins_event para novo agendamento, ao menos que seja uma remarcação (que já chamei no block anterior).
            
            details = (
                f"📅 {start.strftime('%d/%m/%Y')}\n"
                f"🕒 {start.strftime('%H:%M')}\n"
                f"👨‍⚕️ Dr. João – Cardiologista\n\n"
                f"📍 Local: Avenida das Américas, 3500, sala 701 – Barra da Tijuca\n\n"
                f"📄 Leve documento com foto e sua carteirinha do plano."
            )
            
            msg = f"🎉 Parabéns! Atendimento cadastrado/agendado com sucesso pelo sistema.\n✅ Agendamento confirmado para *{patient.get('name')}*!\n\n{details}"
            await send(remote_jid, msg)
            
            # NOVO: Notificar o paciente sobre esse agendamento
            patient_msg = f"✅ Olá, {patient.get('name')}! Seu agendamento foi confirmado pelo nosso consultório.\n\n{details}"
            if patient.get("phone"):
                asyncio.create_task(evo_service.send_text_message(patient["phone"], patient_msg))
            if patient.get("email"):
                try:
                    from src.services.email_service import send_email
                    asyncio.create_task(asyncio.to_thread(send_email, patient["email"], "Confirmação de Consulta - Clínica Dr. João", patient_msg))
                except Exception as ex: 
                    logger.error(f"Erro ao enviar email {ex}")

            await send(remote_jid, MSG_CLINIC_MENU)
        else:
            await send(remote_jid, f"Erro ao agendar: {res.get('error', 'Erro desconhecido')}")
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
    except Exception as e:
        logger.error(f"Erro clinic booking: {e}")
        await send(remote_jid, "Desculpe, ocorreu um erro técnico.")


async def notify_admins_event(motivo, patient, start_time_iso):
    """Envia notificação via whats e email de cancelamentos/remarcações."""
    try:
        dt_obj = datetime.fromisoformat(str(start_time_iso).replace("Z", ""))
        dt_str = dt_obj.strftime("%d/%m/%Y às %H:%M")
    except:
        dt_str = str(start_time_iso)
        
    p = patient or {}
    pname = p.get("name", "Desconhecido")
    msg = f"⚠️ *Aviso Importante do Sistema* ⚠️\n\n{motivo}\n\n👤 Paciente: {pname}\n⌚ Horário Afetado: {dt_str}\n\nAção realizada pelo uso restrito (/consultorio)."

    # Envia WhatsApp para admins
    admins = db_service.list_admins()
    for adm in admins:
        if adm.get("phone"):
            try:
                await evo_service.send_text_message(adm["phone"], msg)
            except:
                pass
                
    # Envia Email
    from src.services.email_service import send_email
    asyncio.create_task(asyncio.to_thread(send_email, "gutofarias.32@gmail.com", f"Aviso de Consultório - {motivo}", msg))
