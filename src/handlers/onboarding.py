import logging
from src.config.messages import *
from src.database.client import db_service, lookup_cep
from src.services.evolution import evo_service

logger = logging.getLogger("CardioAgent")

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

async def handle_onboarding(remote_jid, state, text):
    step = state["conversation_step"]
    txt_lower = text.lower().strip()

    # Extração robusta do número (evita confusão entre 1 e 10)
    import re
    match = re.search(r'\d+', text)
    num_text = match.group() if match else ""

    # ══════════════════════════════════════════════════════════
    # ETAPA: ask_is_patient — "Já é nosso paciente? 1/2"
    # ══════════════════════════════════════════════════════════
    if step == "ask_is_patient":
        if num_text == "1" or "sim" in txt_lower:
            state["conversation_step"] = "ask_cpf_existing"
            await send(remote_jid, MSG_ASK_CPF)
        elif num_text == "2" or "não" in txt_lower or "nao" in txt_lower:
            state["conversation_step"] = "register_name"
            await send(remote_jid, MSG_REGISTER_START)
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "👉 Por favor, digite *1* (Sim) ou *2* (Não) para prosseguirmos.")
        return

    # ══════════════════════════════════════════════════════════
    # ETAPA: ask_update — "Houve mudança no cadastro? 1/2"
    # ══════════════════════════════════════════════════════════
    elif step == "ask_update":
        if num_text == "1" or "sim" in txt_lower:
            state["conversation_step"] = "register_name"
            await send(remote_jid, "Sem problema! Vamos atualizar seu cadastro. 📝\n\nQual é o seu *nome completo* atualizado?")
        elif num_text == "2" or "não" in txt_lower or "nao" in txt_lower:
            state["conversation_step"] = "menu"
            await send(remote_jid, MSG_WELCOME_BACK.format(name=state["name"]))
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "👉 Por favor, responda com *1* (Sim) ou *2* (Não).")
        return

    # ══════════════════════════════════════════════════════════
    # ETAPA: ask_cpf_existing
    # ══════════════════════════════════════════════════════════
    elif step == "ask_cpf_existing":
        from validate_docbr import CPF
        cpf_validator = CPF()
        
        # Limpa o CPF para a busca
        clean_cpf = "".join(filter(str.isdigit, text))
        
        # 1. Validação Matemática Rigorosa
        if clean_cpf and not cpf_validator.validate(clean_cpf):
            await send(remote_jid, "❌ Esse CPF é inválido. Por favor, digite os 11 números do seu CPF corretamente:")
            return

        patient = db_service.get_patient_by_cpf(clean_cpf)
        
        if patient:
            state.update({
                "patient_id": patient["id"],
                "name": patient["name"],
                "email": patient.get("email"),
                "cpf": patient.get("cpf"),
                "cep": patient.get("cep"),
                "address": patient.get("address"),
                "insurance": patient.get("insurance"),
                "is_registered": True
            })
            if patient.get("remote_jid") != remote_jid:
                state["temp_new_phone"] = remote_jid
                state["conversation_step"] = "ask_update_phone"
                await send(remote_jid, MSG_UPDATE_PHONE_ASK)
            else:
                state["conversation_step"] = "ask_update"
                await send(remote_jid, MSG_UPDATE_ASK.format(name=patient["name"]))
        else:
            # CPF Válido mas não encontrado — Salva como candidato para o cadastro
            state["candidate_cpf"] = clean_cpf
            state["conversation_step"] = "register_name"
            await send(remote_jid, MSG_CPF_NOT_FOUND)
        return

    # ══════════════════════════════════════════════════════════
    # ETAPA: ask_update_phone
    # ══════════════════════════════════════════════════════════
    elif step == "ask_update_phone":
        if num_text == "1" or "sim" in txt_lower:
            new_jid = state.get("temp_new_phone")
            new_phone = new_jid.split("@")[0]
            db_service.update_patient(state["patient_id"], remote_jid=new_jid, phone=new_phone)
            state["remote_jid"] = new_jid
            state["temp_new_phone"] = None
            await send(remote_jid, "Telefone atualizado com sucesso! ✅")
            state["conversation_step"] = "ask_update"
            await send(remote_jid, MSG_UPDATE_ASK.format(name=state["name"]))
        elif num_text == "2" or "não" in txt_lower or "nao" in txt_lower:
            state["temp_new_phone"] = None
            state["conversation_step"] = "ask_update"
            await send(remote_jid, MSG_UPDATE_ASK.format(name=state.get("name", "paciente")))
        else:
            await send(remote_jid, "⚠️ Por favor, digite *1* para confirmar a troca de número ou *2* para manter o antigo.")
        return

    # ══════════════════════════════════════════════════════════
    # ETAPAS DE CADASTRO
    # ══════════════════════════════════════════════════════════
    elif step == "register_name":
        state["name"] = text
        # Se veio de uma busca falha por CPF, oferece confirmação automática
        if state.get("candidate_cpf"):
            cpf = state["candidate_cpf"]
            fmt_cpf = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}" if len(cpf) == 11 else cpf
            state["conversation_step"] = "register_cpf_confirm"
            await send(remote_jid, f"Muito prazer, {text}! 😊 Agora, por favor, confirme:\n\nSeu CPF é *{fmt_cpf}*?\n\n1️⃣ Sim\n2️⃣ Não")
        else:
            state["conversation_step"] = "register_cpf"
            await send(remote_jid, MSG_ASK_CPF_NEW.format(name=text))

    elif step == "register_cpf_confirm":
        if num_text == "1" or "sim" in txt_lower:
            state["cpf"] = state["candidate_cpf"]
            state["conversation_step"] = "register_birth_date"
            await send(remote_jid, MSG_ASK_BIRTH_DATE)
        elif num_text == "2" or "não" in txt_lower or "nao" in txt_lower:
            state["conversation_step"] = "register_cpf"
            await send(remote_jid, "Tudo bem! Então, por favor, informe o seu *CPF* corretamente:")
        else:
            state["loop_count"] = state.get("loop_count", 0) + 1
            if state["loop_count"] >= 2:
                await send(remote_jid, MSG_GOLDEN_RULE_SUPPORT)
                state["loop_count"] = 0
            else:
                await send(remote_jid, "🤔 Por favor, responda com *1* (Sim) para confirmar ou *2* (Não).")

    elif step == "register_cpf":
        from validate_docbr import CPF
        cpf_validator = CPF()
        
        # Limpa o CPF para salvar apenas números
        clean_cpf = "".join(filter(str.isdigit, text))
        
        # 1. Validação Matemática
        if not cpf_validator.validate(clean_cpf):
            await send(remote_jid, "❌ Esse CPF é inválido. Por favor, digite os 11 números do seu CPF corretamente:")
            return

        # 2. Verificação de Duplicidade no Banco
        existing_patient = db_service.get_patient_by_cpf(clean_cpf)
        if existing_patient:
            state["loop_cpf_exists"] = state.get("loop_cpf_exists", 0) + 1
            
            if state["loop_cpf_exists"] == 1:
                await send(remote_jid, MSG_CPF_EXISTS_RETRY)
            else:
                # 2ª tentativa com CPF existente: redireciona para menu de antigo
                state["patient_id"] = existing_patient["id"]
                state["name"] = existing_patient["name"]
                state["conversation_step"] = "menu"
                await send(remote_jid, f"Olá, {existing_patient['name']}! 😊 Notei que você já tem cadastro conosco.\n\nComo posso te ajudar hoje?")
                await send(remote_jid, MSG_MENU.format(name=existing_patient['name']))
            return

        # 3. Sucesso: CPF válido e único
        state["cpf"] = clean_cpf
        state["conversation_step"] = "register_birth_date"
        await send(remote_jid, MSG_ASK_BIRTH_DATE)
    elif step == "register_birth_date":
        # Normalização: remove barras e espaços, deixa apenas números
        clean_date = "".join(filter(str.isdigit, text))
        
        if len(clean_date) == 8:
            day = clean_date[:2]
            month = clean_date[2:4]
            year = clean_date[4:]
            # Validação no formato brasileiro, mas salvamento no formato ISO (YYYY-MM-DD) para o banco
            display_date = f"{day}/{month}/{year}"
            db_date = f"{year}-{month}-{day}"
            
            try:
                from datetime import datetime
                # Valida se é uma data real (ex: evita 31/02/1984)
                datetime.strptime(display_date, "%d/%m/%Y")
                state["birth_date"] = db_date
                state["conversation_step"] = "register_cep"
                await send(remote_jid, MSG_ASK_CEP_NEW)
            except ValueError:
                await send(remote_jid, "⚠️ Ops! Essa data parece inválida (ex: 31/02 ou mês inexistente).\n\nPor favor, informe sua *Data de Nascimento* corretamente:\n👉 *31/08/1984* ou *31081984*")
        else:
            await send(remote_jid, "🤔 Não consegui entender o formato.\n\nPor favor, informe sua *Data de Nascimento* usando um destes formatos:\n👉 *31/08/1984* (com barras)\n👉 *31081984* (apenas números)")
        return
    elif step == "register_cep":
        cep_data = await lookup_cep(text)
        if not cep_data:
            await send(remote_jid, MSG_CEP_NOT_FOUND)
            return
        state["cep"] = "".join(filter(str.isdigit, text))
        state["cep_address_base"] = f"{cep_data.get('logradouro', '')}, {cep_data.get('bairro', '')}, {cep_data.get('localidade', '')} – {cep_data.get('uf', '')}"
        state["conversation_step"] = "register_cep_confirm"
        await send(remote_jid, MSG_CEP_CONFIRM.format(
            logradouro=cep_data.get("logradouro", "—"),
            bairro=cep_data.get("bairro", "—"),
            cidade=cep_data.get("localidade", "—"),
            uf=cep_data.get("uf", "—")
        ))
    elif step == "register_cep_confirm":
        if txt_lower in SIM_OPTIONS:
            state["conversation_step"] = "register_address_complement"
            await send(remote_jid, MSG_ASK_COMPLEMENT)
        elif txt_lower in NAO_OPTIONS:
            state["cep_address_base"] = None
            state["conversation_step"] = "register_address"
            await send(remote_jid, MSG_ASK_ADDRESS)
        else:
            await send(remote_jid, "🤔 Digite *1* se o endereço estiver correto ou *2* para digitar manualmente.")
    elif step == "register_address_complement":
        base = state.get("cep_address_base", "")
        complemento = text.strip()
        state["address"] = f"{base}, {complemento}" if complemento else base
        if state.get("intent") == "update":
            await _finalize_update(remote_jid, state, {"address": state["address"], "cep": state["cep"]})
        else:
            state["conversation_step"] = "register_email"
            await send(remote_jid, MSG_ASK_EMAIL_NEW)
    elif step == "register_address":
        state["address"] = text
        if state.get("intent") == "update":
            await _finalize_update(remote_jid, state, {"address": state["address"]})
        else:
            state["conversation_step"] = "register_email"
            await send(remote_jid, MSG_ASK_EMAIL_NEW)
    elif step == "register_email":
        state["email"] = text.lower().strip()
        if state.get("intent") == "update":
            await _finalize_update(remote_jid, state, {"email": state["email"]})
        else:
            state["conversation_step"] = "register_insurance"
            await send(remote_jid, MSG_ASK_INSURANCE)
    elif step == "register_insurance":
        if txt_lower in SIM_OPTIONS:
            state["conversation_step"] = "register_insurance_pick"
            await send(remote_jid, MSG_ASK_INSURANCE_MENU)
        elif txt_lower in NAO_OPTIONS:
            state["conversation_step"] = "register_insurance_particular"
            await send(remote_jid, MSG_PARTICULAR_CONFIRM)
        else:
            await send(remote_jid, "🤔 Não entendi. Você possui plano? Digite *1* (Sim) ou *2* (Não).")
    elif step == "register_insurance_particular":
        if txt_lower in SIM_OPTIONS:
            state["insurance"] = "Particular"
            await _save_and_finish(remote_jid, state)
        elif txt_lower in NAO_OPTIONS:
            state["conversation_step"] = "register_insurance"
            await send(remote_jid, MSG_ASK_INSURANCE)
        else:
            await send(remote_jid, "🤔 Por favor, digite *1* para confirmar particular ou *2* para voltar.")
    elif step == "register_insurance_pick":
        # ... logic for picks (can move helper here if needed)
        from src.handlers.helpers import handle_insurance_pick
        await handle_insurance_pick(remote_jid, state, text)
    elif step == "register_insurance_subcategory":
        from src.handlers.helpers import handle_insurance_subcategory
        await handle_insurance_subcategory(remote_jid, state, text)

async def _finalize_update(remote_jid, state, fields):
    if state.get("patient_id"):
        db_service.update_patient(state["patient_id"], **fields)
    state["conversation_step"] = "menu"
    state["intent"] = None
    await send(remote_jid, MSG_UPDATE_SUCCESS)
    await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))

async def _save_and_finish(remote_jid, state):
    patient = db_service.create_patient(
        jid=remote_jid,
        name=state["name"],
        phone=remote_jid.split("@")[0],
        email=state["email"],
        address=state["address"],
        cep=state["cep"],
        cpf=state["cpf"],
        birth_date=state["birth_date"],
        insurance=state["insurance"],
        insurance_category=state.get("insurance_category")
    )
    if patient:
        state["patient_id"] = patient["id"]
        state["is_registered"] = True
    
    # Extrai apenas o primeiro nome para a mensagem de sucesso
    first_name = state["name"].split()[0] if state.get("name") else "paciente"
    
    state["conversation_step"] = "menu_post_register"
    await send(remote_jid, MSG_REGISTER_DONE.format(first_name=first_name))
