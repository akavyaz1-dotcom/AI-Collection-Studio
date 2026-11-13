
VALID_VERDICTS = {"FAIL", "REVIEW", "SUGGESTION"}

VALID_CATEGORIES = {
    "composition",
    "style",
    "geometry",
    "lighting",
    "materials",
    "artifacts",
    "mobile_readability",
}

VALID_SEVERITIES = {"critical", "major", "minor"}


def validate_vision(analysis, requirements, card_category):
    """
    Проверяет ответ GigaChat и рассчитывает статус.

    Не выполняет запросов к API.
    Не изменяет исходный ответ.
    """

    if not isinstance(analysis, dict):
        raise ValueError("Ответ модели должен быть объектом")

    if str(card_category) not in requirements["category_rules"]:
        raise ValueError("Неизвестная категория карточки")

    # Для одной карточки применяются только правила
    # её категории. SET-правила проверяются отдельно.
    category_rules = requirements["category_rules"][
        str(card_category)
    ]

    mandatory_ids = {
        rule["id"]
        for rule in category_rules
        if rule.get("mandatory", False)
    }

    issues = analysis.get("issues")

    if not isinstance(issues, list):
        raise ValueError("Поле issues должно быть массивом")

    normalized_issues = []

    for index, original in enumerate(issues, start=1):
        if not isinstance(original, dict):
            raise ValueError(
                f"Замечание #{index}: ожидается объект"
            )

        issue = original.copy()

        verdict = issue.get("verdict")
        requirement_id = issue.get("requirement_id", "")
        evidence = issue.get("evidence", "")

        if verdict not in VALID_VERDICTS:
            raise ValueError(
                f"Замечание #{index}: неверный verdict"
            )

        if issue.get("category") not in VALID_CATEGORIES:
            raise ValueError(
                f"Замечание #{index}: неверная категория дефекта"
            )

        if issue.get("severity") not in VALID_SEVERITIES:
            raise ValueError(
                f"Замечание #{index}: неверная severity"
            )

        if not isinstance(requirement_id, str):
            requirement_id = ""

        if not isinstance(evidence, str):
            evidence = ""

        issue["requirement_id"] = requirement_id
        issue["evidence"] = evidence

        # Нельзя автоматически утверждать нарушение,
        # если отсутствует ID требования или evidence.
        if verdict == "FAIL":
            if (
                requirement_id not in mandatory_ids
                or not evidence.strip()
            ):
                issue["verdict"] = "REVIEW"
                issue["validation_note"] = (
                    "Недостаточно данных для подтверждения FAIL"
                )

        # REVIEW — только ручная проверка,
        # без автоматического отклонения.
        if issue["verdict"] == "REVIEW":
            issue["requires_human_review"] = True

        normalized_issues.append(issue)

    verdicts = {
        issue["verdict"]
        for issue in normalized_issues
    }

    if "FAIL" in verdicts:
        status = "rejected"
    elif "REVIEW" in verdicts:
        status = "needs_review"
    else:
        status = "approved"

    result = analysis.copy()
    result["issues"] = normalized_issues
    result["status"] = status

    if status == "approved":
        if normalized_issues:
            result["summary"] = (
                "Модель не заявила нарушений обязательных "
                "требований. Есть необязательные рекомендации."
            )
        else:
            result["summary"] = (
                "Модель не сообщила о нарушениях или "
                "замечаниях. Полнота проверки всех "
                "требований пока не подтверждена."
            )

    return result
