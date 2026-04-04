import logging
from datetime import datetime, timezone
from src.agents.state import AgentState

logger = logging.getLogger("CardioAgent")

# Memória de sessão centralizada para evitar dependências circulares
active_sessions: dict[str, AgentState] = {}

def create_initial_state(remote_jid, patient):
    """Cria o estado inicial para uma nova sessão ou paciente reconhecido."""
    return AgentState(
        messages=[],
        remote_jid=remote_jid,
        patient_id=patient["id"] if patient else None,
        name=patient.get("name") if patient else None,
        email=patient.get("email") if patient else None,
        cpf=patient.get("cpf") if patient else None,
        cep=patient.get("cep") if patient else None,
        address=patient.get("address") if patient else None,
        insurance=patient.get("insurance") if patient else None,
        birth_date=patient.get("birth_date") if patient else None,
        is_registered=True if patient else False,
        candidate_cpf=None,
        temp_new_phone=None,
        date_options=[],
        date_page=0,
        selected_date="",
        hour_options=[],
        cep_address_base=None,
        _insurance_subs=None,
        conversation_step="welcome",
        intent=None,
        doctor_id=None,
        appointment_time=None,
        missing_fields=[],
        loop_count=0,
        last_message_at=datetime.now(timezone.utc),
        inactivity_prompt_sent=False
    )
