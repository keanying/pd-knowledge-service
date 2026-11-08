import pytest

from pdk.auth.context import AuthContext
from pdk.auth.snapshot import AuthzSnapshot, SnapshotUser
from pdk.core.errors import BizError
from pdk.enrich.pii import detect, mask
from pdk.retrieval.filters import build_filter, to_milvus_expr
from pdk.storage.vectors import SearchFilter, VectorRow


def test_detect_and_mask():
    text = "联系人 13812345678，身份证 11010519491231002X，卡号 6222020200112233445，邮箱 zhang@example.com，车牌 浙A12345"
    types = detect(text)
    assert {"phone", "id_card", "email", "plate"} <= set(types)
    out, n = mask(text)
    assert "138****5678" in out and "110***********002X" in out and "z***@example.com" in out and "浙A****5" in out
    assert n >= 4
    # 校验位不对的 18 位数字不当作身份证
    assert "id_card" not in detect("编号 110105194912310021")


def ctx(kbs=None, scenic=("S001",), level=1, admin=("kb_admin",)):
    snap = AuthzSnapshot(user=SnapshotUser(id="u1"), permissions={"pdk:search:use"}, scenicScope=set(scenic),
                         maxSecurityLevel=level, resources={"pdk:kb": {"read": set(kbs or []), "admin": set(admin)}})
    return AuthContext(user_id="u1", name="u1", snapshot=snap, via="test")


def test_filter_only_narrows():
    f = build_filter(ctx(["kb1", "kb2"]), kb_ids=["kb2", "kb9"], now=100)
    assert f.kb_ids == ["kb2"] and f.scenic_ids == ["GROUP", "S001"] and f.max_security_level == 1
    # 管理权包含查看权
    assert "kb_admin" in build_filter(ctx(["kb1"]), now=1).kb_ids
    with pytest.raises(BizError):
        build_filter(ctx([], admin=()), now=1)
    with pytest.raises(BizError):
        build_filter(ctx(["kb1"]), kb_ids=["kb9"], now=1)


def test_filter_rejects_injection():
    with pytest.raises(BizError):
        build_filter(ctx(["kb1"]), kb_ids=['kb1"] or kb_id != ["x'], now=1)


def test_milvus_expr():
    expr = to_milvus_expr(SearchFilter(scenic_ids=["GROUP", "S001"], kb_ids=["kb1"], max_security_level=2, now=5,
                                       tags=['票"务']))
    assert expr == ('scenic_id in ["GROUP", "S001"] and kb_id in ["kb1"] and security_level <= 2 and '
                    'effective_from <= 5 and effective_to >= 5 and array_contains_any(tags, ["票\\"务"])')


def test_memory_filter_match():
    f = SearchFilter(scenic_ids=["S001", "GROUP"], kb_ids=["kb1"], max_security_level=1, now=50)
    row = VectorRow(pk="c", chunk_key="c", scenic_id="S001", kb_id="kb1", doc_id="d", security_level=1, tags=[],
                    chunk_type="text", effective_from=0, effective_to=100, text="", dense=[])
    assert f.match(row)
    for change in ({"scenic_id": "S002"}, {"kb_id": "kb2"}, {"security_level": 2}, {"effective_to": 40}):
        assert not f.match(VectorRow(**{**row.__dict__, **change}))
