"""
CloudWatch Dashboard for Air-Gapped RAG System
Creates comprehensive monitoring dashboards for all environments
"""

from aws_cdk import (
    aws_cloudwatch as cloudwatch,
    aws_logs as logs,
    Duration
)
from constructs import Construct
from typing import List, Dict, Any
import json


class RAGMonitoringDashboard(Construct):
    """Creates CloudWatch dashboard for RAG system monitoring."""
    
    def __init__(self, scope: Construct, construct_id: str, stage: str, 
                 queue_name: str, dlq_name: str, log_group_name: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        
        self.stage = stage
        self.queue_name = queue_name
        self.dlq_name = dlq_name
        self.log_group_name = log_group_name
        
        # Create the dashboard
        self.dashboard = cloudwatch.Dashboard(
            self, f"RAGDashboard-{stage}",
            dashboard_name=f"AirGappedRAG-{stage}",
            period_override=cloudwatch.PeriodOverride.AUTO,
            start="-PT3H",  # Last 3 hours
            widgets=self._create_widgets()
        )
    
    def _create_widgets(self) -> List[List[cloudwatch.IWidget]]:
        """Create dashboard widgets."""
        return [
            # Row 1: System Overview
            [
                self._create_system_health_widget(),
                self._create_processing_status_widget(),
                self._create_error_rate_widget()
            ],
            # Row 2: Queue Metrics
            [
                self._create_queue_depth_widget(),
                self._create_message_flow_widget(),
                self._create_dlq_widget()
            ],
            # Row 3: Performance Metrics
            [
                self._create_inference_performance_widget(),
                self._create_worker_metrics_widget(),
                self._create_resource_utilization_widget()
            ],
            # Row 4: Logs and Alerts
            [
                self._create_log_insights_widget(),
                self._create_alerts_widget()
            ]
        ]
    
    def _create_system_health_widget(self) -> cloudwatch.SingleValueWidget:
        """System health overview widget."""
        return cloudwatch.SingleValueWidget(
            title="System Health",
            width=8,
            height=6,
            metrics=[
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="WorkerHealthy",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(5)
                ),
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="VLLMAccessible",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(5)
                )
            ],
            set_period_to_time_range=False,
            sparkline=True
        )
    
    def _create_processing_status_widget(self) -> cloudwatch.GaugeWidget:
        """Processing status gauge widget."""
        return cloudwatch.GaugeWidget(
            title="Processing Status",
            width=8,
            height=6,
            metrics=[
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="WorkerHealthy",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(1)
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(min=0, max=1),
            annotations=[
                cloudwatch.HorizontalAnnotation(value=0.5, label="Unhealthy", color=cloudwatch.Color.RED),
                cloudwatch.HorizontalAnnotation(value=1.0, label="Healthy", color=cloudwatch.Color.GREEN)
            ]
        )
    
    def _create_error_rate_widget(self) -> cloudwatch.SingleValueWidget:
        """Error rate widget."""
        return cloudwatch.SingleValueWidget(
            title="Error Rate (%)",
            width=8,
            height=6,
            metrics=[
                cloudwatch.MathExpression(
                    expression="(errors / (errors + successes)) * 100",
                    using_metrics={
                        "errors": cloudwatch.Metric(
                            namespace="AirGappedRAG",
                            metric_name="ProcessingErrors",
                            dimensions_map={"Environment": self.stage},
                            statistic="Sum",
                            period=Duration.minutes(5)
                        ),
                        "successes": cloudwatch.Metric(
                            namespace="AirGappedRAG",
                            metric_name="ProcessingSuccesses",
                            dimensions_map={"Environment": self.stage},
                            statistic="Sum",
                            period=Duration.minutes(5)
                        )
                    },
                    label="Error Rate"
                )
            ],
            sparkline=True
        )
    
    def _create_queue_depth_widget(self) -> cloudwatch.GraphWidget:
        """Queue depth over time widget."""
        return cloudwatch.GraphWidget(
            title="Queue Depth",
            width=12,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfVisibleMessages",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Average",
                    period=Duration.minutes(1),
                    label="Messages Available"
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfMessagesNotVisible",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Average",
                    period=Duration.minutes(1),
                    label="Messages In Flight"
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(min=0),
            period=Duration.minutes(5),
            statistic="Average"
        )
    
    def _create_message_flow_widget(self) -> cloudwatch.GraphWidget:
        """Message flow widget."""
        return cloudwatch.GraphWidget(
            title="Message Flow",
            width=12,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesSent",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Messages Sent"
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesReceived",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Messages Received"
                ),
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="NumberOfMessagesDeleted",
                    dimensions_map={"QueueName": self.queue_name},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Messages Processed"
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(min=0),
            period=Duration.minutes(5),
            statistic="Sum"
        )
    
    def _create_dlq_widget(self) -> cloudwatch.SingleValueWidget:
        """Dead letter queue widget."""
        return cloudwatch.SingleValueWidget(
            title="Dead Letter Queue",
            width=8,
            height=6,
            metrics=[
                cloudwatch.Metric(
                    namespace="AWS/SQS",
                    metric_name="ApproximateNumberOfVisibleMessages",
                    dimensions_map={"QueueName": self.dlq_name},
                    statistic="Maximum",
                    period=Duration.minutes(5),
                    label="Failed Messages"
                )
            ],
            sparkline=True
        )
    
    def _create_inference_performance_widget(self) -> cloudwatch.GraphWidget:
        """Inference performance widget."""
        return cloudwatch.GraphWidget(
            title="Inference Performance",
            width=12,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="VLLMResponseTime",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(1),
                    label="Avg Response Time"
                )
            ],
            right=[
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="InferenceCount",
                    dimensions_map={"Environment": self.stage},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Inferences/5min"
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(label="Response Time (ms)", min=0),
            right_y_axis=cloudwatch.YAxisProps(label="Count", min=0),
            period=Duration.minutes(5)
        )
    
    def _create_worker_metrics_widget(self) -> cloudwatch.GraphWidget:
        """Worker metrics widget."""
        return cloudwatch.GraphWidget(
            title="Worker Metrics",
            width=12,
            height=6,
            left=[
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="WorkerUptime",
                    dimensions_map={"Environment": self.stage},
                    statistic="Maximum",
                    period=Duration.minutes(5),
                    label="Uptime (seconds)"
                ),
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="MessagesProcessed",
                    dimensions_map={"Environment": self.stage},
                    statistic="Sum",
                    period=Duration.minutes(5),
                    label="Messages Processed"
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(min=0),
            period=Duration.minutes(5)
        )
    
    def _create_resource_utilization_widget(self) -> cloudwatch.GraphWidget:
        """Resource utilization widget."""
        return cloudwatch.GraphWidget(
            title="Resource Utilization",
            width=8,
            height=6,
            left=[
                # These would be custom metrics from the worker
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="MemoryUsage",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Memory Usage (%)"
                ),
                cloudwatch.Metric(
                    namespace="AirGappedRAG",
                    metric_name="CPUUsage",
                    dimensions_map={"Environment": self.stage},
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="CPU Usage (%)"
                )
            ],
            left_y_axis=cloudwatch.YAxisProps(min=0, max=100),
            period=Duration.minutes(5)
        )
    
    def _create_log_insights_widget(self) -> cloudwatch.LogQueryWidget:
        """Log insights widget."""
        return cloudwatch.LogQueryWidget(
            title="Recent Errors",
            width=12,
            height=6,
            log_group_names=[self.log_group_name],
            query_lines=[
                "fields @timestamp, @message",
                "filter @message like /ERROR/",
                "sort @timestamp desc",
                "limit 20"
            ]
        )
    
    def _create_alerts_widget(self) -> cloudwatch.SingleValueWidget:
        """Active alerts widget."""
        return cloudwatch.SingleValueWidget(
            title="Active Alerts",
            width=12,
            height=6,
            metrics=[
                cloudwatch.Metric(
                    namespace="AWS/CloudWatchAlarms",
                    metric_name="AlarmCount",
                    dimensions_map={"AlarmName": f"*{self.stage}*"},
                    statistic="Sum",
                    period=Duration.minutes(5)
                )
            ]
        )