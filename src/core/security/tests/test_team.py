from src.core.security.team import team_permissions

GROUP = "pic"


def payload(**claims):
    return {"preferred_username": "52998224725", "reliability_level": "ouro", **claims}


def test_member_of_the_team_is_super_admin():
    permissions = team_permissions(payload(groups=["pic"]), GROUP)

    assert permissions is not None
    assert permissions.cpf == "52998224725"
    assert permissions.is_admin
    assert permissions.is_super_admin
    assert permissions.permission == "super_admin"
    assert permissions.active


def test_member_of_other_groups_too_is_super_admin():
    assert team_permissions(payload(groups=["devops", "pic"]), GROUP) is not None


def test_user_of_other_groups_gets_nothing():
    assert team_permissions(payload(groups=["devops"]), GROUP) is None


def test_user_without_groups_gets_nothing():
    assert team_permissions(payload(), GROUP) is None
    assert team_permissions(payload(groups=None), GROUP) is None
    assert team_permissions(payload(groups=[]), GROUP) is None


def test_a_single_group_as_text_is_accepted():
    assert team_permissions(payload(groups="pic"), GROUP) is not None


def test_group_name_is_matched_exactly():
    assert team_permissions(payload(groups=["pic-other", "PIC"]), GROUP) is None


def test_token_without_cpf_gets_nothing():
    assert team_permissions({"groups": ["pic"]}, GROUP) is None


def test_member_without_the_gold_level_gets_nothing():
    for level in ("bronze", "prata", "", None):
        token = payload(groups=["pic"], reliability_level=level)
        assert team_permissions(token, GROUP) is None


def test_member_with_a_token_without_level_gets_nothing():
    token = {"preferred_username": "52998224725", "groups": ["pic"]}
    assert team_permissions(token, GROUP) is None


def test_member_without_the_gold_level_gets_permissions_when_gold_is_not_required():
    for level in ("bronze", "prata", None):
        token = payload(groups=["pic"], reliability_level=level)
        assert team_permissions(token, GROUP, require_gold=False) is not None


def test_gold_is_required_by_default():
    token = payload(groups=["pic"], reliability_level="prata")
    assert team_permissions(token, GROUP) is None


def test_group_is_still_required_when_gold_is_not_required():
    token = payload(groups=["devops"], reliability_level="ouro")
    assert team_permissions(token, GROUP, require_gold=False) is None
