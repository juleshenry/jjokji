from __future__ import annotations

import csv
import contextlib
from datetime import datetime
import importlib.util
import io
import json
import shutil
import subprocess
import uuid
from importlib.machinery import SourceFileLoader
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ALL_LANG_ROOT = REPO_ROOT / "all_lang_notes"
JJ_PATH = REPO_ROOT / "jj"


def load_jj_module():
    loader = SourceFileLoader("jj_module", str(JJ_PATH))
    spec = importlib.util.spec_from_loader("jj_module", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def copy_tree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def run_brainbrew(recipe: str, workdir: Path) -> None:
    result = subprocess.run(
        ["/Users/enrique/.local/bin/brainbrew", "run", recipe],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def run_build_anki(workdir: Path) -> None:
    result = subprocess.run(
        ["python3", str(workdir / "scripts" / "build_anki.py")],
        cwd=workdir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def read_csv_rows(csv_file: Path) -> list[list[str]]:
    with csv_file.open(newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


def count_matching_rows(csv_file: Path, expected_tail: list[str]) -> int:
    return sum(1 for row in read_csv_rows(csv_file)[1:] if row[1:] == expected_tail)


def make_recipe_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "all_lang_notes"
    workspace.mkdir()
    copy_tree(ALL_LANG_ROOT / "recipes", workspace / "recipes")
    copy_tree(ALL_LANG_ROOT / "src", workspace / "src")
    copy_tree(ALL_LANG_ROOT / "scripts", workspace / "scripts")
    copy_tree(ALL_LANG_ROOT / "config", workspace / "config")
    return workspace


def test_source_to_anki_recipe_builds_crowdanki_export(tmp_path: Path) -> None:
    workspace = make_recipe_workspace(tmp_path)

    run_brainbrew("recipes/source_to_anki.yaml", workspace)

    deck_json = workspace / "build" / "all_lang_notes_anki" / "deck.json"
    assert deck_json.exists()

    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    assert deck["name"] == "All Language Notes"
    assert deck["note_models"][0]["name"] == "LanguageModel"
    assert len(deck["notes"]) > 0

    split_note_fronts = [note["fields"][2] for note in deck["notes"]]
    assert "2023-06-16 top-100-albums" not in split_note_fronts
    assert "2023-06-16 top-100-words (1/4)" in split_note_fronts
    assert "2023-06-16 top-100-words (4/4)" in split_note_fronts
    assert "2023-06-16 verb-conjugations (1/3)" in split_note_fronts
    assert "2023-06-16 verb-conjugations (3/3)" in split_note_fronts
    assert "première partie III (1/3)" in split_note_fronts
    assert "première partie III (3/3)" in split_note_fronts
    assert "deuxième partie IV (1/2)" in split_note_fronts
    assert "deuxième partie IV (2/2)" in split_note_fronts


def test_anki_to_source_recipe_restores_language_notes_csv(tmp_path: Path) -> None:
    workspace = make_recipe_workspace(tmp_path)

    run_brainbrew("recipes/source_to_anki.yaml", workspace)

    original_csv = (workspace / "src" / "data" / "LanguageNotes.csv").read_text(encoding="utf-8")
    (workspace / "src" / "data" / "LanguageNotes.csv").unlink()
    shutil.rmtree(workspace / "src" / "media", ignore_errors=True)
    (workspace / "src" / "media").mkdir(parents=True, exist_ok=True)

    run_brainbrew("recipes/anki_to_source.yaml", workspace)

    restored_csv = workspace / "src" / "data" / "LanguageNotes.csv"
    assert restored_csv.exists()

    restored_text = restored_csv.read_text(encoding="utf-8")
    assert len(restored_text.splitlines()) > 0
    assert restored_text != original_csv


def test_source_to_anki_applies_configured_ignore_and_split_rules(tmp_path: Path) -> None:
    workspace = make_recipe_workspace(tmp_path)

    run_brainbrew("recipes/source_to_anki.yaml", workspace)

    deck_json = workspace / "build" / "all_lang_notes_anki" / "deck.json"
    deck = json.loads(deck_json.read_text(encoding="utf-8"))

    notes_by_front = {note["fields"][2]: note for note in deck["notes"]}

    assert "2023-06-16 top-100-albums" not in notes_by_front
    assert "2023-06-16 top-100-words (1/4)" in notes_by_front
    assert "2023-06-16 top-100-words (4/4)" in notes_by_front
    assert "2023-06-16 verb-conjugations (1/3)" in notes_by_front
    assert "2023-06-16 verb-conjugations (3/3)" in notes_by_front

    table_chunks = [
        notes_by_front[f"2023-06-16 top-100-words ({index}/4)"]["fields"][3]
        for index in range(1, 5)
    ]
    assert "| 1 | le | the |" in table_chunks[0]
    assert "| 25 | aller | to go |" in table_chunks[0]
    assert "| 26 | voir | to see |" in table_chunks[1]
    assert "| 50 | premier | first |" in table_chunks[1]
    assert "| 51 | grand | big/large |" in table_chunks[2]
    assert "| 75 | jeune | young |" in table_chunks[2]
    assert "| 76 | regarder | to look/watch |" in table_chunks[3]
    assert "| 85 | plusieurs | several |" in table_chunks[3]

    section_chunks = [
        notes_by_front[f"2023-06-16 verb-conjugations ({index}/3)"]["fields"][3]
        for index in range(1, 4)
    ]
    assert "## ATTENDRE (to wait) -- 3rd group (-re)" in section_chunks[0]
    assert "## FINIR (to finish) -- 2nd group (-ir)" in section_chunks[1]
    assert "## PARLER (to speak) -- 1st group (-er)" in section_chunks[2]

    prose_chunks = [
        notes_by_front[f"première partie III ({index}/3)"]["fields"][3]
        for index in range(1, 4)
    ]
    assert prose_chunks[0].startswith("tromper -> to deceive\n")
    assert prose_chunks[0].endswith("ça vaut mieux -> it's better that way\n")
    assert prose_chunks[1].startswith("tombé -> fell\n")
    assert "modde-piéte -> doormat\n" in prose_chunks[1]
    assert prose_chunks[2].endswith("gémissait -> was groaning\n")


def test_build_anki_wrapper_normalizes_before_export(tmp_path: Path) -> None:
    workspace = make_recipe_workspace(tmp_path)

    active_csv = workspace / "src" / "data" / "LanguageNotes.csv"
    ignored_csv = workspace / "src" / "data" / "LanguageNotesIgnored.csv"

    with active_csv.open(encoding="utf-8", newline="") as handle:
        active_rows = list(csv.DictReader(handle))
    with ignored_csv.open(encoding="utf-8", newline="") as handle:
        ignored_rows = list(csv.DictReader(handle))

    album_row = next(row for row in ignored_rows if row["Front"] == "2023-06-16 top-100-albums")
    ignored_rows = [row for row in ignored_rows if row["Front"] != "2023-06-16 top-100-albums"]
    active_rows.insert(0, album_row)

    with active_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["guid", "Language", "Topic", "Front", "Back", "tags"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(active_rows)

    with ignored_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["guid", "Language", "Topic", "Front", "Back", "tags"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(ignored_rows)

    run_build_anki(workspace)

    deck_json = workspace / "build" / "all_lang_notes_anki" / "deck.json"
    deck = json.loads(deck_json.read_text(encoding="utf-8"))
    fronts = [note["fields"][2] for note in deck["notes"]]
    assert "2023-06-16 top-100-albums" not in fronts

    with ignored_csv.open(encoding="utf-8", newline="") as handle:
        normalized_ignored_rows = list(csv.DictReader(handle))
    assert any(row["Front"] == "2023-06-16 top-100-albums" for row in normalized_ignored_rows)


def test_append_csv_splits_back_on_newlines(tmp_path: Path) -> None:
    jj = load_jj_module()
    csv_file = tmp_path / "LanguageNotes.csv"
    csv_file.write_text("guid,Language,Topic,Front,Back,tags\n", encoding="utf-8")

    count = jj.append_csv(
        str(csv_file),
        "Portuguese",
        "es",
        "lascado",
        "Loucas: chipped\nMadeira: splintered\nRiscos: nicked",
    )

    with csv_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert count == 3
    assert len(rows) == 4
    assert rows[1][2:] == ["es", "lascado", "Loucas: chipped", "portuguese"]
    assert rows[2][2:] == ["es", "lascado", "Madeira: splintered", "portuguese"]
    assert rows[3][2:] == ["es", "lascado", "Riscos: nicked", "portuguese"]


def test_split_back_segments_supports_semicolons_and_numbered_items() -> None:
    jj = load_jj_module()

    segments = jj.split_back_segments(
        "1. Loucas: chipped; 2. Madeira: splintered; 3) Riscos: nicked"
    )

    assert segments == [
        "Loucas: chipped",
        "Madeira: splintered",
        "Riscos: nicked",
    ]


def test_parse_add_args_defaults_target_language_to_en() -> None:
    jj = load_jj_module()

    parsed = jj.parse_add_args(["pt", "convite", "invitation"])

    assert parsed == ("pt", "en", "convite", "invitation")


def test_parse_add_args_keeps_explicit_target_language() -> None:
    jj = load_jj_module()

    parsed = jj.parse_add_args(["pt", "es", "convite", "invitacion"])

    assert parsed == ("pt", "es", "convite", "invitacion")


def test_read_stdin_back_if_needed_returns_literal_when_not_dash() -> None:
    jj = load_jj_module()

    assert jj.read_stdin_back_if_needed("literal text") == "literal text"


def test_parse_google_translate_blob_infers_languages_and_text() -> None:
    jj = load_jj_module()

    parsed = jj.parse_add_args([
        "Portuguese - detected\nEnglish\nalheia\nalien"
    ])

    assert parsed == ("pt", "en", "alheia", "alien")


def test_parse_google_translate_blob_keeps_polysemous_translations() -> None:
    jj = load_jj_module()

    parsed = jj.parse_add_args([
        "Portuguese\n"
        "English\n"
        "aquecimento\n"
        "heating\n"
        "Translations of aquecimento\n"
        "noun\n"
        "heating\n"
        "aquecimento, calefacao, fermentacao\n"
        "warming\n"
        "aquecimento, sova\n"
        "warm\n"
        "aquecimento\n"
        "firing\n"
        "acendimento, fogo, tiroteio, aquecimento, cozimento, combustivel\n"
        "acceleration\n"
        "aceleracao, aquecimento\n"
        "chafe\n"
        "irritacao, escoriacao, aquecimento, calor\n"
        "warming-up\n"
        "aquecimento"
    ])

    assert parsed == (
        "pt",
        "en",
        "aquecimento",
        "heating\nwarming\nwarm\nfiring\nacceleration\nchafe\nwarming-up",
    )


def test_find_exact_duplicates_detects_existing_segments(tmp_path: Path) -> None:
    jj = load_jj_module()
    csv_file = tmp_path / "LanguageNotes.csv"
    csv_file.write_text(
        "guid,Language,Topic,Front,Back,tags\n"
        "1,Portuguese,en,alheia,alien,portuguese\n"
        "2,Portuguese,en,alheia,estranged,portuguese\n",
        encoding="utf-8",
    )

    duplicates = jj.find_exact_duplicates(
        str(csv_file),
        "Portuguese",
        "en",
        "alheia",
        "alien\nestranged\noutsider",
    )

    assert duplicates == ["alien", "estranged"]


def test_notes_markdown_file_uses_local_date_stamp(tmp_path: Path) -> None:
    jj = load_jj_module()

    date_stamp = datetime.now().astimezone().date().isoformat()
    assert jj.notes_markdown_file(str(tmp_path)) == str(
        tmp_path / f"jjokji_notes_{date_stamp}.md"
    )


def test_doctor_lists_discovered_notes_repos_only(tmp_path: Path) -> None:
    jj = load_jj_module()
    (tmp_path / "portuguese").mkdir()
    (tmp_path / "french").mkdir()
    (tmp_path / "random_folder").mkdir()

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        status = jj.doctor(str(tmp_path))

    rendered = output.getvalue()
    assert status == 0
    assert f"ok      {tmp_path / 'french'}" in rendered
    assert f"ok      {tmp_path / 'portuguese'}" in rendered
    assert "spanish" not in rendered
    assert "random_folder" not in rendered


def test_add_note_only_requires_target_repo(tmp_path: Path) -> None:
    jj = load_jj_module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "notes" / "portuguese").mkdir(parents=True)
    shutil.copytree(REPO_ROOT / "all_lang_notes", workspace / "all_lang_notes")

    original_notes_root = jj.notes_root
    original_all_lang_root = jj.all_lang_root
    original_brainbrew_command = jj.brainbrew_command
    original_rebuild = jj.rebuild
    try:
        jj.notes_root = lambda: str(workspace / "notes")
        jj.all_lang_root = lambda: str(workspace / "all_lang_notes")
        jj.brainbrew_command = lambda: "brainbrew"
        jj.rebuild = lambda all_lang_root, brainbrew: 0

        unique_suffix = uuid.uuid4().hex
        front = f"convite_teste_fixture_{unique_suffix}"
        back = f"invitation fixture {unique_suffix}"

        result = jj.add_note("pt", "en", front, back)

        assert result == 0
        date_stamp = datetime.now().astimezone().date().isoformat()
        assert (workspace / "notes" / "portuguese" / f"jjokji_notes_{date_stamp}.md").exists()
    finally:
        jj.notes_root = original_notes_root
        jj.all_lang_root = original_all_lang_root
        jj.brainbrew_command = original_brainbrew_command
        jj.rebuild = original_rebuild


def test_jj_command_splits_multiline_back_into_multiple_cards(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"
    before_count = len(read_csv_rows(csv_file))

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "pt",
            "es",
            "lascado",
            "Loucas: chipped\nMadeira: splintered\nRiscos: nicked",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    after_rows = read_csv_rows(csv_file)
    assert len(after_rows) == before_count + 3
    assert count_matching_rows(csv_file, ["Portuguese", "es", "lascado", "Loucas: chipped", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "es", "lascado", "Madeira: splintered", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "es", "lascado", "Riscos: nicked", "portuguese"]) == 1


def test_jj_command_defaults_target_language_to_en(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "pt",
            "convitezinho_unico",
            "tiny invitation",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert count_matching_rows(csv_file, ["Portuguese", "en", "convitezinho_unico", "tiny invitation", "portuguese"]) == 1


def test_jj_command_accepts_google_translate_blob(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "Portuguese - detected\nEnglish\nalheia_unica\nalien unique",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert count_matching_rows(csv_file, ["Portuguese", "en", "alheia_unica", "alien unique", "portuguese"]) == 1


def test_jj_command_accepts_polysemous_google_translate_blob(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"
    before_count = len(read_csv_rows(csv_file))

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
                "Portuguese\n"
                "English\n"
                "aquecimento_unico\n"
                "heating\n"
                "Translations of aquecimento_unico\n"
                "noun\n"
                "heating\n"
            "aquecimento, calefacao, fermentacao\n"
            "warming\n"
            "aquecimento, sova\n"
            "warm\n"
            "aquecimento\n"
            "firing\n"
            "acendimento, fogo, tiroteio, aquecimento, cozimento, combustivel\n"
            "acceleration\n"
            "aceleracao, aquecimento\n"
            "chafe\n"
            "irritacao, escoriacao, aquecimento, calor\n"
            "warming-up\n"
            "aquecimento",
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout

    after_rows = read_csv_rows(csv_file)
    assert len(after_rows) == before_count + 7
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "heating", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "warming", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "warm", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "firing", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "acceleration", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "chafe", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "aquecimento_unico", "warming-up", "portuguese"]) == 1


def test_jj_command_prompts_and_cancels_on_exact_duplicate(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"
    before_text = csv_file.read_text(encoding="utf-8")

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "Portuguese - detected\nEnglish\nalheia\nalien",
        ],
        cwd=workspace,
        input="n\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "exact duplicate note(s) found:" in result.stdout
    assert "cancelled" in result.stdout
    assert csv_file.read_text(encoding="utf-8") == before_text


def test_jj_command_prompts_and_allows_duplicate_on_yes(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"
    before_count = len(read_csv_rows(csv_file))

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "Portuguese - detected\nEnglish\nalheia\nalien",
        ],
        cwd=workspace,
        input="y\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "exact duplicate note(s) found:" in result.stdout
    assert len(read_csv_rows(csv_file)) == before_count + 1


def test_jj_command_reads_back_text_from_stdin(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    shutil.copytree(REPO_ROOT, workspace / "jjokji")

    csv_file = workspace / "jjokji" / "all_lang_notes" / "src" / "data" / "LanguageNotes.csv"

    result = subprocess.run(
        [
            str(workspace / "jjokji" / "jj"),
            "pt",
            "arrebentar_unico",
            "-",
        ],
        cwd=workspace,
        input="Literal: to break or burst\nSlang: to kill it",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    rows = read_csv_rows(csv_file)
    assert count_matching_rows(csv_file, ["Portuguese", "en", "arrebentar_unico", "Literal: to break or burst", "portuguese"]) == 1
    assert count_matching_rows(csv_file, ["Portuguese", "en", "arrebentar_unico", "Slang: to kill it", "portuguese"]) == 1
