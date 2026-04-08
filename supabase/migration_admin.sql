-- ════════════════════════════════════════════════════
-- Migration: Camada Administrativa e Kanban
-- ════════════════════════════════════════════════════

-- 1. Cria a tabela de administradores autorizados
CREATE TABLE IF NOT EXISTS public.authorized_admins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone TEXT UNIQUE NOT NULL,    -- Ex: 5511999999999
    name TEXT,
    role TEXT DEFAULT 'admin',     -- 'owner' ou 'admin'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now()) NOT NULL
);

-- Insere o Dono (Acesso total inclusive a /acessar)
INSERT INTO public.authorized_admins (phone, name, role) 
VALUES ('5511999999999', 'Dono / Owner', 'owner')
ON CONFLICT (phone) DO NOTHING;

-- Insere os outros números liberados inicialmente para /consultorio
INSERT INTO public.authorized_admins (phone, name, role) VALUES 
('5511999999998', 'Admin 1', 'admin'),
('5511999999997', 'Admin 2', 'admin'),
('5511999999996', 'Admin 3', 'admin')
ON CONFLICT (phone) DO NOTHING;

-- 2. Atualiza os status aceitos na tabela appointments
-- Remove a constraint antiga de status (se ela existir e tiver o nome padrao do postgres para constraint inline)
ALTER TABLE public.appointments DROP CONSTRAINT IF EXISTS appointments_status_check;

-- Adiciona novas colunas para o rastreio do Kanban
ALTER TABLE public.appointments 
ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc', now());

-- Adiciona nova checagem de status com as novas etapas do Kanban
ALTER TABLE public.appointments 
ADD CONSTRAINT appointments_status_check 
CHECK (status IN ('scheduled', 'confirmed', 'waiting', 'in_treatment', 'completed', 'cancelled'));

-- Função para atualizar status_updated_at quando houver update no status
CREATE OR REPLACE FUNCTION update_status_timestamp()
RETURNS TRIGGER AS $$
BEGIN 
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        NEW.status_updated_at = timezone('utc', now());
    END IF;
    RETURN NEW; 
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS appointments_status_update ON public.appointments;
CREATE TRIGGER appointments_status_update
BEFORE UPDATE ON public.appointments
FOR EACH ROW EXECUTE FUNCTION update_status_timestamp();
