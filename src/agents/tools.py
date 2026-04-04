from langchain_core.tools import tool
from src.database.client import db_service
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("CardioAgent")

@tool("verificar_disponibilidade")
def verificar_disponibilidade(data: str) -> str:
    """Verifica os horários disponíveis para consulta em uma data específica com o Dr. João.
    Args:
        data (str): A data desejada. Pode ser "amanhã", "hoje" ou formato DD/MM/AAAA ou AAAA-MM-DD.
    Returns:
        Texto com os horários livres ou motivo de indisponibilidade.
    """
    return db_service.check_availability(data)
    
@tool("buscar_proximas_vagas")
def buscar_proximas_vagas() -> str:
    """Busca as próximas 10 datas com horários disponíveis na agenda do Dr. João."""
    return db_service.find_next_available_dates()


@tool("agendar_consulta")
def agendar_consulta(patient_id: str, data_horario: str) -> str:
    """Agenda uma consulta para o paciente com o Dr. João.
    Args:
        patient_id (str): ID do paciente no banco de dados.
        data_horario (str): Data e hora da consulta em formato ISO8601, ex: "2026-04-06T09:00:00".
    Returns:
        Confirmação ou mensagem de erro.
    """
    doc = db_service.get_doctor_by_name("Dr. João")
    if not doc:
        return "Médico não encontrado. Entre em contato pelo telefone do consultório."

    try:
        start = datetime.fromisoformat(data_horario)
        end = start + timedelta(hours=1)
    except ValueError:
        return f"Formato de data inválido: '{data_horario}'. Use o formato AAAA-MM-DDTHH:MM:SS."

    # Valida o dia na própria ferramenta como segunda camada
    weekday = start.weekday()
    if weekday in [1, 3]:
        return "Terças e quintas são reservadas para cirurgias. Por favor escolha segunda, quarta ou sexta."
    if weekday >= 5:
        return "O consultório não atende fins de semana."
    if start.hour == 12 or start.hour == 13:
        return "Das 12h às 14h é horário de almoço. Escolha outro horário."
    if start.hour < 8 or start.hour >= 19:
        return "Horário fora do expediente. Atendemos das 08h às 19h."

    # Valida UUID do paciente
    if not patient_id or "{" in str(patient_id):
        return "ID de paciente inválido. Comece o atendimento do início por favor."

    res = db_service.book_appointment(patient_id, doc["id"], start.isoformat(), end.isoformat())

    if res["success"]:
        data_fmt = start.strftime("%d/%m/%Y às %H:%M")
        return (
            f"✅ Consulta agendada com sucesso para {data_fmt} com o Dr. João!\n\n"
            f"📄 *Não esqueça de trazer no dia:*\n"
            f"• Sua carteirinha do plano de saúde\n"
            f"• Um documento de identidade oficial com foto (RG ou CNH)\n\n"
            "Te esperamos lá! 😊"
        )
    else:
        logger.error(f"Erro no agendamento para {patient_id}: {res['error']}")
        return f"❌ Não foi possível agendar esse horário: {res['error']}"


@tool("buscar_consultas_paciente")
def buscar_consultas_paciente(patient_id: str) -> str:
    """Busca as próximas consultas agendadas de um paciente.
    Args:
        patient_id (str): ID do paciente.
    Returns:
        Lista de consultas futuras ou aviso de que não há consultas.
    """
    appts = db_service.get_appointments_by_patient(patient_id)
    if not appts:
        return "Não encontrei consultas futuras agendadas para você."

    lines = []
    for a in appts:
        start = datetime.fromisoformat(a["start_time"])
        lines.append(f"• {start.strftime('%d/%m/%Y às %H:%M')} com Dr. João")
    return "Suas próximas consultas:\n" + "\n".join(lines)


@tool("cancelar_consulta")
def cancelar_consulta(appointment_id: str) -> str:
    """Cancela uma consulta pelo ID do agendamento.
    Args:
        appointment_id (str): ID do agendamento a cancelar.
    Returns:
        Confirmação de cancelamento.
    """
    ok = db_service.cancel_appointment(appointment_id)
    if ok:
        return "✅ Consulta cancelada com sucesso."
    return "❌ Não foi possível cancelar. Tente novamente ou ligue para o consultório."


def get_tools():
    return [
        verificar_disponibilidade,
        buscar_proximas_vagas,
        agendar_consulta,
        buscar_consultas_paciente,
        cancelar_consulta,
    ]
