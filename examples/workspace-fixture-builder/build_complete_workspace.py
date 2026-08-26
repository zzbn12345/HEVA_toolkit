"""Build the complete, app-openable HEVA workspace used for Alpha demonstrations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import fitz

from heva.workflow.document_metadata import (
    AnnotationProcessMetadata,
    AnnotatorMetadata,
    ColorConfigurationMetadata,
    ColorMappingMetadata,
    PackageMetadata,
    ResourceMetadata,
    ReviewMetadata,
    SourceMetadata,
    save_package_metadata,
)
from heva.workflow.document_contributors import assign_document_annotators
from heva.workflow.package_validator import DatasetReleaseMetadata, validate_project
from heva.workflow.people_registry import PersonRecord, activate_curator, add_person
from heva.workflow.project_registry import load_project_registry, sync_registry
from heva.workflow.review_state import initialize_sentence_reviews, record_decisions


FIXTURE_DOCUMENTS = (
    {
        "filename": "historic-harbour.pdf",
        "title": "Historic Harbour Demonstration",
        "author": "Amara Example",
        "sentence": "The historic harbour remains central to the town's identity.",
        "entity": "historic harbour",
        "label": "historic",
        "color": "#FF40FF",
    },
    {
        "filename": "coastal-wetland.pdf",
        "title": "Coastal Wetland Demonstration",
        "author": "Bram Example",
        "sentence": "The coastal wetland supports ecological value and local memory.",
        "entity": "ecological value",
        "label": "ecological",
        "color": "#A8D200",
    },
)


def _write_pdf(path: Path, title: str, sentence: str) -> None:
    """Create a small readable source PDF without embedding annotations or private data."""

    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 90), title, fontsize=18)
    page.insert_textbox(fitz.Rect(72, 130, 520, 260), sentence, fontsize=12)
    document.set_metadata({"title": title, "author": "HEVA fixture builder"})
    document.save(path)
    document.close()


def _record(specification: dict[str, str]) -> dict[str, object]:
    """Return one canonical sentence record with stable entity offsets and BIO tags."""

    sentence = specification["sentence"]
    entity = specification["entity"]
    start = sentence.index(entity)
    end = start + len(entity)
    if specification["label"] == "historic":
        tokens = ["The", "historic", "harbour", "remains", "central", "to", "the", "town's", "identity", "."]
        tags = ["O", "B-historic", "I-historic", "O", "O", "O", "O", "O", "O", "O"]
    else:
        tokens = ["The", "coastal", "wetland", "supports", "ecological", "value", "and", "local", "memory", "."]
        tags = ["O", "O", "O", "O", "B-ecological", "I-ecological", "O", "O", "O", "O"]
    return {
        "sentence_id": 1,
        "page": 1,
        "sentence": sentence,
        "tokens": tokens,
        "values": [specification["label"]],
        "entities": [{
            "start": start,
            "end": end,
            "text": entity,
            "label": specification["label"],
            "color": specification["color"],
        }],
        "ner_tags": tags,
        "schema_version": "1.0",
    }


def build_complete_workspace(output: Path, *, force: bool = False) -> Path:
    """Create a deterministic two-document workspace that passes HEVA validation."""

    output = output.expanduser().resolve()
    if output.exists():
        if not force:
            raise FileExistsError(f"Output already exists: {output}")
        if not (output / ".heva/project.json").is_file():
            raise ValueError("Refusing to replace a directory that is not a HEVA fixture.")
        shutil.rmtree(output)
    sources = output / "documents"
    sources.mkdir(parents=True)
    for specification in FIXTURE_DOCUMENTS:
        _write_pdf(
            sources / specification["filename"],
            specification["title"],
            specification["sentence"],
        )

    sync_registry(output, source_dir="documents")
    annotator = add_person(
        output,
        PersonRecord(
            person_id="PERSON-DEMOANNOTATOR",
            name="Dana Demonstrator",
            roles=["annotator"],
            affiliation="HEVA Demonstration Lab",
            orcid="0000-0002-1825-0097",
        ),
    )
    curator = add_person(
        output,
        PersonRecord(
            person_id="PERSON-DEMOCURATOR",
            name="Casey Curator",
            roles=["curator"],
            affiliation="HEVA Demonstration Lab",
        ),
    )
    activate_curator(output, curator.person_id)

    registry = load_project_registry(output)
    entries = {Path(item.source_path).name: item for item in registry.documents}
    completed_at = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
    for specification in FIXTURE_DOCUMENTS:
        entry = entries[specification["filename"]]
        package = output / entry.package_path
        records = [_record(specification)]
        (package / "annotations.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        save_package_metadata(
            output,
            PackageMetadata(
                document_id=entry.document_id,
                source=SourceMetadata(
                    title=specification["title"],
                    creators=[specification["author"]],
                    citation=f"{specification['author']}. {specification['title']}. 2026.",
                    item_type="report",
                    issued_year=2026,
                    source_filename=specification["filename"],
                    reference=f"https://example.org/heva/{entry.document_id.lower()}",
                    validation_method="programmatic",
                    validated_by="complete-workspace-fixture/1.0",
                    validated_at=completed_at,
                ),
                annotator=AnnotatorMetadata(),
                annotation_process=AnnotationProcessMetadata(
                    method="hybrid",
                    extractor="HEVA deterministic fixture",
                    extractor_version="1.0",
                    performed_at=completed_at,
                    review=ReviewMetadata(completed=True, reviewed_at=completed_at),
                ),
                color_configuration=ColorConfigurationMetadata(
                    detection_method="automatic",
                    human_confirmed=True,
                    confirmed_by=curator.name,
                    confirmed_at=completed_at,
                    colors=[ColorMappingMetadata(
                        hex=specification["color"],
                        label=specification["label"],
                        status="approved",
                    )],
                ),
                resources=[ResourceMetadata(
                    name="annotations",
                    path="annotations.json",
                    format="json",
                    record_count=1,
                )],
            ),
        )
        assign_document_annotators(output, entry.document_id, [annotator.person_id])
        initialize_sentence_reviews(output, entry.document_id)
        record_decisions(
            output,
            entry.document_id,
            [1],
            status="approved",
            reviewer=curator.name,
            comment="Accepted demonstration annotation.",
        )

    dataset = DatasetReleaseMetadata(
        name="heva-complete-workspace-fixture",
        title="Complete HEVA workspace fixture",
        description="Two fictional, validated heritage-value annotation documents.",
        creators=["HEVA Toolkit contributors"],
        contributors=[annotator.name, curator.name],
        license="CC-BY-4.0",
        rights="Fictional sources and annotations may be redistributed for demonstration.",
        known_limitations=["Synthetic demonstration data is not an accuracy benchmark."],
    )
    (output / "dataset-metadata.json").write_text(
        dataset.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "README.md").write_text(
        "# Complete dummy HEVA workspace\n\n"
        "Open this folder as an existing HEVA project. Both fictional documents pass "
        "validation and can be selected independently for Data Package export.\n",
        encoding="utf-8",
    )
    report = validate_project(output)
    if not report.release_ready:
        codes = [issue.code for document in report.documents for issue in document.issues]
        raise RuntimeError(f"Generated fixture failed validation: {codes}")
    return output


def main() -> int:
    """Parse the fixture destination and build a complete workspace."""

    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(__file__).resolve().parents[1] / "complete-dummy-project"
    parser.add_argument("--output", type=Path, default=default)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    target = build_complete_workspace(arguments.output, force=arguments.force)
    print(f"Complete HEVA workspace written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
