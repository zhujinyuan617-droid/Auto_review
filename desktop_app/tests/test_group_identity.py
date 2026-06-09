from autoreview_app.groups.identity import anchor_author, author_identity


def test_identity_normalizes_name():
    assert author_identity("Smith, John") == author_identity("john  smith")
    assert author_identity("Smith, J.") == author_identity("J Smith")


def test_identity_is_family_plus_first_initial():
    assert author_identity("Smith, John A.") == "smith_j"
    assert author_identity("Wang, Li") == "wang_l"


def test_empty_identity():
    assert author_identity("") == ""
    assert author_identity("   ") == ""


def test_anchor_is_last_author():
    assert anchor_author(["First, A", "Middle, B", "Senior, C"]) == "Senior, C"


def test_anchor_empty_list():
    assert anchor_author([]) == ""
