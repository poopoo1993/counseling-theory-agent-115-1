import pytest

from src.theory_library import SCHOOLS, get_techniques, validate_selected_techniques


def test_exactly_eleven_schools_and_five_techniques_each():
    assert len(SCHOOLS) == 11
    for school in SCHOOLS.values():
        assert len(school["techniques"]) == 5
        assert len({item["id"] for item in school["techniques"]}) == 5


def test_experience_defaults_are_three_valid_techniques():
    for school_id, school in SCHOOLS.items():
        assert len(school["experience_default"]) == 3
        assert len(get_techniques(school_id, school["experience_default"])) == 3


def test_practice_requires_exactly_three():
    with pytest.raises(ValueError):
        validate_selected_techniques("cbt", ["automatic_thoughts"])
    validate_selected_techniques("cbt", ["automatic_thoughts", "evidence_review", "cognitive_restructuring"])
