from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path("assets/img/posts/feishu-lobster-deployment")
W, H = 1200, 720


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F = {
    "nav": font(18),
    "body": font(20),
    "small": font(16),
    "xs": font(14),
    "title": font(31, True),
    "sub": font(17),
    "h2": font(24, True),
    "h3": font(20, True),
    "badge": font(15, True),
}


COL = {
    "bg": "#F6F9F5",
    "panel": "#FFFFFF",
    "panel2": "#EEF6EF",
    "green": "#2F6F46",
    "green2": "#E4F2E8",
    "green3": "#D4E9DA",
    "text": "#19251E",
    "muted": "#607066",
    "line": "#D8E4DA",
    "gold": "#A36B13",
    "goldbg": "#FFF5DF",
    "blue": "#2F5C9B",
    "red": "#B14B42",
}


def rr(draw, box, r=14, fill="#fff", outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def text(draw, xy, s, kind="body", fill=None, anchor=None):
    draw.text(xy, s, font=F[kind], fill=fill or COL["text"], anchor=anchor)


def chip(draw, xy, label, fill=COL["green2"], fg=COL["green"]):
    x, y = xy
    w = 22 + len(label) * 15
    rr(draw, (x, y, x + w, y + 30), 15, fill=fill, outline=COL["line"])
    text(draw, (x + 12, y + 5), label, "xs", fg)
    return x + w + 8


def base(active="飞书接入"):
    im = Image.new("RGB", (W, H), COL["bg"])
    d = ImageDraw.Draw(im)
    rr(d, (24, 24, W - 24, H - 24), 18, fill="#FBFDFB", outline=COL["line"])

    # Feishu-like shell
    rr(d, (52, 52, 290, H - 52), 0, fill="#ECF4EF")
    rr(d, (318, 52, W - 52, H - 52), 18, fill=COL["panel"], outline=COL["line"])

    rr(d, (76, 74, 114, 112), 10, fill=COL["green"])
    text(d, (95, 82), "飞", "badge", "#FFFFFF", anchor=None)
    text(d, (128, 78), "部门小龙虾", "h3")
    text(d, (128, 108), "飞书部署工作台", "small", COL["muted"])

    items = ["飞书接入", "员工开通", "模型配置", "知识库", "联调检查", "技能库"]
    y = 150
    for item in items:
        if item == active:
            rr(d, (74, y - 10, 272, y + 34), 8, fill="#DDECE1")
            fill = COL["green"]
            kind = "badge"
        else:
            fill = COL["muted"]
            kind = "nav"
        text(d, (90, y), item, kind, fill)
        y += 58
    return im, d


def title_block(d, title, subtitle):
    text(d, (344, 78), title, "title")
    text(d, (344, 118), subtitle, "sub", COL["muted"])


def field(d, x, y, label, value, secret=False, w=330):
    text(d, (x, y), label, "xs", COL["muted"])
    rr(d, (x, y + 24, x + w, y + 68), 8, fill="#FAFCFA", outline=COL["line"])
    shown = "••••••••••••••••" if secret else value
    text(d, (x + 14, y + 35), shown, "small", COL["text"])


def save(name, im):
    im.save(OUT / name, optimize=True)


def feishu_wizard():
    im, d = base("飞书接入")
    title_block(d, "飞书接入", "同一个自建应用承接员工前台和部署工作台")
    rr(d, (342, 154, 724, 492), 14, fill="#F8FBF8", outline=COL["line"])
    text(d, (366, 180), "应用参数", "h2", COL["green"])
    field(d, 366, 222, "App ID", "cli_a6f3xxxx", w=310)
    field(d, 366, 306, "App Secret", "", secret=True, w=310)
    field(d, 366, 390, "Encrypt Key", "", secret=True, w=310)

    rr(d, (748, 154, 1088, 492), 14, fill="#F8FBF8", outline=COL["line"])
    text(d, (772, 180), "事件回调", "h2", COL["green"])
    field(d, 772, 222, "Verification Token", "", secret=True, w=268)
    text(d, (772, 324), "回调地址", "xs", COL["muted"])
    rr(d, (772, 348, 1044, 414), 8, fill="#FAFCFA", outline=COL["line"])
    text(d, (788, 358), "https://lobster.company.com", "small", COL["text"])
    text(d, (788, 383), "/feishu/events", "small", COL["text"])
    rr(d, (772, 436, 930, 474), 8, fill=COL["green"])
    text(d, (797, 445), "测试 challenge", "small", "#FFFFFF")

    rr(d, (342, 526, 1088, 640), 14, fill=COL["goldbg"], outline="#E8C47B")
    text(d, (366, 550), "联调顺序", "h3", COL["gold"])
    x = 366
    for item in ["创建自建应用", "启用机器人", "订阅事件", "发布到部门"]:
        x = chip(d, (x, 590), item, fill="#FFF9EA", fg=COL["gold"])
    return im


def excel_import():
    im, d = base("员工开通")
    title_block(d, "员工 Excel 一键开通", "上传四列信息，后端自动匹配通讯录并创建 profile")
    rr(d, (342, 154, 636, 310), 14, fill=COL["green2"], outline="#CBE2D1")
    text(d, (368, 188), "拖入员工开通表", "h2", COL["green"])
    text(d, (368, 226), "字段：工号、姓名、存储空间容量", "small", COL["muted"])
    text(d, (368, 250), "每月Token容量额度", "small", COL["muted"])
    rr(d, (368, 268, 508, 302), 8, fill=COL["green"])
    text(d, (398, 275), "选择 Excel", "small", "#FFFFFF")

    rr(d, (660, 154, 1088, 310), 14, fill="#F8FBF8", outline=COL["line"])
    text(d, (688, 186), "校验结果", "h2", COL["green"])
    x = 688
    for item in ["通讯录 30/30", "容量 620GB"]:
        x = chip(d, (x, 230), item)
    x = 688
    for item in ["额度 4,600万", "待确认 1人"]:
        x = chip(d, (x, 266), item)

    rr(d, (342, 342, 1088, 640), 14, fill="#FFFFFF", outline=COL["line"])
    headers = ["工号", "姓名", "容量", "月 token 额度", "匹配状态", "profile"]
    widths = [90, 100, 120, 150, 140, 180]
    x0, y0 = 370, 382
    x = x0
    for h, w in zip(headers, widths):
        text(d, (x, y0), h, "xs", COL["muted"])
        x += w
    rows = [
        ["U001", "张三", "20GB", "100万", "已匹配", "lobster-u001"],
        ["U002", "李四", "20GB", "150万", "已匹配", "lobster-u002"],
        ["U003", "王五", "30GB", "200万", "待确认", "预留"],
    ]
    y = 422
    for row in rows:
        rr(d, (362, y - 10, 1060, y + 34), 8, fill="#FAFCFA", outline=COL["line"])
        x = x0
        for val, w in zip(row, widths):
            fill = COL["gold"] if val == "待确认" else COL["text"]
            text(d, (x, y), val, "small", fill)
            x += w
        y += 58
    rr(d, (370, 582, 510, 622), 8, fill=COL["green"])
    text(d, (393, 591), "确认并开通", "small", "#FFFFFF")
    return im


def model_config():
    im, d = base("模型配置")
    title_block(d, "模型配置", "知识库优先走公司内网 API，离线模型只作为兜底")
    x = 344
    for label, active in [("公司内网 API", True), ("本机离线模型", False), ("外部非涉密模型", False)]:
        rr(d, (x, 154, x + 156, 196), 20, fill=COL["green"] if active else "#F3F7F3", outline=COL["line"])
        text(d, (x + 22, 165), label, "small", "#FFFFFF" if active else COL["muted"])
        x += 170
    field(d, 344, 234, "API Base", "https://llm.internal.company/v1", w=352)
    field(d, 736, 234, "API Key", "", secret=True, w=300)
    field(d, 344, 328, "默认模型名", "company-research-chat", w=300)
    field(d, 736, 328, "最大上下文", "128K", w=180)
    rr(d, (344, 450, 528, 492), 8, fill=COL["green"])
    text(d, (382, 461), "测试连接", "small", "#FFFFFF")
    rr(d, (552, 450, 890, 492), 8, fill=COL["green2"], outline="#CBE2D1")
    text(d, (574, 461), "通过：知识库任务将走内网模型", "small", COL["green"])
    rr(d, (344, 544, 1088, 624), 12, fill=COL["goldbg"], outline="#E8C47B")
    text(d, (368, 566), "安全规则", "h3", COL["gold"])
    text(d, (368, 600), "知识库原文、检索片段和引用来源不得进入外部模型通道。", "small", COL["gold"])
    return im


def kb_upload():
    im, d = base("知识库")
    title_block(d, "知识库素材上传", "上传原始资料，机器自动抽取、转写、切分、索引和生成验收报告")
    rr(d, (342, 154, 998, 274), 14, fill=COL["green2"], outline="#CBE2D1")
    text(d, (370, 186), "拖入研究资料文件夹", "h2", COL["green"])
    text(d, (370, 224), "支持 PPT/PPTX、PDF、Word、Excel、Markdown、图片、录音 m4a/mp3/wav。", "small", COL["muted"])
    rr(d, (1018, 172, 1088, 256), 14, fill=COL["green"])
    text(d, (1038, 202), "传", "h2", "#FFFFFF")

    labels = [("上传", "完成 186 个文件"), ("转写/OCR", "音频 12 条处理中"), ("切分", "按章节和访谈对象"), ("索引", "向量 + 关键词双索引"), ("验收", "抽样 20 条引用")]
    x = 354
    for title, sub in labels:
        rr(d, (x, 328, x + 134, 430), 12, fill="#EFF8F1", outline="#CBE2D1")
        text(d, (x + 18, 354), title, "h3", COL["green"])
        text(d, (x + 18, 392), sub, "xs", COL["muted"])
        x += 150
    rr(d, (342, 488, 510, 530), 8, fill=COL["green"])
    text(d, (382, 499), "开始处理", "small", "#FFFFFF")
    rr(d, (528, 488, 696, 530), 8, fill="#FFFFFF", outline=COL["line"])
    text(d, (565, 499), "查看导入报告", "small", COL["green"])
    rr(d, (342, 584, 998, 640), 10, fill=COL["goldbg"], outline="#E8C47B")
    text(d, (366, 604), "部署者只需选择模型方案并上传原始素材；OCR、ASR、embedding、rerank 和引用生成由系统队列自动处理。", "small", COL["gold"])
    return im


def debug_checklist():
    im, d = base("联调检查")
    title_block(d, "联调检查", "不是保存配置就算完成，8 个链路必须逐项通过")
    items = [
        ("飞书 challenge", "通过"),
        ("私聊消息事件", "收到 echo"),
        ("机器人发送消息", "成功"),
        ("卡片按钮回调", "成功"),
        ("工号到 open_id 映射", "30/30"),
        ("员工 Excel 写入多维表格", "成功"),
        ("知识库附件读取", "成功"),
        ("个人 profile 路由", "30/30"),
    ]
    x, y = 344, 158
    for i, (name, status) in enumerate(items):
        rr(d, (x, y, x + 350, y + 74), 12, fill="#F8FBF8", outline=COL["line"])
        rr(d, (x + 20, y + 19, x + 56, y + 55), 18, fill=COL["green"])
        text(d, (x + 29, y + 27), "OK", "xs", "#FFFFFF")
        text(d, (x + 76, y + 18), name, "h3")
        text(d, (x + 76, y + 46), status, "xs", COL["muted"])
        x += 374
        if i % 2 == 1:
            x = 344
            y += 92
    rr(d, (344, 554, 534, 596), 8, fill=COL["green"])
    text(d, (385, 565), "生成联调报告", "small", "#FFFFFF")
    rr(d, (560, 554, 1018, 596), 8, fill=COL["green2"], outline="#CBE2D1")
    text(d, (586, 565), "报告将同步到任务状态表和管理员群", "small", COL["green"])
    return im


def skill_pack():
    im, d = base("技能库")
    title_block(d, "企业 skills 配置", "按研究、分析、办公产出和知识沉淀启用")
    cols = [
        ("全员默认", ["Agent Reach", "Department KB Searcher", "Research Report Distiller", "VOC Synthesizer", "Spreadsheet Analyst", "Executive Briefing", "Humanizer-zh"]),
        ("按岗审批", ["NotebookLM Skill", "bb-browser", "Playwright MCP", "Documents", "Presentations", "Zotero", "skill-creator"]),
        ("质量与合规", ["Citation Guard", "Privacy Redactor", "Cost-Aware Router", "Glossary Keeper", "Insight Backlog", "Audit Log"]),
    ]
    x = 344
    for title, items in cols:
        rr(d, (x, 158, x + 230, 610), 14, fill="#F8FBF8", outline=COL["line"])
        text(d, (x + 22, 186), title, "h2", COL["green"])
        y = 238
        for item in items:
            rr(d, (x + 20, y, x + 210, y + 34), 17, fill=COL["green2"], outline="#CBE2D1")
            text(d, (x + 36, y + 8), item, "xs", COL["green"])
            y += 48
        x += 252
    rr(d, (344, 632, 1088, 668), 8, fill=COL["goldbg"], outline="#E8C47B")
    text(d, (366, 640), "涉及登录态、外部账号、敏感资料或文件系统扩大权限的技能，需要审批后按角色开放。", "xs", COL["gold"])
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save("admin-feishu-wizard.png", feishu_wizard())
    save("admin-excel-import.png", excel_import())
    save("admin-model-config.png", model_config())
    save("admin-kb-upload.png", kb_upload())
    save("admin-debug-checklist.png", debug_checklist())
    save("admin-skill-pack.png", skill_pack())


if __name__ == "__main__":
    main()
