resource "aws_sqs_queue" "jobs_dlq" {
  name                      = "${var.project_name}-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = local.common_tags
}

resource "aws_sqs_queue" "jobs" {
  name                       = "${var.project_name}-jobs"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 1209600 # 14 days
  receive_wait_time_seconds  = 20      # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })

  tags = local.common_tags
}

resource "aws_sqs_queue_policy" "jobs" {
  queue_url = aws_sqs_queue.jobs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.ecs_task.arn }
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.jobs.arn
      }
    ]
  })
}
