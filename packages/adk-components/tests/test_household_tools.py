from forsch.adk_components.tools import household


def _use_tmp_store(tmp_path, monkeypatch):
    monkeypatch.setenv("FORSCH_HOUSEHOLD_DATA", str(tmp_path / "household"))
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)


def test_log_groceries_normalizes_strings_and_dicts(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    result = household.log_groceries(
        ["oat milk", {"name": "eggs", "quantity": 12, "unit": "ct", "category": "dairy"}],
        store="Trader Joe's",
        date="2026-06-21",
    )

    assert result["ok"] is True
    assert result["count"] == 2
    milk, eggs = result["logged"]
    assert milk["name"] == "oat milk"
    assert milk["store"] == "Trader Joe's"
    assert milk["date"] == "2026-06-21"
    assert eggs["quantity"] == 12
    assert eggs["category"] == "dairy"


def test_log_groceries_item_store_overrides_default(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    result = household.log_groceries(
        [{"name": "bananas", "store": "Safeway"}],
        store="Trader Joe's",
        date="2026-06-21",
    )

    assert result["logged"][0]["store"] == "Safeway"


def test_log_groceries_defaults_date_to_today(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    result = household.log_groceries(["coffee"])

    assert result["ok"] is True
    assert result["logged"][0]["date"]  # an ISO date string was filled in


def test_log_groceries_skips_unnamed_items(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    result = household.log_groceries(["", {"quantity": 3}])

    assert result["ok"] is False
    assert result["count"] == 0


def test_get_grocery_log_roundtrips_and_orders_oldest_first(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    household.log_groceries(["late"], date="2026-06-21")
    household.log_groceries(["early"], date="2026-06-01")

    log = household.get_grocery_log()

    assert log["ok"] is True
    assert [r["name"] for r in log["records"]] == ["early", "late"]


def test_get_grocery_log_filters_by_date_and_name(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    household.log_groceries(["oat milk"], date="2026-05-01")
    household.log_groceries(["oat milk"], date="2026-06-10")
    household.log_groceries(["bread"], date="2026-06-10")

    by_date = household.get_grocery_log(since="2026-06-01")
    assert {r["name"] for r in by_date["records"]} == {"oat milk", "bread"}

    by_name = household.get_grocery_log(name="MILK")
    assert by_name["count"] == 2
    assert all(r["name"] == "oat milk" for r in by_name["records"])


def test_get_grocery_log_limit_keeps_most_recent(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)
    household.log_groceries(["a"], date="2026-06-01")
    household.log_groceries(["b"], date="2026-06-02")
    household.log_groceries(["c"], date="2026-06-03")

    log = household.get_grocery_log(limit=2)

    assert [r["name"] for r in log["records"]] == ["b", "c"]


def test_get_grocery_log_empty_when_no_log(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    log = household.get_grocery_log()

    assert log["ok"] is True
    assert log["count"] == 0
    assert log["records"] == []


def test_add_reminder_returns_honest_unsynced_receipt(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    result = household.add_reminder("Buy oat milk", list_name="Groceries", due="2026-06-22")

    assert result["ok"] is True
    receipt = result["receipt"]
    assert receipt["title"] == "Buy oat milk"
    assert receipt["list"] == "Groceries"
    assert receipt["due"] == "2026-06-22"
    assert receipt["synced"] is False
    assert "not yet synced" in receipt["status"]


def test_add_reminder_persists_and_requires_title(tmp_path, monkeypatch):
    _use_tmp_store(tmp_path, monkeypatch)

    assert household.add_reminder("   ")["ok"] is False

    household.add_reminder("Call plumber")
    stored = household._read(household.REMINDERS_LOG)
    assert [r["title"] for r in stored] == ["Call plumber"]


def test_tools_require_a_configured_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("FORSCH_HOUSEHOLD_DATA", raising=False)
    monkeypatch.delenv("FORSCH_ADK_WORKSPACE", raising=False)

    result = household.log_groceries(["coffee"])

    assert result["ok"] is False
    assert "FORSCH_ADK_WORKSPACE" in result["error"]
