"""
Integration Tests: Tank / Subzone-Assignment / Ledger Write API (AUT-1217).

Given/When/Then:
  Given zone + two subzones exist
  When POST tank → POST assignments → POST ledger entry
  Then all return 2xx with persisted objects; no actuator/rule touched.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_access_token, get_password_hash
from src.db.models.esp import ESPDevice
from src.db.models.nutrient_solution_batch import NUTRIENT_BATCH_ENTRY_TYPES
from src.db.models.plan_segment import PlanSegment
from src.db.models.subzone import SubzoneConfig
from src.db.models.user import User
from src.db.models.zone import Zone
from src.main import app


@pytest.fixture
async def operator_user(db_session: AsyncSession) -> User:
    user = User(
        username="tanks_operator",
        email="tanks_op@example.com",
        password_hash=get_password_hash("OperatorP@ss123"),
        full_name="Tanks Operator",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def operator_headers(operator_user: User) -> dict:
    token = create_access_token(
        user_id=operator_user.id,
        additional_claims={"role": operator_user.role},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def zone(db_session: AsyncSession) -> Zone:
    z = Zone(zone_id="zelt_wohnzimmer", name="Zelt Wohnzimmer")
    db_session.add(z)
    await db_session.commit()
    await db_session.refresh(z)
    return z


@pytest.fixture
async def esp(db_session: AsyncSession, zone: Zone) -> ESPDevice:
    device = ESPDevice(
        device_id="ESP_7A19CD52",
        name="Tank API ESP",
        ip_address="192.168.1.52",
        mac_address="AA:BB:CC:DD:EE:52",
        firmware_version="1.0.0",
        hardware_type="ESP32_WROOM",
        status="online",
        zone_id=zone.zone_id,
        zone_name=zone.name,
        domain="wasser",
        capabilities={"max_sensors": 20, "max_actuators": 12},
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest.fixture
async def subzones(db_session: AsyncSession, esp: ESPDevice) -> list[SubzoneConfig]:
    rows = []
    for sid, name in (("topf_1", "Topf 1"), ("topf_2", "Topf 2")):
        row = SubzoneConfig(
            esp_id=esp.device_id,
            subzone_id=sid,
            subzone_name=name,
            parent_zone_id=esp.zone_id,
            assigned_gpios=[4],
        )
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    for row in rows:
        await db_session.refresh(row)
    return rows


@pytest.mark.asyncio
async def test_given_when_then_pilot_write_path(
    db_session: AsyncSession,
    operator_headers: dict,
    zone: Zone,
    subzones: list[SubzoneConfig],
) -> None:
    """Full GWT: create tank → assign Topf 1+2 → ledger Neuansatz."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Pilot-Tank",
                "operation_mode": "drain_to_waste",
                "nominal_volume_l": 20.0,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        tank = create_resp.json()
        tank_id = tank["id"]
        assert tank["zone_id"] == "zelt_wohnzimmer"

        for sz in subzones:
            assign_resp = await client.post(
                f"/api/v1/tanks/{tank_id}/subzones",
                headers=operator_headers,
                json={"subzone_config_id": str(sz.id)},
            )
            assert assign_resp.status_code == 200, assign_resp.text
            body = assign_resp.json()
            assert body["tank_id"] == tank_id
            assert body["subzone_config_id"] == str(sz.id)
            assert body["assigned_by"] is not None

        batch_resp = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "full_reset",
                "volume_l": 18.0,
                "components": [
                    {"kind": "product", "name": "Grow A", "dose_ml_per_l": 2.0},
                    {
                        "kind": "salt",
                        "name": "MgSO4",
                        "conc_g_per_l": 0.3,
                    },
                ],
                "acquisition_method": "manual_entry",
                "qualifier": "approximate",
                "ec_was_measured": False,
            },
        )
        assert batch_resp.status_code == 201, batch_resp.text
        batch = batch_resp.json()
        assert batch["entry_type"] == "full_reset"
        assert batch["acquisition_method"] == "manual_entry"
        assert batch["qualifier"] == "approximate"
        assert batch["ec_was_measured"] is False
        assert batch["ec_measured_after"] is None
        assert len(batch["components"]) == 2


@pytest.mark.asyncio
async def test_create_tank_unknown_zone_404(
    operator_headers: dict,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": "does_not_exist",
                "name": "X",
                "operation_mode": "recirculating",
            },
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_create_returns_401() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/tanks",
            json={
                "zone_id": "zelt_wohnzimmer",
                "name": "X",
                "operation_mode": "drain_to_waste",
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_type", list(NUTRIENT_BATCH_ENTRY_TYPES))
async def test_ledger_entry_each_entry_type(
    operator_headers: dict,
    zone: Zone,
    entry_type: str,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": f"Tank-{entry_type}",
                "operation_mode": "drain_to_waste",
            },
        )
        assert tank_resp.status_code == 201
        tank_id = tank_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": entry_type,
                "volume_l": 0.0 if entry_type == "remeasurement_only" else 5.0,
                "components": [],
                "acquisition_method": "manual_entry",
                "qualifier": "precise",
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["entry_type"] == entry_type


@pytest.mark.asyncio
async def test_ledger_product_and_salt_accuracy_levels(
    operator_headers: dict,
    zone: Zone,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Accuracy Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]

        product_resp = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "full_reset",
                "volume_l": 10.0,
                "components": [
                    {"kind": "product", "name": "A", "dose_g_per_l": 1.0},
                ],
                "acquisition_method": "measured_flow",
                "qualifier": "precise",
            },
        )
        assert product_resp.status_code == 201, product_resp.text

        salt_resp = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "top_up_dose",
                "volume_l": 2.0,
                "components": [
                    {"kind": "salt", "name": "KNO3", "conc_g_per_l": 0.5},
                ],
                "acquisition_method": "manual_entry",
                "qualifier": "estimated",
            },
        )
        assert salt_resp.status_code == 201, salt_resp.text


@pytest.mark.asyncio
async def test_ec_was_measured_false_vs_zero_via_api(
    operator_headers: dict,
    zone: Zone,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "EC Dist Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]

        never = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "remeasurement_only",
                "volume_l": 0.0,
                "components": [],
                "acquisition_method": "manual_entry",
                "qualifier": "estimated",
                "ec_was_measured": False,
            },
        )
        assert never.status_code == 201
        never_body = never.json()
        assert never_body["ec_was_measured"] is False
        assert never_body["ec_measured_after"] is None

        zero = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "remeasurement_only",
                "volume_l": 0.0,
                "components": [],
                "acquisition_method": "manual_entry",
                "qualifier": "precise",
                "ec_was_measured": True,
                "ec_measured_after": 0.0,
            },
        )
        assert zero.status_code == 201
        zero_body = zero.json()
        assert zero_body["ec_was_measured"] is True
        assert zero_body["ec_measured_after"] == 0.0


@pytest.mark.asyncio
async def test_delete_assignment(
    operator_headers: dict,
    zone: Zone,
    subzones: list[SubzoneConfig],
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Delete Assign Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]
        sz_id = str(subzones[0].id)

        await client.post(
            f"/api/v1/tanks/{tank_id}/subzones",
            headers=operator_headers,
            json={"subzone_config_id": sz_id},
        )
        del_resp = await client.delete(
            f"/api/v1/tanks/{tank_id}/subzones/{sz_id}",
            headers=operator_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True

        missing = await client.delete(
            f"/api/v1/tanks/{tank_id}/subzones/{sz_id}",
            headers=operator_headers,
        )
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_mixed_component_fields_rejected(
    operator_headers: dict,
    zone: Zone,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Bad Comp Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]
        resp = await client.post(
            f"/api/v1/tanks/{tank_id}/batches",
            headers=operator_headers,
            json={
                "entry_type": "full_reset",
                "volume_l": 1.0,
                "components": [
                    {
                        "kind": "product",
                        "name": "Bad",
                        "dose_ml_per_l": 1.0,
                        "conc_g_per_l": 0.2,
                    }
                ],
                "acquisition_method": "manual_entry",
                "qualifier": "precise",
            },
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_and_get_tank(
    operator_headers: dict,
    zone: Zone,
) -> None:
    """GET /v1/tanks and GET /v1/tanks/{tank_id} (AUT-1223 Q3)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Listable Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        assert create_resp.status_code == 201
        tank_id = create_resp.json()["id"]

        list_resp = await client.get("/api/v1/tanks", headers=operator_headers)
        assert list_resp.status_code == 200
        names = {t["name"] for t in list_resp.json()}
        assert "Listable Tank" in names

        get_resp = await client.get(f"/api/v1/tanks/{tank_id}", headers=operator_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == tank_id

        missing_resp = await client.get(f"/api/v1/tanks/{uuid.uuid4()}", headers=operator_headers)
        assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_device_assignment_lifecycle(
    operator_headers: dict,
    zone: Zone,
    esp: ESPDevice,
) -> None:
    """PUT/GET/DELETE /v1/tanks/{tank_id}/devices/{esp_id} (n:1, AUT-1223 Q2)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Device Assign Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]

        # Assign
        assign_resp = await client.put(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert assign_resp.status_code == 200, assign_resp.text
        assign_body = assign_resp.json()
        assert assign_body["tank_id"] == tank_id
        assert assign_body["device_id"] == esp.device_id

        # Read: tank -> devices
        devices_resp = await client.get(
            f"/api/v1/tanks/{tank_id}/devices", headers=operator_headers
        )
        assert devices_resp.status_code == 200
        devices_body = devices_resp.json()
        assert devices_body["count"] == 1
        assert devices_body["devices"][0]["device_id"] == esp.device_id

        # Read: device -> tank (mirrored via ESP GET, AUT-1223)
        esp_get_resp = await client.get(
            f"/api/v1/esp/devices/{esp.device_id}", headers=operator_headers
        )
        assert esp_get_resp.status_code == 200
        assert esp_get_resp.json()["tank_id"] == tank_id

        # Clear
        clear_resp = await client.delete(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert clear_resp.status_code == 200, clear_resp.text
        assert clear_resp.json()["success"] is True

        # Clearing again: device no longer assigned to this tank -> 404
        missing_clear_resp = await client.delete(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert missing_clear_resp.status_code == 404


@pytest.mark.asyncio
async def test_reassign_device_replaces_previous_tank(
    operator_headers: dict,
    zone: Zone,
    esp: ESPDevice,
) -> None:
    """n:1 cardinality: assigning to tank B clears the tank A assignment."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_a_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Reassign Tank A",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_a_id = tank_a_resp.json()["id"]
        tank_b_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Reassign Tank B",
                "operation_mode": "recirculating",
            },
        )
        tank_b_id = tank_b_resp.json()["id"]

        await client.put(
            f"/api/v1/tanks/{tank_a_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        await client.put(
            f"/api/v1/tanks/{tank_b_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )

        devices_a = await client.get(f"/api/v1/tanks/{tank_a_id}/devices", headers=operator_headers)
        devices_b = await client.get(f"/api/v1/tanks/{tank_b_id}/devices", headers=operator_headers)
        assert devices_a.json()["count"] == 0
        assert devices_b.json()["count"] == 1


@pytest.mark.asyncio
async def test_assign_device_unknown_esp_404(
    operator_headers: dict,
    zone: Zone,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Unknown Device Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]
        resp = await client.put(
            f"/api/v1/tanks/{tank_id}/devices/ESP_GHOST",
            headers=operator_headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_batch_unknown_tank_404(operator_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            f"/api/v1/tanks/{uuid.uuid4()}/batches",
            headers=operator_headers,
            json={
                "entry_type": "withdrawal",
                "volume_l": 1.0,
                "components": [],
                "acquisition_method": "manual_entry",
                "qualifier": "precise",
            },
        )
        assert resp.status_code == 404


# =============================================================================
# Targets: canonical Soll from plan_segment@now (AUT-1225 Q4)
# =============================================================================


@pytest.mark.asyncio
async def test_get_tank_targets_without_segment_returns_null_values(
    operator_headers: dict,
    zone: Zone,
) -> None:
    """GWT: tank in a zone with no plan_segments → both measures null/none."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Targets No Plan Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]

        resp = await client.get(f"/api/v1/tanks/{tank_id}/targets", headers=operator_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["tank_id"] == tank_id
        assert body["zone_id"] == zone.zone_id
        assert body["subzone_config_id"] is None
        assert body["domain"] == "nutrient_solution"
        targets_by_measure = {t["measure"]: t for t in body["targets"]}
        assert set(targets_by_measure.keys()) == {"target_ec", "target_ph"}
        for target in targets_by_measure.values():
            assert target["value"] is None
            assert target["resolved_via"] == "none"
        assert body["assigned_device_ids"] == []


@pytest.mark.asyncio
async def test_get_tank_targets_with_covering_segment_returns_values(
    db_session: AsyncSession,
    operator_headers: dict,
    zone: Zone,
) -> None:
    """GWT: zone-wide plan_segment covering 'now' resolves target_ec via zone."""
    now = datetime.now(timezone.utc)
    segment = PlanSegment(
        zone_id=zone.zone_id,
        domain="nutrient_solution",
        measure="target_ec",
        value=1.6,
        from_ts=now - timedelta(days=1),
        to_ts=now + timedelta(days=1),
        interp="step",
        status="active",
    )
    db_session.add(segment)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_resp = await client.post(
            "/api/v1/tanks",
            headers=operator_headers,
            json={
                "zone_id": zone.zone_id,
                "name": "Targets With Plan Tank",
                "operation_mode": "drain_to_waste",
            },
        )
        tank_id = tank_resp.json()["id"]

        resp = await client.get(f"/api/v1/tanks/{tank_id}/targets", headers=operator_headers)
        assert resp.status_code == 200, resp.text
        targets_by_measure = {t["measure"]: t for t in resp.json()["targets"]}
        assert targets_by_measure["target_ec"]["value"] == 1.6
        assert targets_by_measure["target_ec"]["unit"] == "µS/cm"
        assert targets_by_measure["target_ec"]["resolved_via"] == "zone"
        assert targets_by_measure["target_ph"]["value"] is None
        assert targets_by_measure["target_ph"]["resolved_via"] == "none"


@pytest.mark.asyncio
async def test_get_tank_targets_unknown_tank_404(operator_headers: dict) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/tanks/{uuid.uuid4()}/targets", headers=operator_headers)
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_tank_targets_unauthenticated_401(zone: Zone) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/tanks/{uuid.uuid4()}/targets")
        assert resp.status_code == 401


# =============================================================================
# AUT-1328: Domain != wasser => tank_id must be cleared
# =============================================================================


async def _create_tank(client: AsyncClient, headers: dict, zone_id: str, name: str) -> str:
    tank_resp = await client.post(
        "/api/v1/tanks",
        headers=headers,
        json={
            "zone_id": zone_id,
            "name": name,
            "operation_mode": "drain_to_waste",
        },
    )
    assert tank_resp.status_code == 201, tank_resp.text
    return tank_resp.json()["id"]


@pytest.mark.asyncio
async def test_patch_domain_luft_clears_tank_id_without_tank_in_body(
    operator_headers: dict,
    zone: Zone,
    esp: ESPDevice,
) -> None:
    """GWT-1: PATCH {domain:luft} without tank_id clears stale membership."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_id = await _create_tank(client, operator_headers, zone.zone_id, "AUT-1328 Clear Tank")
        assign_resp = await client.put(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert assign_resp.status_code == 200, assign_resp.text

        patch_resp = await client.patch(
            f"/api/v1/esp/devices/{esp.device_id}",
            headers=operator_headers,
            json={"domain": "luft"},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        body = patch_resp.json()
        assert body["domain"] == "luft"
        assert body["tank_id"] is None
        assert body["zone_id"] == zone.zone_id
        assert body["zone_name"] == zone.name

        members = await client.get(f"/api/v1/tanks/{tank_id}/devices", headers=operator_headers)
        assert members.status_code == 200
        assert members.json()["count"] == 0


@pytest.mark.asyncio
async def test_assign_device_rejects_luft_domain(
    operator_headers: dict,
    zone: Zone,
    esp: ESPDevice,
    db_session: AsyncSession,
) -> None:
    """GWT-2: Alias PUT on domain=luft does not create a stale member."""
    esp.domain = "luft"
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_id = await _create_tank(client, operator_headers, zone.zone_id, "AUT-1328 Reject Luft")
        assign_resp = await client.put(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert assign_resp.status_code == 400, assign_resp.text
        assert "wasser" in assign_resp.json()["detail"]

        members = await client.get(f"/api/v1/tanks/{tank_id}/devices", headers=operator_headers)
        assert members.status_code == 200
        assert members.json()["count"] == 0

        esp_get = await client.get(f"/api/v1/esp/devices/{esp.device_id}", headers=operator_headers)
        assert esp_get.status_code == 200
        assert esp_get.json()["tank_id"] is None
        assert esp_get.json()["domain"] == "luft"


@pytest.mark.asyncio
async def test_patch_tank_id_null_keeps_wasser_domain(
    operator_headers: dict,
    zone: Zone,
    esp: ESPDevice,
) -> None:
    """GWT-3: PATCH {tank_id:null} keeps domain=wasser."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tank_id = await _create_tank(client, operator_headers, zone.zone_id, "AUT-1328 Keep Wasser")
        assign_resp = await client.put(
            f"/api/v1/tanks/{tank_id}/devices/{esp.device_id}",
            headers=operator_headers,
        )
        assert assign_resp.status_code == 200, assign_resp.text

        patch_resp = await client.patch(
            f"/api/v1/esp/devices/{esp.device_id}",
            headers=operator_headers,
            json={"tank_id": None},
        )
        assert patch_resp.status_code == 200, patch_resp.text
        body = patch_resp.json()
        assert body["domain"] == "wasser"
        assert body["tank_id"] is None
