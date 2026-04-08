import logging
import re
from datetime import datetime
from src.database.client import db_service, lookup_cep
from src.handlers.helpers import INSURANCE_SUBCATEGORIES
from src.services.evolution import evo_service
from src.config.messages import *

logger = logging.getLogger("CardioAgent")

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

def is_valid_cpf(cpf: str) -> bool:
    cpf = "".join(filter(str.isdigit, cpf))
    if len(cpf) != 11 or len(set(cpf)) == 1:
        return False
    for i in range(9, 11):
        value = sum((int(cpf[num]) * ((i + 1) - num) for num in range(i)))
        digit = ((value * 10) % 11) % 10
        if digit != int(cpf[i]):
            return False
    return True

# ── FLUXO DE NOVO CADASTRO DA CLÍNICA ──

async def start_clinic_onboarding_fast(remote_jid, state, cpf=None):
    """Utilizado quando o agendamento requer paciente novo ou escolhido via menu."""
    state["clinic_step"] = "onboarding_ask_name"
    state["clinic_register_data"] = {}
    
    if cpf:
        state["clinic_register_data"]["cpf"] = cpf
        await send(remote_jid, f"📝 *Cadastro Rápido*\n\nCPF definido: {cpf}\nQual é o *Nome Completo* do paciente?")
    else:
        state["clinic_step"] = "onboarding_ask_cpf"
        await send(remote_jid, "📝 *Novo Cadastro*\n\nPara iniciar, por favor informe o *CPF* do paciente:")

async def handle_clinic_onboarding(remote_jid, state, text):
    txt_lower = text.lower().strip()
    step = state.get("clinic_step", "")

    if text.strip() == "9" and step != "onboarding_ask_cpf":
         # Global return
         pass 

    # ----- NOVO CADASTRO -----
    
    if step == "onboarding_ask_cpf":
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            from src.config.messages import MSG_CLINIC_MENU
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return

        clean_cpf = "".join(filter(str.isdigit, text))
        if not is_valid_cpf(clean_cpf):
            await send(remote_jid, "❌ CPF inválido. Por favor, digite um CPF válido (11 números) ou 9 para voltar.")
            return
            
        p = db_service.get_patient_by_cpf(clean_cpf)
        if p:
            await send(remote_jid, f"⚠️ Atenção, o CPF já está cadastrado para: {p.get('name')}.\n\nSe quiser atualizar os dados, volte ao menu e escolha Atualizar Cadastro.\n↩️ Voltando ao menu.")
            from src.config.messages import MSG_CLINIC_MENU
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        state["clinic_register_data"]["cpf"] = clean_cpf
        state["clinic_step"] = "onboarding_ask_name"
        await send(remote_jid, "Qual é o *Nome Completo* do paciente?")
        return

    if step == "onboarding_ask_name":
        state["clinic_register_data"]["name"] = text.strip()
        state["clinic_step"] = "onboarding_ask_phone"
        await send(remote_jid, "Qual é o *Telefone* (WhatsApp) do paciente?\n⚠️ *Formato:* 5521999999999\n(sem espaços, traços ou caracteres espciais)")
        return
        
    if step == "onboarding_ask_phone":
        clean_phone = "".join(filter(str.isdigit, text))
        
        # Padronização: se tiver 10 ou 11 dígitos, assume Brasil e adiciona 55
        if len(clean_phone) in (10, 11) and not clean_phone.startswith("55"):
            clean_phone = f"55{clean_phone}"
            
        if len(clean_phone) < 12:
             await send(remote_jid, "⚠️ Telefone inválido ou muito curto.\nDigite no formato com DDD: 5521999999999 (ou apenas o DDD e número)")
             return
             
        # Armazena o JID formatado do paciente
        state["clinic_register_data"]["remote_jid"] = f"{clean_phone}@s.whatsapp.net"
        state["clinic_register_data"]["phone"] = clean_phone
        state["clinic_step"] = "onboarding_ask_birth"
        await send(remote_jid, "Qual a *Data de Nascimento*? (DD/MM/AAAA)\n\n👉 *Digite 1 para pular essa etapa.*")
        return
        
    if step == "onboarding_ask_birth":
        if text.strip() == "1":
            state["clinic_step"] = "onboarding_ask_cep"
            await send(remote_jid, "Qual é o *CEP*?\n\n👉 *Digite 1 para pular essa etapa.*")
            return

        clean_date = "".join(filter(str.isdigit, text))
        if len(clean_date) == 8:
            day, month, year = clean_date[:2], clean_date[2:4], clean_date[4:]
            display_date = f"{day}/{month}/{year}"
            db_date = f"{year}-{month}-{day}"
            
            try:
                datetime.strptime(display_date, "%d/%m/%Y")
                state["clinic_register_data"]["birth_date"] = db_date
                state["clinic_step"] = "onboarding_ask_cep"
                await send(remote_jid, "Obrigada! Agora, qual é o *CEP*?\n\n👉 *Digite 1 para pular essa etapa.*")
            except ValueError:
                await send(remote_jid, "⚠️ Ops! Essa data parece inválida (ex: 31/02 ou mês inexistente).\n\nPor favor, informe a *Data de Nascimento* corretamente:\n👉 *31/08/1984* ou *31081984*")
        else:
            await send(remote_jid, "🤔 Não consegui entender o formato.\n\nPor favor, informe a *Data de Nascimento* usando um destes formatos:\n👉 *31/08/1984* (com barras)\n👉 *31081984* (apenas números)\n\n👉 *Ou digite 1 para pular.*")
        return

    if step == "onboarding_ask_cep":
        if text.strip() == "1":
            state["clinic_step"] = "onboarding_ask_email"
            await send(remote_jid, "Qual é o *E-mail*?\n\n👉 *Digite 1 para pular essa etapa.*")
            return

        cep_data = await lookup_cep(text)
        if not cep_data:
            await send(remote_jid, MSG_CEP_NOT_FOUND)
            return

        state["clinic_register_data"]["cep"] = "".join(filter(str.isdigit, text))
        state["clinic_register_data"]["cep_address_base"] = f"{cep_data.get('logradouro', '')}, {cep_data.get('bairro', '')}, {cep_data.get('localidade', '')} – {cep_data.get('uf', '')}"
        state["clinic_step"] = "onboarding_confirm_cep"
        
        await send(remote_jid, MSG_CEP_CONFIRM.format(
            logradouro=cep_data.get("logradouro", "—"),
            bairro=cep_data.get("bairro", "—"),
            cidade=cep_data.get("localidade", "—"),
            uf=cep_data.get("uf", "—")
        ))
        return

    if step == "onboarding_confirm_cep":
        if txt_lower in SIM_OPTIONS:
            state["clinic_step"] = "onboarding_ask_complement"
            await send(remote_jid, MSG_ASK_COMPLEMENT)
        elif txt_lower in NAO_OPTIONS:
            state["clinic_register_data"]["cep_address_base"] = None
            state["clinic_step"] = "onboarding_ask_manual_address"
            await send(remote_jid, MSG_ASK_ADDRESS)
        else:
            await send(remote_jid, "🤔 Digite *1* se o endereço estiver correto ou *2* para digitar manualmente.")
        return

    if step == "onboarding_ask_complement":
        base = state["clinic_register_data"].get("cep_address_base", "")
        complemento = text.strip()
        state["clinic_register_data"]["address"] = f"{base}, {complemento}" if complemento else base
        state["clinic_step"] = "onboarding_ask_email"
        await send(remote_jid, "Qual é o *E-mail*?\n\n👉 *Digite 1 para pular essa etapa.*")
        return

    if step == "onboarding_ask_manual_address":
        state["clinic_register_data"]["address"] = text.strip()
        state["clinic_step"] = "onboarding_ask_email"
        await send(remote_jid, "Qual é o *E-mail*?\n\n👉 *Digite 1 para pular essa etapa.*")
        return
        
    if step == "onboarding_ask_email":
        if text.strip() != "1":
            state["clinic_register_data"]["email"] = text.strip()
            
        state["clinic_step"] = "onboarding_ask_insurance"
        msg = MSG_ASK_INSURANCE_MENU.replace("↩️ 11️⃣ Voltar\n", "👉 *Digite 0 para pular*\n")
        await send(remote_jid, msg)
        return
        
    if step == "onboarding_ask_insurance":
        insurance = None
        match = re.search(r'\d+', text)
        if match:
            idx = int(match.group())
            if idx == 0:
                insurance = "Particular"
            elif idx == 1: insurance = "Amil"
            elif idx == 2: insurance = "Assim Saúde"
            elif idx == 3: insurance = "Bradesco Saúde"
            elif idx == 4: insurance = "Golden Cross"
            elif idx == 5: insurance = "Klini Saúde"
            elif idx == 6: insurance = "Leve Saúde"
            elif idx == 7: insurance = "NotreDame Intermédica"
            elif idx == 8: insurance = "Porto Seguro Saúde"
            elif idx == 9: insurance = "SulAmérica Saúde"
            elif idx == 10: insurance = "Particular"
            else:
                 await send(remote_jid, "Opção inválida.")
                 return
                 
        if insurance:
            state["clinic_register_data"]["insurance"] = insurance
            
            # Se for plano (não particular), pede a subcategoria
            if insurance != "Particular":
                subs = INSURANCE_SUBCATEGORIES.get(insurance, [])
                if subs:
                    state["_clinic_insurance_subs"] = subs
                    state["clinic_step"] = "onboarding_ask_insurance_subcategory"
                    lines = [f"{i+1}️⃣ {s}" for i, s in enumerate(subs)]
                    await send(remote_jid, f"Ótimo! Você escolheu *{insurance}* 😊\n\nAgora selecione qual *modalidade* do plano:\n\n" + "\n".join(lines) + "\n\n👉 Digite o número da opção desejada")
                    return
            
            # Se for particular ou não tiver subcategorias, finaliza
            await _finish_clinic_registration(remote_jid, state)
            return

    if step == "onboarding_ask_insurance_subcategory":
        subs = state.get("_clinic_insurance_subs", [])
        match = re.search(r'\d+', text)
        if match:
            idx = int(match.group())
            if 1 <= idx <= len(subs):
                state["clinic_register_data"]["insurance_category"] = subs[idx - 1]
                state.pop("_clinic_insurance_subs", None)
                await _finish_clinic_registration(remote_jid, state)
                return
        
        await send(remote_jid, "🤔 Opção inválida. Digite o número da modalidade correspondente.")
        return

    if step == "onboarding_update_ask_cpf":
        if text.strip() == "9" or txt_lower in ("voltar", "v"):
            from src.config.messages import MSG_CLINIC_MENU
            state["clinic_step"] = "menu"
            await send(remote_jid, MSG_CLINIC_MENU)
            return
            
        clean_cpf = "".join(filter(str.isdigit, text))
        if not is_valid_cpf(clean_cpf):
            await send(remote_jid, "❌ CPF inválido. Por favor, digite um CPF válido (11 números) ou 9 para voltar.")
            return
            
        p = db_service.get_patient_by_cpf(clean_cpf)
        if not p:
            await send(remote_jid, "❌ Paciente não encontrado com esse CPF.\nDigite outro CPF ou 9 para voltar.")
            return
            
        state["clinic_update_patient"] = p
        state["clinic_update_fields"] = [
            ("name", "Nome Completo"),
            ("remote_jid", "Telefone (WhatsApp)"),
            ("birth_date", "Data de Nascimento"),
            ("cep", "CEP"),
            ("email", "E-mail"),
            ("insurance", "Plano de Saúde")
        ]
        state["clinic_update_index"] = 0
        await _show_next_update_field(remote_jid, state)
        return

    if step == "onboarding_update_field":
        idx = state["clinic_update_index"]
        fields = state["clinic_update_fields"]
        current_field_key, current_field_name = fields[idx]
        p = state["clinic_update_patient"]
        
        # Validar clique em 1 (OK)
        # Ajuste: aceitar 1, OK, ok, Ok, oK
        is_ok = text.strip() == "1" or txt_lower in ("ok", "sim", "cadastro ok")
        
        if not is_ok:
             # Atualizar!
             db_val = text.strip()
             if current_field_key == "remote_jid":
                 clean_phone = "".join(filter(str.isdigit, db_val))
                 db_val = f"{clean_phone}@s.whatsapp.net"
                 
             if current_field_key == "insurance":
                 match = re.search(r'\d+', text)
                 if match:
                     i_idx = int(match.group())
                     if i_idx == 1: db_val = "Amil"
                     elif i_idx == 2: db_val = "Assim Saúde"
                     elif i_idx == 3: db_val = "Bradesco Saúde"
                     elif i_idx == 4: db_val = "Golden Cross"
                     elif i_idx == 5: db_val = "Klini Saúde"
                     elif i_idx == 6: db_val = "Leve Saúde"
                     elif i_idx == 7: db_val = "NotreDame Intermédica"
                     elif i_idx == 8: db_val = "Porto Seguro Saúde"
                     elif i_idx == 9: db_val = "SulAmérica Saúde"
                     elif i_idx == 10: db_val = "Particular"
                     else: db_val = "Particular"
                 else:
                     db_val = "Particular"

             db_service.update_patient(p["id"], {current_field_key: db_val})
             # update state too
             state["clinic_update_patient"][current_field_key] = db_val
             
        # Avançar para o proximo
        state["clinic_update_index"] += 1
        await _show_next_update_field(remote_jid, state)
        return

async def _finish_clinic_registration(remote_jid, state):
    data = state["clinic_register_data"]
    try:
        res = db_service.create_patient(
            jid=data.get("remote_jid"),
            name=data.get("name"),
            phone=data.get("phone") or data.get("remote_jid", "").split("@")[0],
            cpf=data.get("cpf"),
            email=data.get("email"),
            address=data.get("address"),
            cep=data.get("cep"),
            birth_date=data.get("birth_date"),
            insurance=data.get("insurance"),
            insurance_category=data.get("insurance_category")
        )
    except Exception as e:
        logger.error(f"Erro ao criar paciente no banco: {e}")
        await send(remote_jid, "❌ Erro ao salvar no banco de dados. Verifique se o CPF ou Telefone já estão cadastrados.\n\n↩️ Voltando ao menu.")
        from src.config.messages import MSG_CLINIC_MENU
        state["clinic_step"] = "menu"
        state["clinic_register_data"] = {}
        await send(remote_jid, MSG_CLINIC_MENU)
        return

    if not res:
        await send(remote_jid, "⚠️ Não foi possível concluir o cadastro. O paciente já pode existir no sistema.")
        state["clinic_step"] = "menu"
        state["clinic_register_data"] = {}
        from src.config.messages import MSG_CLINIC_MENU
        await send(remote_jid, MSG_CLINIC_MENU)
        return

    # Preparamos os dados para finalizar, mas já "limpamos" o estado de cadastro para evitar re-processamento
    has_appointment = bool(state.get("selected_hour") and state.get("selected_date"))
    
    # MENSAGEM PARA O FUNCIONÁRIO (CLERK)
    await send(remote_jid, "🎉 Cadastro efetuado com sucesso!\nVoltando ao menu principal.")
    
    # Limpeza antecipada do estado de cadastro
    state["clinic_step"] = "menu"
    state["clinic_register_data"] = {}

    # Verifica se havia agendamento pendente:
    if has_appointment:
        from src.handlers.clinic_scheduling import finalize_clinic_booking
        # O finalize_clinic_booking já enviará a mensagem detalhada ao PACIENTE e enviará o MSG_CLINIC_MENU ao Clerk.
        await finalize_clinic_booking(remote_jid, state, res)
        return
    else:
        # Se for APENAS cadastro (sem agendamento), apenas notifica o paciente
        p_name = res.get("name", "paciente")
        patient_welcome = f"✅ Olá, {p_name}! Seu cadastro foi realizado com sucesso em nosso consultório. Ficamos à disposição! 😊"
        p_phone = res.get("phone") or res.get("remote_jid")
        if p_phone:
            import asyncio
            from src.services.evolution import evo_service
            asyncio.create_task(evo_service.send_text_message(p_phone, patient_welcome))

    # Se chegou aqui, não houve agendamento, então enviamos o menu agora
    from src.config.messages import MSG_CLINIC_MENU
    await send(remote_jid, MSG_CLINIC_MENU)



async def _show_next_update_field(remote_jid, state):
    idx = state["clinic_update_index"]
    fields = state["clinic_update_fields"]
    p = state["clinic_update_patient"]
    
    if idx >= len(fields):
        # FIM!
        from src.config.messages import MSG_CLINIC_MENU
        state["clinic_step"] = "menu"
        await send(remote_jid, "✅ Atualização cadastral concluída com sucesso!")
        await send(remote_jid, MSG_CLINIC_MENU)
        return

    current_field_key, current_field_name = fields[idx]
    
    current_value = p.get(current_field_key)
    if current_value and current_field_key == "remote_jid":
        current_value = current_value.split("@")[0] # remove s.whatsapp.net for visual
    
    if not current_value:
        msg = f"📝 *Campo: {current_field_name}*\nNenhum dado cadastrado.\n\n👉 *Digite a informação correspondente* ou envie *1* para pular."
    else:
        msg = f"📝 *Campo: {current_field_name}*\nDado Atual: _{current_value}_\n\n👉 Escolha:\n*1* - Cadastro OK (manter igual)\n*Ou digite a nova informação para substituir.*"
        
    if current_field_key == "insurance":
         from src.config.messages import MSG_ASK_INSURANCE_MENU
         msg += "\n\n(Se for atualizar o plano, envie o NÚMERO correspondente da lista abaixo:\n"
         msg += MSG_ASK_INSURANCE_MENU.replace("↩️ 11️⃣ Voltar\n👉 Me diga o número da opção desejada", "")
        
    await send(remote_jid, msg)
    state["clinic_step"] = "onboarding_update_field"
