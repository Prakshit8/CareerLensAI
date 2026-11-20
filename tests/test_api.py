def test_profile_search_memory_and_saved_job_workflow(client, monkeypatch):
    from backend.app.search.service import semantic_index
    from backend.app.search.vector import SemanticSearchUnavailable

    def unavailable(*args, **kwargs):
        raise SemanticSearchUnavailable("offline in test")

    monkeypatch.setattr(semantic_index, "search", unavailable)
    job_response = client.post("/api/jobs", json={
        "external_id": "workflow-1",
        "source": "test",
        "title": "AI Engineer Intern",
        "company": "Example Labs",
        "description": "Build Python tools for retrieval augmented generation and LLM systems.",
        "location": "Remote - India",
        "employment_type": "Internship",
        "experience_level": "Internship",
        "skills": ["Python", "RAG", "LLM"],
        "is_synthetic": True,
    })
    assert job_response.status_code == 201
    job = job_response.json()

    profile_response = client.patch("/api/profiles/me", json={
        "skills": ["Python", "RAG"],
        "experience_level": "Fresher",
        "preferred_roles": ["AI Engineer"],
    })
    assert profile_response.status_code == 200

    search_response = client.post("/api/search", json={
        "query": "Python RAG AI internship",
        "mode": "keyword",
    })
    assert search_response.status_code == 200
    assert search_response.json()["results"][0]["job"]["id"] == job["id"]

    remote = client.put("/api/memories", json={
        "kind": "preference", "key": "preferred_locations",
        "value": ["Remote"], "is_explicit": True,
    })
    assert remote.status_code == 200
    saved = client.put(f"/api/saved/{job['id']}")
    assert saved.status_code == 204
    assert client.get("/api/saved").json()[0]["id"] == job["id"]
    feedback = client.post("/api/feedback", json={
        "job_id": job["id"], "feedback": "not_relevant",
    })
    assert feedback.status_code == 201
    assert client.get("/api/memories").json()[0]["value"] == ["Remote"]


def test_assistant_persists_remote_preference_and_reuses_last_search(client, monkeypatch):
    from backend.app.search.service import semantic_index
    from backend.app.search.vector import SemanticSearchUnavailable

    monkeypatch.setattr(
        semantic_index, "search",
        lambda *args, **kwargs: (_ for _ in ()).throw(SemanticSearchUnavailable("offline")),
    )
    job = client.post("/api/jobs", json={
        "external_id": "remote-workflow-1", "source": "test",
        "title": "AI Engineer Intern", "company": "Example",
        "description": "Python LLM RAG internship.",
        "location": "Remote - India", "skills": ["Python", "LLM", "RAG"],
        "is_synthetic": True,
    }).json()
    first = client.post("/api/search", json={
        "query": "AI internship Python LLM", "mode": "keyword",
    })
    assert first.status_code == 200
    response = client.post("/api/assistant/chat", json={
        "message": "Only show me remote opportunities",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["conversation_id"]
    assert "remote preference" in data["reply"].lower()
    assert all(item["job"]["id"] == job["id"] for item in data["results"])
    assert client.get("/api/memories").json()[0]["value"] == ["Remote"]
