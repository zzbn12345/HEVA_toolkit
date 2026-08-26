"""Build the complete, app-openable HEVA workspace used for Alpha demonstrations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

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
    """Create a small byte-stable PDF without timestamps or random document identifiers."""

    def pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = (
        f"BT /F1 18 Tf 72 752 Td ({pdf_text(title)}) Tj "
        f"0 -40 Td /F1 12 Tf ({pdf_text(sentence)}) Tj ET\n"
    ).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
        + content
        + b"endstream",
        b"<< /Title (HEVA complete workspace fixture) /Author (HEVA Toolkit) >>",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, item in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(item)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f\n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n\n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.write_bytes(output)


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
        review_path = output / ".heva" / "documents" / entry.document_id / "review-state.json"
        review_payload = json.loads(review_path.read_text(encoding="utf-8"))
        for sentence_review in review_payload["sentences"]:
            sentence_review["decided_at"] = "2026-08-26T12:00:00Z"
            for event in sentence_review["audit"]:
                event["occurred_at"] = "2026-08-26T12:00:00Z"
        review_path.write_text(
            json.dumps(review_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
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
