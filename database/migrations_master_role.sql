ALTER TABLE usuarios
  ADD COLUMN IF NOT EXISTS nivel_acesso VARCHAR(20) NOT NULL DEFAULT 'user';

UPDATE usuarios
SET nivel_acesso = 'master'
WHERE email = COALESCE(NULLIF(current_setting('app.initial_admin_email', true), ''), 'admin@ideau.local')
  AND nivel_acesso <> 'master';
