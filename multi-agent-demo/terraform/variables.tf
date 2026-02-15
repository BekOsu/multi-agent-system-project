variable "project_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "multi-agent"
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "container_image" {
  description = "ECR image URI for the worker container"
  type        = string
}

variable "desired_workers" {
  description = "Desired number of ECS worker tasks"
  type        = number
  default     = 2
}

variable "max_workers" {
  description = "Maximum number of ECS worker tasks for autoscaling"
  type        = number
  default     = 10
}

variable "min_workers" {
  description = "Minimum number of ECS worker tasks for autoscaling"
  type        = number
  default     = 1
}

variable "openai_api_key" {
  description = "OpenAI API key passed to worker containers"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "PostgreSQL connection string for job history"
  type        = string
  default     = ""
  sensitive   = true
}
