resource "aws_appautoscaling_target" "ecs_workers" {
  max_capacity       = var.max_workers
  min_capacity       = var.min_workers
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.worker.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

# Scale out: add workers when queue depth > 10
resource "aws_appautoscaling_policy" "scale_out" {
  name               = "${var.project_name}-scale-out"
  resource_id        = aws_appautoscaling_target.ecs_workers.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_workers.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_workers.service_namespace
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 120
    metric_aggregation_type = "Average"

    step_adjustment {
      scaling_adjustment          = 2
      metric_interval_lower_bound = 0
    }
  }
}

# Scale in: remove workers when queue depth < 2
resource "aws_appautoscaling_policy" "scale_in" {
  name               = "${var.project_name}-scale-in"
  resource_id        = aws_appautoscaling_target.ecs_workers.resource_id
  scalable_dimension = aws_appautoscaling_target.ecs_workers.scalable_dimension
  service_namespace  = aws_appautoscaling_target.ecs_workers.service_namespace
  policy_type        = "StepScaling"

  step_scaling_policy_configuration {
    adjustment_type         = "ChangeInCapacity"
    cooldown                = 300
    metric_aggregation_type = "Average"

    step_adjustment {
      scaling_adjustment          = -1
      metric_interval_upper_bound = 0
    }
  }
}

# CloudWatch alarm: queue depth high -> scale out
resource "aws_cloudwatch_metric_alarm" "queue_high" {
  alarm_name          = "${var.project_name}-queue-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 10
  alarm_description   = "Scale out when SQS queue depth > 10"

  dimensions = {
    QueueName = aws_sqs_queue.jobs.name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_out.arn]

  tags = local.common_tags
}

# CloudWatch alarm: queue depth low -> scale in
resource "aws_cloudwatch_metric_alarm" "queue_low" {
  alarm_name          = "${var.project_name}-queue-low"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 5
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Average"
  threshold           = 2
  alarm_description   = "Scale in when SQS queue depth < 2"

  dimensions = {
    QueueName = aws_sqs_queue.jobs.name
  }

  alarm_actions = [aws_appautoscaling_policy.scale_in.arn]

  tags = local.common_tags
}
