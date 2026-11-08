from pdk.chunking.base import ChunkStrategy, chunk_faq, chunk_key, chunk_structure, split_long, split_table
from pdk.parsers.base import Block


def B(i, t, text, level=None):
    return Block(block_id=f"b{i}", type=t, text=text, level=level)


def test_structure_title_path_and_table():
    blocks = [B(0, "title", "游客须知", 1), B(1, "title", "票务", 2), B(2, "text", "成人票 120 元。"),
              B(3, "title", "优惠", 3), B(4, "text", "老人免票。"), B(5, "title", "交通", 2), B(6, "text", "乘 7 路公交。"),
              B(7, "table", "| a | b |\n|---|---|\n| 1 | 2 |"), B(8, "footer", "第 1 页")]
    cs = chunk_structure(blocks, ChunkStrategy())
    assert [c.title_path for c in cs] == ["游客须知 > 票务", "游客须知 > 票务 > 优惠", "游客须知 > 交通", "游客须知 > 交通"]
    assert cs[1].embed_text.startswith("游客须知 > 票务 > 优惠\n") and cs[1].text == "老人免票。"
    assert cs[3].chunk_type == "table"
    assert all("第 1 页" not in c.text for c in cs)


def test_split_long_breaks_at_sentence_with_overlap():
    text = "第一句话。" * 30  # 150 字
    parts = split_long(text, 50, 10)
    assert len(parts) >= 3
    assert all(len(p) <= 60 for p in parts)
    assert parts[1].startswith(parts[0][-10:])
    assert parts[0].endswith("。")


def test_big_table_repeats_header():
    rows = "\n".join(f"| 设施{i} | 开放时间 08:00-18:00 |" for i in range(80))
    md = "| 名称 | 时间 |\n|---|---|\n" + rows
    parts = split_table(md, 200)
    assert len(parts) > 2 and all(p.startswith("| 名称 | 时间 |\n|---|---|") for p in parts)


def test_faq_text_and_table():
    cs = chunk_faq([B(0, "text", "问：几点开门？\n答：8 点。\n问：能带宠物吗？\n答：不能。"),
                    B(1, "table", "| 问题 | 答案 |\n|---|---|\n| 有停车场吗 | 有 |")], ChunkStrategy(mode="faq"))
    assert [c.embed_text for c in cs] == ["几点开门？", "能带宠物吗？", "有停车场吗"]
    assert cs[0].text == "问：几点开门？\n答：8 点。" and cs[0].chunk_type == "faq"


def test_chunk_key_is_version_independent():
    assert chunk_key("d1", "h", 0) == chunk_key("d1", "h", 0) != chunk_key("d1", "h", 1) != chunk_key("d2", "h", 0)
