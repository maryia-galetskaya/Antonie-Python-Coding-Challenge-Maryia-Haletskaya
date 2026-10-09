output "api_base_url" {
  description = "Public HTTP URL of the API load balancer."
  value       = "http://${aws_lb.api.dns_name}"
}

output "nat_gateway_public_ip" {
  description = "Static egress IP to allow-list in MongoDB Atlas Network Access."
  value       = aws_eip.nat.public_ip
}

output "api_log_group" {
  description = "CloudWatch log group for API container logs."
  value       = aws_cloudwatch_log_group.api.name
}
