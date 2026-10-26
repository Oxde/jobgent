from jobgent.ats import AtsReport, ats_report


def test_ats_report_matches_keywords_case_and_plural_insensitive():
    cv = "Built trading bots in Python with asyncio and Docker. Dashboards in React."
    r = ats_report(cv, ["python", "Docker", "SQL", "react", "Kubernetes", "asyncio"])
    assert isinstance(r, AtsReport)
    assert r.matched == ["python", "Docker", "react", "asyncio"]
    assert r.missing == ["SQL", "Kubernetes"]
    assert r.percent == 67


def test_ats_report_empty_keywords():
    r = ats_report("anything", [])
    assert r.percent == 0 and r.matched == [] and r.missing == []


def test_multi_word_keyword():
    r = ats_report("Experience with machine learning models and data pipelines", ["machine learning", "data pipeline", "Spark"])
    assert r.matched == ["machine learning", "data pipeline"] and r.missing == ["Spark"]
