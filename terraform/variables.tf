variable "aws_region" {
  description = "AWS region in which to create the service."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Short name used to prefix AWS resource names."
  type        = string
  default     = "antonie-books"

  validation {
    condition     = can(regex("^[A-Za-z][A-Za-z0-9-]{0,27}$", var.project_name))
    error_message = "project_name must start with a letter, contain only letters, digits, and hyphens, and be at most 28 characters."
  }
}

variable "container_image" {
  description = "Immutable tag or digest of the API image in a registry reachable by ECS, for example an ECR URI."
  type        = string
}

variable "mongo_uri_secret_arn" {
  description = "ARN of a Secrets Manager secret whose SecretString is the MongoDB connection URI."
  type        = string
}

variable "mongo_database" {
  description = "MongoDB database name used by the API."
  type        = string
  default     = "antonie_books"
}

variable "desired_count" {
  description = "Number of API tasks to keep running."
  type        = number
  default     = 2

  validation {
    condition     = var.desired_count >= 0
    error_message = "desired_count cannot be negative."
  }
}

variable "task_cpu" {
  description = "Fargate task CPU units."
  type        = number
  default     = 256
}

variable "task_memory" {
  description = "Fargate task memory in MiB."
  type        = number
  default     = 512
}
