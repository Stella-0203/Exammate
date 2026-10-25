
import re
ALLOWED_ITEM_TYPES = {
    "knowledge",
    "skill",
    "question_type",
    "other",
}


def validate_suggestions(
    result: object,
    source_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    校验模型生成的候选展开项。

    返回的每个候选项都附带 source_sort_order，
    由后续业务服务负责映射到数据库中的原始条目 ID。
    """
    if not isinstance(result, dict):
        raise ValueError("模型结果必须是 JSON 对象。")

    groups = result.get("items")

    if not isinstance(groups, list):
        raise ValueError("模型结果缺少 items 数组。")

    expected_orders = {
        item["sort_order"]
        for item in source_items
    }

    seen_orders = set()
    validated = []

    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("每组展开结果都必须是对象。")

        order = group.get("source_sort_order")

        if type(order) is not int or order not in expected_orders:
            raise ValueError(f"无效的原始条目编号：{order!r}")

        if order in seen_orders:
            raise ValueError(f"原始条目 {order} 被重复处理。")

        seen_orders.add(order)

        suggestions = group.get("suggestions")

        if not isinstance(suggestions, list):
            raise ValueError(f"条目 {order} 的 suggestions 必须是数组。")

        for suggestion in suggestions:
            if not isinstance(suggestion, dict):
                raise ValueError("候选展开项必须是对象。")

            content = suggestion.get("content")
            item_type = suggestion.get("item_type")
            rationale = suggestion.get("rationale")

            if not isinstance(content, str) or not content.strip():
                raise ValueError("候选展开项的 content 不能为空。")

            if len(content) > 500:
                raise ValueError("候选展开项过长，请缩短后重试。")

            if (
                not isinstance(item_type, str)
                or item_type not in ALLOWED_ITEM_TYPES
            ):
                raise ValueError(f"不支持的条目类型：{item_type!r}")

            if not isinstance(rationale, str) or not rationale.strip():
                raise ValueError("每个候选展开项都必须说明推断依据。")

            if len(rationale) > 1000:
                raise ValueError("候选展开项的推断依据过长。")

            validated.append(
                {
                    "source_sort_order": order,
                    "content": content.strip(),
                    "item_type": item_type,
                    "origin": "inferred",
                    "review_status": "pending",
                    "rationale": rationale.strip(),
                }
            )

    if seen_orders != expected_orders:
        missing = expected_orders - seen_orders
        raise ValueError(f"模型遗漏了原始条目：{sorted(missing)}")

    # 过滤纯空白字符已在上方处理；进一步拒绝重复建议，
    # 避免相同原始条目下出现完全重复的候选项。
    unique_items = []
    seen_content = set()

    for item in validated:
        key = (
            item["source_sort_order"],
            re.sub(r"\s+", " ", item["content"]).casefold(),
        )

        if key not in seen_content:
            seen_content.add(key)
            unique_items.append(item)

    return unique_items



COVERAGE_STATUSES = {
    "covered",
    "partial",
    "uncovered",
    "needs_review",
}


def _normalize_evidence_text(text: str) -> str:
    """统一空白字符，便于检查证据摘录是否来自原始资料。"""
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate_coverage_results(
    result: object,
    syllabus_items: list[dict[str, object]],
    materials: list[dict[str, object]],
) -> list[dict[str, object]]:
    """
    校验模型生成的覆盖分析结果。

    检查：
    1. 考纲条目是否完整且没有重复；
    2. 覆盖状态是否合法；
    3. 判断理由和不确定原因的格式；
    4. 证据引用的资料是否确实参与了本次分析；
    5. 证据摘录是否能在对应资料正文中找到。

    返回通过校验的覆盖分析结果。
    """
    if not isinstance(result, dict):
        raise ValueError("覆盖分析结果必须是 JSON 对象。")

    groups = result.get("items")
    if not isinstance(groups, list):
        raise ValueError("覆盖分析结果缺少 items 数组。")

    expected_ids = {
        item["id"] for item in syllabus_items
    }
    material_by_id = {
        material["id"]: material for material in materials
    }

    seen_ids = set()
    validated = []

    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("每条覆盖分析结果都必须是对象。")

        item_id = group.get("syllabus_item_id")

        if type(item_id) is not int or item_id not in expected_ids:
            raise ValueError(f"无效的考纲条目 ID：{item_id!r}")

        if item_id in seen_ids:
            raise ValueError(f"考纲条目 {item_id} 被重复分析。")

        seen_ids.add(item_id)

        status = group.get("status")
        if not isinstance(status, str) or status not in COVERAGE_STATUSES:
            raise ValueError(f"不支持的覆盖状态：{status!r}")

        reason = group.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("每条分析结果都必须提供判断理由。")
        if len(reason) > 2000:
            raise ValueError("覆盖分析的判断理由过长。")

        uncertainty = group.get("uncertainty", "")
        if not isinstance(uncertainty, str):
            raise ValueError("uncertainty 必须是字符串。")
        if len(uncertainty) > 2000:
            raise ValueError("不确定原因过长。")

        evidence_list = group.get("evidence")
        if not isinstance(evidence_list, list):
            raise ValueError("evidence 必须是数组。")
        if len(evidence_list) > 10:
            raise ValueError("单个考纲条目的证据数量不能超过 10 条。")

        validated_evidence = []

        for evidence in evidence_list:
            if not isinstance(evidence, dict):
                raise ValueError("每条证据都必须是对象。")

            material_id = evidence.get("material_id")
            if (
                type(material_id) is not int
                or material_id not in material_by_id
            ):
                raise ValueError(
                    f"证据引用了未参与本次分析的资料：{material_id!r}"
                )

            quote = evidence.get("quote")
            if not isinstance(quote, str) or not quote.strip():
                raise ValueError("每条证据都必须包含非空摘录。")

            quote = quote.strip()
            if len(quote) > 2000:
                raise ValueError("单条证据摘录过长。")

            source_text = material_by_id[material_id]["extracted_text"]
            if not isinstance(source_text, str):
                raise ValueError("资料正文格式异常。")

            normalized_quote = _normalize_evidence_text(quote)
            normalized_source = _normalize_evidence_text(source_text)

            if normalized_quote not in normalized_source:
                raise ValueError(
                    f"证据摘录无法在资料 "
                    f"{material_id} 的原文中找到。"
                )

            validated_evidence.append({
                "material_id": material_id,
                "quote": quote,
            })

        if status in {"covered", "partial"} and not validated_evidence:
            raise ValueError(
                f"条目 {item_id} 的状态为 {status}，"
                "但没有提供支持证据。"
            )

        if status == "needs_review" and not uncertainty.strip():
            raise ValueError(
                f"条目 {item_id} 需要确认，但没有说明不确定原因。"
            )

        validated.append({
            "syllabus_item_id": item_id,
            "status": status,
            "reason": reason.strip(),
            "evidence": validated_evidence,
            "uncertainty": uncertainty.strip(),
        })

    if seen_ids != expected_ids:
        missing = expected_ids - seen_ids
        raise ValueError(
            f"模型遗漏了考纲条目：{sorted(missing)}"
        )

    return validated
