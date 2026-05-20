from ai_inference.inference.batching import BatchCandidate, BatchingPolicy, DynamicBatcher


def candidate(request_id, model="small-local", event_type="general_inference", priority=5, tokens=100, batchable=True):
    return BatchCandidate(
        request_id=request_id,
        prompt=f"prompt {request_id}",
        model_name=model,
        event_type=event_type,
        priority=priority,
        estimated_tokens=tokens,
        batchable=batchable,
    )


def test_batches_compatible_requests_by_model_and_event_type():
    batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=1000))

    batches = batcher.build_batches([
        candidate("a"),
        candidate("b"),
        candidate("c", model="large-local"),
    ])

    assert len(batches) == 2
    small_batch = next(batch for batch in batches if batch.model_name == "small-local")
    large_batch = next(batch for batch in batches if batch.model_name == "large-local")
    assert small_batch.size == 2
    assert [item.request_id for item in small_batch.candidates] == ["a", "b"]
    assert large_batch.size == 1


def test_splits_batches_when_max_size_is_reached():
    batcher = DynamicBatcher(BatchingPolicy(max_batch_size=2, max_batch_tokens=1000))

    batches = batcher.build_batches([candidate("a"), candidate("b"), candidate("c")])

    assert [batch.size for batch in batches] == [2, 1]


def test_splits_batches_when_token_budget_is_reached():
    batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=250))

    batches = batcher.build_batches([candidate("a", tokens=150), candidate("b", tokens=150)])

    assert len(batches) == 2
    assert all(batch.size == 1 for batch in batches)


def test_high_priority_requests_are_not_delayed_for_batching():
    batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=1000, high_priority_threshold=2))

    batches = batcher.build_batches([candidate("urgent", priority=1), candidate("normal", priority=5)])

    urgent = next(batch for batch in batches if batch.candidates[0].request_id == "urgent")
    assert urgent.reason == "high_priority_singleton"
    assert urgent.size == 1


def test_non_batchable_requests_are_isolated():
    batcher = DynamicBatcher(BatchingPolicy(max_batch_size=4, max_batch_tokens=1000))

    batches = batcher.build_batches([candidate("solo", batchable=False), candidate("normal")])

    solo = next(batch for batch in batches if batch.candidates[0].request_id == "solo")
    assert solo.reason == "not_batchable"
    assert solo.size == 1
