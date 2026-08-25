# AutomationOne - Logging Strategy

## Primary Log Path (Queries & Monitoring)

```
stdout -> Docker json-file driver -> Alloy -> Loki (7-day retention)
```

All services use the Docker `json-file` logging driver with rotation (`max-size: 5-10m`, `max-file: 3`).
Grafana Alloy scrapes Docker container logs via the Docker socket and ships them to Loki.
(Migrated from Promtail 2026-02-24; Promtail EOL: 2026-03-02)

## Bind-Mount Logs (Direct Debugging)

| Path | Service | Format | Rotation |
|------|---------|--------|----------|
| `logs/server/` | el-servador | JSON (RotatingFileHandler) | 10MB x 5 backups |
| `logs/postgres/` | postgres | Text with timestamps | Daily + 50MB intra-day |
| `logs/mqtt/` | mqtt-broker | Disabled (stdout-only since v3.1) | n/a |
| `stdout-only` | esp32-serial-logger | JSON (structured ESP32 logs) | Docker json-file (5m x 3) |

### Why Bind-Mounts Exist

Server and Postgres write to bind-mounted directories **in addition** to stdout.
This provides direct file access for debugging without needing `docker logs` or Grafana.
Mosquitto was switched to stdout-only; the `logs/mqtt/` mount is retained for optional
file logging (uncomment `log_dest file` in `docker/mosquitto/mosquitto.conf`).

## When to Use Which Path

| Scenario | Recommended Path |
|----------|-----------------|
| Log search across services | Loki (Grafana Explore) |
| Filter by level, service, container | Loki (Grafana Explore) |
| Server JSON fields (request IDs, context) | Bind-mount `logs/server/god_kaiser.log` |
| SQL debugging, slow queries | Bind-mount `logs/postgres/postgresql-*.log` |
| Quick last N lines check | `docker logs <container> --tail 100` |
| MQTT broker events | `docker logs automationone-mqtt` |
| ESP32 serial debugging (hardware) | Loki (Grafana Explore) or `docker logs automationone-esp32-serial` |

## Storage Impact

The triple-path approach (bind-mount + Docker json-file + Loki) creates redundancy:

- **Docker json-file:** Auto-rotated, max ~30MB per service (10m x 3)
- **Bind-mount server:** Max ~50MB (10MB x 5 backups)
- **Bind-mount postgres:** Daily files, no auto-deletion (manual cleanup needed)
- **Loki:** 7-day retention, auto-compacted

Total estimated redundant storage: ~100-300MB depending on activity.

## Cleanup

Bind-mount logs in `./logs/` are **not** automatically deleted.
When disk space is needed:

```bash
# Remove server logs (will be recreated on next write)
rm -f logs/server/*.log

# Remove old postgres logs (keep last 3 days)
find logs/postgres/ -name "postgresql-*.log" -mtime +3 -delete

# MQTT logs (normally empty since stdout-only)
rm -f logs/mqtt/*.log
```

## Configuration References

| Component | Config File | Key Settings |
|-----------|-------------|-------------|
| Server logging | `El Servador/god_kaiser_server/config/logging.yaml` | RotatingFileHandler, JSON format |
| Mosquitto logging | `docker/mosquitto/mosquitto.conf` | `log_dest stdout` |
| PostgreSQL logging | `docker/postgres/postgresql.conf` | `logging_collector = on`, daily rotation |
| Docker log driver | `docker-compose.yml` (per service) | `json-file`, max-size/max-file |
| Alloy pipeline | `docker/promtail/config.yml` | Docker SD, label extraction (read by Alloy via --config.format=promtail) |
| Loki retention | `docker/loki/loki-config.yml` | `retention_period: 168h` |
