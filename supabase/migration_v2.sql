-- ════════════════════════════════════════════════════
-- MIGRATION: Adiciona campos de cadastro completo
-- Execute este arquivo no Supabase SQL Editor
-- ════════════════════════════════════════════════════

-- 1. Adiciona colunas faltantes na tabela patients
ALTER TABLE public.patients
  ADD COLUMN IF NOT EXISTS email TEXT,
  ADD COLUMN IF NOT EXISTS address TEXT,
  ADD COLUMN IF NOT EXISTS insurance_category TEXT,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now());

-- 2. Cria índice único no email (identificador principal)
CREATE UNIQUE INDEX IF NOT EXISTS patients_email_idx ON public.patients(email) WHERE email IS NOT NULL;

-- 3. Corrige duração das consultas: de 30min para 60min
UPDATE public.doctors
SET appointment_duration_minutes = 60
WHERE name ILIKE '%João%';

-- 4. Trigger para updated_at automático
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = timezone('utc', now()); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS patients_updated_at ON public.patients;
CREATE TRIGGER patients_updated_at
BEFORE UPDATE ON public.patients
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Confirma
SELECT 'Migration aplicada com sucesso!' AS resultado;
