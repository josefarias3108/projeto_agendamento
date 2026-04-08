import logging
import asyncio
from datetime import datetime
from src.config.messages import *
from src.database.client import db_service

logger = logging.getLogger("CardioAgent")

async def send(remote_jid: str, text: str):
    from src.services.evolution import evo_service
    await evo_service.send_text_message(remote_jid, text)

async def handle_clinic(remote_jid: str, state: dict, text: str):
    """
    Fluxo do comando /consultorio. Exclusivo para secretárias/admins.
    """
    txt_lower = text.lower().strip()
    
    if "clinic_step" not in state:
        state["clinic_step"] = "menu"

    step = state["clinic_step"]

    # 1. Comando Global: Encerrar
    if "encerrar" in txt_lower or "emcerrar" in txt_lower or "cancelar atendimento" in txt_lower:
        if remote_jid in active_sessions_ref():
            del active_sessions_ref()[remote_jid]
        await send(remote_jid, MSG_ENCERRAR)
        return

    # 2. Roteamento para as Camadas de Submenus
    
    # ── AGENDAMENTOS ──
    if step.startswith("scheduling_"):
        from src.handlers.clinic_scheduling import handle_clinic_scheduling
        await handle_clinic_scheduling(remote_jid, state, text)
        return
        
    # ── CADASTROS ──
    if step.startswith("onboarding_"):
        from src.handlers.clinic_onboarding import handle_clinic_onboarding
        await handle_clinic_onboarding(remote_jid, state, text)
        return

    # Verificador IA de Contexto global para os menus passivos
    if len(text) > 3 and step in ["menu", "viewing_report"]:
        from src.agents.classifier import check_out_of_context
        ctx_status = await check_out_of_context(text)
        if ctx_status:
            if ctx_status == "offensive":
                await send(remote_jid, MSG_OUT_OF_CONTEXT_OFFENSIVE)
            else:
                await send(remote_jid, MSG_OUT_OF_CONTEXT_DEFAULT)
            return

    # Atalho Global Escapar
    if step != "menu" and txt_lower in ("voltar", "v") and not step.startswith("select_specific") and not step.startswith("select_bulk") and not step.startswith("type_bulk"):
        state["clinic_step"] = "menu"
        await send(remote_jid, MSG_CLINIC_MENU)
        return

    # ========== MENU PRINCIPAL ==========
    if step == "menu":
        if text == "1":
            state["clinic_step"] = "menu_agenda"
            await send(remote_jid, MSG_CLINIC_MENU_AGENDA)
        elif text == "2":
            state["clinic_step"] = "menu_envios"
            await send(remote_jid, MSG_CLINIC_MENU_ENVIOS)
        elif text == "3":
            state["clinic_step"] = "menu_cadastros"
            await send(remote_jid, MSG_CLINIC_MENU_CADASTROS)
        elif text == "4":
            state["clinic_step"] = "menu_busca"
            await send(remote_jid, MSG_CLINIC_MENU_BUSCA)
        elif text == "5":
            # 5. Pesquisa de exames
            await send(remote_jid, "📄 *Central de Documentos*\n\nPor favor, digite o *CPF* do paciente para buscar exames/documentos:")
            state["clinic_step"] = "search_docs"
        elif text == "6":
             # 6. Métricas PO
             from src.handlers.metrics_qa_po import handle_metrics
             await handle_metrics(remote_jid, state)
        elif text == "7":
             if remote_jid in active_sessions_ref():
                 del active_sessions_ref()[remote_jid]
             await send(remote_jid, MSG_ENCERRAR)
        else:
             await send(remote_jid, MSG_CLINIC_MENU)

    # ========== SUBMENU 1: AGENDAMENTOS ==========
    elif step == "menu_agenda":
        if text == "1":
            appointments = db_service.get_todays_appointments()
            waiting = [a for a in appointments if a.get("status") == "waiting"]
            in_treatment = [a for a in appointments if a.get("status") == "in_treatment"]
            
            msg = f"📊 *Relatório de Espera*\n\n"
            msg += f"Na Espera: {len(waiting)} paciente(s)\n"
            msg += f"Em Atendimento: {len(in_treatment)} paciente(s)\n\n"
            msg += "↩️ 9️⃣ Voltar para retornar ao menu."
            await send(remote_jid, msg)
            state["clinic_step"] = "viewing_report"
        elif text == "2":
            from src.handlers.clinic_scheduling import start_clinic_scheduling
            await start_clinic_scheduling(remote_jid, state)
        elif text == "3":
            from src.handlers.clinic_scheduling import start_clinic_reschedule
            await start_clinic_reschedule(remote_jid, state)
        elif text == "4":
            from src.handlers.clinic_scheduling import start_clinic_cancellation
            await start_clinic_cancellation(remote_jid, state)
        elif text == "9":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
        else:
            await send(remote_jid, MSG_CLINIC_MENU_AGENDA)

    # ========== SUBMENU 2: ENVIOS ==========
    elif step == "menu_envios":
        if text == "1":
            await format_and_send_date_pagination(remote_jid, state, "select_bulk_date", 0)
        elif text == "2":
            await format_and_send_date_pagination(remote_jid, state, "select_specific_patient", 0)
        elif text == "3":
            state["clinic_step"] = "send_msg_by_cpf"
            await send(remote_jid, "📨 *Mensagem por CPF*\n\nPor favor, informe o *CPF* do paciente:")
        elif text == "9":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
        else:
            await send(remote_jid, MSG_CLINIC_MENU_ENVIOS)

    # Lógica Submenu 2 (MENSAGENS POR CPF)
    elif step == "send_msg_by_cpf":
        if text.strip() == "9":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        clean_cpf = "".join(filter(str.isdigit, text))
        if len(clean_cpf) != 11:
            await send(remote_jid, "CPF inválido. Digite 11 números ou 9 para voltar.")
            return
            
        p = db_service.get_patient_by_cpf(clean_cpf)
        if not p:
            await send(remote_jid, "❌ Paciente não encontrado.\n👉 Digite outro CPF ou 9 para voltar.")
            return
            
        state["clinic_target_patient"] = p
        state["clinic_step"] = "type_msg_by_cpf"
        await send(remote_jid, f"Paciente encontrado: *{p.get('name')}*.\n\nDigite a mensagem que deseja enviar para este paciente (WhatsApp e Email):")
        
    elif step == "type_msg_by_cpf":
        p = state.get("clinic_target_patient")
        if p:
            # WhatsApp
            if p.get("phone"):
                 try:
                     import asyncio
                     from src.services.evolution import evo_service
                     asyncio.create_task(evo_service.send_text_message(p["phone"], text))
                 except: pass
                 
            # E-mail
            if p.get("email"):
                 try:
                     from src.services.email_service import send_email
                     asyncio.create_task(asyncio.to_thread(send_email, p["email"], "Mensagem do Consultório", text))
                 except: pass
                 
        await send(remote_jid, "✅ Mensagem Enviada com Sucesso para WhatsApp e E-mail.")
        state["clinic_step"] = "menu"
        state["clinic_target_patient"] = None
        await send(remote_jid, MSG_CLINIC_MENU)


    # Lógica Submenu 2 (Lote: Datas)
    elif step == "select_bulk_date":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu_envios"
            await send(remote_jid, MSG_CLINIC_MENU_ENVIOS)
            return
        elif text == "8":
            offset = state.get("clinic_date_offset", 0) + 7
            await format_and_send_date_pagination(remote_jid, state, "select_bulk_date", offset)
            return

        date_map = state.get("clinic_date_map", {})
        if text in date_map:
            selected_date = date_map[text]
            state["selected_bulk_date"] = selected_date
            
            # Novo Passo: Selecionar Horários Ocupados
            appts = db_service.get_appointments_by_date(datetime.strptime(selected_date, "%Y-%m-%d").date())
            if not appts:
                await send(remote_jid, "Não há consultas agendadas para este dia.\n↩️ 9️⃣ Voltar.")
                return
                
            msg = "Selecione os horários (pacientes) que deseja notificar:\n\n"
            bulk_time_map = {}
            for i, a in enumerate(appts):
                idx = i + 1
                h_str = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00")).strftime("%H:%M")
                p_name = a.get("patients", {}).get("name", "Desconhecido")
                msg += f"{idx}️⃣ {h_str} - {p_name}\n"
                bulk_time_map[str(idx)] = a
            
            msg += f"\n{len(appts)+1}️⃣ *Todos os horários*\n"
            msg += "\n↩️ 9️⃣ Voltar"
            msg += "\n\n👉 Digite os números separados por vírgula ou o número da opção 'Todos':"
            
            state["clinic_bulk_time_map"] = bulk_time_map
            state["clinic_step"] = "select_bulk_times"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "Opção inválida. Escolha um número válido ou 9️⃣ Voltar.")

    elif step == "select_bulk_times":
        if text == "9" or txt_lower == "voltar":
            await format_and_send_date_pagination(remote_jid, state, "select_bulk_date", 0)
            return
            
        bulk_time_map = state.get("clinic_bulk_time_map", {})
        choices = [c.strip() for c in text.split(",")]
        
        selected_appts = []
        # Opção "Todos"
        if str(len(bulk_time_map) + 1) in choices or txt_lower == "todos":
            selected_appts = list(bulk_time_map.values())
        else:
            for c in choices:
                if c in bulk_time_map:
                    selected_appts.append(bulk_time_map[c])
        
        if selected_appts:
            state["selected_bulk_appts"] = selected_appts
            state["clinic_step"] = "type_bulk_message"
            
            p_names = ", ".join([a.get("patients", {}).get("name", "??") for a in selected_appts[:3]])
            if len(selected_appts) > 3: p_names += "..."
            
            await send(remote_jid, f"✅ {len(selected_appts)} horário(s) selecionado(s) de {p_names}.\n\nDigite a mensagem para disparar (WhatsApp e Email):")
        else:
            await send(remote_jid, "Não identifiquei as opções. Digite os números ou 9️⃣ Voltar.")

    elif step == "type_bulk_message":
        appts = state.get("selected_bulk_appts", [])
        count_wa, count_em = 0, 0
        from src.services.evolution import evo_service
        from src.services.email_service import send_email
        
        await send(remote_jid, "⏳ Iniciando envios. Por favor, aguarde...")
        
        for a in appts:
             p = a.get("patients", {})
             if p.get("phone"):
                 try:
                     asyncio.create_task(evo_service.send_text_message(p["phone"], text))
                     count_wa += 1
                     await asyncio.sleep(0.5) 
                 except: pass
             if p.get("email"):
                 try:
                     asyncio.create_task(asyncio.to_thread(send_email, p["email"], "Mensagem do Consultório", text))
                     count_em += 1
                 except: pass
                 
        await send(remote_jid, f"✅ Mensagem enviada com sucesso!\n{count_wa} via WhatsApp\n{count_em} via E-mail\n\nVoltando ao menu...")
        state["clinic_step"] = "menu"
        await send(remote_jid, MSG_CLINIC_MENU)

    # Lógica Submenu 2 (Específico: Datas/Horários)
    elif step == "select_specific_patient":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu_envios"
            await send(remote_jid, MSG_CLINIC_MENU_ENVIOS)
            return
        elif text == "8":
            offset = state.get("clinic_date_offset", 0) + 7
            await format_and_send_date_pagination(remote_jid, state, "select_specific_patient", offset)
            return

        date_map = state.get("clinic_date_map", {})
        if text in date_map:
            selected_date = date_map[text]
            state["selected_specific_date"] = selected_date
            appts = db_service.get_appointments_by_date(datetime.strptime(selected_date, "%Y-%m-%d").date())
            msg = "Perfeito! 😊\n\nVeja os horários disponíveis para o dia escolhido:\n\n"
            time_map = {}
            for i, a in enumerate(appts):
                idx = i + 1
                try:
                    h_str = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00")).strftime("%H:%M")
                except:
                    h_str = "??"
                msg += f"{idx}️⃣ {h_str}\n"
                time_map[str(idx)] = a
            
            msg += "\n↩️ 8️⃣ Voltar para escolher outra data"
            msg += "\n\n👉 Me diga o número ou os números (separados por vírgula) das opções:"
            
            state["clinic_time_map"] = time_map
            state["clinic_step"] = "select_specific_times"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "Opção inválida.")
            
    elif step == "select_specific_times":
        if text == "8" or txt_lower == "voltar":
            await format_and_send_date_pagination(remote_jid, state, "select_specific_patient", 0)
            return
            
        time_map = state.get("clinic_time_map", {})
        choices = [c.strip() for c in text.split(",")]
        
        selected_appts = []
        for c in choices:
            if c in time_map:
                selected_appts.append(time_map[c])
                
        if selected_appts:
            state["selected_specific_appts"] = selected_appts
            state["clinic_step"] = "type_specific_message_list"
            p_name = selected_appts[0].get("patients", {}).get("name", "Paciente")
            await send(remote_jid, f"✅ {len(selected_appts)} horário(s) selecionado(s) de {p_name}.\n\nDigite a mensagem para disparar (WhatsApp e Email):")
        else:
            await send(remote_jid, "Não identifiquei as opções corretas. Digite 8️⃣ Voltar.")

    elif step == "type_specific_message_list":
        appts = state.get("selected_specific_appts", [])
        count_wa, count_em = 0, 0
        from src.services.evolution import evo_service
        from src.services.email_service import send_email
        
        await send(remote_jid, "⏳ Enviando...")
        
        for a in appts:
             p = a.get("patients", {})
             if p.get("phone"):
                 try:
                     asyncio.create_task(evo_service.send_text_message(p["phone"], text))
                     count_wa += 1
                     await asyncio.sleep(0.5)
                 except: pass
             if p.get("email"):
                 try:
                     asyncio.create_task(asyncio.to_thread(send_email, p["email"], "Mensagem do Consultório", text))
                     count_em += 1
                 except: pass
                 
        await send(remote_jid, f"✅ Mensagem disparada!\n{count_wa} WhatsApp\n{count_em} E-mails.\n\nVoltando ao menu...")
        state["clinic_step"] = "menu_envios"
        await send(remote_jid, MSG_CLINIC_MENU_ENVIOS)


    # ========== SUBMENU 3: CADASTROS ==========
    elif step == "menu_cadastros":
        if text == "1":
            from src.handlers.clinic_onboarding import start_clinic_onboarding_fast
            await start_clinic_onboarding_fast(remote_jid, state)
        elif text == "2":
            state["clinic_step"] = "onboarding_update_ask_cpf"
            await send(remote_jid, "🔄 *Atualizar Cadastro*\n\nPor favor, informe o *CPF* do paciente (apenas números):")
        elif text == "9":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
        else:
            await send(remote_jid, MSG_CLINIC_MENU_CADASTROS)


    # ========== SUBMENU 4: BUSCAR PACIENTES ==========
    elif step == "menu_busca":
        if text == "1":
             await send(remote_jid, "🔍 Por favor, digite o *CPF* do paciente (apenas números):")
             state["clinic_step"] = "search_cpf"
        elif text == "2":
             await send(remote_jid, "📜 *Histórico de Consultas*\n\nPor favor, digite o *CPF* do paciente para listar todas as consultas:")
             state["clinic_step"] = "search_history"
        elif text == "3":
             state["clinic_step"] = "search_flexible_ficha"
             await send(remote_jid, MSG_SEARCH_PATIENT_PROMPT)
        elif text == "9":
             state["clinic_step"] = "menu"
             await send(remote_jid, MSG_CLINIC_MENU)
        else:
             await send(remote_jid, MSG_CLINIC_MENU_BUSCA)

    elif step == "search_cpf":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu_busca"
            await send(remote_jid, MSG_CLINIC_MENU_BUSCA)
            return

        clean_cpf = "".join(filter(str.isdigit, text))
        if len(clean_cpf) == 11:
            p = db_service.get_patient_by_cpf(clean_cpf)
            if p:
                msg = f"🔎 *Paciente Encontrado*\n\n"
                msg += f"Nome: {p.get('name')}\n"
                msg += f"Telefone: {p.get('phone')}\n"
                msg += f"E-mail: {p.get('email', 'Sem e-mail')}\n"
                msg += f"Convênio: {p.get('insurance', 'Particular')}\n"
                
                patient_appts = db_service.get_patient_appointments(p["id"])
                from datetime import timezone
                agora = datetime.now(timezone.utc)
                
                future_appts = []
                for a in patient_appts:
                    try:
                        d_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                        if d_obj >= agora:
                            future_appts.append((d_obj, a))
                    except: pass
                
                if not future_appts:
                    msg += "Consulta Agendada: Sem Agendamento\n\n"
                else:
                    for d_obj, a in future_appts:
                        msg += f"Consulta Agendada: {d_obj.strftime('%d/%m/%Y')} às {d_obj.strftime('%H:%M')}\n"
                    msg += "\n"
                
                msg += "↩️ 9️⃣ Voltar"
            else:
                msg = "❌ Paciente não encontrado com esse CPF.\n↩️ 9️⃣ Voltar."
            state["clinic_step"] = "viewing_report_busca"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "CPF inválido. Envie 11 números ou 9️⃣ Voltar.")
    elif step == "search_flexible_ficha":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu_busca"
            await send(remote_jid, MSG_CLINIC_MENU_BUSCA)
            return

        patients = db_service.search_patient_flexible(text)
        if not patients:
            await send(remote_jid, "❌ Nenhum paciente encontrado com esses dados.\n👉 Tente novamente ou 9️⃣ Voltar.")
            return

        if len(patients) > 1:
            msg = "Encontrei mais de um paciente. Por favor, escolha o correto:\n\n"
            p_map = {}
            for i, p in enumerate(patients):
                idx = i + 1
                msg += f"{idx}️⃣ {p['name']} ({p.get('cpf', 'S/ CPF')})\n"
                p_map[str(idx)] = p
            state["clinic_search_results"] = p_map
            state["clinic_step"] = "select_flexible_result"
            await send(remote_jid, msg)
            return
        
        # Apenas um encontrado
        await show_patient_ficha(remote_jid, state, patients[0])

    elif step == "select_flexible_result":
        p_map = state.get("clinic_search_results", {})
        if text in p_map:
            await show_patient_ficha(remote_jid, state, p_map[text])
        else:
            await send(remote_jid, "Opção inválida. Escolha um número da lista.")

    elif step == "view_patient_ficha_actions":
        p = state.get("clinic_target_patient")
        if not p:
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return

        if text == "1": # Consultas Agendadas
            patient_appts = db_service.get_patient_appointments(p["id"])
            if not patient_appts:
                await send(remote_jid, "Não há consultas agendadas para este paciente.")
            else:
                msg = f"🗓️ *Consultas Agendadas de {p['name']}*\n\n"
                for a in patient_appts:
                    d_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                    msg += f"• {d_obj.strftime('%d/%m/%Y às %H:%M')}\n"
                await send(remote_jid, msg)
            await send(remote_jid, MSG_CLINIC_DETAILS_SEARCH_MENU)
            
        elif text == "2": # Remarcar
            from src.handlers.clinic_scheduling import start_clinic_reschedule_for_patient
            await start_clinic_reschedule_for_patient(remote_jid, state, p)
            
        elif text == "3": # Cancelar
            from src.handlers.clinic_scheduling import start_clinic_cancellation_for_patient
            await start_clinic_cancellation_for_patient(remote_jid, state, p)
            
        elif text == "4": # Agendar
            from src.handlers.clinic_scheduling import start_clinic_scheduling_for_patient
            await start_clinic_scheduling_for_patient(remote_jid, state, p)
            
        elif text == "9":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)

    elif step == "search_history":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu_busca"
            await send(remote_jid, MSG_CLINIC_MENU_BUSCA)
            return

        clean_cpf = "".join(filter(str.isdigit, text))
        if len(clean_cpf) == 11:
            p = db_service.get_patient_by_cpf(clean_cpf)
            if p:
                history = db_service.get_patient_full_history(p["id"])
                if not history:
                    msg = f"📜 *Histórico - {p.get('name')}*\n\nNão foram encontradas consultas no histórico desse paciente.\n\n↩️ 9️⃣ Voltar"
                else:
                    msg = f"📜 *Histórico - {p.get('name')}*\n\n"
                    for a in history:
                        try:
                            d_obj = datetime.fromisoformat(a["start_time"].replace("Z", "+00:00"))
                            d_str = d_obj.strftime("%d/%m/%Y")
                            h_str = d_obj.strftime("%H:%M")
                            status = a.get("status")
                            status_label = "✅" if status == "completed" else "🗓️" if status == "scheduled" else "❌" if status == "cancelled" else "⏳"
                            msg += f"{status_label} {d_str} às {h_str}\n"
                        except: pass
                    msg += "\n↩️ 9️⃣ Voltar"
            else:
                msg = "❌ Paciente não encontrado com esse CPF.\n↩️ 9️⃣ Voltar."
            state["clinic_step"] = "viewing_report_busca"
            await send(remote_jid, msg)
        else:
            await send(remote_jid, "CPF inválido. Envie 11 números ou 9️⃣ Voltar.")

    elif step == "viewing_report_busca":
         if text in ("9", "voltar"):
             state["clinic_step"] = "menu_busca"
             await send(remote_jid, MSG_CLINIC_MENU_BUSCA)

    elif step == "search_docs":
        if text == "9" or txt_lower == "voltar":
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        clean_cpf = "".join(filter(str.isdigit, text))
        docs = db_service.get_patient_documents(clean_cpf)
        if not docs:
            await send(remote_jid, "📉 Nenhum documento/exame encontrado para este CPF (ou funcionalidade em construção no Drive).\n↩️ 9️⃣ Voltar.")
        else:
            await send(remote_jid, "Documentos encontrados! (Em construção)\n↩️ 9️⃣ Voltar.")
        state["clinic_step"] = "viewing_report"
        

def normalize_date(date_str):
    """Normaliza datas de YYYY-MM-DD ou DD/MM/YYYY para DD/MM/YYYY."""
    if not date_str or date_str == "Não informado":
        return "Não informado"
    try:
        # Tenta YYYY-MM-DD
        if "-" in date_str:
            parts = date_str.split("-")
            if len(parts[0]) == 4: # YYYY-MM-DD
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
        return date_str
    except:
        return date_str

async def show_patient_ficha(remote_jid, state, p):
    """Exibe os dados detalhados do paciente e o menu de ações."""
    msg = f"🔎 *Ficha do Paciente*\n\n"
    msg += f"Nome: {p.get('name')}\n"
    msg += f"CPF: {p.get('cpf')}\n"
    msg += f"Telefone: {p.get('phone')}\n"
    msg += f"E-mail: {p.get('email', 'Sem e-mail')}\n"
    msg += f"Convênio: {p.get('insurance', 'Particular')}\n"
    msg += f"CEP: {p.get('cep', 'Não informado')}\n"
    birth = p.get('birth_date') or p.get('data_de_nascimento')
    msg += f"Nascimento: {normalize_date(birth)}\n\n"
    
    msg += MSG_CLINIC_DETAILS_SEARCH_MENU
    
    state["clinic_target_patient"] = p
    state["clinic_step"] = "view_patient_ficha_actions"
    await send(remote_jid, msg)

# Helper function to avoid circular imports / missing deps
def active_sessions_ref():
    from src.services.sessions import active_sessions
    return active_sessions

# Helper paginador de datas
async def format_and_send_date_pagination(remote_jid: str, state: dict, step_name: str, offset: int):
    dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    dates, total_found = db_service.get_upcoming_appointment_dates(limit=7, offset=offset)
    
    if not dates and offset == 0:
        await send(remote_jid, "Não há consultas agendadas nos próximos 60 dias.\n↩️ 9️⃣ Voltar ao menu principal")
        state["clinic_step"] = "viewing_report" # Will fall back to menu on 9
        return
    elif not dates:
        await send(remote_jid, "Não há mais datas adiante.\n↩️ 9️⃣ Voltar")
        return
        
    msg = "Aqui estão as próximas datas com consultas marcadas 😊\n\n"
    date_map = {}
    for i, d in enumerate(dates):
        idx = i + 1
        d_fmt = d.strftime("%d/%m")
        w_day = dias_semana[d.weekday()]
        msg += f"{idx}️⃣ {d_fmt} ({w_day})\n"
        date_map[str(idx)] = d.isoformat()
        
    if total_found == 7:
        msg += "\n8️⃣ Ver mais datas disponíveis\n"
    
    msg += "\n↩️ 9️⃣ Voltar\n\n👉 Digite o número correspondente:"
    state["clinic_step"] = step_name
    state["clinic_date_map"] = date_map
    state["clinic_date_offset"] = offset
    await send(remote_jid, msg)
