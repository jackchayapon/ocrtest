"""Exercise every configured adapter while respecting the per-request limit."""


def run_config_groups(client, case_id, pipeline_ids):
    runs = []
    for start in range(0, len(pipeline_ids), 3):
        response = client.post(f"/api/test-cases/{case_id}/run",
                               json={"pipelines": pipeline_ids[start:start + 3]})
        assert response.status_code == 200, response.text
        group = response.json()["runs"]
        assert [r["pipeline_id"] for r in group] == pipeline_ids[start:start + 3]
        runs.extend(group)
    return runs
