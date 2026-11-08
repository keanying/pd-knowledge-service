from pdk.parsers.mineru import convert_response
from pdk.parsers.plaintext import PlainTextParser


async def test_markdown_blocks():
    doc = await PlainTextParser().parse("# 标题\n\n正文一。\n\n- 列表1\n- 列表2\n\n| a | b |\n|---|---|\n| 1 | 2 |\n".encode(), "x.md")
    assert [b.type for b in doc.blocks] == ["title", "text", "list", "table"]
    assert doc.blocks[0].level == 1


async def test_gbk_csv():
    doc = await PlainTextParser().parse("名称,价格\n成人票,120\n".encode("gbk"), "价格.csv")
    assert doc.blocks[0].type == "table" and "成人票" in doc.blocks[0].text


def test_mineru_content_list():
    body = {"backend": "pipeline", "version": "2.x", "results": {"a.pdf": {"md_content": "# 标题", "content_list": [
        {"type": "text", "text": "标题", "text_level": 1, "page_idx": 0, "bbox": [1, 2, 3, 4]},
        {"type": "text", "text": "正文", "page_idx": 0},
        {"type": "table", "table_body": "<table><tr><td>1</td></tr></table>", "table_caption": ["表1"], "page_idx": 1},
        {"type": "image", "img_path": "x.jpg", "image_caption": ["示意图"], "page_idx": 1},
        {"type": "image", "img_path": "y.jpg", "page_idx": 1},
    ]}}}
    doc = convert_response(body)
    assert [(b.type, b.page_no) for b in doc.blocks] == [("title", 1), ("text", 1), ("table", 2), ("image", 2)]
    assert doc.blocks[0].bbox == [1.0, 2.0, 3.0, 4.0] and doc.blocks[2].text.startswith("表1\n")
