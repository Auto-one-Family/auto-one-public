"""
WebSocket API: Real-time Data Streaming

Provides WebSocket endpoint for real-time updates from the server.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError

from ....core.logging_config import get_logger
from ....core.security import verify_token
from ....db.models.audit_log import AuditSourceType
from ....db.repositories.audit_log_repo import AuditLogRepository
from ....db.repositories.token_blacklist_repo import TokenBlacklistRepository
from ....db.repositories.user_repo import UserRepository
from ....db.session import get_session
from ....websocket.manager import WebSocketManager

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws/realtime/{client_id}")
async def websocket_realtime(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time updates.

    Clients can subscribe to specific message types and filters:
    - sensor_data: Sensor readings
    - actuator_status: Actuator state updates
    - logic_execution: Logic rule executions
    - esp_health: ESP device health updates
    - system_event: System events

    Authentication:
    - Token must be provided as query parameter: ?token=<jwt_token>
    - Token is validated before connection is accepted
    - User must be active to connect

    Example subscribe message:
    {
        "action": "subscribe",
        "filters": {
            "types": ["sensor_data", "actuator_status"],
            "esp_ids": ["ESP_12AB34CD"],
            "sensor_types": ["temperature", "humidity"]
        }
    }

    Args:
        websocket: WebSocket connection
        client_id: Unique client identifier
    """
    # Extract token from query parameters
    query_params = dict(websocket.query_params)
    token = query_params.get("token")

    if not token:
        logger.warning(f"WebSocket connection rejected: Missing token (client_id={client_id})")
        await websocket.close(code=4001, reason="Missing token")
        return

    # Verify token
    try:
        payload = verify_token(token, expected_type="access")
        user_id_str = payload.get("sub")

        if user_id_str is None:
            logger.warning(
                f"WebSocket connection rejected: Token missing 'sub' claim (client_id={client_id})"
            )
            await websocket.close(code=4001, reason="Invalid token")
            return

        try:
            user_id = int(user_id_str)
        except ValueError:
            logger.warning(
                f"WebSocket connection rejected: Invalid user_id in token (client_id={client_id})"
            )
            await websocket.close(code=4001, reason="Invalid token")
            return

    except JWTError as e:
        logger.warning(
            f"WebSocket connection rejected: JWT verification failed (client_id={client_id}): {e}"
        )
        await websocket.close(code=4001, reason="Authentication failed")
        return
    except ValueError as e:
        logger.warning(
            f"WebSocket connection rejected: Token validation error (client_id={client_id}): {e}"
        )
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Check if token is blacklisted and validate user
    # Note: Session cleanup is handled automatically by the async generator
    async for session in get_session():
        blacklist_repo = TokenBlacklistRepository(session)
        if await blacklist_repo.is_blacklisted(token):
            logger.warning(
                f"WebSocket connection rejected: Blacklisted token (client_id={client_id}, user_id={user_id})"
            )
            await websocket.close(code=4001, reason="Token has been revoked")
            return

        # Get user from database and check if active
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        if user is None:
            logger.warning(
                f"WebSocket connection rejected: User not found (client_id={client_id}, user_id={user_id})"
            )
            await websocket.close(code=4001, reason="Invalid user")
            return

        if not user.is_active:
            logger.warning(
                f"WebSocket connection rejected: User inactive (client_id={client_id}, user_id={user_id})"
            )
            await websocket.close(code=4001, reason="User account is disabled")
            return

        # Authentication successful - proceed with connection
        # Break out of session context (session will be cleaned up automatically)
        break

    manager = await WebSocketManager.get_instance()
    await manager.connect(websocket, client_id)

    try:
        while True:
            # Receive client messages (subscribe/unsubscribe)
            data = await websocket.receive_json()
            action = data.get("action")

            if action == "subscribe":
                filters = data.get("filters", {})
                await manager.subscribe(client_id, filters)
                logger.debug(f"Client {client_id} subscribed with filters: {filters}")

            elif action == "unsubscribe":
                filters = data.get("filters", None)
                await manager.unsubscribe(client_id, filters)
                logger.debug(f"Client {client_id} unsubscribed")

            elif action == "client_stage":
                stage = str(data.get("stage") or "").strip()
                correlation_id = str(data.get("correlation_id") or "").strip()
                observed_at_ms = data.get("observed_at_ms")
                extra = data.get("extra") if isinstance(data.get("extra"), dict) else {}
                if stage and correlation_id:
                    # Keep stage logs aligned with server_window capture level.
                    logger.warning(
                        "latency_stage stage=%s correlation_id=%s observed_at_ms=%s client_id=%s",
                        stage,
                        correlation_id,
                        observed_at_ms,
                        client_id,
                    )
                    try:
                        async for session in get_session():
                            audit_repo = AuditLogRepository(session)
                            await audit_repo.create(
                                event_type="latency_stage",
                                severity="info",
                                source_type=AuditSourceType.API,
                                source_id=f"ws_client:{client_id}",
                                status=stage[:50],
                                message=f"Frontend stage observation: {stage}",
                                details={
                                    "client_id": client_id,
                                    "stage": stage,
                                    "observed_at_ms": observed_at_ms,
                                    "user_id": user_id,
                                    "extra": extra,
                                },
                                correlation_id=correlation_id,
                            )
                            await session.commit()
                            break
                    except Exception as stage_persist_error:
                        logger.warning(
                            "Failed to persist latency_stage observation: %s",
                            stage_persist_error,
                        )

            else:
                logger.warning(f"Unknown action from client {client_id}: {action}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected")
    except Exception as e:
        logger.error(f"Error in WebSocket connection for {client_id}: {e}", exc_info=True)
    finally:
        await manager.disconnect(client_id)
