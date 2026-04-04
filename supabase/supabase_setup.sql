-- Execute esse código no SQL Editor do seu projeto Supabase

-- 1. Criação da tabela para armazenar os metadados dos exames
CREATE TABLE IF NOT EXISTS public.patient_exams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id UUID REFERENCES public.patients(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL, -- Caminho dentro do bucket
    file_url TEXT NOT NULL,  -- URL pública ou assinada
    file_type TEXT,         -- Ex: 'image/jpeg', 'application/pdf'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Criação do Bucket de Storage (via SQL)
-- Nota: Isso tenta criar o bucket diretamente. Se falhar por falta de permissão, siga o passo 3.
INSERT INTO storage.buckets (id, name, public)
VALUES ('exams', 'exams', true)
ON CONFLICT (id) DO NOTHING;

-- 3. Configuração de Políticas de Acesso (RLS) para o Storage
-- Permite que qualquer pessoa leia os arquivos (já que o bucket é público)
CREATE POLICY "Acesso Público de Leitura"
ON storage.objects FOR SELECT
USING (bucket_id = 'exams');

-- Permite inserção de arquivos no bucket 'exams'
CREATE POLICY "Permitir Upload de Exames"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'exams');

-- 4. Observações importantes:
-- - Certifique-se de que a tabela 'patients' já possui a coluna 'id' como UUID.
-- - Se o comando INSERT falhar, crie o bucket manualmente no painel Storage com o nome 'exams' e marque como PUBLIC.
