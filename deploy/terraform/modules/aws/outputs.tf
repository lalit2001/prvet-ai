output "api_url" {
  value       = "https://TBD-M5.execute-api.${var.region}.amazonaws.com"
  description = "Populated in M5 once API Gateway is provisioned."
}

output "web_url" {
  value       = "https://TBD-M5.cloudfront.net"
  description = "Populated in M5 once CloudFront distribution is provisioned."
}

output "db_endpoint" {
  value       = "TBD-M5"
  description = "Populated in M5."
}
