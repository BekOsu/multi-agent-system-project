output "alb_dns_name" {
  description = "ALB DNS name for accessing worker metrics"
  value       = aws_lb.main.dns_name
}

output "sqs_queue_url" {
  description = "SQS queue URL for submitting jobs"
  value       = aws_sqs_queue.jobs.url
}

output "sqs_dlq_url" {
  description = "SQS dead-letter queue URL"
  value       = aws_sqs_queue.jobs_dlq.url
}

output "ecr_repository_url" {
  description = "ECR repository URL for pushing container images"
  value       = aws_ecr_repository.app.repository_url
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "ECS service name"
  value       = aws_ecs_service.worker.name
}
