from app.service_layer.analysis import hospital_compare


def test_patient_hospital_compare_only_returns_public_sections(monkeypatch):
    grouped = []
    monkeypatch.setattr(hospital_compare.cache, "remember", lambda _namespace, _payload, producer, **_kwargs: (producer(), False))
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
    monkeypatch.setattr(hospital_compare.cache, "remember", lambda _namespace, _payload, producer, **_kwargs: (producer(), False))
    monkeypatch.setattr(hospital_compare, "_summary", lambda hospital, _filters, _role: {"hospital": hospital, "count": 500})
    monkeypatch.setattr(hospital_compare, "_trend", lambda *_args: [])
    monkeypatch.setattr(hospital_compare, "_group", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hospital_compare.mining, "case_mix_adjusted_hospitals", lambda **_kwargs: {"rows": [{"case_mix_cost_index": 0.95}]})
    monkeypatch.setattr(hospital_compare, "_case_mix_pair", lambda *_args: {"a": [{"case_mix_cost_index": 0.95}], "b": [{"case_mix_cost_index": 1.05}]})

    result = hospital_compare.compare_hospitals("医院 A", "医院 B", role="admin")

    assert set(result["mixes"]) == {"disease", "severity", "admission"}
    assert result["case_mix"]["a"][0]["case_mix_cost_index"] == 0.95


def test_case_mix_pair_reuses_one_full_benchmark_cache(monkeypatch):
    calls = []
    rows = {
        "rows": [
            {"hospital": "医院 A", "case_mix_cost_index": 0.95},
            {"hospital": "医院 B", "case_mix_cost_index": 1.05},
        ],
    }
    monkeypatch.setattr(
        hospital_compare.cache, "remember",
        lambda namespace, payload, producer, **kwargs: calls.append((namespace, payload, kwargs)) or (producer(), False),
    )
    monkeypatch.setattr(hospital_compare.mining, "case_mix_adjusted_hospitals", lambda **kwargs: calls.append(kwargs) or rows)

    result = hospital_compare._case_mix_pair("医院 A", "医院 B", {})

    assert result["a"][0]["case_mix_cost_index"] == 0.95
    assert result["b"][0]["case_mix_cost_index"] == 1.05
    assert calls[0][0] == "hospital_case_mix_benchmark"
    assert calls[1]["limit"] == 300


def test_hospital_profile_cache_is_scoped_by_hospital_role_and_filters(monkeypatch):
    captured = {}
    monkeypatch.setattr(hospital_compare, "_summary", lambda hospital, *_args: {"hospital": hospital, "count": 200})
    monkeypatch.setattr(hospital_compare, "_group", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hospital_compare, "_trend", lambda *_args: [])
    monkeypatch.setattr(
        hospital_compare.cache, "remember",
        lambda namespace, payload, producer, **kwargs: captured.update(namespace=namespace, payload=payload, kwargs=kwargs) or (producer(), False),
    )

    profile = hospital_compare._hospital_profile("医院 A", {"year": 2024}, "admin")

    assert profile["summary"]["count"] == 200
    assert captured["namespace"] == "hospital_operation_profile"
    assert captured["payload"]["hospital"] == "医院 A"
    assert captured["payload"]["role"] == "admin"
    assert captured["payload"]["filters"] == {"year": 2024}


def test_hospital_search_uses_parameter_binding(monkeypatch):
    captured = {}
    monkeypatch.setattr(hospital_compare.aggregation, "_run_query", lambda sql, params: captured.update(sql=sql, params=params) or [])

    hospital_compare.list_hospitals(search="O'Brien")

    assert "O'BRIEN" not in captured["sql"]
    assert captured["params"] == ["__ALL__", "%O'BRIEN%"]
