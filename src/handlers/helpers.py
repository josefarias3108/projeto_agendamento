from src.config.messages import *
from src.database.client import db_service
from src.services.evolution import evo_service

async def send(remote_jid, text):
    await evo_service.send_text_message(remote_jid, text)

INSURANCE_NAMES = {
    "1": "Amil", "2": "Assim Saúde", "3": "Bradesco Saúde",
    "4": "Golden Cross", "5": "Klini Saúde", "6": "Leve Saúde",
    "7": "NotreDame Intermédica", "8": "Porto Seguro Saúde", "9": "SulAmérica Saúde"
}

INSURANCE_SUBCATEGORIES = {
    "Amil":                  ["Amil 750", "Amil 800", "Amil 900", "Amil 1000"],
    "Assim Saúde":           ["Assim Executivo", "Assim Superior"],
    "Bradesco Saúde":        ["Nacional Plus", "Premium"],
    "Golden Cross":          ["Golden Select", "Golden Premium"],
    "Klini Saúde":           ["Klini Top"],
    "Leve Saúde":            ["Leve Top"],
    "NotreDame Intermédica": ["Premium 800 / 900"],
    "Porto Seguro Saúde":    ["Porto Ouro", "Porto Diamante"],
    "SulAmérica Saúde":      ["Especial", "Executivo"],
}

async def handle_insurance_pick(remote_jid, state, text):
    txt_lower = text.lower().strip()
    if txt_lower in INSURANCE_NAMES:
        chosen = INSURANCE_NAMES[txt_lower]
        state["insurance"] = chosen
        subs = INSURANCE_SUBCATEGORIES[chosen]
        lines = [f"{i+1}️⃣ {s}" for i, s in enumerate(subs)]
        sub_msg = (
            f"Ótimo! Você escolheu *{chosen}* 😊\n\n"
            f"Agora selecione qual *modalidade* do plano:\n\n"
            + "\n".join(lines) +
            "\n\n🔟 Nenhum desses — voltar ao menu de planos"
            "\n\n👉 Digite o número da opção desejada"
        )
        state["_insurance_subs"] = subs
        state["conversation_step"] = "register_insurance_subcategory"
        await send(remote_jid, sub_msg)
    elif txt_lower == "10":
        state["insurance"] = "Particular"
        await _save_and_finish(remote_jid, state)
    elif txt_lower == "11" or txt_lower in NAO_OPTIONS: # 11 ou Voltar
        state["conversation_step"] = "register_insurance"
        await send(remote_jid, MSG_ASK_INSURANCE)
    else:
        await send(remote_jid, "🤔 Opção inválida. Por favor, digite o número do seu plano (1 a 9), *10* para Particular ou *11* para voltar.")

async def handle_insurance_subcategory(remote_jid, state, text):
    subs = state.get("_insurance_subs") or []
    if text.isdigit() and 1 <= int(text) <= len(subs):
        state["insurance_category"] = subs[int(text) - 1]
        state.pop("_insurance_subs", None)
        await _save_and_finish(remote_jid, state)
    elif text == "10" or txt_lower in NAO_OPTIONS: # 10 ou Voltar
        state["insurance"] = None
        state.pop("_insurance_subs", None)
        state["conversation_step"] = "register_insurance_pick"
        await send(remote_jid, MSG_ASK_INSURANCE_MENU)
    else:
        await send(remote_jid, "🤔 Opção inválida. Digite o número da sua modalidade no menu acima ou *10* para voltar.")

async def _save_and_finish(remote_jid, state):
    if state.get("intent") == "update" and state.get("patient_id"):
        db_service.update_patient(
            state["patient_id"],
            insurance=state["insurance"],
            insurance_category=state.get("insurance_category")
        )
        state["conversation_step"] = "menu"
        state["intent"] = None
        await send(remote_jid, MSG_UPDATE_SUCCESS)
        await send(remote_jid, MSG_MENU.format(name=state.get("name", "paciente")))
        return

    # Lógica de Cadastro Novo
    patient = None
    if state.get("patient_id"):
         patient = db_service.update_patient(
            state["patient_id"],
            insurance=state["insurance"],
            insurance_category=state.get("insurance_category")
        )
    else:
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
        
    name_val = state.get("name", "paciente")
    first_name = name_val.split()[0] if name_val else "paciente"
    state["conversation_step"] = "menu"
    await send(remote_jid, MSG_REGISTER_DONE.format(first_name=first_name))
