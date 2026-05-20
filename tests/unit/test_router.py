from ai_inference.inference.router import (
    InferenceRequest,
    ModelProfile,
    ModelRouter,
    RoutingReason,
)


def build_router() -> ModelRouter:
    return ModelRouter(
        profiles=[
            ModelProfile(name="small-local", max_context_tokens=2048, priority=10),
            ModelProfile(name="large-local", max_context_tokens=32768, priority=20),
        ],
        default_model="small-local",
    )


def test_routes_simple_requests_to_small_model():
    router = build_router()
    decision = router.route(InferenceRequest(prompt="Answer briefly", context="Short context"))

    assert decision.model_name == "small-local"
    assert decision.reason == RoutingReason.DEFAULT_SMALL_MODEL
    assert decision.batchable is True


def test_routes_large_context_to_larger_model():
    router = build_router()
    large_context = "x" * 12000
    decision = router.route(InferenceRequest(prompt="Summarize", context=large_context))

    assert decision.model_name == "large-local"
    assert decision.reason == RoutingReason.CONTEXT_TOO_LARGE_FOR_SMALL_MODEL


def test_routes_complex_event_type_to_larger_model():
    router = build_router()
    decision = router.route(
        InferenceRequest(
            prompt="Analyze the system behavior",
            context="short",
            event_type="analysis",
        )
    )

    assert decision.model_name == "large-local"
    assert decision.reason == RoutingReason.COMPLEX_TASK_TYPE


def test_respects_explicit_model_request():
    router = build_router()
    decision = router.route(
        InferenceRequest(
            prompt="Use the requested model",
            context="short",
            requested_model="large-local",
        )
    )

    assert decision.model_name == "large-local"
    assert decision.reason == RoutingReason.EXPLICIT_MODEL_REQUESTED


def test_high_priority_routes_to_larger_model():
    router = build_router()
    decision = router.route(
        InferenceRequest(
            prompt="Urgent answer needed",
            context="short",
            priority=1,
        )
    )

    assert decision.model_name == "large-local"
    assert decision.reason == RoutingReason.HIGH_PRIORITY_REQUEST
