"""瑕疵定位（locate-defects）算法单元测试。"""
import pytest

from app.imposition import press_layout, locate_defects, DefectPointError


def _layout(**overrides):
    params = {
        "total_pages": 4,
        "max_sheets": 1,
        "binding": "left",
        "page_width_mm": 210.0,
        "page_height_mm": 297.0,
        "gutter_mm": 10.0,
        "duplex_flip": "long",
    }
    params.update(overrides)
    return press_layout(**params)


def _point(side="front", x=10.0, y=20.0, signature=1, sheet=1):
    return {
        "signature_index": signature,
        "sheet_index": sheet,
        "side": side,
        "x_mm": x,
        "y_mm": y,
    }


def test_front_slots_return_pages_and_in_slot_coordinates():
    # 4 页左装订 long：正面 左槽=页4(x=0)、右槽=页1(x=220)
    result = locate_defects(_layout(), [_point("front", 10.0, 20.0),
                                        _point("front", 230.0, 30.0)])
    d1, d2 = result["defects"]
    assert (d1["status"], d1["slot"], d1["page"]) == ("located", "left", 4)
    assert (d1["page_x_mm"], d1["page_y_mm"]) == (10.0, 20.0)
    assert (d2["status"], d2["slot"], d2["page"]) == ("located", "right", 1)
    # 右槽 x=220 起算：230 -> 页内 10
    assert (d2["page_x_mm"], d2["page_y_mm"]) == (10.0, 30.0)


def test_long_flip_back_uses_swapped_slots():
    # long 背面交换槽位：左槽=页3(x=0)、右槽=页2(x=220)，旋转 0
    result = locate_defects(_layout(), [_point("back", 5.0, 7.0),
                                        _point("back", 225.0, 9.0)])
    d1, d2 = result["defects"]
    assert (d1["slot"], d1["page"], d1["page_x_mm"]) == ("left", 3, 5.0)
    assert (d2["slot"], d2["page"], d2["page_x_mm"]) == ("right", 2, 5.0)


def test_short_flip_back_keeps_slot_and_inverts_180():
    # short 背面槽位保持：左槽=页2(x=0)、右槽=页3(x=210)，各旋转 180°
    result = locate_defects(
        _layout(duplex_flip="short", gutter_mm=0.0),
        [_point("back", 10.0, 20.0), _point("back", 220.0, 30.0)],
    )
    d1, d2 = result["defects"]
    assert (d1["slot"], d1["page"]) == ("left", 2)
    # 逆转 180°：(210-10, 297-20) = (200, 277)
    assert (d1["page_x_mm"], d1["page_y_mm"]) == (200.0, 277.0)
    assert (d2["slot"], d2["page"]) == ("right", 3)
    # 右槽 x=210 起算槽内 10 -> 200；y 30 -> 267
    assert (d2["page_x_mm"], d2["page_y_mm"]) == (200.0, 267.0)


def test_short_flip_back_center_point_is_invariant():
    # 页位中心点逆转后仍是中心
    result = locate_defects(
        _layout(duplex_flip="short", gutter_mm=0.0),
        [_point("back", 105.0, 148.5)],
    )
    d = result["defects"][0]
    assert d["page"] == 2
    assert d["page_x_mm"] == pytest.approx(105.0)
    assert d["page_y_mm"] == pytest.approx(148.5)


def test_gutter_points_marked_without_page():
    # 中缝区间 [210, 220]（边界归入中缝）
    result = locate_defects(
        _layout(),
        [
            _point("front", 210.0, 5.0),   # 中缝左缘
            _point("front", 215.0, 297.0),  # 中缝中央
            _point("front", 220.0, 0.0),   # 中缝右缘
        ],
    )
    for d in result["defects"]:
        assert d["status"] == "gutter"
        assert d["slot"] is None
        assert d["page"] is None
        assert d["page_x_mm"] is None and d["page_y_mm"] is None
    assert result["gutter_count"] == 3
    assert result["located_count"] == 0


def test_zero_gutter_fold_line_is_gutter():
    # gutter=0：x=页宽（左右槽分界折线）归中缝
    result = locate_defects(
        _layout(gutter_mm=0.0), [_point("front", 210.0, 10.0)]
    )
    d = result["defects"][0]
    assert d["status"] == "gutter"
    assert d["page"] is None


def test_blank_slot_points_marked_without_page():
    # 1 页补 3 空白：正面 (null, 1)、背面 (null, null)
    layout = _layout(total_pages=1, duplex_flip="short", gutter_mm=0.0)
    result = locate_defects(
        layout,
        [
            _point("front", 10.0, 10.0),    # 左槽空白
            _point("back", 10.0, 10.0),     # 背面左槽空白
            _point("back", 300.0, 10.0),    # 背面右槽空白
        ],
    )
    assert all(d["status"] == "blank" for d in result["defects"])
    assert all(d["page"] is None for d in result["defects"])
    assert result["blank_count"] == 3
    # 同帖正面右槽仍是真实页
    ok = locate_defects(layout, [_point("front", 220.0, 10.0)])
    assert ok["defects"][0]["status"] == "located"
    assert ok["defects"][0]["page"] == 1


def test_paper_boundary_points_are_inside():
    # 恰在纸面四缘：不越界；四角落在槽位/中缝
    result = locate_defects(
        _layout(gutter_mm=0.0),
        [
            _point("front", 0.0, 0.0),
            _point("front", 420.0, 297.0),
            _point("front", 0.0, 297.0),
        ],
    )
    assert result["defects"][0]["status"] == "located"
    assert (result["defects"][0]["page_x_mm"], result["defects"][0]["page_y_mm"]) == (0.0, 0.0)
    assert result["defects"][1]["status"] == "located"
    assert (result["defects"][1]["page_x_mm"], result["defects"][1]["page_y_mm"]) == (210.0, 297.0)
    assert result["defects"][2]["page_y_mm"] == 297.0


def test_right_binding_page_order_used():
    # 右装订镜像：正面 (1, 4)；long 背面交换槽位：左=2、右=3
    result = locate_defects(
        _layout(binding="right"),
        [_point("front", 1.0, 1.0), _point("front", 221.0, 1.0),
         _point("back", 1.0, 1.0)],
    )
    pages = [(d["slot"], d["page"]) for d in result["defects"]]
    assert pages == [("left", 1), ("right", 4), ("left", 2)]


def test_multi_signature_indexing():
    # 每帖 1 张：6 页 -> 2 帖；帖 2 正面 (null, 5)、long 背面交换 (null, 6 落右槽)
    layout = _layout(total_pages=6, max_sheets=1)
    result = locate_defects(
        layout,
        [
            _point("front", 230.0, 10.0, signature=2),
            _point("back", 230.0, 10.0, signature=2),
        ],
    )
    d1, d2 = result["defects"]
    assert (d1["status"], d1["page"]) == ("located", 5)
    assert (d2["status"], d2["slot"], d2["page"]) == ("located", "right", 6)


def test_counts_and_echo_fields():
    result = locate_defects(
        _layout(),
        [
            _point("front", 1.0, 1.0),    # located
            _point("front", 215.0, 1.0),  # gutter
        ],
    )
    assert result["defect_count"] == 2
    assert result["located_count"] == 1
    assert result["gutter_count"] == 1
    assert result["blank_count"] == 0
    assert result["signature_count"] == 1
    assert result["paper_width_mm"] == 430.0
    assert result["paper_height_mm"] == 297.0
    # 输入坐标原样回显
    assert (result["defects"][1]["x_mm"], result["defects"][1]["y_mm"]) == (215.0, 1.0)


def test_invalid_signature_index_raises():
    with pytest.raises(DefectPointError) as exc:
        locate_defects(_layout(), [_point(signature=2)])
    assert exc.value.field == "signature_index"
    assert exc.value.defect_index == 0


def test_invalid_sheet_index_raises():
    # 8 页、每帖 2 张：帖 1 有 2 张，张号 3 非法
    layout = _layout(total_pages=8, max_sheets=2)
    with pytest.raises(DefectPointError) as exc:
        locate_defects(layout, [_point(sheet=3)])
    assert exc.value.field == "sheet_index"


def test_out_of_paper_raises():
    with pytest.raises(DefectPointError) as exc:
        locate_defects(_layout(), [_point(x=430.1, y=1.0)])
    assert exc.value.field == "x_mm"
    with pytest.raises(DefectPointError) as exc:
        locate_defects(_layout(), [_point(x=1.0, y=297.1)])
    assert exc.value.field == "y_mm"
    with pytest.raises(DefectPointError):
        locate_defects(_layout(), [_point(x=-0.1, y=1.0)])


def test_non_finite_coordinate_raises():
    for x, y in ((float("nan"), 1.0), (float("inf"), 1.0), (1.0, float("-inf"))):
        with pytest.raises(DefectPointError):
            locate_defects(_layout(), [_point(x=x, y=y)])


def test_error_keeps_defect_list_index():
    # 第 3 个点（索引 2）帖号非法
    with pytest.raises(DefectPointError) as exc:
        locate_defects(
            _layout(),
            [_point(), _point(), _point(signature=9)],
        )
    assert exc.value.defect_index == 2
