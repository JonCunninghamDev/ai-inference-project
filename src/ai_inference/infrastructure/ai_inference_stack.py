from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_sqs as sqs,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_logs as logs,
    aws_ssm as ssm,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_kms as kms,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Tags
)
from constructs import Construct
import json


class AirGappedRagStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, stage: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. RETRIEVE ENVIRONMENT VARS FROM CONTEXT
        env_config = self.node.try_get_context(stage)
        if not env_config:
            raise ValueError(f"No configuration found for stage: {stage}")
            
        home_ip = env_config['home_ip']
        vpc_cidr = env_config['vpc_cidr']
        
        # 2. ENCRYPTION: KMS Key for SQS
        sqs_key = kms.Key(self, f"SQSKey-{stage}",
                          description=f"KMS key for SQS encryption in {stage}",
                          enable_key_rotation=True,
                          removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN
                          )
        
        # 3. MONITORING: SNS Topic for Alerts
        alert_topic = sns.Topic(self, f"AlertTopic-{stage}",
                               topic_name=f"ai-inference-alerts-{stage}",
                               display_name=f"Air-Gapped RAG Alerts ({stage})"
                               )

        # 4. THE NETWORK: Isolated with Security Groups
        vpc = ec2.Vpc(self, f"SecureVPC-{stage}",
                      ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
                      max_azs=2,
                      subnet_configuration=[
                          ec2.SubnetConfiguration(
                              name=f"IsolatedInference-{stage}",
                              subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                              cidr_mask=24
                          )
                      ],
                      enable_dns_hostnames=True,
                      enable_dns_support=True
                      )
        
        # Security Group for VPC Endpoints
        endpoint_sg = ec2.SecurityGroup(self, f"EndpointSG-{stage}",
                                       vpc=vpc,
                                       description=f"Security group for VPC endpoints in {stage}",
                                       allow_all_outbound=False
                                       )
        
        # Allow HTTPS from VPC
        endpoint_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc_cidr),
            connection=ec2.Port.tcp(443),
            description="HTTPS from VPC"
        )

        # 5. THE HAND-OFF: PrivateLink Endpoints with Security
        sqs_endpoint = vpc.add_interface_endpoint(f"SQSEndpoint-{stage}",
                                                 service=ec2.InterfaceVpcEndpointAwsService.SQS,
                                                 security_groups=[endpoint_sg],
                                                 private_dns_enabled=True
                                                 )

        logs_endpoint = vpc.add_interface_endpoint(f"LogsEndpoint-{stage}",
                                                  service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
                                                  security_groups=[endpoint_sg],
                                                  private_dns_enabled=True
                                                  )

        # SSM Endpoint for the Kill Switch
        ssm_endpoint = vpc.add_interface_endpoint(f"SSMEndpoint-{stage}",
                                                 service=ec2.InterfaceVpcEndpointAwsService.SSM,
                                                 security_groups=[endpoint_sg],
                                                 private_dns_enabled=True
                                                 )

        # 6. THE MESSAGE BUS (with DLQ and Encryption)
        dlq = sqs.Queue(self, f"InferenceDLQ-{stage}",
                        queue_name=f"ai-inference-dlq-{stage}",
                        retention_period=Duration.days(14),
                        encryption=sqs.QueueEncryption.KMS,
                        encryption_master_key=sqs_key
                        )

        inference_queue = sqs.Queue(self, f"InferenceQueue-{stage}",
                                    queue_name=f"ai-inference-queue-{stage}",
                                    visibility_timeout=Duration.seconds(600 if stage == "Prod" else 300),
                                    dead_letter_queue=sqs.DeadLetterQueue(
                                        max_receive_count=5 if stage == "Prod" else 3,
                                        queue=dlq
                                    ),
                                    encryption=sqs.QueueEncryption.KMS,
                                    encryption_master_key=sqs_key
                                    )

        # 6b. RESULT STORE: DynamoDB table for inference request lifecycle
        result_table = dynamodb.Table(self, f"ResultTable-{stage}",
                                      table_name=f"ai-inference-results-{stage}",
                                      partition_key=dynamodb.Attribute(
                                          name="request_id",
                                          type=dynamodb.AttributeType.STRING
                                      ),
                                      billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                                      encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
                                      encryption_key=sqs_key,
                                      point_in_time_recovery=True,
                                      removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN,
                                      time_to_live_attribute="ttl",
                                      )

        # 7. OBSERVABILITY & IDENTITY
        log_group = logs.LogGroup(self, f"WorkerLogs-{stage}",
                                  log_group_name=f"/ai-inference/worker-{stage}",
                                  retention=logs.RetentionDays.ONE_MONTH if stage == "Prod" else logs.RetentionDays.ONE_WEEK,
                                  removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN
                                  )

        gateway_log_group = logs.LogGroup(self, f"GatewayLogs-{stage}",
                                          log_group_name=f"/ai-inference/gateway-{stage}",
                                          retention=logs.RetentionDays.ONE_MONTH if stage == "Prod" else logs.RetentionDays.ONE_WEEK,
                                          removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN
                                          )

        reconciliation_log_group = logs.LogGroup(self, f"ReconciliationLogs-{stage}",
                                                 log_group_name=f"/ai-inference/reconciliation-{stage}",
                                                 retention=logs.RetentionDays.THREE_MONTHS if stage == "Prod" else logs.RetentionDays.TWO_WEEKS,
                                                 removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN
                                                 )

        scheduler_log_group = logs.LogGroup(self, f"SchedulerLogs-{stage}",
                                            log_group_name=f"/ai-inference/scheduler-{stage}",
                                            retention=logs.RetentionDays.ONE_MONTH if stage == "Prod" else logs.RetentionDays.ONE_WEEK,
                                            removal_policy=RemovalPolicy.DESTROY if stage != "Prod" else RemovalPolicy.RETAIN
                                            )

        worker_role = iam.Role(self, f"WorkerRole-{stage}",
                               assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                               description=f"Role for the RAG Inference Worker in {stage}",
                               managed_policies=[
                                   iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
                               ]
                               )

        # 8. MONITORING & ALERTING
        # Import monitoring dashboard
        from ..monitoring import RAGMonitoringDashboard
        
        # Create monitoring dashboard
        monitoring_dashboard = RAGMonitoringDashboard(
            self, f"MonitoringDashboard-{stage}",
            stage=stage,
            queue_name=inference_queue.queue_name,
            dlq_name=dlq.queue_name,
            log_group_name=log_group.log_group_name
        )
        
        # Queue depth alarm
        queue_depth_alarm = cloudwatch.Alarm(self, f"QueueDepthAlarm-{stage}",
                                             metric=inference_queue.metric(
                                                 "ApproximateNumberOfMessagesVisible",
                                                 statistic="Average",
                                                 period=Duration.minutes(5),
                                             ),
                                             threshold=10 if stage != "Prod" else 50,
                                             evaluation_periods=2,
                                             alarm_description=f"High message count in inference queue ({stage})",
                                             alarm_name=f"RAG-QueueDepth-{stage}",
                                             treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
                                             )
        
        queue_depth_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
        
        # DLQ alarm
        dlq_alarm = cloudwatch.Alarm(self, f"DLQAlarm-{stage}",
                                     metric=dlq.metric(
                                         "ApproximateNumberOfMessagesVisible",
                                         statistic="Average",
                                         period=Duration.minutes(5),
                                     ),
                                     threshold=1,
                                     evaluation_periods=1,
                                     alarm_description=f"Messages in dead letter queue ({stage})",
                                     alarm_name=f"RAG-DLQ-{stage}",
                                     treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
                                     )
        
        dlq_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
        
        # Worker health check alarm (custom metric)
        worker_health_alarm = cloudwatch.Alarm(self, f"WorkerHealthAlarm-{stage}",
                                               metric=cloudwatch.Metric(
                                                   namespace="AirGappedRAG",
                                                   metric_name="WorkerHealthy",
                                                   dimensions_map={"Environment": stage}
                                               ),
                                               threshold=1,
                                               comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                                               evaluation_periods=3,
                                               treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
                                               alarm_description=f"Worker health check failed ({stage})",
                                               alarm_name=f"RAG-WorkerHealth-{stage}"
                                               )
        
        worker_health_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # 9. FEATURE FLAGS & PERMISSIONS
        processing_switch = ssm.StringParameter(self, f"ProcessingSwitch-{stage}",
                                                parameter_name=f"/ai-inference/config/{stage}/enable-processing",
                                                string_value="true",
                                                description=f"Global toggle to enable/disable RAG worker processing for {stage}"
                                                )

        # Grant Permissions
        processing_switch.grant_read(worker_role)
        inference_queue.grant_consume_messages(worker_role)
        dlq.grant_consume_messages(worker_role)
        log_group.grant_write(worker_role)
        gateway_log_group.grant_write(worker_role)
        reconciliation_log_group.grant_write(worker_role)
        scheduler_log_group.grant_write(worker_role)
        sqs_key.grant_decrypt(worker_role)
        result_table.grant_read_write_data(worker_role)
        
        # Grant CloudWatch metrics permissions
        worker_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudwatch:PutMetricData",
                "cloudwatch:GetMetricStatistics",
                "cloudwatch:ListMetrics"
            ],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "cloudwatch:namespace": "AirGappedRAG"
                }
            }
        ))

        # Create the Instance Profile
        instance_profile = iam.CfnInstanceProfile(self, f"WorkerProfile-{stage}",
                                                  roles=[worker_role.role_name],
                                                  instance_profile_name=f"RAG-Worker-Profile-{stage}"
                                                  )

        # 7. THE TUNNEL (Site-to-Site VPN)
        vgw = ec2.CfnVPNGateway(self, f"VGW-{stage}", type="ipsec.1")

        ec2.CfnVPCGatewayAttachment(self, f"VGWAttach-{stage}",
                                    vpc_id=vpc.vpc_id,
                                    vpn_gateway_id=vgw.ref
                                    )

        cgw = ec2.CfnCustomerGateway(self, f"HomeCGW-{stage}",
                                     bgp_asn=65000,
                                     ip_address=home_ip,
                                     type="ipsec.1"
                                     )

        vpn = ec2.CfnVPNConnection(self, f"HomeVPN-{stage}",
                                   customer_gateway_id=cgw.ref,
                                   vpn_gateway_id=vgw.ref,
                                   type="ipsec.1",
                                   static_routes_only=True,
                                   vpn_tunnel_options_specifications=[
                                       ec2.CfnVPNConnection.VpnTunnelOptionsSpecificationProperty(
                                           pre_shared_key=f"YourSecureSecretKey_{stage}_2026",
                                           tunnel_inside_cidr="169.254.10.0/30"
                                       )
                                   ]
                                   )

        # 8. OUTPUTS
        CfnOutput(self, "QueueUrl", value=inference_queue.queue_url)
        CfnOutput(self, "ResultTableName", value=result_table.table_name)
        CfnOutput(self, "LogGroupName", value=log_group.log_group_name)
        CfnOutput(self, "InstanceProfileName", value=instance_profile.ref)
        CfnOutput(self, "VpnId", value=vpn.ref)