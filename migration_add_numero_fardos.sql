-- Migration to add numero_fardos column to itens_compra table
-- This script adds a new column numero_fardos to store the number of bundles/bales per item

ALTER TABLE itens_compra 
ADD COLUMN numero_fardos INT NULL COMMENT 'Número de fardos por item';

-- Optional: Add index for better performance if needed in the future
-- CREATE INDEX idx_itens_compra_numero_fardos ON itens_compra(numero_fardos);