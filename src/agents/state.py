from typing import TypedDict, Annotated, Sequence, Optional
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    remote_jid: str

    # Dados do paciente
    patient_id: Optional[str]
    name: Optional[str]
    email: Optional[str]
    cpf: Optional[str]
    cep: Optional[str]
    address: Optional[str]
    insurance: Optional[str]       # Nome do plano (ex: "Unimed")
    birth_date: Optional[str]      # Data de nascimento (novo campo)
    is_registered: bool            # True se paciente já existe no banco
    temp_new_phone: Optional[str]  # Temporário para guardar o novo número de troca
    date_options: list[str]        # Lista de datas sugeridas (menu)
    date_page: int                 # Paginação do menu de datas
    selected_date: str             # Data escolhida pelo usuário
    hour_options: list[int]        # Lista de horas sugeridas (menu)
    cep_address_base: Optional[str]  # Endereço base retornado pela ViaCEP
    _insurance_subs: Optional[list]  # Subcategorias do plano em seleção

    # Controle de fluxo conversacional
    conversation_step: str         # "welcome", "menu", "booking", "rebooking"
    intent: Optional[str]          # "agendar", "remarcar", "info"

    # Dados do agendamento
    doctor_id: Optional[str]
    appointment_time: Optional[str]
    missing_fields: list

    # Anti-loop
    loop_count: int
