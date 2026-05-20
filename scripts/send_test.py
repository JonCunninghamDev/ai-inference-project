import boto3
import json

sqs = boto3.client("sqs")
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/221278850141/ai-inference-queue-Dev"

test_payload = {
    "prompt": "What is the primary benefit of an air-gapped vLLM setup?",
    "context": "An air-gapped setup ensures that sensitive weights and data never leave the private network.",
    "event_type": "security_test"
}

sqs.send_message(
    QueueUrl=QUEUE_URL,
    MessageBody=json.dumps(test_payload)
)

print("SUCCESS: Prompt tunneled through VPN to SQS.")