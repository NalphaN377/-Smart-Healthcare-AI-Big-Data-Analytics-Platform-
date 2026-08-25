from app.service_layer.analysis import hospital_compare


def test_patient_hospital_compare_only_returns_public_sections(monkeypatch):
    grouped = []
    monkeypatch.setattr(hospital_compare, "_summary", lambda hospital, _filters, _role: {
        "hospital": hospital, "count": 120, "avg_length_of_stay": 5.5, "avg_total_charges": 80000,
    })
    monkeypatch.setattr(hospital_compare, "_trend", lambda *_args: [{"year": 2024, "count": 120}])
    monkeypatch.setattr(hospital_compare, "_group", lambda hospital, dimension, *_args, **_kwargs: grouped.append((hospital, dimension)) or [{"dimension_value": "A", "count": 120}])

    result = hospital_compare.compare_hospitals("医院 A", "医院 B", role="patient")

    assert result["role_scope"] == "patient"
    assert set(result["mixes"]) == {"disease"}
    assert result["case_mix"] is None
    assert {dimension for _hospital, dimension in grouped} == {"disease"}


def test_admin_hospital_compare_includes_case_mix_and_clinical_mix(monkeypatch):
    monkeypatch.setattr(hospital_compare, "_summary", lambda hospital, _filters, _role: {"hospital": hospital, "count": 500})
    monkeypatch.setattr(hospital_compare, "_trend", lambda *_args: [])
    monkeypatch.setattr(hospital_compare, "_group", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hospital_compare.mining, "case_mix_adjusted_hospitals", lambda **_kwargs: {"rows": [{"case_mix_cost_index": 0.95}]})

    result = hospital_compare.compare_hospitals("医院 A", "医院 B", role="admin")

    assert set(result["mixes"]) == {"disease", "severity", "admission"}
    assert result["case_mix"]["a"][0]["case_mix_cost_index"] == 0.95


def test_hospital_search_uses_parameter_binding(monkeypatch):
    captured = {}
    monkeypatch.setattr(hospital_compare.aggregation, "_run_query", lambda sql, params: captured.update(sql=sql, params=params) or [])

    hospital_compare.list_hospitals(search="O'Brien")

    assert "O'BRIEN" not in captured["sql"]
    assert captured["params"] == ["__ALL__", "%O'BRIEN%"]
