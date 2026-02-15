resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 30

  tags = local.common_tags
}

# Alarm when dead-letter queue has messages (jobs failing repeatedly)
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.project_name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Dead-letter queue has messages — jobs are failing"

  dimensions = {
    QueueName = aws_sqs_queue.jobs_dlq.name
  }

  tags = local.common_tags
}

# Alarm when main queue depth exceeds 50 (backlog building up)
resource "aws_cloudwatch_metric_alarm" "queue_backlog" {
  alarm_name          = "${var.project_name}-queue-backlog"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 50
  alarm_description   = "SQS queue backlog exceeds 50 messages"

  dimensions = {
    QueueName = aws_sqs_queue.jobs.name
  }

  tags = local.common_tags
}
