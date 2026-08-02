variable "stack_name" {
  type        = string
  description = "Prefix for all created resources."
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "worker_task_count" {
  type    = number
  default = 2
}

variable "use_bedrock" {
  type    = bool
  default = false
}
