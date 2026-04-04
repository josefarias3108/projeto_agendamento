-- ════════════════════════════════════════════════════
-- Migration: Adiciona coluna google_event_id na tabela appointments
-- Execute no Supabase: Database > SQL Editor > New Query
-- ════════════════════════════════════════════════════

ALTER TABLE public.appointments
  ADD COLUMN IF NOT EXISTS google_event_id TEXT;

-- Comentário opcional da coluna
COMMENT ON COLUMN public.appointments.google_event_id
  IS 'ID do evento no Google Calendar. Null = ainda não sincronizado.';
