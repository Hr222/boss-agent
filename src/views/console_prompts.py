"""控制台提示词辅助函数。"""


def print_banner() -> None:
    """打印 CLI 欢迎横幅。"""
    print(
        """
    ╔═══════════════════════════════════════════════════════╗
    ║                                                       ║
    ║        🤖 智能求职 Agent - 生成打招呼语               ║
    ║                                                       ║
    ╚═══════════════════════════════════════════════════════╝
    """
    )


def collect_manual_job_input() -> dict:
    """从控制台采集手动 JD 输入。"""
    print("\n" + "=" * 60)
    print("请输入职位信息 (逐项填写，留空跳过)")
    print("=" * 60)

    job_title = input("\n1. 职位名称: ").strip() or "职位"
    company_name = input("2. 公司名称: ").strip() or "公司"
    salary = input("3. 薪资范围: ").strip() or "面议"
    location = input("4. 工作地点: ").strip() or "地点"

    print("\n5. 职位要求/描述 (多行输入，输入 === 结束):")
    print("-" * 40)
    # 使用多行输入，便于直接粘贴整段 JD。
    jd_lines = []
    while True:
        line = input()
        if line.strip() == "===":
            break
        jd_lines.append(line)
    job_desc = "\n".join(jd_lines).strip()

    print("\n6. 技能标签 (用逗号分隔，如: Python,Django,MySQL):")
    tags_input = input("标签: ").strip()
    tags = [tag.strip() for tag in tags_input.split(",")] if tags_input else []

    return {
        "job_title": job_title,
        "company_name": company_name,
        "salary_range": salary,
        "location": location,
        "job_requirements": job_desc,
        "job_description": job_desc,
        "tags": tags,
        "job_url": "手动输入",
    }
