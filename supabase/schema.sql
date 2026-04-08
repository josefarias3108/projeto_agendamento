-- ════════════════════════════════════════════════════
-- Schema: Consultório Dr. João — Agente de Agendamento
-- ════════════════════════════════════════════════════

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── DOCTORS ──────────────────────────────────────────
CREATE TABLE public.doctors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    specialty TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    daily_limit INTEGER DEFAULT 11,          -- Max consultas/dia (08-19 excl. almoço = 11 slots)
    appointment_duration_minutes INTEGER DEFAULT 60,  -- 1 hora por consulta
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) NOT NULL
);

-- ── PATIENTS ─────────────────────────────────────────
CREATE TABLE public.patients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    remote_jid TEXT UNIQUE NOT NULL,         -- Número WhatsApp (identificador da sessão)
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT UNIQUE,                       -- Identificador principal do paciente
    address TEXT,                            -- Endereço completo
    cpf TEXT,
    insurance TEXT,                          -- Ex: "Unimed", "Bradesco Saúde", "Particular"
    insurance_category TEXT,                 -- Ex: "Unimed Nacional", "Bradesco Top Executivo"
    birth_date DATE,                         -- Data de nascimento do paciente
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) NOT NULL
);

-- Atualiza updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = timezone('utc', now()); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER patients_updated_at
BEFORE UPDATE ON public.patients
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ── APPOINTMENTS ─────────────────────────────────────
CREATE TABLE public.appointments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID REFERENCES public.doctors(id) ON DELETE CASCADE,
    patient_id UUID REFERENCES public.patients(id) ON DELETE CASCADE,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('scheduled', 'cancelled', 'completed')),
    notified_24h BOOLEAN DEFAULT FALSE,
    notified_same_day BOOLEAN DEFAULT FALSE,
    notes TEXT,
    google_event_id TEXT,                    -- ID do evento no Google Calendar (sync automático)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) NOT NULL
);

-- Índice para prevenir Double Booking
CREATE UNIQUE INDEX no_double_booking_idx
ON public.appointments (doctor_id, start_time)
WHERE status = 'scheduled';

-- ── BLOCKED SLOTS (feriados / bloqueios manuais) ─────
CREATE TABLE public.blocked_slots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doctor_id UUID REFERENCES public.doctors(id) ON DELETE CASCADE,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT
);

-- ════════════════════════════════════════════════════
-- DADOS INICIAIS
-- ════════════════════════════════════════════════════

-- Inserir Dr. João como único médico da clínica
INSERT INTO public.doctors(name, specialty, active, appointment_duration_minutes, daily_limit)
VALUES ('Dr. João', 'Cardiologista', TRUE, 60, 11);

-- ════════════════════════════════════════════════════
-- MIGRAÇÕES (Execute apenas se já tiver tabelas existentes)
-- Descomente e rode se precisar atualizar sem recriar tudo:
-- ════════════════════════════════════════════════════
/*
ALTER TABLE public.patients
  ADD COLUMN IF NOT EXISTS email TEXT UNIQUE,
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS insurance_category TEXT,
  ADD COLUMN IF NOT EXISTS birth_date DATE,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now());

UPDATE public.doctors SET appointment_duration_minutes = 60 WHERE name ILIKE '%João%';
*/
