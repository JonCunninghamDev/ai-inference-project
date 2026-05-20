import aws_cdk as core
import aws_cdk.assertions as assertions

from ai_inference.infrastructure.ai_inference_stack import AirGappedRagStack


def test_sqs_queue_created():
    app = core.App(
        context={
            "dev": {
                "home_ip": "1.2.3.4",
                "vpc_cidr": "10.0.0.0/16",
            }
        }
    )
    stack = AirGappedRagStack(app, "ai-inference", stage="dev")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::SQS::Queue", {
        "VisibilityTimeout": 300
    })


def test_result_table_created():
    app = core.App(
        context={
            "dev": {
                "home_ip": "1.2.3.4",
                "vpc_cidr": "10.0.0.0/16",
            }
        }
    )
    stack = AirGappedRagStack(app, "ai-inference", stage="dev")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::DynamoDB::Table", {
        "TableName": "ai-inference-results-dev",
        "KeySchema": [{"AttributeName": "request_id", "KeyType": "HASH"}],
        "BillingMode": "PAY_PER_REQUEST",
        "PointInTimeRecoverySpecification": {"PointInTimeRecoveryEnabled": True},
        "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
    })
