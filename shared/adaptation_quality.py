from __future__ import annotations

from textwrap import dedent


QUALITY_CONSTITUTION = {
    "hard_metrics": [
        {
            "id": "fidelity",
            "name": "还原度",
            "threshold": 8.5,
            "checks": [
                "角色人设不崩：性格、动机、关系不乱改",
                "名场面、名台词保留：不魔改、不删关键剧情",
                "世界观逻辑一致：不随便加设定、乱改规则",
                "改编必须尊重原作，而不是借 IP 拍原创剧",
            ],
        },
        {
            "id": "pacing",
            "name": "叙事节奏",
            "threshold": 8.0,
            "checks": [
                "漫画分镜转影视化后要流畅，不尴尬",
                "不疯狂注水回忆，不硬塞原创支线",
                "高潮前要有铺垫，情绪必须能顶上去",
                "单章独立可看，整包连起来不乱、不赶、不水",
            ],
        },
        {
            "id": "production",
            "name": "制作水平",
            "threshold": 7.8,
            "checks": [
                "画面、建模、分镜不能崩、不能廉价、不能敷衍",
                "配音或旁白要贴脸，情绪要到位",
                "配乐与音效要能烘托氛围，不违和",
                "字幕、镜头说明、交付文件要完整可审片",
            ],
        },
        {
            "id": "adaptation",
            "name": "改编合理性",
            "threshold": 8.0,
            "checks": [
                "夸张表现必须完成合理化，不尴尬中二",
                "战斗和特效要有明确动因，不五毛、不糊弄",
                "剧情逻辑自洽，不强行降智",
                "没看过原作的人也能看懂当前章冲突",
            ],
        },
    ],
    "bonus_metrics": [
        "补全人物动机和世界观，让原作更立体",
        "情绪感染力强，能燃、能虐、能打动路人",
        "路人友好，不看原作也能入坑",
    ],
    "qa": {
        "overall_threshold": 8.2,
        "max_rounds": 3,
        "hard_blockers": [
            "缺少章节视频",
            "缺少章节分镜交付物",
            "核心名场面或名台词丢失",
            "世界观规则冲突",
            "章节节奏严重失衡",
        ],
    },
}


def build_quality_markdown() -> str:
    lines = [
        "# 改编质量宪章",
        "",
        "以下标准是 AI 漫剧工厂所有智能体、脚本和 QA 的共同硬约束。",
        "",
        "## 四个硬指标",
        "",
    ]
    for item in QUALITY_CONSTITUTION["hard_metrics"]:
        lines.append(f"### {item['name']}")
        lines.extend([f"- {check}" for check in item["checks"]])
        lines.append(f"- QA 通过阈值：{item['threshold']}/10")
        lines.append("")

    lines.extend(
        [
            "## 三个加分项",
            "",
            *[f"- {item}" for item in QUALITY_CONSTITUTION["bonus_metrics"]],
            "",
            "## QA 门禁",
            "",
            f"- 总体通过阈值：{QUALITY_CONSTITUTION['qa']['overall_threshold']}/10",
            f"- 单章最大返工轮次：{QUALITY_CONSTITUTION['qa']['max_rounds']}",
            "- 以下问题出现即判定为硬阻塞：",
            *[f"- {item}" for item in QUALITY_CONSTITUTION["qa"]["hard_blockers"]],
            "",
        ]
    )
    return "\n".join(lines)


def build_quality_prompt() -> str:
    return dedent(
        """
        你必须严格遵守 AI 漫剧工厂的改编质量宪章。
        第一，四个硬指标必须同时达标：
        1. 还原度：角色不崩、动机不乱改、名场面和名台词优先保留、世界观规则不能乱加。
        2. 叙事节奏：不水、不赶、不乱，高潮有铺垫，单章也能看懂。
        3. 制作水平：画面、分镜、配音/旁白、配乐音效和字幕都要形成完整交付体验。
        4. 改编合理性：能落地、不尴尬、不降智，战斗和特效有明确动因。
        第二，优先追求三个加分项：补全人物动机、强化情绪感染力、提高路人友好度。
        第三，任何方案都必须支持 QA 迭代，不允许把缺少章节视频、缺少分镜交付、核心剧情丢失、世界观冲突或节奏严重失衡的结果当成完成品。
        """
    ).strip()


def qa_thresholds() -> dict[str, float]:
    thresholds = {
        item["id"]: float(item["threshold"])
        for item in QUALITY_CONSTITUTION["hard_metrics"]
    }
    thresholds["overall"] = float(QUALITY_CONSTITUTION["qa"]["overall_threshold"])
    return thresholds


def qa_max_rounds() -> int:
    return int(QUALITY_CONSTITUTION["qa"]["max_rounds"])
