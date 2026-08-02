variable "stack_name" {
  type = string
}

variable "location" {
  type    = string
  default = "eastus"
}

variable "db_sku" {
  type    = string
  default = "B_Standard_B2ms"
}

variable "worker_min_replicas" {
  type    = number
  default = 1
}

variable "worker_max_replicas" {
  type    = number
  default = 10
}
