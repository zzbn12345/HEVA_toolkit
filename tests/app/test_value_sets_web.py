"""Web workflow tests for naming project value sets and mapping colors to them."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from heva.app.main import create_app
from heva.curation.color_mapping import propose_color_configuration, save_color_configuration
from heva.curation.people_registry import PersonRecord, activate_curator, add_person
from heva.curation.project_registry import sync_registry


def _project(tmp_path: Path, *, curator: bool = True) -> str:
    sources = tmp_path / "documents"
    sources.mkdir()
    (sources / "source.pdf").write_bytes(b"source")
    sync_registry(tmp_path, source_dir="documents")
    if curator:
        person = add_person(tmp_path, PersonRecord(name="Project Curator", roles=["curator"]))
        activate_curator(tmp_path, person.person_id)
    registry = json.loads((tmp_path / ".heva/project.json").read_text())
    return registry["documents"][0]["document_id"]


HEALTH = {
    "value_set_id": "health-values",
    "name": "Health values",
    "description": "Values for a community health study.",
    "values": [
        {"label": "physical", "description": "Bodily health"},
        {"label": "mental", "description": None},
    ],
}


def test_value_set_page_uses_external_assets(tmp_path: Path) -> None:
    _project(tmp_path)
    client = TestClient(create_app(tmp_path))

    page = client.get("/value-sets")
    palette_script = client.get("/static/project_colors.js").text

    assert page.status_code == 200
    assert '/static/value_sets.js' in page.text
    assert client.get("/static/value_sets.js").status_code == 200
    assert "/api/value-sets" in palette_script
    assert '"social", "economic"' not in palette_script


def test_built_in_heritage_values_are_listed_without_project_files(tmp_path: Path) -> None:
    _project(tmp_path)
    client = TestClient(create_app(tmp_path))

    response = client.get("/api/value-sets")

    assert response.status_code == 200
    value_sets = response.json()["value_sets"]
    assert [item["value_set_id"] for item in value_sets] == ["heva-heritage-values"]
    assert value_sets[0]["built_in"] is True
    assert "historic" in {value["label"] for value in value_sets[0]["values"]}
    assert not (tmp_path / ".heva/value-sets.json").exists()


def test_value_set_creation_requires_curator_and_rejects_reserved_id(tmp_path: Path) -> None:
    _project(tmp_path, curator=False)
    client = TestClient(create_app(tmp_path))

    without_curator = client.post("/api/value-sets", json=HEALTH)
    person = add_person(tmp_path, PersonRecord(name="Project Curator", roles=["curator"]))
    activate_curator(tmp_path, person.person_id)
    reserved = client.post(
        "/api/value-sets",
        json={**HEALTH, "value_set_id": "heva-heritage-values"},
    )
    invalid = client.post(
        "/api/value-sets",
        json={**HEALTH, "values": [{"label": "Mental Health"}]},
    )
    created = client.post("/api/value-sets", json=HEALTH)

    assert without_curator.status_code == 422
    assert "active curator" in without_curator.json()["detail"]
    assert reserved.status_code == 422
    assert invalid.status_code == 422
    assert created.status_code == 201
    assert created.json()["version"] == 1
    listed = client.get("/api/value-sets").json()["value_sets"]
    assert [item["value_set_id"] for item in listed] == ["heva-heritage-values", "health-values"]
    assert listed[1]["built_in"] is False


def test_document_colors_are_assigned_to_the_selected_palette_value_set(tmp_path: Path) -> None:
    """A health palette offers and accepts health values on the document color step."""

    document_id = _project(tmp_path)
    save_color_configuration(tmp_path, document_id, propose_color_configuration(["#FFFF00"]))
    client = TestClient(create_app(tmp_path))
    client.post("/api/value-sets", json=HEALTH)

    heritage_palette = client.post(
        "/api/project-colors",
        json={
            "configuration_id": "wrong-set",
            "name": "Wrong set",
            "mappings": [{"label": "historic", "hexes": ["#FFFF00"]}],
            "value_set_id": "health-values",
            "value_set_version": 1,
        },
    )
    palette = client.post(
        "/api/project-colors",
        json={
            "configuration_id": "health-palette",
            "name": "Health palette",
            "mappings": [{"label": "physical", "hexes": ["#FFFF00"]}],
            "value_set_id": "health-values",
            "value_set_version": 1,
        },
    )
    selected = client.post(
        "/api/project-colors/select",
        json={"configuration_id": "health-palette", "version": 1},
    )
    colors = client.get(f"/api/documents/{document_id}/colors").json()
    rejected = client.post(
        f"/api/documents/{document_id}/colors/confirm",
        json={"decisions": [{"hex": "#FFFF00", "label": "historic"}]},
    )
    confirmed = client.post(
        f"/api/documents/{document_id}/colors/confirm",
        json={"decisions": [{"hex": "#FFFF00", "label": "physical"}]},
    )

    assert heritage_palette.status_code == 422
    assert palette.status_code == 201
    assert palette.json()["value_set_id"] == "health-values"
    assert selected.status_code == 200
    assert colors["labels"] == ["mental", "physical"]
    assert colors["value_set"] == {
        "value_set_id": "health-values",
        "version": 1,
        "name": "Health values",
        "built_in": False,
    }
    assert rejected.status_code == 422
    assert "value set" in rejected.json()["detail"]
    assert confirmed.status_code == 200
    project_colors = json.loads((tmp_path / ".heva/color-configurations.json").read_text())
    assert project_colors["selected"]["configuration_id"] == "health-palette"
    assert len(project_colors["configurations"]) == 1
    metadata = json.loads(
        (tmp_path / f"documents/{document_id}/metadata.json").read_text()
    )
    assert metadata["color_configuration"]["colors"][0]["label"] == "physical"
    assert metadata["color_configuration"]["configuration_id"] == "health-palette"
    after = client.get(f"/api/documents/{document_id}/colors").json()
    assert after["labels"] == ["mental", "physical"]


def test_heritage_projects_keep_heritage_labels_on_color_step(tmp_path: Path) -> None:
    document_id = _project(tmp_path)
    save_color_configuration(tmp_path, document_id, propose_color_configuration(["#FFFF00"]))
    client = TestClient(create_app(tmp_path))

    colors = client.get(f"/api/documents/{document_id}/colors").json()

    assert "historic" in colors["labels"] and len(colors["labels"]) == 8
    assert colors["value_set"]["built_in"] is True


def test_value_set_can_be_chosen_on_color_step_without_a_palette(tmp_path: Path) -> None:
    """A new value set is usable directly; confirming creates its project palette."""

    document_id = _project(tmp_path)
    save_color_configuration(tmp_path, document_id, propose_color_configuration(["#FFFF00"]))
    client = TestClient(create_app(tmp_path))
    client.post("/api/value-sets", json=HEALTH)

    colors = client.get(f"/api/documents/{document_id}/colors").json()
    confirmed = client.post(
        f"/api/documents/{document_id}/colors/confirm",
        json={
            "decisions": [{"hex": "#FFFF00", "label": "mental"}],
            "value_set_id": "health-values",
            "value_set_version": 1,
        },
    )

    assert colors["value_set"]["built_in"] is True
    assert {(item["value_set_id"], tuple(item["labels"])) for item in colors["value_sets"]} >= {
        ("health-values", ("mental", "physical")),
    }
    assert confirmed.status_code == 200
    project_colors = json.loads((tmp_path / ".heva/color-configurations.json").read_text())
    palette = project_colors["configurations"][0]
    assert (palette["value_set_id"], palette["value_set_version"]) == ("health-values", 1)
    assert project_colors["selected"]["configuration_id"] == palette["configuration_id"]
    after = client.get(f"/api/documents/{document_id}/colors").json()
    assert after["value_set"]["value_set_id"] == "health-values"
    assert after["configuration"]["colors"][0]["label"] == "mental"
