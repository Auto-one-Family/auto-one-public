-- Phase 5b DB-Cleanup: Vorbereitung fuer zweiten Hardware-Test
-- ESP_472204 bleibt approved, nur alte Daten werden entfernt

-- 1. Alte sensor_configs loeschen (GPIO=0 vom 1. Test)
DELETE FROM sensor_configs WHERE esp_id = (
  SELECT id FROM esp_devices WHERE device_id = 'ESP_472204'
);

-- 2. Alte Audit-Logs bereinigen (>24h)
DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '24 hours';

-- 3. Heartbeat-Logs bereinigen fuer ESP_472204
DELETE FROM esp_heartbeat_logs WHERE esp_id = (
  SELECT id FROM esp_devices WHERE device_id = 'ESP_472204'
);

-- 4. Mock-Device loeschen
DELETE FROM esp_devices WHERE device_id = 'MOCK_0954B2B1';

-- 5. Verifizierung
SELECT 'esp_devices' as tbl, device_id, status, approved_at FROM esp_devices;
SELECT 'sensor_configs' as tbl, COUNT(*) FROM sensor_configs;
SELECT 'audit_logs' as tbl, COUNT(*) FROM audit_logs;
SELECT 'heartbeat_logs' as tbl, COUNT(*) FROM esp_heartbeat_logs;
