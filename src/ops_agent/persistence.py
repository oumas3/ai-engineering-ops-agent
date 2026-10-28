from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


def create_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            ("ops_agent.models", "CIResult"),
            ("ops_agent.models", "FailedTest"),
            ("ops_agent.models", "FailedTestsReport"),
            ("ops_agent.models", "LogEntry"),
            ("ops_agent.models", "LogsReport"),
            ("ops_agent.models", "ServiceStatus"),
        ]
    )