"""
Unit tests for salt_compositions (AUT-1418 / B1).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models.salt_composition import SaltComposition
from src.db.repositories.salt_composition_repo import SaltCompositionRepository
from src.schemas.salt_composition import (
    SaltCompositionCreate,
    SaltCompositionResponse,
)


# YaraLiva Calcinit label (AUT-1417); stoich tetrahydrate kept as separate fixture.
_CALCINIT = {
    "name": "Calcinit",
    "formula": None,
    "n_pct": 15.5,
    "p_pct": 0.0,
    "k_pct": 0.0,
    "ca_pct": 18.5821,
    "mg_pct": 0.0,
    "s_pct": 0.0,
    "source_type": "manufacturer_label",
    "source_note": "YaraLiva Calcinit — Hersteller-Etikett; CaO→Ca",
}
_STOICH_TETRAHYDRATE = {
    "name": "Ca(NO₃)₂·4H₂O",
    "formula": "Ca(NO₃)₂·4H₂O",
    "n_pct": 11.8628,
    "p_pct": 0.0,
    "k_pct": 0.0,
    "ca_pct": 16.9718,
    "mg_pct": 0.0,
    "s_pct": 0.0,
    "source_type": "stoichiometric",
    "source_note": "MM=236.1441; N%=11.8628; Ca%=16.9718",
}
_MGSO4 = {
    "name": "MgSO₄·7H₂O",
    "formula": "MgSO₄·7H₂O",
    "n_pct": 0.0,
    "p_pct": 0.0,
    "k_pct": 0.0,
    "ca_pct": 0.0,
    "mg_pct": 9.6487,
    "s_pct": 13.0,
    "source_type": "manufacturer_label",
    "source_note": "EPSO Top® — MgO 16% → Mg 9.6487%; S 13%",
}
_MKP = {
    "name": "MKP",
    "formula": "KH₂PO₄",
    "n_pct": 0.0,
    "p_pct": 22.7,
    "k_pct": 28.7,
    "ca_pct": 0.0,
    "mg_pct": 0.0,
    "s_pct": 0.0,
    "source_type": "manufacturer_label",
    "source_note": "MKP — Hersteller-Zusammensetzung: P 22,7%; K 28,7% (P₂O₅ 52%; K₂O 34%)",
}
_KRISTALON = {
    "name": "Kristalon Rot",
    "formula": None,
    "n_pct": 12.0,
    "p_pct": 5.2371,
    "k_pct": 29.8854,
    "ca_pct": 0.0,
    "mg_pct": 0.6030,
    "s_pct": 1.0,
    "source_type": "manufacturer_label",
    "source_note": "YaraTera Kristalon Rot — Hersteller-Etikett; P₂O₅/K₂O/MgO→elementar",
}
_BELEG_OFFEN_CUSTOM = {
    "name": "Custom Mix Open",
    "formula": None,
    "n_pct": None,
    "p_pct": None,
    "k_pct": None,
    "ca_pct": None,
    "mg_pct": None,
    "s_pct": None,
    "source_type": "beleg_offen",
    "source_note": "[BELEG offen] — wartet auf Produkt-Etikett",
}


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_create_yaraliva_calcinit_label(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    row = await repo.create(**_CALCINIT, active=True)
    await db_session.flush()

    found = await repo.get_by_name("Calcinit")
    assert found is not None
    assert found.id == row.id
    assert _as_float(found.n_pct) == pytest.approx(15.5, abs=1e-4)
    assert _as_float(found.ca_pct) == pytest.approx(18.5821, abs=1e-4)
    assert found.source_type == "manufacturer_label"
    assert "YaraLiva" in found.source_note or "Hersteller-Etikett" in found.source_note

    resp = SaltCompositionResponse.model_validate(found)
    assert resp.name == "Calcinit"
    assert resp.n_pct == pytest.approx(15.5, abs=1e-4)


@pytest.mark.asyncio
async def test_create_stoichiometric_tetrahydrate(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    row = await repo.create(**_STOICH_TETRAHYDRATE, active=True)
    await db_session.flush()

    found = await repo.get_by_name("Ca(NO₃)₂·4H₂O")
    assert found is not None
    assert found.id == row.id
    assert _as_float(found.n_pct) == pytest.approx(11.8628, abs=1e-4)
    assert _as_float(found.ca_pct) == pytest.approx(16.9718, abs=1e-4)
    assert found.source_type == "stoichiometric"
    assert "236.1441" in found.source_note


@pytest.mark.asyncio
async def test_kristalon_manufacturer_label_elements(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    await repo.create(**_KRISTALON, active=True)
    await db_session.flush()

    found = await repo.get_by_name("Kristalon Rot")
    assert found is not None
    assert found.source_type == "manufacturer_label"
    assert _as_float(found.n_pct) == pytest.approx(12.0, abs=1e-4)
    assert _as_float(found.p_pct) == pytest.approx(5.2371, abs=1e-4)
    assert _as_float(found.k_pct) == pytest.approx(29.8854, abs=1e-4)
    assert _as_float(found.ca_pct) == pytest.approx(0.0, abs=1e-4)
    assert _as_float(found.mg_pct) == pytest.approx(0.6030, abs=1e-4)
    assert _as_float(found.s_pct) == pytest.approx(1.0, abs=1e-4)
    assert "YaraTera" in found.source_note or "Hersteller-Etikett" in found.source_note


@pytest.mark.asyncio
async def test_beleg_offen_null_elements_still_supported(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    await repo.create(**_BELEG_OFFEN_CUSTOM, active=True)
    await db_session.flush()

    found = await repo.get_by_name("Custom Mix Open")
    assert found is not None
    assert found.source_type == "beleg_offen"
    assert found.n_pct is None
    assert "BELEG offen" in found.source_note


@pytest.mark.asyncio
async def test_seed_like_four_salts_and_list(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    for payload in (_CALCINIT, _MGSO4, _MKP, _KRISTALON):
        await repo.create(**payload, active=True)
    await db_session.flush()

    rows = await repo.list_filtered(active_only=True)
    names = {r.name for r in rows}
    assert names == {"Calcinit", "MgSO₄·7H₂O", "MKP", "Kristalon Rot"}

    stoich = await repo.list_filtered(source_type="stoichiometric")
    assert len(stoich) == 0
    labeled = await repo.list_filtered(source_type="manufacturer_label")
    assert len(labeled) == 4
    assert {r.name for r in labeled} == {
        "Calcinit",
        "Kristalon Rot",
        "MKP",
        "MgSO₄·7H₂O",
    }


@pytest.mark.asyncio
async def test_create_new_salt_does_not_mutate_others(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    first = await repo.create(**_CALCINIT, active=True)
    await db_session.flush()
    first_id = first.id
    first_n = _as_float(first.n_pct)

    second = await repo.create(
        name="Custom Nitrate",
        formula="NaNO3",
        n_pct=16.5,
        p_pct=0.0,
        k_pct=0.0,
        ca_pct=0.0,
        mg_pct=0.0,
        s_pct=0.0,
        source_type="manufacturer_label",
        source_note="test label",
        active=True,
    )
    await db_session.flush()

    reloaded = await repo.get_by_id(first_id)
    assert reloaded is not None
    assert _as_float(reloaded.n_pct) == first_n
    assert second.id != first_id
    assert isinstance(second.id, uuid.UUID)


@pytest.mark.asyncio
async def test_soft_delete_hides_from_active_list(db_session: AsyncSession) -> None:
    repo = SaltCompositionRepository(db_session)
    row = await repo.create(**_MKP, active=True)
    await db_session.flush()
    await repo.update_fields(row.id, active=False)
    await db_session.flush()

    assert await repo.get_by_name("MKP", active_only=True) is None
    assert await repo.get_by_id(row.id) is not None
    active = await repo.list_filtered(active_only=True)
    assert all(r.name != "MKP" for r in active)


def test_schema_rejects_invalid_source_type() -> None:
    with pytest.raises(ValidationError):
        SaltCompositionCreate(
            name="X",
            source_type="guessed",  # type: ignore[arg-type]
            n_pct=1.0,
        )


def test_schema_rejects_pct_out_of_range() -> None:
    with pytest.raises(ValidationError):
        SaltCompositionCreate(
            name="X",
            source_type="stoichiometric",
            n_pct=101.0,
        )


def test_schema_accepts_stoichiometric_mkp_numbers() -> None:
    create = SaltCompositionCreate(
        name="MKP",
        formula="KH2PO4",
        n_pct=0.0,
        p_pct=22.7608,
        k_pct=28.7311,
        ca_pct=0.0,
        mg_pct=0.0,
        s_pct=0.0,
        source_type="stoichiometric",
        source_note="stoichiometric MKP elemental percents",
    )
    assert create.p_pct == pytest.approx(22.7608)
    assert create.k_pct == pytest.approx(28.7311)
    assert create.source_type == "stoichiometric"


def test_model_tablename_isolated_from_recipes() -> None:
    """Guardrail: B1 must not touch stock_mix_recipes table name."""
    assert SaltComposition.__tablename__ == "salt_compositions"
